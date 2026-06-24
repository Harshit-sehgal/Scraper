"""Job mutation services — encapsulate business logic for cancel, backfill, and reclean operations.

Extracted from ``app.routers.jobs_write.register_jobs_write_routes`` to
separate HTTP concerns (request parsing, response formatting) from domain
logic (access control, result processing, quality reporting, disk offload).

Usage::

    service = JobCancellerService(manager)
    result = await service.cancel_job(job_id, auth)
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from app.config import settings
from app.models import JobStatus
from app.routers.jobs_state import JobStoreManager, save_job
from app.utils.job import deduplicate_results, mark_job_canceled, normalize_job_results
from app.utils.quality import build_quality_report, compute_source_breakdown, safe_score
from app.utils.rbac import UserRole, can_access_scoped_resource

logger = logging.getLogger(__name__)


def _ensure_job_write_access(job, role: UserRole, user_id: str, org_id: str, project_id: str, action: str) -> None:
    """Enforce tenant isolation on job-mutation operations.

    Mirrors the route-level guard but usable from service classes.
    """
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
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="Job not found")


# ═════════════════════════════════════════════════════════════════════════════
# JobCancellerService
# ═════════════════════════════════════════════════════════════════════════════


class JobCancellerService:
    """Encapsulates the business logic for cancelling a running or pending job."""

    def __init__(self, manager: JobStoreManager) -> None:
        self._manager = manager

    async def cancel_job(
        self,
        job_id: str,
        role: UserRole,
        user_id: str,
        org_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        """Cancel a job: set cancel_requested flag, optionally cancel in worker queue.

        Returns a response dict with job_id, status, cancel_requested, and message.
        """
        from fastapi import HTTPException

        with self._manager.lock:
            if job_id not in self._manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = self._manager.jobs_store[job_id]
            _ensure_job_write_access(job, role, user_id, org_id, project_id, "cancel_job")

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

        # Worker queue cancellation (outside the lock to avoid blocking)
        cancel_task_success = True
        if settings.WORKER_QUEUE:
            try:
                from app.worker_queue import get_worker_queue

                queue = get_worker_queue()
                await queue.cancel(job_id)
            except (RuntimeError, ValueError, OSError) as e:
                cancel_task_success = False
                logger.warning("Failed to cancel queued task for job %s: %s", job_id, e)

        await save_job(job)
        return {
            "job_id": job.id,
            "status": job.status.value,
            "cancel_requested": True,
            "cancel_queued_task": cancel_task_success,
            "message": "Cancellation requested",
        }


# ═════════════════════════════════════════════════════════════════════════════
# JobBackfillService
# ═════════════════════════════════════════════════════════════════════════════


class JobBackfillService:
    """Encapsulates the business logic for backfilling source metadata on job results."""

    def __init__(self, manager: JobStoreManager) -> None:
        self._manager = manager

    async def backfill_metadata(
        self,
        job_id: str,
        role: UserRole,
        user_id: str,
        org_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        """Backfill source metadata for manual-mode job results.

        Iterates over results and infers ``source_type`` and
        ``source_trust_score`` for rows where ``source_type`` is
        ``"unknown"``.
        """
        from fastapi.concurrency import run_in_threadpool as _run_sync

        from app.discovery import infer_source_metadata
        from app.utils.job_results_store import load_job_results_from_disk, save_job_results_to_disk

        job = await _run_sync(self._manager.get_job, job_id)
        _ensure_job_write_access(job, role, user_id, org_id, project_id, "backfill_metadata")

        results_list = list(job.results)
        if job.results_on_disk:
            results_list = await _run_sync(load_job_results_from_disk, job.id, job.results_file_path)

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
                await _run_sync(save_job_results_to_disk, job.id, results_list)
            await save_job(job)

        return {"message": "Metadata backfilled successfully", "updated": updated}


# ═════════════════════════════════════════════════════════════════════════════
# JobRecleanerService
# ═════════════════════════════════════════════════════════════════════════════


class JobRecleanerService:
    """Encapsulates the business logic for re-running AI cleaning on job results.

    Handles AI structuring, result filtering, deduplication, source-metadata
    inference, quality-report building, and disk offload — all without
    re-scraping URLs.
    """

    def __init__(self, manager: JobStoreManager) -> None:
        self._manager = manager

    async def reclean_job(
        self,
        job_id: str,
        role: UserRole,
        user_id: str,
        org_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        """Re-run AI cleaning and schema alignment on existing job results.

        Returns a response dict with job_id, status, before/after record
        counts, and warnings.
        """
        import asyncio

        from fastapi import HTTPException
        from fastapi.concurrency import run_in_threadpool as _run_sync

        from app.discovery import infer_source_metadata
        from app.filters import process_results
        from app.scraper import ai_clean_and_align_records
        from app.utils.job_results_store import (
            delete_job_results_from_disk,
            load_job_results_from_disk,
            save_job_results_to_disk,
        )

        with self._manager.lock:
            if job_id not in self._manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = self._manager.jobs_store[job_id]
            _ensure_job_write_access(job, role, user_id, org_id, project_id, "reclean_job")
            if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
                raise HTTPException(
                    status_code=409,
                    detail="Job is still running; wait for completion before re-cleaning",
                )

        results_list = list(job.results)
        loaded_from_disk = False
        if job.results_on_disk:
            results_list = await _run_sync(load_job_results_from_disk, job.id, job.results_file_path)
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
                file_path = await _run_sync(save_job_results_to_disk, job.id, job.results)
                job.results_on_disk = True
                job.results_file_path = file_path
                job.results = []
            elif loaded_from_disk:
                await _run_sync(delete_job_results_from_disk, job.id, job.results_file_path)
                job.results_on_disk = False
                job.results_file_path = None

            # Build quality report
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
                logger.exception("Job %s: Failed to persist job state after reclean rollback", job_id)
            raise HTTPException(status_code=500, detail="Reclean failed due to an internal error.") from e

        return {
            "job_id": job.id,
            "status": job.status.value,
            "before_records": before_records,
            "after_records": filtered_count,
            "warnings": reclean_warnings,
        }
