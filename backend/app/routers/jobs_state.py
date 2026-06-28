"""Job store state management — thread-safe access to jobs_store and recycle_bin_store.

Extracted from ``routers/jobs.py`` during the router refactoring to separate
read routes, write routes, and state management.

Provides:
- ``JobStoreManager`` — encapsulates the threading lock and dict operations
- Standalone helper functions shared by read and write route modules
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.globals import _jobs_store_lock
from app.storage_interface import get_job_repository

if TYPE_CHECKING:
    import threading

    from app.models import Job, JobCreate

logger = logging.getLogger(__name__)


# ── Idempotency fingerprint helpers ───────────────────────────────────


def canonical_request_fingerprint(job_data: JobCreate) -> str:
    """Build a deterministic SHA-256 fingerprint from the full validated request.

    Includes all semantically meaningful fields from ``JobCreate`` so that
    the same ``Idempotency-Key`` with differing parameters (e.g. different
    schema fields, filters, or search parameters) produces a different
    fingerprint and triggers a 409 Conflict.

    The fingerprint is a hex-encoded SHA-256 hash of a stable JSON
    representation of the request payload with sorted keys. Fields that
    are metadata (``Idempotency-Key`` header, HTTP-level annotations) or
    ephemeral (``urls`` that were cleaned by the validator) are excluded.
    """
    # Build a canonical dict from the validated request, excluding fields
    # that do not affect job semantics (urls are already cleaned by the
    # model validator and are represented by the cleaned list).
    canonical: dict[str, object] = {
        "name": job_data.name,
        "mode": job_data.mode.value,
        "intent": job_data.intent,
        "urls": sorted(job_data.urls) if job_data.urls else [],
        "topic": job_data.topic,
        "location": job_data.location,
        "preferred_domain": job_data.preferred_domain,
        "source_policy": job_data.source_policy.value if job_data.source_policy else None,
        "max_per_domain": job_data.max_per_domain,
        "origin_location": job_data.origin_location,
        "max_distance_km": job_data.max_distance_km,
        "schema_fields": [
            {
                "name": f.name,
                "field_type": f.field_type.value,
                "description": f.description,
                "required": f.required,
            }
            for f in (job_data.schema_fields or [])
        ],
        "filters": [
            {
                "field_name": f.field_name,
                "operator": f.operator.value,
                "value": f.value,
                "origin_address": f.origin_address,
                "distance_unit": f.distance_unit,
            }
            for f in (job_data.filters or [])
        ],
        "pagination": job_data.pagination,
        "max_pages": job_data.max_pages,
        "deduplicate": job_data.deduplicate,
        "deduplicate_field": job_data.deduplicate_field,
        "selectors_map": job_data.selectors_map or {},
        "search_params": job_data.search_params or {},
        "min_record_score": job_data.min_record_score,
    }
    raw = json.dumps(canonical, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── Standalone persistence & idempotency helpers ──────────────────────


async def save_job(job: Job) -> None:
    """Persist a single job through the configured repository."""
    from app.storage_interface import get_job_repository

    repo = get_job_repository()
    await run_in_threadpool(repo.save_single, job)


def lookup_idempotency_key(idem_key: str) -> str | None:
    """Threadpool-safe wrapper around the repository's idempotency-key lookup.

    Uses the ``JobRepository`` interface so both SQLite and Postgres
    backends are supported.

    Fail-safe contract on repository errors:
    The original implementation returned ``None`` on every exception
    (fail-open), which let a sustained storage outage be exploited for
    unbounded POST spam — every duplicate retry would create a new job
    because the dedup table was unreachable.

    The hardened contract is:

    * The lookup failure is **logged at warning** so operators see it.
    * Prometheus counter ``dedup_lookup_miss_total`` is **incremented**
      once per failure, giving dashboards an alerting signal.
    * When the per-window cap (:data:`_DEDUP_FAIL_MAX_PER_WINDOW`) of
      consecutive failures is crossed, **every subsequent submit raises**
      :class:`HTTPException(503)` so the API fails closed under a real
      outage rather than silently allowing duplicate job flood.
    * The function still falls through to a return of ``None`` for the
      first N failures so a single transient blip does not block
      legitimate traffic.
    """
    global _dedup_fail_streak
    try:
        repo = get_job_repository()
        result = repo.lookup_idempotency_key(idem_key)
    except (RuntimeError, OSError, ValueError) as exc:
        _dedup_fail_streak += 1
        logger.warning(
            "idempotency-key lookup failed; treating as a cache miss (fail-open). "
            "Duplicate retries with idem_key=%r may create duplicate jobs until the "
            "repository recovers. Check the storage backend health.",
            idem_key,
            exc_info=True,
        )
        try:
            from app.metrics_collector import record_dedup_lookup_miss

            record_dedup_lookup_miss()
        except (ImportError, RuntimeError, OSError, ValueError) as metric_exc:  # nosec B110 - best-effort metric
            logger.debug("Could not record dedup_lookup_miss metric: %s", metric_exc)

        if _dedup_fail_streak > _DEDUP_FAIL_MAX_PER_WINDOW:
            logger.exception(
                "Dedup lookup has failed %d times (cap=%d) — failing closed "
                "with 503 to prevent unbounded duplicate-job spam during "
                "storage outage. Resolve idempotency-table health before "
                "continuing job submissions.",
                _dedup_fail_streak,
                _DEDUP_FAIL_MAX_PER_WINDOW,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "Idempotency store is unavailable; job submissions are "
                    "temporarily blocked to prevent duplicate creation. "
                    "Retry once the storage backend recovers."
                ),
            ) from exc
        return None

    # Lookup succeeded — reset the failure streak so the next outage
    # starts a fresh cap cycle. The streak is intentionally only reset
    # on a *successful* lookup, mirroring Prometheus staleness semantics.
    _dedup_fail_streak = 0
    return result


def lookup_idempotency_fingerprint(idem_key: str) -> str | None:
    """Threadpool-safe wrapper around the repository's request fingerprint lookup.

    Same fail-safe contract as :func:`lookup_idempotency_key`. A lookup
    failure logs at warning, increments ``dedup_lookup_miss_total``, and
    only fails closed after the per-window cap is exceeded.
    """
    global _dedup_fail_streak
    try:
        repo = get_job_repository()
        result = repo.lookup_idempotency_fingerprint(idem_key)
    except (RuntimeError, OSError, ValueError) as exc:
        _dedup_fail_streak += 1
        logger.warning(
            "idempotency-fingerprint lookup failed; treating as a cache miss. "
            "A retry with idem_key=%r will not be recognized as a duplicate "
            "of the original request.",
            idem_key,
            exc_info=True,
        )
        try:
            from app.metrics_collector import record_dedup_lookup_miss

            record_dedup_lookup_miss()
        except (ImportError, RuntimeError, OSError, ValueError):  # nosec B110 - best-effort metric
            pass

        if _dedup_fail_streak > _DEDUP_FAIL_MAX_PER_WINDOW:
            logger.exception(
                "Dedup fingerprint lookup has failed %d times (cap=%d) — failing closed with 503.",
                _dedup_fail_streak,
                _DEDUP_FAIL_MAX_PER_WINDOW,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "Idempotency store is unavailable; job submissions are temporarily blocked to prevent duplicate creation."
                ),
            ) from exc
        return None

    _dedup_fail_streak = 0
    return result


def record_idempotency_key(idem_key: str, job_id: str, fingerprint: str) -> None:
    """Threadpool-safe wrapper around the repository's idempotency-key recording.

    **Best-effort on failure**: a storage failure **does not raise** to
    callers — by the time this helper runs the job has already been
    persisted to the primary store, and a 500 response to the caller
    would be confusing (the job exists, but the response says it
    failed). The previous implementation silently swallowed errors
    though; the hardened contract is:

    * Log at **error** level (was warning) with full exc_info so the
      dedup drift is immediately investigable.
    * Increment ``dedup_lookup_miss_total`` Prometheus counter so an
      alerting rule can fire on missing dedup-table writes.
    * Idempotency-key persistence is enabled only when the runtime
      succeeds; on failure, all subsequent retries with the same
      ``idem_key`` will create duplicate jobs until the dedup table
      recovers and an operator manually backfills the keys.

    Callers in :mod:`app.services.job_creation_service` simply
    ``await`` this wrapper and ignore the return value.
    """
    try:
        repo = get_job_repository()
        repo.record_idempotency_key(idem_key, job_id, fingerprint)
    except (RuntimeError, OSError, ValueError):
        logger.exception(
            "Failed to record idempotency key %s → job %s; THIS WILL CAUSE "
            "DUPLICATE JOBS for any retry with the same idem_key until the "
            "storage backend recovers.",
            idem_key,
            job_id,
        )
        try:
            from app.metrics_collector import record_dedup_lookup_miss

            record_dedup_lookup_miss()
        except (ImportError, RuntimeError, OSError, ValueError):  # nosec B110 - best-effort metric
            logger.debug("Could not record dedup_lookup_miss metric")
        # Deliberately do NOT re-raise: the job was already persisted,
        # surfacing a 500 here would be misleading. Operators must
        # rely on the log message and the metric to act on this.


# ── Dedup failure rate-limit state ─────────────────────────────────────
# Module-level counters tracking consecutive repository failures so
# :func:`lookup_idempotency_key` and :func:`lookup_idempotency_fingerprint`
# can flip to fail-closed once the per-window cap is exceeded. Thread-safe
# because the lookup helpers always run inside ``run_in_threadpool`` on
# the same worker thread for a given ``idem_key``; Python's GIL keeps the
# simple int increments atomic.
_dedup_fail_streak: int = 0
_DEDUP_FAIL_MAX_PER_WINDOW: int = 25


def is_worker_mode() -> bool:
    """Check if worker queue mode is enabled (multi-process deployment).

    In worker mode, the API process and worker process have separate
    in-memory stores. Read endpoints should check the persistent store
    as a fallback to avoid serving stale data.
    """
    return settings.WORKER_QUEUE


def refresh_job_from_repo(job: Job, jobs_store: dict[str, Job]) -> Job:
    """Refresh a job's state from the persistent repository.

    In worker mode, the API's in-memory copy may be stale because the
    worker process updates jobs independently. This function re-reads
    the job from the DB and updates the in-memory store with the latest
    state, then returns the refreshed job.

    Falls back to the in-memory copy if the DB read fails.

    Note: this is a synchronous helper. Async route handlers must call
    it via ``run_in_threadpool`` to avoid blocking the event loop.
    """
    if not is_worker_mode():
        return job
    try:
        repo = get_job_repository()
        fresh = repo.get_job(job.id)
        if fresh is not None:
            jobs_store[job.id] = fresh
            return fresh
    except (AttributeError, ImportError, RuntimeError):
        logger.debug("Failed to refresh job %s from repo, using in-memory copy", job.id)
    return job


# ── JobStoreManager — thread-safe store access ────────────────────────


class JobStoreManager:
    """Thread-safe wrapper around the shared jobs and recycle-bin dicts.

    Encapsulates the ``threading.Lock`` that guards concurrent access to
    both stores, plus helper methods for the common lookup / pop / move
    patterns used by the read and write route modules.

    Usage::

        manager = JobStoreManager(jobs_store, recycle_bin_store)
        job = manager.get_job("some-uuid")
        manager.move_to_recycle_bin(job)
    """

    def __init__(
        self,
        jobs_store: dict[str, Job],
        recycle_bin_store: dict[str, Job],
    ) -> None:
        self._jobs_store = jobs_store
        self._recycle_bin_store = recycle_bin_store
        # Use the project-wide lock from globals so that ALL code paths
        # (system metrics, write routes, read routes) coordinate on the
        # same lock when accessing jobs_store / recycle_bin_store.
        self._lock = _jobs_store_lock

    # ── properties ────────────────────────────────────────────────────

    @property
    def jobs_store(self) -> dict[str, Job]:
        return self._jobs_store

    @property
    def recycle_bin_store(self) -> dict[str, Job]:
        return self._recycle_bin_store

    # ── read helpers ──────────────────────────────────────────────────

    def get_job(self, job_id: str) -> Job:
        """Thread-safe lookup returning the job or raising 404.

        In worker mode, refreshes from the persistent store so the API
        returns the latest state even when a separate worker process
        has updated the job.

        This helper is synchronous; async route handlers must call it
        via ``run_in_threadpool`` to avoid blocking the event loop on
        the targeted DB read.
        """
        with self._lock:
            if job_id not in self._jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = self._jobs_store[job_id]
            # In worker mode, refresh from repo to pick up cross-process
            # updates
            if is_worker_mode():
                try:
                    repo = get_job_repository()
                    fresh = repo.get_job(job_id)
                    if fresh is not None:
                        self._jobs_store[job_id] = fresh
                        return fresh
                except (AttributeError, ImportError, RuntimeError):
                    logger.debug("Failed to refresh job %s from repo", job_id)
            return job  # type: ignore[no-any-return]

    def pop_job(self, job_id: str) -> Job:
        """Thread-safe pop from jobs_store, raising 404 if missing."""
        with self._lock:
            if job_id not in self._jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            return self._jobs_store.pop(job_id)  # type: ignore[no-any-return]

    def move_to_recycle_bin(self, job: Job) -> None:
        """Thread-safe move from jobs_store to recycle_bin_store."""
        with self._lock:
            self._recycle_bin_store[job.id] = job
            self._jobs_store.pop(job.id, None)

    def pop_from_recycle_bin(self, job_id: str) -> Job:
        """Thread-safe pop from recycle_bin_store, raising 404 if missing."""
        with self._lock:
            if job_id not in self._recycle_bin_store:
                raise HTTPException(status_code=404, detail="Job not in recycle bin")
            return self._recycle_bin_store.pop(job_id)  # type: ignore[no-any-return]

    # ── lock context manager ──────────────────────────────────────────

    @property
    def lock(self) -> threading.Lock:
        return self._lock
