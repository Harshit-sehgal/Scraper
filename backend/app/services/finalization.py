"""Finalization phase extracted from ``job_runner.run_job`` (D2/L1 strangler refactor).

Encapsulates cost calculation, disk offload, status determination,
and terminal persistence.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.models import JobStatus
from app.services._job_log import log_job_message as _log
from app.services.job_state_machine import transition_to
from app.services.status_classifier import classify_job_status, job_completion_message
from app.utils.datetime_normalization import parse_datetime

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def _parse_job_timestamp(value: Any) -> datetime.datetime | None:
    """Parse a job timestamp string using the central normalizer.

    Falls back to ``None`` for unparseable values (matching the
    pre-migration behaviour of ``fromisoformat`` + ``ValueError``).
    """
    try:
        return parse_datetime(str(value)) if value else None
    except ValueError:
        return None


def _record_job_duration_metric(job: Any) -> None:
    started = _parse_job_timestamp(getattr(job, "started_at", None) or getattr(job, "created_at", None))
    completed = _parse_job_timestamp(getattr(job, "completed_at", None))
    if not started or not completed:
        return
    duration = (completed - started).total_seconds()
    if duration < 0:
        return
    try:
        from app.metrics_collector import record_job_duration

        record_job_duration(duration)
    except (ImportError, RuntimeError, ValueError, TypeError):
        logger.debug("Job-duration metric skipped for job %s", getattr(job, "id", ""))


def _record_job_completed_usage(job: Any) -> None:
    """Record terminal job usage without letting billing failures break finalization."""
    user_id = getattr(job, "created_by", "") or getattr(job, "user_id", "") or ""
    if not user_id:
        return
    try:
        from app.utils.usage_ledger import UsageType, get_usage_ledger

        get_usage_ledger().record_usage(
            user_id,
            UsageType.JOB_COMPLETED,
            quantity=1,
            metadata={
                "job_id": getattr(job, "id", ""),
                "status": getattr(getattr(job, "status", ""), "value", str(getattr(job, "status", ""))),
                "total_records": getattr(job, "total_records", 0),
                "filtered_records": getattr(job, "filtered_records", 0),
            },
            idempotency_key=f"job-completed:{getattr(job, 'id', '')}",
            org_id=getattr(job, "org_id", "") or "",
            project_id=getattr(job, "project_id", "") or "",
        )
    except ValueError:
        logger.warning("Job-completion quota exceeded for job %s", getattr(job, "id", ""))
    except (RuntimeError, OSError, TypeError) as exc:
        logger.debug("Job-completion metering skipped: %s", exc)


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

    # LLM + per-URL base cost (existing formula)
    llm_url_cost = round(
        (job.total_llm_calls * settings.COST_PER_LLM_CALL) + (job.progress_total * settings.COST_PER_URL_SCRAPE),
        4,
    )

    # Per-job cost breakdown from the resource tracker
    try:
        from app.job_cost_tracker import get_job_cost_tracker

        tracker = get_job_cost_tracker()
        cost_breakdown = tracker.finalize_job(job.id)
        job.cost_breakdown = cost_breakdown
        resource_cost = cost_breakdown.get("total_usd", 0.0)
    except (ImportError, RuntimeError, ValueError, OSError):
        logger.debug("[finalization] Cost tracker unavailable, using LLM+URL formula only", exc_info=True)
        resource_cost = 0.0
        job.cost_breakdown = {}

    job.estimated_cost_usd = round(llm_url_cost + resource_cost, 4)

    if len(job.results) > settings.JOB_RESULTS_DISK_OFFLOAD_THRESHOLD:
        try:
            from app.utils.job_results_store import save_job_results_to_disk

            file_path = await _run_in_threadpool(save_job_results_to_disk, job.id, job.results)
            job.results_on_disk = True
            job.results_file_path = file_path
            job.results = []
            _log(
                job,
                (
                    f"Job results bounded and offloaded to disk "
                    f"due to size (>{settings.JOB_RESULTS_DISK_OFFLOAD_THRESHOLD} records)."
                ),
                persist_fn=persist_job_state_fn,
            )
        except (RuntimeError, OSError, ValueError) as e:
            logger.exception("Failed to offload results to disk")
            _log(job, f"Failed to offload results to disk: {e}", level="warning", persist_fn=persist_job_state_fn)

    total_urls = len(job.urls)
    terminal_status, error_message = classify_job_status(
        total_urls=total_urls,
        urls_with_records=urls_with_records,
        all_raw_results_count=len(all_raw_results),
    )
    transition_to(
        job,
        terminal_status,
        error=error_message,
        cancel_requested=False,
    )
    _record_job_duration_metric(job)
    try:
        from app.metrics_collector import record_job_failed, record_job_succeeded

        if terminal_status == JobStatus.FAILED:
            record_job_failed()
        elif terminal_status in (JobStatus.COMPLETED, JobStatus.DEGRADED, JobStatus.EMPTY_RESULT):
            record_job_succeeded()
    except ImportError as exc:
        logger.debug("metrics_collector not available, skipping job metric recording: %s", exc)
    job.progress_current = job.progress_total
    _record_job_completed_usage(job)

    from app.services.job_runner import save_semantic_state

    save_semantic_state()

    log_level = "warning" if job.status in (JobStatus.DEGRADED, JobStatus.EMPTY_RESULT) else "info"
    _log(job, job_completion_message(job.status), level=log_level, persist_fn=persist_fn)
    if job.status in (JobStatus.DEGRADED, JobStatus.EMPTY_RESULT):
        _log(job, job.error, level="warning", persist_fn=persist_fn)
    await _persist_critical(job, persist_single_critical_fn, persist_single_fn, persist_fn)

    # Fire outbound webhook if configured
    await _deliver_webhook_if_configured(job)

    # Fire notification channels if configured (Feat 35/36)
    await _deliver_notifications_if_configured(job)

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


async def _deliver_webhook_if_configured(job: Any) -> None:
    """Fire outbound webhook if the job has a ``webhook_url`` configured.

    Webhook delivery is best-effort — failures are logged but never
    prevent the job from being marked terminal.
    """
    webhook_url = getattr(job, "webhook_url", None)
    if not webhook_url:
        return
    try:
        from app.services.webhook_delivery import deliver_webhook

        await deliver_webhook(job)
    except (ImportError, RuntimeError, ValueError) as exc:
        logger.debug("Webhook delivery skipped for job %s: %s", getattr(job, "id", ""), exc)
    except (OSError, TypeError):
        logger.exception("Webhook delivery threw unexpected error for job %s", getattr(job, "id", ""))


async def _deliver_notifications_if_configured(job: Any) -> None:
    """Deliver notifications to all configured channels for a job (Feat 35/36).

    Notification delivery is best-effort — failures are logged but never
    prevent the job from being marked terminal.
    """
    job_id = getattr(job, "id", "")
    if not job_id:
        return
    try:
        from app.services.notifications import deliver_notifications

        status_value = getattr(getattr(job, "status", ""), "value", str(getattr(job, "status", "")))
        subject = f"DataForge Job {job_id[:8]} — {status_value}"
        body = (
            f"Job *{getattr(job, 'name', '')}* finished with status *{status_value}*.\n"
            f"Records: {getattr(job, 'total_records', 0)} total, "
            f"{getattr(job, 'filtered_records', 0)} filtered.\n"
            f"Cost: ${getattr(job, 'estimated_cost_usd', 0.0):.4f}"
        )
        error = getattr(job, "error", None)
        if error:
            body += f"\nError: {error}"
        metadata: dict = {
            "Job ID": job_id,
            "Status": status_value,
            "Records": str(getattr(job, "total_records", 0)),
        }
        await deliver_notifications(job_id, "completed", subject, body, metadata)
    except (ImportError, RuntimeError, ValueError) as exc:
        logger.debug("Notification delivery skipped for job %s: %s", job_id, exc)
    except (OSError, TypeError):
        logger.exception("Notification delivery threw unexpected error for job %s", job_id)


async def _run_in_threadpool(fn: Callable, *args: Any) -> Any:
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(fn, *args)
