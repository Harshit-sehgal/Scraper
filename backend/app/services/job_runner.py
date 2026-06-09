import datetime
import logging
from concurrent.futures import ThreadPoolExecutor

from starlette.concurrency import run_in_threadpool

from app.models import JobStatus, ScrapeMode
from app.services.ai_structuring import apply_global_ai_structuring
from app.services.discovery import run_discovery_phase
from app.services.finalization import run_finalization
from app.services.insight import run_insight_phase
from app.services.post_processing import run_post_processing
from app.services.scraping import run_scraping_phase
from app.storage_interface import get_job_repository
from app.utils.job import mark_job_canceled

logger = logging.getLogger(__name__)


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


_log_persist_executor: ThreadPoolExecutor | None = None
"""Dedicated executor for fire-and-forget log persistence.

Initialised lazily by :func:`_get_log_persist_executor` so module import
is side-effect-free.  Call :func:`shutdown_log_persist_executor` during
application lifespan shutdown to release the thread.
"""


def _get_log_persist_executor() -> ThreadPoolExecutor:
    global _log_persist_executor
    if _log_persist_executor is None:
        _log_persist_executor = ThreadPoolExecutor(max_workers=1)
    return _log_persist_executor


def shutdown_log_persist_executor() -> None:
    """Shut down the log persistence executor, if it was ever created.

    Called from the FastAPI lifespan shutdown handler to release the
    dedicated thread.  Idempotent — safe to call multiple times.
    """
    global _log_persist_executor
    if _log_persist_executor is not None:
        _log_persist_executor.shutdown(wait=True)
        _log_persist_executor = None


def _add_job_log(job, message: str, level: str = "info", persist_fn=None, persist_single_fn=None) -> None:
    from app.models import LogEntry

    job.logs.append(LogEntry(message=message, level=level))
    executor = _get_log_persist_executor()
    if persist_single_fn:
        executor.submit(persist_single_fn)
    elif persist_fn:
        executor.submit(persist_fn)


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
) -> None:
    job = jobs_store.get(job_id)
    if not job:
        return

    async def _cancel_requested_from_db() -> bool:
        """Check the persistent store for a cross-process cancellation signal."""
        try:
            return await run_in_threadpool(get_job_repository().is_cancel_requested, job_id)
        except (AttributeError, ImportError, RuntimeError):
            return False

    async def _persist_job_state(critical: bool = False) -> None:
        if critical and persist_state_single_critical_fn:
            await run_in_threadpool(persist_state_single_critical_fn)
        elif persist_state_single_fn:
            await run_in_threadpool(persist_state_single_fn)
        elif persist_state_fn:
            await run_in_threadpool(persist_state_fn)

    persist_job_state_fn = persist_state_single_fn or persist_state_fn

    _add_job_log(
        job,
        f"Initializing job: {job.name}",
        persist_fn=persist_job_state_fn,
    )

    ai_source_prediction = {
        "sources_attempted": 0,
        "sources_with_ai_structuring": 0,
        "records_processed": 0,
        "records_ai_structured": 0,
    }
    warnings: list[str] = []

    if not job.started_at:
        job.started_at = datetime.datetime.now(datetime.UTC).isoformat()

    if job.cancel_requested or await _cancel_requested_from_db():
        job.cancel_requested = True
        mark_job_canceled(job, "Canceled before execution.")
        await _persist_job_state(critical=True)
        return

    try:
        load_semantic_state()

        # ── Phase 1: Discovery (AUTO mode only) ────────────────────────
        if job.mode == ScrapeMode.AUTO:
            discovery_ok = await run_discovery_phase(
                job,
                max_discovery_urls=max_discovery_urls,
                persist_fn=persist_job_state_fn,
                cancel_check=_cancel_requested_from_db,
            )
            if not discovery_ok:
                await _persist_job_state(critical=True)
                return

        job.status = JobStatus.RUNNING
        if job.mode == ScrapeMode.MANUAL:
            job.progress_total = len(job.urls) + 1
            job.progress_current = 0
        _add_job_log(job, f"Scraping started ({len(job.urls)} URLs queue)", persist_fn=persist_job_state_fn)

        # ── Phase 2: Scraping ─────────────────────────────────────────
        all_raw_results, urls_with_records, scrape_warnings, scraped = await run_scraping_phase(
            job,
            max_job_runtime_seconds=max_job_runtime_seconds,
            per_url_scrape_timeout_seconds=per_url_scrape_timeout_seconds,
            persist_fn=persist_job_state_fn,
            cancel_check=_cancel_requested_from_db,
            persist_single_fn=persist_state_single_fn,
        )
        warnings.extend(scrape_warnings)

        if job.cancel_requested or job.status == JobStatus.CANCELED:
            await _persist_job_state(critical=True)
            return

        # Accumulate AI source prediction stats from scrape metadata
        for _idx, results, success, meta in sorted(scraped, key=lambda x: x[0]):
            if success and meta:
                ai_source_prediction["sources_attempted"] += 1
                ai_source_prediction["records_processed"] += len(results)
                ai_source_prediction["records_ai_structured"] += meta.get("ai_structured_count", 0)
                if meta.get("ai_structured_count", 0) > 0:
                    ai_source_prediction["sources_with_ai_structuring"] += 1

        # ── Phase 3: AI Structuring ───────────────────────────────────
        all_raw_results, ai_structuring_report, struct_warnings = await apply_global_ai_structuring(
            all_raw_results=all_raw_results,
            schema_fields=job.schema_fields,
            ai_source_prediction=ai_source_prediction,
            ai_structuring_timeout_seconds=ai_structuring_timeout_seconds,
            add_job_log=lambda msg, level="info": _add_job_log(job, msg, level=level, persist_fn=persist_job_state_fn),
            on_llm_call=lambda count: setattr(job, "total_llm_calls", job.total_llm_calls + count),
            min_record_score=job.min_record_score or 0.35,
        )
        warnings.extend(struct_warnings)

        if job.cancel_requested or await _cancel_requested_from_db():
            job.cancel_requested = True
            mark_job_canceled(job)
            await _persist_job_state(critical=True)
            return

        # ── Phase 4: Post-processing ──────────────────────────────────
        await run_post_processing(
            job,
            all_raw_results=all_raw_results,
            scraped=scraped,
            ai_source_prediction=ai_source_prediction,
            ai_structuring_report=ai_structuring_report,
            warnings=warnings,
            persist_fn=persist_job_state_fn,
        )

        # ── Phase 5: AI Insight ───────────────────────────────────────
        await run_insight_phase(
            job,
            insight_timeout_seconds=insight_timeout_seconds,
            persist_fn=persist_job_state_fn,
            cancel_check=_cancel_requested_from_db,
        )

        # ── Phase 6: Finalization ─────────────────────────────────────
        await run_finalization(
            job,
            all_raw_results=all_raw_results,
            urls_with_records=urls_with_records,
            persist_fn=persist_job_state_fn,
            persist_single_fn=persist_state_single_fn,
            persist_single_critical_fn=persist_state_single_critical_fn,
        )

        total = job.total_records
        filtered_count = job.filtered_records
        logger.info("Job %s: Completed (%s): %d total, %d after filtering", job_id, job.status.value, total, filtered_count)

    except Exception as e:
        logger.exception("Job %s failed", job_id)
        if job.cancel_requested:
            mark_job_canceled(job)
            _add_job_log(job, "Job canceled", level="warning")
            logger.warning("Job %s: Canceled", job_id)
        else:
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.completed_at = datetime.datetime.now(datetime.UTC).isoformat()
            _add_job_log(job, f"Job failed: {e!s}", level="error")
            logger.exception("Job %s: Failed (%s)", job_id, type(e).__name__)
        await _persist_job_state(critical=True)
