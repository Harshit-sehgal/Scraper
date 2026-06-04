import asyncio
import datetime
import logging
import time
from urllib.parse import urlparse

from app.config import settings
from app.discovery import discover_urls, infer_source_metadata
from app.filters import apply_location_radius, process_results
from app.llm_bridge import get_llm_call_count, reset_llm_call_count
from app.models import FieldType, JobStatus, ScrapeMode
from app.scraper import (
    ai_clean_and_align_records,
)
from app.storage_interface import get_job_repository
from app.utils.job import deduplicate_results, mark_job_canceled, normalize_job_results
from app.utils.quality import build_quality_report, compute_source_breakdown, safe_score


# --- Dynamic delegation to research-shell modules to keep imports lazy but mockable ---
async def scrape_url_with_recovery(*args, **kwargs):
    from app.scraper_recovery_integration import scrape_url_with_recovery as impl

    return await impl(*args, **kwargs)


def load_semantic_state(*args, **kwargs):
    from app.semantic_persistence import load_semantic_state as impl

    return impl(*args, **kwargs)


def save_semantic_state(*args, **kwargs):
    from app.semantic_persistence import save_semantic_state as impl

    return impl(*args, **kwargs)


def run_pipeline(*args, **kwargs):
    from app.semantic_pipeline import run_pipeline as impl

    return impl(*args, **kwargs)


def _add_job_log(job, message: str, level: str = "info", persist_fn=None, persist_single_fn=None):
    from app.models import LogEntry

    job.logs.append(LogEntry(message=message, level=level))
    if persist_single_fn:
        persist_single_fn()
    elif persist_fn:
        persist_fn()


async def run_job(
    job_id: str,
    jobs_store: dict,
    persist_state_fn,
    max_discovery_urls: int,
    max_job_runtime_seconds: int,
    per_url_scrape_timeout_seconds: int,
    ai_structuring_timeout_seconds: int,
    insight_timeout_seconds: int,
    persist_state_single_fn=None,
    persist_state_single_critical_fn=None,
):
    job = jobs_store.get(job_id)
    if not job:
        return

    # ── Cross-process cancellation check ───────────────────────────────
    # In worker mode (separate process), the API may have cancelled this job
    # via the database. Poll the repository for the latest flag.
    def _cancel_requested_from_db() -> bool:
        """Check the persistent store for a cross-process cancellation signal."""
        try:
            return get_job_repository().is_cancel_requested(job_id)
        except Exception:
            return False

    # Optimize persistence: use single-row updates for job-local saves
    # when available, while preserving persist_state_fn for full-store saves.
    persist_job_state_fn = persist_state_single_fn or persist_state_fn

    _add_job_log(
        job,
        f"Initializing job: {job.name}",
        persist_fn=persist_job_state_fn,
    )

    all_raw_results: list[dict] = []
    urls_with_records = 0
    warnings: list[str] = []
    ai_source_prediction = {
        "sources_attempted": 0,
        "sources_with_ai_structuring": 0,
        "records_processed": 0,
        "records_ai_structured": 0,
    }
    ai_structuring_report: dict = {
        "applied": False,
        "input_records": 0,
        "output_records": 0,
        "total_chunks": 0,
        "ai_chunks": 0,
        "fallback_chunks": 0,
        "capped_records": 0,
        "quality_filtered_after_ai": 0,
    }
    started_at = time.monotonic()
    if not job.started_at:
        job.started_at = datetime.datetime.now().isoformat()

    if job.cancel_requested or _cancel_requested_from_db():
        job.cancel_requested = True
        mark_job_canceled(job, "Canceled before execution.")
        if persist_state_single_critical_fn:
            persist_state_single_critical_fn()
        else:
            persist_state_fn()
        return

    try:
        # Using module-level lazy wrappers to satisfy quarantine and mockability

        load_semantic_state()

        # Auto-discovery mode
        if job.mode == ScrapeMode.AUTO:
            reset_llm_call_count()
            job.status = JobStatus.DISCOVERING
            job.progress_total = int(job.max_pages or 10) + 2  # Discovery + URLs + Final
            job.progress_current = 1
            _add_job_log(job, f"Starting auto-discovery for topic: {job.topic}", persist_fn=persist_job_state_fn)
            logging.info("Job %s: Auto-discovering URLs for: %s", job_id, job.topic)

            # In auto mode, reuse max_pages as discovery count and cap to
            # runtime-safe limits.
            discovery_limit = int(job.max_pages or 10)
            discovery_limit = max(1, min(discovery_limit, max_discovery_urls))

            discovered = await discover_urls(
                query=job.topic,
                domain=job.preferred_domain,
                num_results=discovery_limit,
                location=job.location,
                data_fields=[f.name for f in job.schema_fields],
                origin_location=job.origin_location,
                max_distance_km=job.max_distance_km,
                source_policy=job.source_policy,
                max_per_domain=job.max_per_domain,
            )
            job.total_llm_calls += get_llm_call_count()
            from app.url_safety import validate_public_http_url

            safe_discovered = []
            safe_urls = []
            for d in discovered:
                url = d.get("url")
                if url:
                    try:
                        validate_public_http_url(url)
                        safe_discovered.append(d)
                        safe_urls.append(url)
                    except ValueError:
                        pass
            job.discovered_urls = safe_discovered
            job.urls = safe_urls

            if not job.urls:
                if job.cancel_requested or _cancel_requested_from_db():
                    job.cancel_requested = True
                    mark_job_canceled(job)
                    _add_job_log(job, "Job canceled during discovery", level="warning", persist_fn=persist_job_state_fn)
                    if persist_state_single_critical_fn:
                        persist_state_single_critical_fn()
                    else:
                        persist_state_fn()
                else:
                    job.status = JobStatus.FAILED
                    job.error = "Could not discover any URLs for this topic"
                    job.completed_at = datetime.datetime.now().isoformat()
                    _add_job_log(job, "Discovery failed: No URLs found", level="error", persist_fn=persist_job_state_fn)
                    if persist_state_single_critical_fn:
                        persist_state_single_critical_fn()
                    else:
                        persist_state_fn()
                return

            _add_job_log(job, f"Discovered {len(job.urls)} potential source URLs", persist_fn=persist_job_state_fn)
            job.progress_total = len(job.urls) + 2
            job.progress_current = 1
            logging.info("Job %s: Discovered %d URLs", job_id, len(job.urls))

            if job.cancel_requested or _cancel_requested_from_db():
                job.cancel_requested = True
                mark_job_canceled(job)
                _add_job_log(job, "Job canceled after discovery", level="warning", persist_fn=persist_job_state_fn)
                if persist_state_single_critical_fn:
                    persist_state_single_critical_fn()
                else:
                    persist_state_fn()
                return

        job.status = JobStatus.RUNNING
        if job.mode == ScrapeMode.MANUAL:
            job.progress_total = len(job.urls) + 1
            job.progress_current = 0
        _add_job_log(job, f"Scraping started ({len(job.urls)} URLs queue)", persist_fn=persist_job_state_fn)

        semaphore = asyncio.Semaphore(settings.JOB_MAX_PARALLEL_URLS)
        # Per-domain semaphores for domain-level concurrency control
        domain_semaphores: dict[str, asyncio.Semaphore] = {}
        job_lock = asyncio.Lock()

        async def _safe_log(message: str, level: str = "info"):
            async with job_lock:
                _add_job_log(
                    job,
                    message,
                    level=level,
                    persist_fn=persist_job_state_fn,
                    persist_single_fn=persist_state_single_fn,
                )

        completed_count = 0

        async def _mark_completed():
            nonlocal completed_count
            async with job_lock:
                completed_count += 1
                job.progress_current = completed_count
                persist_job_state_fn()

        async def _safe_warning(msg: str):
            async with job_lock:
                warnings.append(msg)

        async def _scrape_single_url(idx: int, url: str) -> tuple[int, list[dict], bool, dict]:
            if job.cancel_requested or _cancel_requested_from_db():
                job.cancel_requested = True
                return idx, [], False, {}
            elapsed = time.monotonic() - started_at
            if elapsed > max_job_runtime_seconds:
                await _safe_warning(f"Job runtime limit reached at {int(elapsed)}s; partial results returned.")
                await _mark_completed()
                return idx, [], False, {}

            # ── DomainRuntimePolicy check ─────────────────────────────────
            from app.acquisition_state import AcquisitionLineage, AcquisitionState
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

            # ── Domain-level concurrency ──────────────────────────────────
            domain = urlparse(url).netloc.lower()
            if domain not in domain_semaphores:
                max_parallel = policy.get_or_create(url).max_parallel
                domain_semaphores[domain] = asyncio.Semaphore(max_parallel)
            domain_sem = domain_semaphores[domain]

            # Global capacity is reserved first, then domain-level capacity,
            # to avoid holding a scarce domain slot while waiting for global
            # capacity.
            async with semaphore:
                async with domain_sem:
                    await _safe_log(f"Scraping ({idx}/{len(job.urls)}): {url}")

                    from app.semantic_world_state import get_world_state

                    ws = get_world_state()
                    try:
                        reset_llm_call_count()
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

                        # Log network diagnostics and warnings to job Activity
                        # Logs
                        if "network_diagnostics" in recovery_stats:
                            for diag in recovery_stats["network_diagnostics"]:
                                await _safe_log(f"[NetworkDiagnostics] {diag}", level="info")
                        if "warnings" in recovery_stats:
                            for warn in recovery_stats["warnings"]:
                                await _safe_warning(warn)

                        # Record success if results were extracted
                        if results:
                            policy.record_success(url)
                        else:
                            policy.record_failure(url, failure_type="zero_records_extracted")

                        # Integrate results into world state in a short transaction
                        # (do NOT hold the transaction across the network scrape)
                        async with job_lock:
                            job.total_llm_calls += get_llm_call_count()

                        with ws.transaction(f"integrate_scrape:{url}"):
                            pass  # Future: integrate semantic / motif / world-state updates here

                        if recovery_stats.get("recovery_attempts", 0) > 0:
                            actions = ", ".join(recovery_stats.get("recovery_actions_taken", []))
                            await _safe_log(f"Recovery applied to {url}: {actions}", level="info")

                        # Count AI-structured records
                        ai_structured_count = 0
                        for record in results:
                            if record.pop("_ai_source_structured", False):
                                ai_structured_count += 1
                            record["source_url"] = url
                            inferred = infer_source_metadata(url=url)
                            record["source_type"] = str(inferred.get("source_type") or "unknown")
                            record["source_trust_score"] = round(safe_score(inferred.get("source_trust_score") or 0.4), 3)

                        # Attach acquisition lineage to each record so it's
                        # exposed in job results via the API
                        lineage = recovery_stats.get("acquisition_lineage", {}).copy()
                        for record in results:
                            record["_acquisition_lineage"] = lineage

                        url_meta = {
                            "ai_structured_count": ai_structured_count,
                            "attempted": True,
                            "acquisition_lineage": lineage,
                        }

                        await _safe_log(f"Extracted {len(results)} raw records from {url}")
                        async with job_lock:
                            persist_job_state_fn()
                        await _mark_completed()
                        return idx, results, True, url_meta
                    except asyncio.CancelledError:
                        policy.record_failure(url, failure_type="canceled")
                        await _safe_log(f"Canceled scrape for {url}", level="warning")
                        raise
                    except asyncio.TimeoutError:
                        policy.record_failure(url, failure_type="timeout")
                        await _safe_log(f"Timeout on {url}", level="warning")
                        logging.warning("Job %s: Timeout for %s", job_id, url)
                        await _safe_warning(f"URL timeout skipped ({idx}/{len(job.urls)}): {url}")
                        await _mark_completed()
                        return idx, [], False, {}
                    except Exception as e:
                        policy.record_failure(url, failure_type=type(e).__name__)
                        logging.exception("Job %s: URL scrape failed: %s", job_id, url)
                        await _safe_log(f"Failed to scrape {url}: {type(e).__name__}", level="warning")
                        await _safe_warning(f"URL scrape failed ({idx}/{len(job.urls)}): {url} ({type(e).__name__})")
                        await _mark_completed()
                        return idx, [], False, {}

        scrape_tasks = [asyncio.create_task(_scrape_single_url(idx, url)) for idx, url in enumerate(job.urls, start=1)]

        # Active cancellation watcher — polls cancel_requested while tasks run
        # so in-flight scrapes are interrupted promptly instead of waiting
        # for all tasks to finish before checking the cancel flag.
        # Also polls the DB for cross-process cancellation signals.
        # NOTE: check all(done) BEFORE cancel_requested to avoid a tight race
        # where all tasks finish and cancel is flagged in the same polling
        # cycle.
        while True:
            if all(task.done() for task in scrape_tasks):
                break

            if job.cancel_requested or _cancel_requested_from_db():
                job.cancel_requested = True
                for task in scrape_tasks:
                    if not task.done():
                        task.cancel()
                scraped_raw = await asyncio.gather(*scrape_tasks, return_exceptions=True)
                mark_job_canceled(job)
                if persist_state_single_critical_fn:
                    persist_state_single_critical_fn()
                else:
                    persist_state_fn()
                return

            await asyncio.sleep(0.25)

        scraped_raw = await asyncio.gather(*scrape_tasks, return_exceptions=True)
        scraped: list[tuple[int, list[dict], bool, dict]] = [r for r in scraped_raw if isinstance(r, tuple) and len(r) == 4]

        for idx, results, success, meta in sorted(scraped, key=lambda x: x[0]):
            if job.cancel_requested or _cancel_requested_from_db():
                job.cancel_requested = True
                mark_job_canceled(job)
                if persist_state_single_critical_fn:
                    persist_state_single_critical_fn()
                else:
                    persist_state_fn()
                return
            if success:
                all_raw_results.extend(results)
                if len(results) > 0:
                    urls_with_records += 1
                    ai_source_prediction["sources_attempted"] += 1
                    ai_source_prediction["records_processed"] += len(results)
                    ai_source_prediction["records_ai_structured"] += meta.get("ai_structured_count", 0)
                    if meta.get("ai_structured_count", 0) > 0:
                        ai_source_prediction["sources_with_ai_structuring"] += 1

        run_global_ai_structuring = (
            bool(all_raw_results) and bool(job.schema_fields) and ai_source_prediction.get("sources_with_ai_structuring", 0) == 0
        )

        if run_global_ai_structuring and all_raw_results:
            ext_methods = set(a.get("_extraction_method", "") for a in all_raw_results if isinstance(a, dict))
            if ext_methods and "" not in ext_methods and "regex" not in ext_methods:
                _add_job_log(
                    job,
                    "Skipping AI structuring — records extracted via structured method (not regex)",
                    persist_fn=persist_job_state_fn,
                )
                run_global_ai_structuring = False

        if job.cancel_requested or _cancel_requested_from_db():
            job.cancel_requested = True
            mark_job_canceled(job)
            if persist_state_single_critical_fn:
                persist_state_single_critical_fn()
            return

        if run_global_ai_structuring:
            _add_job_log(
                job,
                f"Running global AI structuring on {len(all_raw_results)} records...",
                persist_fn=persist_job_state_fn,
            )
            logging.info("Job %s: AI structuring %d scraped rows...", job_id, len(all_raw_results))
            try:
                reset_llm_call_count()
                all_raw_results, ai_structuring_report = await asyncio.wait_for(
                    ai_clean_and_align_records(
                        all_raw_results,
                        job.schema_fields,
                        min_record_score=job.min_record_score,
                    ),
                    timeout=ai_structuring_timeout_seconds,
                )
                job.total_llm_calls += get_llm_call_count()
                # Integration Phase: ensure AI-cleaned records are integrated
                # into the world state
                from app.semantic_world_state import get_world_state

                with get_world_state().transaction("global_ai_structuring"):
                    all_raw_results = run_pipeline(all_raw_results, [f.name for f in job.schema_fields])

                if ai_structuring_report.get("capped_records", 0) > 0:
                    warnings.append(
                        "AI structuring processed a capped subset of rows; remaining rows used deterministic cleaning.",
                    )
                if ai_structuring_report.get("model_fallback_mode"):
                    warnings.append("AI structuring switched to deterministic fallback after repeated model timeouts / errors.")
                _add_job_log(job, "AI structuring complete")
            except asyncio.TimeoutError:
                warnings.append(
                    f"AI structuring timed out after {ai_structuring_timeout_seconds}s; continuing with deterministic processing.",
                )
                _add_job_log(job, "AI structuring timed out, using fallback", level="warning")
                logging.warning("Job %s: AI structuring timed out", job_id)
            except Exception as struct_err:
                logging.exception("Job %s: AI structuring failed: %s", job_id, struct_err)
                warnings.append("AI structuring failed; continuing with deterministic processing.")
                _add_job_log(job, "AI structuring failed, using fallback", level="error")
        elif all_raw_results and job.schema_fields:
            ai_structuring_report = {
                "applied": False,
                "reason": "skipped_global_ai_source_level_applied",
                "input_records": len(all_raw_results),
                "output_records": len(all_raw_results),
                "total_chunks": 0,
                "ai_chunks": 0,
                "fallback_chunks": 0,
                "model_fallback_mode": False,
                "capped_records": 0,
                "quality_filtered_after_ai": 0,
            }

        # Post-process
        _add_job_log(job, "Applying filters and deduplication...", persist_fn=persist_job_state_fn)
        filtered_results, total, filtered_count, type_integrity_report = await process_results(
            all_raw_results,
            job.schema_fields,
            job.filters,
        )
        post_filter_count = len(filtered_results)

        # Optional radius filtering against origin location
        location_field = next((f.name for f in job.schema_fields if f.field_type.value == "location"), "")
        radius_report = {
            "applied": False,
            "reason": "not_configured",
            "origin": job.origin_location,
            "max_distance_km": job.max_distance_km,
        }
        if job.origin_location and job.max_distance_km is not None:
            filtered_results, radius_report = await apply_location_radius(
                records=filtered_results,
                schema_fields=job.schema_fields,
                origin_address=job.origin_location,
                max_distance_km=job.max_distance_km,
                preferred_location_field=location_field,
            )
            filtered_count = len(filtered_results)
        post_radius_count = len(filtered_results)

        # Deduplication
        if job.deduplicate and filtered_results:
            filtered_results = deduplicate_results(
                records=filtered_results,
                schema_fields=job.schema_fields,
                deduplicate_field=job.deduplicate_field,
            )
            filtered_count = len(filtered_results)

        source_breakdown = compute_source_breakdown(filtered_results)

        has_contact_fields = any(field.field_type in {FieldType.EMAIL, FieldType.PHONE} for field in job.schema_fields)
        if has_contact_fields and ai_source_prediction["sources_attempted"] > 0:
            if ai_source_prediction["records_ai_structured"] == 0:
                if settings.GROQ_API_KEY:
                    warnings.append(
                        "AI source structuring covered 0% rows in this run; provider timeouts / rate limits may reduce phone / email extraction.",
                    )
                else:
                    warnings.append(
                        "AI source structuring covered 0% rows in this run; set GROQ_API_KEY to improve phone / email extraction reliability.",
                    )

        job.quality_report = build_quality_report(
            raw_results=all_raw_results,
            post_filter_count=post_filter_count,
            post_radius_count=post_radius_count,
            radius_report=radius_report,
            final_results=filtered_results,
            min_record_score=job.min_record_score,
            type_integrity_report=type_integrity_report,
            source_breakdown=source_breakdown,
            ai_source_prediction=ai_source_prediction,
            ai_structuring_report=ai_structuring_report,
            warnings=warnings,
            acquisition_lineages=[m.get("acquisition_lineage", {}) for _, _, _, m in scraped if m.get("acquisition_lineage")],
        )

        job.results = normalize_job_results(filtered_results, job.schema_fields)
        job.total_records = total
        job.filtered_records = filtered_count
        _add_job_log(
            job,
            f"Final results: {filtered_count} records kept after filtering ({total} raw)",
            persist_fn=persist_job_state_fn,
        )

        # Add scraped_at timestamp to each record
        scraped_at = datetime.datetime.now().isoformat()
        for record in job.results:
            record["scraped_at"] = scraped_at

        # AI Insight Phase
        if job.results:
            if job.cancel_requested or _cancel_requested_from_db():
                job.cancel_requested = True
                mark_job_canceled(job)
                _add_job_log(job, "Job canceled before AI insight", level="warning", persist_fn=persist_job_state_fn)
                return

            job.status = JobStatus.RUNNING
            _add_job_log(job, f"Generating AI insights for {len(job.results)} records...", persist_fn=persist_job_state_fn)
            logging.info("Job %s: Generating AI insights over %d records...", job_id, len(job.results))
            try:
                from app.insight_engine import generate_data_insight  # research-shell, lazy

                reset_llm_call_count()
                analysis_text = await asyncio.wait_for(
                    generate_data_insight(job.results),
                    timeout=insight_timeout_seconds,
                )
                job.total_llm_calls += get_llm_call_count()
                job.analysis = analysis_text
                _add_job_log(job, "AI insights generated successfully")
            except asyncio.TimeoutError:
                job.total_llm_calls += get_llm_call_count()
                _add_job_log(job, "AI insight generation timed out", level="warning")
                logging.warning(
                    "Job %s: AI insight timed out after %ds; continuing without insight.",
                    job_id,
                    insight_timeout_seconds,
                )
                job.analysis = "Insight generation timed out."
            except Exception as ai_e:
                job.total_llm_calls += get_llm_call_count()
                logging.exception("Job %s: AI insight generation failed: %s", job_id, ai_e)
                _add_job_log(job, "AI insight generation failed", level="error")

        # Final cost calculation (Phase 80: Economic Optimization)
        # $0.01 per LLM call + estimated browser cost ($0.02 per URL)
        job.estimated_cost_usd = round(
            (job.total_llm_calls * settings.COST_PER_LLM_CALL) + (job.progress_total * settings.COST_PER_URL_SCRAPE),
            4,
        )

        # Bound memory footprint if results > 1000
        if len(job.results) > settings.JOB_RESULTS_DISK_OFFLOAD_THRESHOLD:
            try:
                from app.utils.job_results_store import save_job_results_to_disk

                file_path = save_job_results_to_disk(job.id, job.results)
                job.results_on_disk = True
                job.results_file_path = file_path
                job.results = []
                _add_job_log(
                    job,
                    f"Job results bounded and offloaded to disk due to size (>{
                        settings.JOB_RESULTS_DISK_OFFLOAD_THRESHOLD
                    } records).",
                )
            except Exception as e:
                logging.exception("Job %s: Failed to offload results to disk: %s", job_id, e)
                _add_job_log(job, f"Failed to offload results to disk: {e}", level="warning")

        total_urls = len(job.urls)
        if total_urls == 0:
            job.status = JobStatus.EMPTY_RESULT
            job.error = "No URLs to scrape (empty URL list)."
            _add_job_log(job, job.error, level="warning", persist_fn=persist_job_state_fn)
            if persist_state_single_critical_fn:
                persist_state_single_critical_fn()
        elif len(all_raw_results) == 0:
            job.status = JobStatus.EMPTY_RESULT
            job.error = "The job completed but no records were extracted. This may be due to a session-bound URL, empty response, anti-bot block, JavaScript-rendered results, or missing search-form replay."
            _add_job_log(job, job.error, level="warning", persist_fn=persist_job_state_fn)
            if persist_state_single_critical_fn:
                persist_state_single_critical_fn()
        elif urls_with_records > 0 and urls_with_records < total_urls:
            job.status = JobStatus.DEGRADED
            msg = f"{urls_with_records} of {total_urls} URLs produced results. Some pages may have anti-bot protection, expired sessions, or require JavaScript rendering."
            job.error = msg
            _add_job_log(job, msg, level="warning", persist_fn=persist_job_state_fn)
            if persist_state_single_critical_fn:
                persist_state_single_critical_fn()
        else:
            job.status = JobStatus.COMPLETED
            job.error = ""
        job.cancel_requested = False
        job.completed_at = datetime.datetime.now().isoformat()
        job.progress_current = job.progress_total
        save_semantic_state()
        # Contextual completion log message — use critical persistence for
        # terminal state
        if job.status == JobStatus.COMPLETED:
            _add_job_log(job, "Job completed successfully", persist_fn=persist_job_state_fn)
            if persist_state_single_critical_fn:
                persist_state_single_critical_fn()
        elif job.status == JobStatus.DEGRADED:
            _add_job_log(job, "Job completed with degraded results", level="warning", persist_fn=persist_job_state_fn)
            if persist_state_single_critical_fn:
                persist_state_single_critical_fn()
        elif job.status == JobStatus.EMPTY_RESULT:
            _add_job_log(job, "Job completed with empty result", level="warning", persist_fn=persist_job_state_fn)
            if persist_state_single_critical_fn:
                persist_state_single_critical_fn()

        logging.info("Job %s: Completed (%s): %d total, %d after filtering", job_id, job.status.value, total, filtered_count)

    except Exception as e:
        logging.exception(e)
        if job.cancel_requested:
            mark_job_canceled(job)
            _add_job_log(job, "Job canceled", level="warning")
            logging.warning("Job %s: Canceled", job_id)
        else:
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.completed_at = datetime.datetime.now().isoformat()
            _add_job_log(job, f"Job failed: {e!s}", level="error")
            logging.error("Job %s: Failed: %s", job_id, e)
        if persist_state_single_critical_fn:
            persist_state_single_critical_fn()
        else:
            persist_state_fn()
