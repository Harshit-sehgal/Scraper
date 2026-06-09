"""Finalization phase extracted from ``job_runner.run_job`` (D2/L1 strangler refactor).

Encapsulates cost calculation, disk offload, status determination,
and terminal persistence.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from typing import Any

from app.config import settings
from app.models import JobStatus
from app.services._job_log import log_job_message as _log
from app.services.status_classifier import classify_job_status, job_completion_message

logger = logging.getLogger(__name__)


async def run_finalization(
    job: Any,
    *,
    all_raw_results: list[dict],
    urls_with_records: int,
    persist_fn: Callable,
    persist_single_fn: Callable | None = None,
    persist_single_critical_fn: Callable | None = None,
) -> None:
    """Finalize job: calculate cost, offload large results, set terminal status."""
    persist_job_state_fn = persist_single_fn or persist_fn

    job.estimated_cost_usd = round(
        (job.total_llm_calls * settings.COST_PER_LLM_CALL) + (job.progress_total * settings.COST_PER_URL_SCRAPE),
        4,
    )

    if len(job.results) > settings.JOB_RESULTS_DISK_OFFLOAD_THRESHOLD:
        try:
            from app.utils.job_results_store import save_job_results_to_disk

            file_path = await _run_in_threadpool(save_job_results_to_disk, job.id, job.results)
            job.results_on_disk = True
            job.results_file_path = file_path
            job.results = []
            _log(
                job,
                f"Job results bounded and offloaded to disk due to size (>{settings.JOB_RESULTS_DISK_OFFLOAD_THRESHOLD} records).",
                persist_fn=persist_job_state_fn,
            )
        except Exception as e:
            logger.exception("Failed to offload results to disk")
            _log(job, f"Failed to offload results to disk: {e}", level="warning", persist_fn=persist_job_state_fn)

    total_urls = len(job.urls)
    job.status, job.error = classify_job_status(
        total_urls=total_urls,
        urls_with_records=urls_with_records,
        all_raw_results_count=len(all_raw_results),
    )

    job.cancel_requested = False
    job.completed_at = datetime.datetime.now(datetime.UTC).isoformat()
    job.progress_current = job.progress_total

    from app.services.job_runner import save_semantic_state

    save_semantic_state()

    log_level = "warning" if job.status in (JobStatus.DEGRADED, JobStatus.EMPTY_RESULT) else "info"
    _log(job, job_completion_message(job.status), level=log_level, persist_fn=persist_fn)
    if job.status in (JobStatus.DEGRADED, JobStatus.EMPTY_RESULT):
        _log(job, job.error, level="warning", persist_fn=persist_fn)
    await _persist_critical(job, persist_single_critical_fn, persist_single_fn, persist_fn)

    logger.info("Completed (%s): %d total results", job.status.value, len(all_raw_results))


async def _persist_critical(
    _job: Any,
    persist_single_critical_fn: Callable | None,
    persist_single_fn: Callable | None,
    persist_fn: Callable,
) -> None:
    """Persist critical state using the best available function."""
    from starlette.concurrency import run_in_threadpool

    if persist_single_critical_fn:
        await run_in_threadpool(persist_single_critical_fn)
    elif persist_single_fn:
        await run_in_threadpool(persist_single_fn)
    else:
        await run_in_threadpool(persist_fn)


async def _run_in_threadpool(fn: Callable, *args: Any) -> Any:
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(fn, *args)
