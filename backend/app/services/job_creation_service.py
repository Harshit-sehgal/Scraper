"""Job creation service — encapsulates the business logic of creating a new job.

Extracted from ``app.routers.jobs_write.register_jobs_write_routes`` to
separate HTTP concerns (request parsing, response formatting) from domain
logic (auth resolution, URL safety, idempotency, usage metering, persistence,
scheduling).

Usage::

    service = JobCreationService(manager)
    result = await service.create_job(job_data, request)
    # result is a JobCreationResult namedtuple
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.models import Job, JobCreate, ScrapeMode
from app.routers.jobs_state import (
    JobStoreManager,
    canonical_request_fingerprint,
    lookup_idempotency_fingerprint,
    lookup_idempotency_key,
    record_idempotency_key,
    save_job,
)
from app.utils.usage_ledger import UsageType, get_usage_ledger

if TYPE_CHECKING:
    from fastapi import Request


logger = logging.getLogger(__name__)


class JobCreationError(Exception):
    """Base exception for job creation failures. Maps to an HTTP error response."""

    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class SSRFValidationError(JobCreationError):
    """Raised when a manual URL fails SSRF/security validation."""

    def __init__(self, url: str):
        super().__init__(
            detail=f"URL failed security validation: {url}",
            status_code=400,
        )


class InvalidIdempotencyKeyError(JobCreationError):
    """Raised when the Idempotency-Key header has an invalid format."""

    def __init__(self):
        super().__init__(
            detail="Idempotency-Key header is invalid. Allowed characters: letters, digits, underscore, hyphen. Max length: 128.",
            status_code=400,
        )


class IdempotencyConflictError(JobCreationError):
    """Raised when the same Idempotency-Key is reused with a different payload."""

    def __init__(self):
        super().__init__(
            detail="Conflict: Another request with a different payload was already sent for this Idempotency-Key.",
            status_code=409,
        )


class UsageQuotaExceededError(JobCreationError):
    """Raised when the user has exceeded their plan quota."""

    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=429)


class WorkerQueueQuotaExceededError(JobCreationError):
    """Raised when the worker queue rejects the job (e.g., scheduled-job quota)."""

    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=429)


class WorkerQueueEnqueueError(JobCreationError):
    """Raised when the worker queue fails to enqueue the job."""

    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=503)


@dataclass
class JobCreationResult:
    """Result of a successful job creation.

    ``idempotent_replay`` distinguishes a freshly created job from one
    returned via Idempotency-Key replay.

    Attributes:
        job_id: The ID of the created (or replayed) job.
        status: The job's status string.
        idempotent_replay: Whether this was an idempotent replay of an existing job.
    """

    job_id: str
    status: str
    idempotent_replay: bool = False


# Backwards-compatible type alias that emphasises the "idempotent replay"
# semantic at the call-site. Both names resolve to the same dataclass so
# callers can return either without type errors.
IdempotentReplayResult = JobCreationResult


def _schedule_job(job_id: str) -> None:
    """Schedule a job for execution via the active runtime dependency container."""
    from app.runtime_deps import run_job_coro_fn as _rjf
    from app.runtime_deps import schedule_task_fn as _stf

    _stf(_rjf(job_id))


class JobCreationService:
    """Encapsulates the business logic for creating scraping jobs.

    The service is stateless: all dependencies (store, ledger, queue) are
    resolved from global singletons or the provided ``JobStoreManager``.
    """

    def __init__(self, manager: JobStoreManager) -> None:
        self._manager = manager

    # ── Public API ─────────────────────────────────────────────────────

    async def create_job(
        self,
        job_data: JobCreate,
        request: Request,
    ) -> JobCreationResult:
        """Execute the full job creation pipeline.

        Steps:
        1. Resolve user identity and tenant context
        2. Validate and sanitize URLs
        3. M2: Check semantic mode availability if required
        4. Handle idempotency key (replay or reject conflicts)
        5. Build and persist the Job object
        6. Record usage in the ledger
        7. Enqueue or schedule the job for execution
        8. Return the result
        """
        # Step 1: Resolve identity and tenant context
        user_id, owner_org_id, owner_project_id = self._resolve_identity(request)

        # Step 2: Validate URLs
        urls = self._validate_urls(job_data)

        # M2: Fail fast if semantic mode is required but unavailable
        mode = str(job_data.mode or "fast").lower()
        if mode == "semantic":
            try:
                from app.semantic_pipeline import get_pipeline_status  # type: ignore[attr-defined]

                status = await get_pipeline_status()
                if not status.get("available", False):
                    from app.exceptions import JobCreationError

                    raise JobCreationError(
                        status_code=400, detail="M2: Semantic mode is not available. Use 'fast' or 'browser' mode instead."
                    )
            except (ImportError, RuntimeError):
                from app.exceptions import JobCreationError

                raise JobCreationError(status_code=503, detail="M2: Semantic pipeline unavailable; try again later.")

        # Step 3: Handle idempotency
        idem_key = self._extract_idempotency_key(request)
        if idem_key:
            replay = await self._check_idempotent_replay(idem_key, job_data)
            if replay is not None:
                return replay

        # Step 4: Build the Job
        job = self._build_job(job_data, urls, user_id, owner_org_id, owner_project_id)

        # Step 5: Record usage
        self._record_usage(user_id, job.id, idem_key, owner_org_id, owner_project_id)

        # Step 6: Persist
        with self._manager.lock:
            self._manager.jobs_store[job.id] = job
        await save_job(job)

        try:
            from app.metrics_collector import record_job_created

            record_job_created()
        except ImportError:
            pass

        # Step 7: Record idempotency key
        if idem_key:
            fingerprint = canonical_request_fingerprint(job_data)
            await run_in_threadpool(record_idempotency_key, idem_key, job.id, fingerprint)

        # Step 8: Schedule
        await self._schedule_execution(job.id, user_id, owner_org_id, owner_project_id)

        return JobCreationResult(
            job_id=job.id,
            status=job.status.value,
            idempotent_replay=False,
        )

    # ── Internal steps ─────────────────────────────────────────────────

    def _resolve_identity(self, request: Request) -> tuple[str, str, str]:
        """Extract user_id, org_id, project_id from the request auth context."""
        from app.utils.rbac import get_current_user, resolve_auth_context

        _role, user_id = get_current_user(request)
        try:
            _ctx = resolve_auth_context(request, allow_cookie=True)
            return user_id, _ctx.org_id, _ctx.project_id
        except Exception:
            logger.warning(
                "Failed to resolve org/project context for user %s; defaulting to empty",
                user_id,
                exc_info=True,
            )
            return user_id, "", ""

    def _validate_urls(self, job_data: JobCreate) -> list[str]:
        """Validate and sanitize URLs, rejecting SSRF targets.

        Note: basic format validation (blank URLs, non-http schemes) is
        handled by the ``JobCreate`` Pydantic model. This method performs
        the defence-in-depth SSRF check that mirrors the same guard on
        ``/api/scraper/diagnostics``.
        """
        from app.url_safety import validate_public_http_url

        if job_data.mode != ScrapeMode.MANUAL:
            return []

        manual_urls = [u.strip() for u in job_data.urls if str(u or "").strip()]
        safe_urls: list[str] = []
        for u in manual_urls:
            try:
                validate_public_http_url(u)
                safe_urls.append(u)
            except ValueError:
                raise SSRFValidationError(u) from None
        return safe_urls

    def _extract_idempotency_key(self, request: Request) -> str:
        """Extract and validate the Idempotency-Key header."""
        idem_key = (request.headers.get("Idempotency-Key") or "").strip()
        if idem_key and not re.fullmatch(r"[A-Za-z0-9_\-]{1,128}", idem_key):
            raise InvalidIdempotencyKeyError
        return idem_key

    async def _check_idempotent_replay(
        self,
        idem_key: str,
        job_data: JobCreate,
    ) -> IdempotentReplayResult | None:
        """Check if this idempotency key matches an existing job.

        Returns:
            - ``IdempotentReplayResult`` if a replay should be returned
            - ``None`` if this is a new request (proceed with creation)
        """
        existing_job_id = await run_in_threadpool(lookup_idempotency_key, idem_key)
        if existing_job_id is None:
            return None

        # Key exists — check fingerprint for conflict
        existing_fingerprint = await run_in_threadpool(lookup_idempotency_fingerprint, idem_key)
        if existing_fingerprint is not None and existing_fingerprint != canonical_request_fingerprint(job_data):
            raise IdempotencyConflictError

        # Same payload — return existing job info. ``idempotent_replay=True``
        # signals the HTTP layer that this is a replay (so the response can
        # distinguish "new" from "already-existed").
        cached = self._manager.jobs_store.get(existing_job_id)
        if cached is not None:
            return IdempotentReplayResult(
                job_id=cached.id,
                status=cached.status.value,
                idempotent_replay=True,
            )
        return IdempotentReplayResult(
            job_id=existing_job_id,
            status="unknown",
            idempotent_replay=True,
        )

    def _build_job(
        self,
        job_data: JobCreate,
        urls: list[str],
        user_id: str,
        org_id: str,
        project_id: str,
    ) -> Job:
        """Construct a Job domain object from validated input."""
        return Job(
            name=job_data.name,
            mode=job_data.mode,
            intent=job_data.intent,
            urls=urls,
            topic=job_data.topic,
            location=job_data.location,
            preferred_domain=job_data.preferred_domain,
            source_policy=job_data.source_policy,
            max_per_domain=job_data.max_per_domain,
            origin_location=job_data.origin_location,
            max_distance_km=job_data.max_distance_km,
            schema_fields=job_data.schema_fields,
            filters=job_data.filters,
            selectors_map=job_data.selectors_map,
            search_params=job_data.search_params,
            pagination=job_data.pagination,
            max_pages=job_data.max_pages,
            deduplicate=job_data.deduplicate,
            deduplicate_field=job_data.deduplicate_field,
            min_record_score=job_data.min_record_score,
            created_by=user_id,
            org_id=org_id,
            project_id=project_id,
        )

    def _record_usage(
        self,
        user_id: str,
        job_id: str,
        idem_key: str,
        org_id: str,
        project_id: str,
    ) -> None:
        """Record job creation in the usage ledger."""
        try:
            get_usage_ledger().record_usage(
                user_id,
                UsageType.JOB_CREATED,
                quantity=1,
                metadata={"job_id": job_id},
                idempotency_key=idem_key or f"job-created:{job_id}",
                org_id=org_id,
                project_id=project_id,
            )
        except ValueError as exc:
            raise UsageQuotaExceededError(detail=str(exc)) from exc

    async def _schedule_execution(
        self,
        job_id: str,
        user_id: str,
        org_id: str,
        project_id: str,
    ) -> None:
        """Enqueue the job to the worker queue or schedule it inline."""
        if not settings.WORKER_QUEUE:
            _schedule_job(job_id)
            return

        try:
            from app.worker_queue import Priority, get_worker_queue

            queue = get_worker_queue()
            task_id = await queue.enqueue(
                task_type="scrape_job",
                payload={
                    "job_id": job_id,
                    "user_id": user_id,
                    "org_id": org_id,
                    "project_id": project_id,
                },
                priority=Priority.NORMAL,
                task_id=job_id,
                usage_context={
                    "user_id": user_id,
                    "org_id": org_id,
                    "project_id": project_id,
                    "job_id": job_id,
                },
            )
            logger.info("Job %s enqueued to worker queue (task=%s)", job_id, task_id)
        except ValueError as e:
            # Quota rejection — rollback
            self._rollback_job(job_id)
            raise WorkerQueueQuotaExceededError(detail=str(e)) from e
        except Exception as e:
            if settings.ENV.lower() == "production":
                logger.exception("Failed to enqueue job %s to worker queue in production", job_id)
                self._rollback_job(job_id)
                raise WorkerQueueEnqueueError(
                    detail=(
                        f"Failed to enqueue job {job_id} to worker queue. "
                        "Inline fallback is disabled in production. "
                        "Check that the worker queue is running and healthy."
                    ),
                ) from e
            logger.warning(
                "Failed to enqueue job %s to worker queue, falling back to inline: %s",
                job_id,
                e,
            )
            _schedule_job(job_id)

    def _rollback_job(self, job_id: str) -> None:
        """Remove a partially-created job from both in-memory and persistent stores."""
        from app.storage_interface import get_job_repository

        with self._manager.lock:
            self._manager.jobs_store.pop(job_id, None)
        try:
            repo = get_job_repository()
            repo.hard_delete(job_id)
        except (AttributeError, ImportError, RuntimeError):
            logger.warning("Failed to hard-delete job %s after enqueue failure", job_id)
