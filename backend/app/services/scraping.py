"""Scraping orchestration phase extracted from ``job_runner.run_job`` (D2/L1 strangler refactor).

Encapsulates per-URL scraping with concurrency control, domain semaphores,
acquisition lineage tracking, and cancellation monitoring.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import threading
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.llm_bridge import get_llm_call_count, reset_llm_call_count
from app.models import JobStatus

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

ScrapeResult = tuple[int, list[dict], bool, dict]

# Feat 9 — lazy asyncio.Lock for the per-job ``request_delay_ms`` throttle.
#
# Why lazy: ``asyncio.Lock()`` binds to whichever event loop is *currently*
# running at instantiation time. If the lifecycle outlives a single loop
# (uvloop/pytest-asyncio per-test loops, lifespan restart, child process
# forking into a fresh loop), the captured lock raises
# ``RuntimeError: ... is bound to a different event loop`` on next acquire.
#
# Instead we hold ``(loop_identity -> lock)`` and create a fresh lock
# whenever the running loop changes. Re-binding per loop keeps the
# throttle correct across worker restarts.
_JOB_DELAY_LOCKS: dict[int, asyncio.Lock] = {}
_JOB_DELAY_LOCKS_GUARD: threading.Lock = threading.Lock()


def _get_job_delay_lock() -> asyncio.Lock:
    """Return the asyncio.Lock bound to the *currently running* event loop.

    Creates a new lock when the loop identity (id() of loop) changes,
    so each new event loop gets its own bound lock instead of raising
    RuntimeError on the next acquire.
    """
    running_loop = asyncio.get_running_loop()
    loop_id = id(running_loop)
    with _JOB_DELAY_LOCKS_GUARD:
        lock = _JOB_DELAY_LOCKS.get(loop_id)
        if lock is None:
            lock = asyncio.Lock()
            _JOB_DELAY_LOCKS[loop_id] = lock
        return lock


def _record_page_fetch(job: Any, url: str) -> bool:
    """Record a page-fetch usage event for billing/quota enforcement.

    Called once per attempted URL scrape (not for domain-cooldown skips).
    Returns ``False`` only when the user's page-fetch quota is exhausted.
    Other ledger failures are logged but do not block extraction.
    """
    user_id = getattr(job, "created_by", None) or getattr(job, "user_id", None) or ""
    if not user_id:
        return True
    try:
        from app.utils.usage_ledger import UsageType, get_usage_ledger

        get_usage_ledger().record_usage(
            user_id,
            UsageType.PAGE_FETCHED,
            quantity=1,
            metadata={"url": url, "job_id": getattr(job, "id", "")},
            org_id=getattr(job, "org_id", "") or "",
            project_id=getattr(job, "project_id", "") or "",
        )
        return True
    except ValueError:
        logger.warning("Page-fetch quota exceeded for job %s URL %s", getattr(job, "id", ""), url)
        return False
    except (RuntimeError, OSError, TypeError) as exc:
        logger.debug("Page-fetch metering skipped: %s", exc)
        return True


def _record_page_fetch_duration_metric(started_at: float) -> None:
    try:
        from app.metrics_collector import record_page_fetch_duration

        record_page_fetch_duration(time.monotonic() - started_at)
    except (ImportError, RuntimeError, ValueError, TypeError):
        logger.debug("Page-fetch duration metric skipped")


async def run_scraping_phase(
    job: Any,
    *,
    max_job_runtime_seconds: int,
    per_url_scrape_timeout_seconds: int,
    persist_fn: Callable,
    cancel_check: Callable[[], Any],
    persist_single_fn: Callable | None = None,
) -> tuple[list[dict], int, list[str], list[ScrapeResult]]:
    """Execute the scraping phase: scrape all URLs concurrently.

    Returns:
        Tuple of (all_raw_results, urls_with_records, warnings, scraped_metadata).

    """
    all_raw_results: list[dict] = []
    urls_with_records = 0
    warnings: list[str] = []
    started_at = time.monotonic()

    # Feat 9 — per-job concurrency cap.  Use the job's user-configurable
    # ``max_concurrent_urls`` (default 4) when present, else fall back to
    # the platform-wide ``JOB_MAX_PARALLEL_URLS`` setting.
    try:
        job_max_concurrent = int(getattr(job, "max_concurrent_urls", settings.JOB_MAX_PARALLEL_URLS))
        if job_max_concurrent < 1:
            job_max_concurrent = settings.JOB_MAX_PARALLEL_URLS
    except (TypeError, ValueError):
        job_max_concurrent = settings.JOB_MAX_PARALLEL_URLS
    semaphore = asyncio.Semaphore(min(job_max_concurrent, settings.JOB_MAX_PARALLEL_URLS))
    # N+8: ``domain_semaphores`` is scoped to this ``run_scraping_phase()``
    # call (one job), not module-level, so the memory footprint per-job
    # is bounded by the # of unique domains that *this* job scrapes.
    # Even for a hostile fan-out of O(10K) distinct domains, each
    # ``asyncio.Semaphore`` is ~256 bytes — well under 3 MB total.  A
    # soft cap below prevents pathological fan-out from exceeding sane
    # memory; if hit, the additional domains fall through to the global
    # ``semaphore`` (still respects the per-job parallelism limit).
    domain_semaphores: dict[str, asyncio.Semaphore] = {}
    _DOMAIN_SEMAPHORE_SOFT_CAP = 4096
    job_lock = asyncio.Lock()
    completed_count = 0

    persist_job_state_fn = persist_single_fn or persist_fn

    async def _safe_log(message: str, level: str = "info") -> None:
        from app.models import LogEntry

        async with job_lock:
            job.logs.append(LogEntry(message=message, level=level))
        await run_in_threadpool(persist_job_state_fn)

    async def _mark_completed() -> None:
        nonlocal completed_count
        async with job_lock:
            completed_count += 1
            job.progress_current = completed_count
        await run_in_threadpool(persist_job_state_fn)

    async def _safe_warning(msg: str) -> None:
        async with job_lock:
            warnings.append(msg)

    async def _scrape_single_url(idx: int, url: str) -> ScrapeResult:
        # Feat 9 — per-job delay between consecutive URL fetches.  This is
        # a fairness throttle inside a single job: it ensures the scraper
        # does not hammer the target domain even when the semaphore allows
        # high concurrency.  Sleeps BEFORE the actual fetch.  Acquiring an
        # extra per-job delay lock prevents burst fetches from sibling
        # concurrent tasks within the same job.
        job_delay_ms = int(getattr(job, "request_delay_ms", 0) or 0)
        if job_delay_ms > 0:
            try:
                async with _get_job_delay_lock():
                    await asyncio.sleep(job_delay_ms / 1000.0)
            except RuntimeError:
                # Event loop changed mid-flight; skip the throttle.
                logger.debug("Per-job rate-limit delay skipped (loop mismatch)")

        # Corrected cancellation check: Check both flag and DB signal,
        # then update flag if signaled. Read and write ``cancel_requested``
        # under ``_jobs_store_lock`` so a concurrent cancel request from
        # the API handler doesn't race the orchestrator loop, which
        # reads/writes the same field at lines 350-355 / 400-405.
        from app.globals import _jobs_store_lock

        with _jobs_store_lock:
            cancel_already_requested = job.cancel_requested
        if cancel_already_requested or await cancel_check():
            with _jobs_store_lock:
                job.cancel_requested = True
            return idx, [], False, {}

        elapsed = time.monotonic() - started_at
        if elapsed > max_job_runtime_seconds:
            await _safe_warning(f"Job runtime limit reached at {int(elapsed)}s; partial results returned.")
            await _mark_completed()
            return idx, [], False, {}

        from app.domain_runtime_policy import get_domain_runtime_policy

        policy = get_domain_runtime_policy()

        if not policy.can_fetch(url):
            rec_action = policy.recommended_action(url)
            await _safe_log(
                f"Skipping ({idx}/{len(job.urls)}): {url} — domain in cooldown ({rec_action})",
                level="warning",
            )
            await _safe_warning(f"URL skipped due to domain cooldown ({idx}/{len(job.urls)}): {url}")
            cooldown_remaining = policy.remaining_cooldown(url)
            domain_key = urlparse(url).netloc.lower()
            from app.acquisition_state import AcquisitionLineage, AcquisitionState

            lineage = AcquisitionLineage(
                original_url=url,
                final_url=url,
                state=AcquisitionState.DOMAIN_COOLDOWN,
                fetch_method="skipped",
                recovery_method="domain_runtime_policy",
                anti_bot_score=0.0,
                data_evidence_score=0.0,
                user_message=f"Domain '{domain_key}' in cooldown for {cooldown_remaining:.0f}s — {rec_action}",
                recommended_next_action=rec_action,
            )
            url_meta = {
                "ai_structured_count": 0,
                "attempted": False,
                "acquisition_lineage": lineage.to_dict(),
            }
            await _mark_completed()
            return idx, [], False, url_meta

        domain = urlparse(url).netloc.lower()
        if domain not in domain_semaphores:
            # Soft cap: emerging-domain-hostile job fan-out doesn't
            # blow up ``domain_semaphores``.  When the cap is hit, we
            # still respect the global ``semaphore`` (per-job
            # parallelism) — only the *per-domain* throttling caps
            # collapse for the remainder of the job.  Acceptable
            # trade-off: a hostile fan-out sees less per-domain
            # fairness, not unbounded memory growth.
            if len(domain_semaphores) >= _DOMAIN_SEMAPHORE_SOFT_CAP:
                domain_sem = semaphore
            else:
                max_parallel = policy.get_or_create(url).max_parallel
                domain_semaphores[domain] = asyncio.Semaphore(max_parallel)
                domain_sem = domain_semaphores[domain]
        else:
            domain_sem = domain_semaphores[domain]

        async with semaphore, domain_sem:
            await _safe_log(f"Scraping ({idx}/{len(job.urls)}): {url}")
            if not _record_page_fetch(job, url):
                await _safe_log(f"Skipping ({idx}/{len(job.urls)}): {url} — page-fetch quota exceeded", level="warning")
                await _safe_warning(f"URL skipped due to page-fetch quota ({idx}/{len(job.urls)}): {url}")
                await _mark_completed()
                return idx, [], False, {"attempted": False, "quota_exceeded": True}

            from app.semantic_world_state import get_world_state

            ws = get_world_state()
            fetch_started_at = time.monotonic()
            try:
                reset_llm_call_count()

                from app.services.job_runner import scrape_url_with_recovery

                results, recovery_stats = await asyncio.wait_for(
                    scrape_url_with_recovery(
                        url,
                        job.schema_fields,
                        min_record_score=job.min_record_score,
                        user_intent=job.intent,
                        world_state=ws,
                        max_recovery_attempts=settings.MAX_RECOVERY_ATTEMPTS,
                        selectors_map=job.selectors_map,
                        search_params=job.search_params,
                        usage_context={
                            "user_id": getattr(job, "created_by", "") or getattr(job, "user_id", "") or "",
                            "org_id": getattr(job, "org_id", "") or "",
                            "project_id": getattr(job, "project_id", "") or "",
                            "job_id": getattr(job, "id", "") or "",
                        },
                        headers=getattr(job, "headers", None),
                        cookies=getattr(job, "cookies", None),
                        hydration_wait_ms=getattr(job, "hydration_wait_ms", None),
                        scroll_attempts=getattr(job, "scroll_attempts", None),
                        fetch_strategy=getattr(job, "fetch_strategy", None) or None,
                    ),
                    timeout=per_url_scrape_timeout_seconds * settings.RECOVERY_TIMEOUT_MULTIPLIER,
                )

                if recovery_stats and "network_diagnostics" in recovery_stats:
                    for diag in recovery_stats["network_diagnostics"]:
                        await _safe_log(f"[NetworkDiagnostics] {diag}", level="info")
                if recovery_stats and "warnings" in recovery_stats:
                    for warn in recovery_stats["warnings"]:
                        await _safe_warning(warn)

                if results:
                    policy.record_success(url)
                else:
                    policy.record_failure(url, failure_type="zero_records_extracted")

                async with job_lock:
                    job.total_llm_calls += get_llm_call_count()

                with ws.transaction(f"integrate_scrape:{url}"):
                    pass

                if recovery_stats.get("recovery_attempts", 0) > 0:
                    actions = ", ".join(recovery_stats.get("recovery_actions_taken", []))
                    await _safe_log(f"Recovery applied to {url}: {actions}", level="info")

                ai_structured_count = 0
                for record in results:
                    if record.pop("_ai_source_structured", False):
                        ai_structured_count += 1
                    record["source_url"] = url
                    from app.discovery import infer_source_metadata

                    inferred = infer_source_metadata(url=url)
                    record["source_type"] = str(inferred.get("source_type") or "unknown")
                    from app.utils.quality import safe_score

                    record["source_trust_score"] = round(safe_score(inferred.get("source_trust_score") or 0.4), 3)

                lineage = recovery_stats.get("acquisition_lineage", {}).copy()
                for record in results:
                    record["_acquisition_lineage"] = lineage

                url_meta = {
                    "ai_structured_count": ai_structured_count,
                    "attempted": True,
                    "acquisition_lineage": lineage,
                }

                await _safe_log(f"Extracted {len(results)} raw records from {url}")
                await run_in_threadpool(persist_job_state_fn)
                async with job_lock:
                    pass
                await _mark_completed()
                return idx, results, True, url_meta
            except asyncio.CancelledError:
                policy.record_failure(url, failure_type="canceled")
                await _safe_log(f"Canceled scrape for {url}", level="warning")
                raise
            except TimeoutError:
                policy.record_failure(url, failure_type="timeout")
                await _safe_log(f"Timeout on {url}", level="warning")
                logger.warning("Timeout for %s", url)
                await _safe_warning(f"URL timeout skipped ({idx}/{len(job.urls)}): {url}")
                await _mark_completed()
                return idx, [], False, {}
            except Exception as e:
                policy.record_failure(url, failure_type=type(e).__name__)
                logger.exception("URL scrape failed: %s", url)
                await _safe_log(f"Failed to scrape {url}: {type(e).__name__}", level="warning")
                await _safe_warning(f"URL scrape failed ({idx}/{len(job.urls)}): {url} ({type(e).__name__})")
                await _mark_completed()
                return idx, [], False, {}
            finally:
                _record_page_fetch_duration_metric(fetch_started_at)

    scrape_tasks = [asyncio.create_task(_scrape_single_url(idx, url)) for idx, url in enumerate(job.urls, start=1)]

    # Safety net: if every _scrape_single_url task hangs such that
    # ``done()`` is never true AND neither ``cancel_requested`` nor
    # ``cancel_check`` ever fires (e.g. a missing cancel signal hook),
    # the bare ``while True`` loop would never exit.  Bound the polling
    # phase to ``_CANCEL_POLL_TIMEOUT`` so the worker can't wedge the
    # job indefinitely.  Individual scrape tasks have their own
    # timeouts inside ``_scrape_single_url`` so this is *only* a
    # belt-and-braces ceiling on the cancellation loop itself.
    poll_started_at = time.monotonic()
    _CANCEL_POLL_DEADLINE_S = float(os.environ.get("DATAFORGE_CANCEL_POLL_DEADLINE", "300"))

    while True:
        if all(task.done() for task in scrape_tasks):
            break

        if job.cancel_requested or await cancel_check():
            # Guard mutation of job state using the global store lock
            from app.globals import _jobs_store_lock

            with _jobs_store_lock:
                job.cancel_requested = True
                from app.services.job_state_machine import transition_to

                # Use transition_to to strictly follow the state machine.
                # A ValueError just means the job transitioned elsewhere
                # (e.g. FAILED) before the cancel could apply — not fatal.
                with contextlib.suppress(ValueError):
                    transition_to(job, JobStatus.CANCELED, error="Canceled during scraping phase")

            for task in scrape_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*scrape_tasks, return_exceptions=True)

            # Now that status is updated via transition_to, cleanup is final
            return all_raw_results, urls_with_records, warnings, []

        if (time.monotonic() - poll_started_at) > _CANCEL_POLL_DEADLINE_S:
            # Cancel everything: at least one task is wedged past the
            # per-URL timeout, and no cancel signal is propagating.  We
            # return whatever completed cleanly rather than block the
            # worker indefinitely.
            logger.error(
                "Cancel-poll deadline exceeded (%ds) on job %s with %d/%d tasks complete — force-cancelling",
                int(_CANCEL_POLL_DEADLINE_S),
                getattr(job, "id", "?"),
                sum(1 for t in scrape_tasks if t.done()),
                len(scrape_tasks),
            )
            for task in scrape_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*scrape_tasks, return_exceptions=True)
            break

        await asyncio.sleep(0.25)

    scraped_raw = await asyncio.gather(*scrape_tasks, return_exceptions=True)
    exceptions = [r for r in scraped_raw if isinstance(r, BaseException)]
    if exceptions:
        for exc in exceptions:
            logger.warning("per-URL scrape raised %s", exc)
    scraped: list[ScrapeResult] = [r for r in scraped_raw if isinstance(r, tuple) and len(r) == 4]

    for _idx, results, success, _meta in sorted(scraped, key=lambda x: x[0]):
        if job.cancel_requested or await cancel_check():
            # Guard mutation of job state using the global store lock
            from app.globals import _jobs_store_lock

            with _jobs_store_lock:
                job.cancel_requested = True
                from app.services.job_state_machine import transition_to

                with contextlib.suppress(ValueError):
                    transition_to(job, JobStatus.CANCELED, error="Canceled during result aggregation")
            return all_raw_results, urls_with_records, warnings, scraped
        if success:
            all_raw_results.extend(results)
            if len(results) > 0:
                urls_with_records += 1

    return all_raw_results, urls_with_records, warnings, scraped
