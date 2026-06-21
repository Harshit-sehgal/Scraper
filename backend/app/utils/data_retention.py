"""Data retention enforcement — TTL-based cleanup for completed jobs, recycle bin, and stale state.

Provides a configurable retention policy and a central ``enforce_retention``
entry point that routers and scheduled tasks can call to purge data that has
passed its retention window.

Retention defaults (overridable via env / settings):
- ``DATAFORGE_RETENTION_DAYS_COMPLETED``: days to keep completed jobs (default 90)
- ``DATAFORGE_RETENTION_DAYS_RECYCLE``: days to keep jobs in recycle bin (default 30)
- ``DATAFORGE_RETENTION_DAYS_IDEMPOTENCY``: days to keep idempotency keys (default 7)
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from app.models import JobStatus

logger = logging.getLogger(__name__)

# ─── Defaults (overridden by settings when available) ───────────────────


def _get_days(key: str, default: int) -> int:
    """Read an integer retention setting from env fallback.

    Tries ``app.config.settings`` first, then ``os.environ``, then
    the provided *default*.
    """
    import os

    try:
        from app.config import settings

        val = getattr(settings, key, None)
        if val is not None:
            return max(1, int(val))
    except (ImportError, AttributeError, ValueError, TypeError):
        pass
    try:
        return max(1, int(os.environ.get(key, str(default))))
    except (ValueError, TypeError):
        return default


_RETENTION_DAYS_COMPLETED = 90
_RETENTION_DAYS_RECYCLE = 30
_RETENTION_DAYS_IDEMPOTENCY = 7


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _age_in_days(iso_timestamp: str | None) -> float | None:
    """Return the age in days of an ISO-8601 timestamp, or None if unparseable."""
    if not iso_timestamp:
        return None
    try:
        dt = datetime.datetime.fromisoformat(iso_timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.UTC)
        return (_now_utc() - dt).total_seconds() / 86400.0
    except (ValueError, TypeError, AttributeError):
        return None


# ─── Retention Policy ──────────────────────────────────────────────────


def get_retention_config() -> dict[str, int]:
    """Return current retention policy as a flat dict."""
    return {
        "completed_jobs_days": _get_days("DATAFORGE_RETENTION_DAYS_COMPLETED", _RETENTION_DAYS_COMPLETED),
        "recycle_bin_days": _get_days("DATAFORGE_RETENTION_DAYS_RECYCLE", _RETENTION_DAYS_RECYCLE),
        "idempotency_keys_days": _get_days("DATAFORGE_RETENTION_DAYS_IDEMPOTENCY", _RETENTION_DAYS_IDEMPOTENCY),
    }


# ─── Enforcement ───────────────────────────────────────────────────────


def enforce_retention(
    jobs_store: dict[str, Any],
    recycle_bin_store: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Enforce the current retention policy against the in-memory stores.

    Returns a dict with keys:
    - ``jobs_purged``: number of completed/done jobs removed
    - ``recycle_purged``: number of recycle-bin items removed
    - ``jobs_skipped``: number of completed jobs within retention window
    - ``recycle_skipped``: number of recycle items within retention window

    When ``dry_run=True``, no entries are actually removed; the returned
    counts reflect what *would* be purged.
    """
    config = get_retention_config()
    completed_days = config["completed_jobs_days"]
    recycle_days = config["recycle_bin_days"]

    terminal_statuses = {
        JobStatus.COMPLETED.value,
        JobStatus.DEGRADED.value,
        JobStatus.EMPTY_RESULT.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELED.value,
    }

    jobs_purged = 0
    jobs_skipped = 0
    recycle_purged = 0
    recycle_skipped = 0

    # Terminal jobs
    to_delete: list[str] = []
    for job_id, job in list(jobs_store.items()):
        status_str = str(job.status.value if hasattr(job.status, "value") else job.status)
        if status_str not in terminal_statuses:
            continue
        age = _age_in_days(getattr(job, "completed_at", None))
        if age is not None and age >= completed_days:
            to_delete.append(job_id)
            jobs_purged += 1
        else:
            jobs_skipped += 1

    if to_delete and not dry_run:
        for job_id in to_delete:
            jobs_store.pop(job_id, None)
        logger.info("Data retention purged %d terminal jobs older than %d days", len(to_delete), completed_days)

    # Recycle bin items
    recycle_to_delete: list[str] = []
    for job_id, job in list(recycle_bin_store.items()):
        completed_at = getattr(job, "completed_at", None) or getattr(job, "created_at", None)
        age = _age_in_days(completed_at)
        if age is not None and age >= recycle_days:
            recycle_to_delete.append(job_id)
            recycle_purged += 1
        else:
            recycle_skipped += 1

    if recycle_to_delete and not dry_run:
        for job_id in recycle_to_delete:
            recycle_bin_store.pop(job_id, None)
        logger.info("Data retention purged %d recycle-bin items older than %d days", len(recycle_to_delete), recycle_days)

    return {
        "jobs_purged": jobs_purged,
        "recycle_purged": recycle_purged,
        "jobs_skipped": jobs_skipped,
        "recycle_skipped": recycle_skipped,
    }


def enforce_idempotency_retention(*, dry_run: bool = False) -> int:
    """Delete idempotency keys older than the retention window.

    Returns the number of keys that would be (or were) deleted.
    Delegates to the existing ``prune_idempotency_keys`` in ``job_store``.
    """
    config = get_retention_config()
    days = config["idempotency_keys_days"]
    if dry_run:
        return 0
    try:
        from app.job_store import prune_idempotency_keys

        deleted = prune_idempotency_keys(older_than_days=days)
        if deleted:
            logger.info("Data retention pruned %d idempotency keys older than %d days", deleted, days)
        return deleted
    except (ImportError, RuntimeError, OSError) as e:
        logger.debug("Idempotency key pruning skipped: %s", e)
        return 0
