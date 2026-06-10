"""Scraping orchestration phase extracted from ``job_runner.run_job`` (D2/L1 strangler refactor).

Encapsulates per-URL scraping with concurrency control, domain semaphores,
acquisition lineage tracking, and cancellation monitoring.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.llm_bridge import get_llm_call_count, reset_llm_call_count

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

ScrapeResult = tuple[int, list[dict], bool, dict]


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

    semaphore = asyncio.Semaphore(settings.JOB_MAX_PARALLEL_URLS)
    domain_semaphores: dict[str, asyncio.Semaphore] = {}
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
        if job.cancel_requested or await cancel_check():
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
            max_parallel = policy.get_or_create(url).max_parallel
            domain_semaphores[domain] = asyncio.Semaphore(max_parallel)
        domain_sem = domain_semaphores[domain]

        async with semaphore, domain_sem:
            await _safe_log(f"Scraping ({idx}/{len(job.urls)}): {url}")

            from app.semantic_world_state import get_world_state

            ws = get_world_state()
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

    scrape_tasks = [asyncio.create_task(_scrape_single_url(idx, url)) for idx, url in enumerate(job.urls, start=1)]

    while True:
        if all(task.done() for task in scrape_tasks):
            break

        if job.cancel_requested or await cancel_check():
            job.cancel_requested = True
            for task in scrape_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*scrape_tasks, return_exceptions=True)
            from app.utils.job import mark_job_canceled

            mark_job_canceled(job)
            return all_raw_results, urls_with_records, warnings, []

        await asyncio.sleep(0.25)

    scraped_raw = await asyncio.gather(*scrape_tasks, return_exceptions=True)
    exceptions = [r for r in scraped_raw if isinstance(r, BaseException)]
    if exceptions:
        for exc in exceptions:
            logger.warning("per-URL scrape raised %s", exc)
    scraped: list[ScrapeResult] = [r for r in scraped_raw if isinstance(r, tuple) and len(r) == 4]

    for _idx, results, success, _meta in sorted(scraped, key=lambda x: x[0]):
        if job.cancel_requested or await cancel_check():
            job.cancel_requested = True
            from app.utils.job import mark_job_canceled

            mark_job_canceled(job)
            return all_raw_results, urls_with_records, warnings, scraped
        if success:
            all_raw_results.extend(results)
            if len(results) > 0:
                urls_with_records += 1

    return all_raw_results, urls_with_records, warnings, scraped
