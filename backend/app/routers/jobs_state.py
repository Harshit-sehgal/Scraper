"""Job store state management — thread-safe access to jobs_store and recycle_bin_store.

Extracted from ``routers/jobs.py`` during the router refactoring to separate
read routes, write routes, and state management.

Provides:
- ``JobStoreManager`` — encapsulates the threading lock and dict operations
- Standalone helper functions shared by read and write route modules
"""

from __future__ import annotations

import logging
import threading

from app.config import settings
from app.models import Job
from app.storage_interface import get_job_repository
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)


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

    On lookup failure the function returns ``None`` and logs at warning
    level. Returning ``None`` is the *fail-open* behavior required so
    that a transient DB outage does not block every job submission,
    but the warning makes the silent dedup-miss visible to operators
    who can then decide whether to block writes until the DB recovers.
    """
    try:
        repo = get_job_repository()
        return repo.lookup_idempotency_key(idem_key)
    except Exception:
        logger.warning(
            "idempotency-key lookup failed; treating as a cache miss (fail-open). "
            "Duplicate retries with idem_key=%r may create duplicate jobs until the "
            "repository recovers. Check the storage backend health.",
            idem_key,
            exc_info=True,
        )
        return None


def lookup_idempotency_fingerprint(idem_key: str) -> str | None:
    """Threadpool-safe wrapper around the repository's request fingerprint lookup.

    Same fail-open contract as :func:`lookup_idempotency_key`. A lookup
    failure logs at warning level so a sustained outage is visible.
    """
    try:
        repo = get_job_repository()
        return repo.lookup_idempotency_fingerprint(idem_key)
    except Exception:
        logger.warning(
            "idempotency-fingerprint lookup failed; treating as a cache miss. "
            "A retry with idem_key=%r will not be recognized as a duplicate "
            "of the original request.",
            idem_key,
            exc_info=True,
        )
        return None


def record_idempotency_key(idem_key: str, job_id: str, fingerprint: str) -> None:
    """Threadpool-safe wrapper around the repository's idempotency-key recording.

    A failure is logged at warning level (not just debug) so the operator
    can see that subsequent retries with the same ``idem_key`` will
    not be deduplicated.
    """
    try:
        repo = get_job_repository()
        repo.record_idempotency_key(idem_key, job_id, fingerprint)
    except Exception:
        logger.warning(
            "Failed to record idempotency key %s; subsequent retries will not be deduplicated.",
            idem_key,
            exc_info=True,
        )


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
        self._lock = threading.Lock()

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
