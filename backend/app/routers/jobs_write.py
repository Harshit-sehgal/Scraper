"""Write/mutation job routes — ``POST/DELETE`` endpoints for jobs and recycle bin.

Extracted from ``routers/jobs.py`` during the router refactoring to separate
mutation routes from read-only routes.

All routes are registered by ``register_jobs_write_routes(router, manager, ...)``
which is called from ``app.routers.jobs.create_jobs_router``.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from app.audit_logger import log_admin_action, log_job_event
from app.config import settings
from app.discovery import (
    DiscoveryDependencyError,
    discover_urls,
    infer_source_metadata,
)
from app.filters import process_results
from app.models import (
    DiscoveryRequest,
    JobCreate,
    JobStatus,
    SchemaSuggestionRequest,
)
from app.plan_enforcer import require_plan_limit
from app.routers.jobs_state import (
    JobStoreManager,
    save_job,
)
from app.scraper import ai_clean_and_align_records
from app.services.job_creation_service import (
    JobCreationError,
    JobCreationService,
)
from app.storage_interface import get_job_repository
from app.utils.job import deduplicate_results, mark_job_canceled, normalize_job_results
from app.utils.quality import build_quality_report, compute_source_breakdown, safe_score
from app.utils.rbac import (
    UserRole,
    can_access_scoped_resource,
    require_principal,
    require_role,
)
from app.utils.usage_ledger import UsageType

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def _ensure_job_write_access(job, auth_tuple, action: str) -> None:
    """Enforce tenant isolation on job-mutation routes.

    Mirrors ``jobs_read._ensure_job_access`` but lives in the write
    router so mutation routes (cancel / backfill / reclean) cannot
    mutate a job from another org/project. Env-backed admin/operator
    keys retain all-access; persistent SaaS WRITE keys are scoped to
    their own org/project (via ``can_access_scoped_resource``).
    """
    role, user_id, org_id, project_id = auth_tuple
    if can_access_scoped_resource(
        role,
        user_id,
        org_id,
        project_id,
        resource_owner_id=getattr(job, "created_by", ""),
        resource_org_id=getattr(job, "org_id", ""),
        resource_project_id=getattr(job, "project_id", ""),
    ):
        return
    from app.audit_logger import log_rbac_event

    log_rbac_event(
        actor=user_id,
        action=action,
        resource=f"job:{job.id}",
        role=role.value,
        outcome="denied",
        details={
            "owner_id": getattr(job, "created_by", ""),
            "org_id": getattr(job, "org_id", ""),
            "project_id": getattr(job, "project_id", ""),
            "policy": "scoped_resource_or_saas_org_project",
        },
    )
    raise HTTPException(status_code=404, detail="Job not found")


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

    @router.post("/api/jobs")
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
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            _ensure_job_write_access(job, auth, "cancel_job")
            if job.status in {
                JobStatus.COMPLETED,
                JobStatus.DEGRADED,
                JobStatus.EMPTY_RESULT,
                JobStatus.FAILED,
                JobStatus.CANCELED,
            }:
                return {
                    "job_id": job.id,
                    "status": job.status.value,
                    "cancel_requested": bool(job.cancel_requested),
                    "message": "Job already in terminal state",
                }

            job.cancel_requested = True
            if job.status == JobStatus.PENDING:
                mark_job_canceled(job, "Canceled before execution.")

        cancel_task_success = True
        if settings.WORKER_QUEUE:
            try:
                from app.worker_queue import get_worker_queue

                queue = get_worker_queue()
                await queue.cancel(job_id)
            except (RuntimeError, ValueError, OSError) as e:
                cancel_task_success = False
                logger.warning(
                    "Failed to cancel queued task for job %s: %s",
                    job_id,
                    e,
                )

        await save_job(job)
        return {
            "job_id": job.id,
            "status": job.status.value,
            "cancel_requested": True,
            "cancel_queued_task": cancel_task_success,
            "message": "Cancellation requested",
        }

    @router.post("/api/jobs/{job_id}/backfill-metadata")
    async def backfill_job_metadata(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Explicitly backfill source metadata for manual-mode job results."""
        job = await run_in_threadpool(manager.get_job, job_id)
        _ensure_job_write_access(job, auth, "backfill_metadata")

        results_list = list(job.results)
        if job.results_on_disk:
            from app.utils.job_results_store import load_job_results_from_disk

            results_list = await run_in_threadpool(load_job_results_from_disk, job.id, job.results_file_path)

        updated = False
        for row in results_list:
            source_url = str(row.get("source_url") or "")
            source_type = str(row.get("source_type") or "unknown").strip().lower()
            if source_type == "unknown" and source_url:
                inferred = infer_source_metadata(url=source_url)
                row["source_type"] = str(inferred.get("source_type") or "unknown")
                row["source_trust_score"] = round(safe_score(inferred.get("source_trust_score") or 0.4), 3)
                updated = True

        if updated:
            job.results = results_list
            if job.results_on_disk:
                from app.utils.job_results_store import save_job_results_to_disk

                await run_in_threadpool(save_job_results_to_disk, job.id, results_list)
            await save_job(job)

        return {"message": "Metadata backfilled successfully", "updated": updated}

    @router.post("/api/jobs/{job_id}/reclean")
    async def reclean_job(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Re-run AI cleaning and schema alignment on existing job results without re-scraping URLs."""
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            _ensure_job_write_access(job, auth, "reclean_job")
            if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
                raise HTTPException(
                    status_code=409,
                    detail="Job is still running; wait for completion before re-cleaning",
                )

        results_list = list(job.results)
        loaded_from_disk = False
        if job.results_on_disk:
            from app.utils.job_results_store import load_job_results_from_disk

            results_list = await run_in_threadpool(load_job_results_from_disk, job.id, job.results_file_path)
            loaded_from_disk = True

        if not results_list:
            raise HTTPException(status_code=400, detail="No results to re-clean")
        if not job.schema_fields:
            raise HTTPException(status_code=400, detail="Job has no schema fields for re-cleaning")

        started = datetime.datetime.now(datetime.UTC).isoformat()
        before_records = len(results_list)
        working_rows = [dict(r) for r in results_list]
        reclean_warnings: list[str] = []

        previous_status = job.status
        job.status = JobStatus.RUNNING

        ai_report = {
            "applied": False,
            "input_records": len(working_rows),
            "output_records": len(working_rows),
            "total_chunks": 0,
            "ai_chunks": 0,
            "fallback_chunks": 0,
            "model_fallback_mode": False,
            "noise_rows_removed": 0,
            "capped_records": 0,
            "quality_filtered_after_ai": 0,
        }

        try:
            try:
                cleaned_rows, ai_report = await asyncio.wait_for(
                    ai_clean_and_align_records(
                        working_rows,
                        job.schema_fields,
                        min_record_score=job.min_record_score,
                    ),
                    timeout=settings.AI_STRUCTURING_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                cleaned_rows = working_rows
                timeout_s = settings.AI_STRUCTURING_TIMEOUT_SECONDS
                reclean_warnings.append(
                    f"AI re-clean timed out after {timeout_s}s; used deterministic post-processing.",
                )
            except Exception:
                cleaned_rows = working_rows
                reclean_warnings.append("AI re-clean failed; used deterministic post-processing.")
                logger.exception("Job %s: Re-clean failed", job_id)

            filtered_results, total, filtered_count, type_integrity_report = await process_results(
                cleaned_rows,
                job.schema_fields,
                job.filters,
            )

            if job.deduplicate and filtered_results:
                filtered_results = deduplicate_results(
                    records=filtered_results,
                    schema_fields=job.schema_fields,
                    deduplicate_field=job.deduplicate_field,
                )
                filtered_count = len(filtered_results)

            for row in filtered_results:
                source_url = str(row.get("source_url") or "")
                source_type = str(row.get("source_type") or "unknown").strip().lower()
                if source_type == "unknown" and source_url:
                    inferred = infer_source_metadata(url=source_url)
                    row["source_type"] = str(inferred.get("source_type") or "unknown")
                    row["source_trust_score"] = round(safe_score(inferred.get("source_trust_score") or 0.4), 3)

            job.results = normalize_job_results(filtered_results, job.schema_fields)
            job.total_records = total
            job.filtered_records = filtered_count
            job.completed_at = datetime.datetime.now(datetime.UTC).isoformat()
            job.status = JobStatus.COMPLETED

            scraped_at = datetime.datetime.now(datetime.UTC).isoformat()
            for row in job.results:
                row["scraped_at"] = scraped_at

            if len(job.results) > settings.JOB_RESULTS_DISK_OFFLOAD_THRESHOLD:
                from app.utils.job_results_store import save_job_results_to_disk

                file_path = await run_in_threadpool(save_job_results_to_disk, job.id, job.results)
                job.results_on_disk = True
                job.results_file_path = file_path
                job.results = []
            elif loaded_from_disk:
                from app.utils.job_results_store import delete_job_results_from_disk

                await run_in_threadpool(delete_job_results_from_disk, job.id, job.results_file_path)
                job.results_on_disk = False
                job.results_file_path = None

            prev_quality = dict(job.quality_report or {})
            existing_warnings = list(prev_quality.get("warnings") or [])
            radius_report = prev_quality.get("radius")
            if not isinstance(radius_report, dict):
                radius_report = {
                    "applied": False,
                    "reason": "not_configured",
                    "origin": job.origin_location,
                    "max_distance_km": job.max_distance_km,
                }

            ai_source_prediction = prev_quality.get("ai_source_prediction")
            if not isinstance(ai_source_prediction, dict):
                ai_source_prediction = {
                    "sources_attempted": 0,
                    "sources_with_ai_structuring": 0,
                    "records_processed": 0,
                    "records_ai_structured": 0,
                }

            source_breakdown = compute_source_breakdown(filtered_results)
            quality = build_quality_report(
                raw_results=cleaned_rows,
                post_filter_count=len(filtered_results),
                post_radius_count=len(filtered_results),
                radius_report=radius_report,
                final_results=filtered_results,
                min_record_score=job.min_record_score,
                type_integrity_report=type_integrity_report,
                source_breakdown=source_breakdown,
                ai_source_prediction=ai_source_prediction,
                ai_structuring_report=ai_report,
                warnings=[*existing_warnings, *reclean_warnings],
            )

            quality["reclean"] = {
                "applied": True,
                "started_at": started,
                "completed_at": job.completed_at,
                "before_records": before_records,
                "after_records": filtered_count,
                "ai_structuring": ai_report,
                "warnings": reclean_warnings,
            }
            job.quality_report = quality
            await save_job(job)
        except (RuntimeError, OSError, ValueError) as e:
            logger.exception(
                "Job %s: Reclean failed irrecoverably, restoring previous status %s",
                job_id,
                previous_status.value if hasattr(previous_status, "value") else previous_status,
            )
            job.status = previous_status
            reclean_warnings.append(f"Reclean failed: {e}")
            try:
                await save_job(job)
            except (RuntimeError, OSError, ValueError):
                logger.exception(
                    "Job %s: Failed to persist job state after reclean rollback",
                    job_id,
                )
            raise HTTPException(status_code=500, detail="Reclean failed due to an internal error.") from e

        return {
            "job_id": job.id,
            "status": job.status.value,
            "before_records": before_records,
            "after_records": filtered_count,
            "warnings": reclean_warnings,
        }

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
