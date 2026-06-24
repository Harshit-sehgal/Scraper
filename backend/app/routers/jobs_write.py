"""Write/mutation job routes — ``POST/DELETE`` endpoints for jobs and recycle bin.

Extracted from ``routers/jobs.py`` during the router refactoring to separate
mutation routes from read-only routes.

All routes are registered by ``register_jobs_write_routes(router, manager, ...)``
which is called from ``app.routers.jobs.create_jobs_router``.

Route handlers are kept thin — business logic lives in dedicated services
under ``app.services.job_mutation_service``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from app.audit_logger import log_admin_action, log_job_event
from app.config import settings

# Satisfy pyflakes — `settings` is patched in tests via ``jobs_write.settings``
# and is also used by service modules that import it through this namespace.
_SETTINGS_IMPORT_GUARD = settings

from app.discovery import (
    DiscoveryDependencyError,
    discover_urls,
)
from app.models import (
    DiscoveryRequest,
    JobCreate,
    JobStatus,
    SchemaSuggestionRequest,
)
from app.plan_enforcer import require_plan_limit
from app.routers.jobs_state import (
    JobStoreManager,
)
from app.services.job_creation_service import (
    JobCreationError,
    JobCreationService,
)
from app.services.job_mutation_service import (
    JobBackfillService,
    JobCancellerService,
    JobRecleanerService,
)
from app.storage_interface import get_job_repository
from app.utils.rbac import (
    UserRole,
    require_principal,
    require_role,
)
from app.utils.usage_ledger import UsageType

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def _auth_tuple(auth) -> tuple:
    """Normalise the ``require_principal`` dependency result.

    Returns ``(role, user_id, org_id, project_id)``.
    """
    if len(auth) == 4:
        return auth
    role, user_id = auth
    return role, user_id, "", ""


def register_jobs_write_routes(
    router: APIRouter,
    manager: JobStoreManager,
    _schedule_task_fn: Callable | None = None,
    _run_job_coro_fn: Callable | None = None,
) -> None:
    """Register all write/mutation job endpoints on the given router.

    Args:
        router: The APIRouter to register routes on.
        manager: Thread-safe store manager for jobs and recycle bin.
        _schedule_task_fn: Deprecated — kept for backward compatibility.
            Route handlers now use ``app.runtime_deps.schedule_task_fn``.
        _run_job_coro_fn: Deprecated — kept for backward compatibility.
            Route handlers now use ``app.runtime_deps.run_job_coro_fn``.

    """

    @router.post("/api/discover")
    async def discover(
        req: DiscoveryRequest,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        """Auto-discover best URLs to scrape for a topic."""
        try:
            results = await discover_urls(
                query=req.topic,
                domain=req.domain,
                num_results=req.num_results,
                location=req.location,
                data_fields=req.schema_field_names,
                origin_location=req.origin_location,
                max_distance_km=req.max_distance_km,
                source_policy=req.source_policy,
                max_per_domain=req.max_per_domain,
            )
        except DiscoveryDependencyError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        from app.url_safety import validate_public_http_url

        safe_results = []
        for r in results:
            url = r.get("url")
            if url:
                try:
                    validate_public_http_url(url)
                    safe_results.append(r)
                except ValueError:
                    pass
        return {"urls": safe_results}

    @router.post("/api/schema/suggest")
    async def suggest_schema(
        req: SchemaSuggestionRequest,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        """Infer topic + schema fields from plain-language user intent."""
        from app.insight_engine import (
            suggest_schema_from_intent,  # research-shell, lazy
        )

        return await suggest_schema_from_intent(req.intent, max_fields=req.max_fields)

    @router.post("/api/jobs", status_code=201)
    async def create_job(
        job_data: JobCreate,
        request: Request,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
        _plan_check: Annotated[dict[str, Any], Depends(require_plan_limit(UsageType.JOB_CREATED, quantity=1))],
    ):
        """Create a new scraping job.

        Delegates business logic to ``JobCreationService``. This route
        handler is a thin HTTP adapter that converts domain results
        and exceptions to FastAPI responses.
        """
        service = JobCreationService(manager)
        try:
            result = await service.create_job(job_data, request)
            return {
                "id": result.job_id,
                "job_id": result.job_id,
                "status": result.status,
                "idempotent_replay": result.idempotent_replay,
            }
        except JobCreationError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    @router.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Cancel a running or pending job.

        Delegates business logic to ``JobCancellerService``.
        """
        role, user_id, org_id, project_id = _auth_tuple(auth)
        service = JobCancellerService(manager)
        return await service.cancel_job(job_id, role, user_id, org_id, project_id)

    @router.post("/api/jobs/{job_id}/backfill-metadata")
    async def backfill_job_metadata(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Explicitly backfill source metadata for manual-mode job results.

        Delegates business logic to ``JobBackfillService``.
        """
        role, user_id, org_id, project_id = _auth_tuple(auth)
        service = JobBackfillService(manager)
        return await service.backfill_metadata(job_id, role, user_id, org_id, project_id)

    @router.post("/api/jobs/{job_id}/reclean")
    async def reclean_job(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Re-run AI cleaning and schema alignment on existing job results without re-scraping URLs.

        Delegates business logic to ``JobRecleanerService``.
        """
        role, user_id, org_id, project_id = _auth_tuple(auth)
        service = JobRecleanerService(manager)
        return await service.reclean_job(job_id, role, user_id, org_id, project_id)

    @router.delete("/api/jobs/{job_id}")
    async def delete_job(
        job_id: str,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    ):
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
                raise HTTPException(
                    status_code=409,
                    detail="Cannot delete/recycle an active job. Cancel the job first.",
                )
        # Consistency contract: the in-memory pop is fast (microseconds) and
        # the repo.move_to_recycle_bin call is the slow part (a network round
        # trip + transaction). We deliberately release the lock between
        # them so concurrent reads / writes to other jobs are not blocked
        # while we wait for the DB. The trade-off is that, if the DB move
        # fails after the in-memory pop, the in-memory store is consistent
        # (job is gone) but the persistent store is not (job is still
        # active). Callers therefore MUST treat the in-memory store as the
        # source of truth; the persistent store is only a recovery record.
        # If you need strict cross-store consistency, wrap both steps in
        # a single ``with manager.lock:`` and accept the throughput cost.
        repo = get_job_repository()
        try:
            await run_in_threadpool(repo.move_to_recycle_bin, job_id)
        except (RuntimeError, OSError, ValueError):
            logger.exception("Failed to move job %s to recycle bin in repository", job_id)
            raise HTTPException(
                status_code=500,
                detail="Failed to move job to recycle bin. The job remains in the active store.",
            ) from None
        with manager.lock:
            if job_id in manager.jobs_store:
                manager.recycle_bin_store[job_id] = manager.jobs_store.pop(job_id)
        log_job_event(actor="admin", action="job_recycled", job_id=job_id)
        return {"message": "Job moved to recycle bin"}

    @router.delete("/api/jobs/cleanup/terminal")
    async def clear_terminal_jobs(
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],  # noqa: B008, RUF100
        keep_recent: Annotated[int, Query(ge=0, le=5000)] = 5,
    ):
        terminal_statuses = {
            JobStatus.COMPLETED,
            JobStatus.DEGRADED,
            JobStatus.EMPTY_RESULT,
            JobStatus.FAILED,
            JobStatus.CANCELED,
        }
        with manager.lock:
            terminal = [(jid, job) for jid, job in manager.jobs_store.items() if job.status in terminal_statuses]

        if not terminal:
            return {
                "message": "No terminal jobs to clear",
                "cleared": 0,
                "kept_recent": keep_recent,
                "remaining": len(manager.jobs_store),
            }

        terminal.sort(key=lambda item: item[1].created_at, reverse=True)
        keep_ids = {jid for jid, _ in terminal[:keep_recent]}

        repo = get_job_repository()
        cleared_ids: list[str] = []
        failed_ids: list[str] = []

        for jid, _ in terminal:
            if jid in keep_ids:
                continue
            try:
                await run_in_threadpool(repo.move_to_recycle_bin, jid)
                cleared_ids.append(jid)
            except (RuntimeError, OSError, ValueError):
                logger.exception("Failed to move terminal job %s to recycle bin during cleanup", jid)
                failed_ids.append(jid)

        with manager.lock:
            for jid in cleared_ids:
                if jid in manager.jobs_store:
                    manager.recycle_bin_store[jid] = manager.jobs_store.pop(jid)
            remaining = len(manager.jobs_store)

        result: dict[str, Any] = {
            "message": f"Cleared {len(cleared_ids)} terminal jobs",
            "cleared": len(cleared_ids),
            "kept_recent": keep_recent,
            "remaining": remaining,
        }
        if failed_ids:
            result["failed"] = failed_ids
            result["message"] += f" ({len(failed_ids)} failed)"
        log_admin_action(
            actor="admin",
            action="bulk_cleanup_terminal",
            resource="jobs",
            details={"cleared": len(cleared_ids), "kept_recent": keep_recent, "remaining": remaining},
        )
        return result

    @router.post("/api/recycle_bin/{job_id}/restore")
    async def restore_job(
        job_id: str,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    ):
        with manager.lock:
            if job_id not in manager.recycle_bin_store:
                raise HTTPException(status_code=404, detail="Job not in recycle bin")
        # Lock is released before the async DB call. This avoids holding a
        # sync threading.Lock across an await, which would block the event
        # loop's thread pool and risk deadlock under concurrent requests.
        # The trade-off (previously documented in delete_job / clear_terminal):
        # a concurrent hard_delete between the DB restore and the in-memory
        # move could orphan a DB restored record. Hard-delete callers are
        # designed to tolerate this (they retry or accept eventual consistency).
        repo = get_job_repository()
        try:
            await run_in_threadpool(repo.restore_from_recycle_bin, job_id)
        except (RuntimeError, OSError, ValueError) as e:
            logger.exception("Failed to restore job %s from recycle bin in repository", job_id)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to restore job: {e}",
            ) from e
        with manager.lock:
            if job_id in manager.recycle_bin_store:
                manager.jobs_store[job_id] = manager.recycle_bin_store.pop(job_id)
        return {"message": "Job restored"}

    @router.delete("/api/recycle_bin/{job_id}")
    async def hard_delete_job(
        job_id: str,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    ):
        with manager.lock:
            if job_id not in manager.recycle_bin_store:
                raise HTTPException(status_code=404, detail="Job not in recycle bin")
            job = manager.recycle_bin_store.get(job_id)
            file_path = job.results_file_path if job else None
        # Do DB hard_delete FIRST so that a file-deletion failure does not
        # orphan a DB record. If the DB call fails, the file is never touched.
        repo = get_job_repository()
        try:
            await run_in_threadpool(repo.hard_delete, job_id)
        except (RuntimeError, OSError, ValueError) as e:
            logger.exception("Failed to hard-delete job %s from repository", job_id)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to permanently delete job: {e}",
            ) from e
        with manager.lock:
            manager.recycle_bin_store.pop(job_id, None)
        if file_path:
            from app.utils.job_results_store import delete_job_results_from_disk

            await run_in_threadpool(delete_job_results_from_disk, job_id, file_path)
        log_job_event(actor="admin", action="job_hard_deleted", job_id=job_id)
        return {"message": "Job permanently deleted"}

    @router.delete("/api/recycle_bin")
    async def clear_recycle_bin(
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    ):
        from app.utils.job_results_store import delete_job_results_from_disk

        with manager.lock:
            snapshot = list(manager.recycle_bin_store.items())
        # Do DB hard-deletes FIRST so that a file-deletion failure does not
        # orphan DB records. Handle per-job errors so one failure does not
        # abort the remaining jobs.
        repo = get_job_repository()
        deleted_ids: list[str] = []
        failed_ids: list[str] = []
        for jid, _ in snapshot:
            try:
                await run_in_threadpool(repo.hard_delete, jid)
                deleted_ids.append(jid)
            except (RuntimeError, OSError, ValueError):
                logger.exception("Failed to hard-delete job %s during recycle bin clear", jid)
                failed_ids.append(jid)
        for jid, job in snapshot:
            if jid not in deleted_ids:
                continue
            file_path = job.results_file_path if job else None
            if file_path:
                await run_in_threadpool(delete_job_results_from_disk, jid, file_path)
        with manager.lock:
            for jid in deleted_ids:
                manager.recycle_bin_store.pop(jid, None)
        result: dict[str, Any] = {"message": f"Recycle bin cleared ({len(deleted_ids)} items)", "cleared": len(deleted_ids)}
        if failed_ids:
            result["failed"] = failed_ids
            result["message"] += f" ({len(failed_ids)} failed)"
        log_admin_action(
            actor="admin",
            action="clear_recycle_bin",
            resource="recycle_bin",
            details={"cleared": len(deleted_ids), "failed": len(failed_ids)},
        )
        return result
