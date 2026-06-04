"""Job routes — job lifecycle endpoints for the kernel API."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from forge_kernel.api.deps import (
    get_jobs_store,
    get_recycle_bin_store,
    require_operator,
    require_viewer,
)
from forge_kernel.contracts.job import CreateJobRequest, Job
from forge_kernel.services.job_service import JobService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _get_service(
    jobs_store: dict[str, Job] = Depends(get_jobs_store),
    recycle_bin: dict[str, Job] = Depends(get_recycle_bin_store),
) -> JobService:
    return JobService(jobs_store=jobs_store, recycle_bin_store=recycle_bin)


@router.get("")
async def list_jobs(
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    service: JobService = Depends(_get_service),
    _=Depends(require_viewer),
):
    """List all jobs, optionally filtered by status."""
    jobs = service.list_all()
    if status:
        jobs = [j for j in jobs if j.status.value == status]

    return {
        "jobs": [_job_summary(j) for j in sorted(jobs, key=lambda x: x.created_at, reverse=True)],
        "total": len(jobs),
    }


@router.post("")
async def create_job(
    req: CreateJobRequest,
    service: Annotated[JobService, Depends(_get_service)],
    _=Depends(require_operator),
):
    """Create a new scraping job."""
    job = Job(
        name=req.name,
        mode=req.mode,
        intent=req.intent,
        urls=req.urls,
        topic=req.topic,
        location=req.location,
        preferred_domain=req.preferred_domain,
        source_policy=req.source_policy,
        max_per_domain=req.max_per_domain,
        origin_location=req.origin_location,
        max_distance_km=req.max_distance_km,
        schema_fields=req.schema_fields,
        filters=req.filters,
        pagination=req.pagination,
        max_pages=req.max_pages,
        deduplicate=req.deduplicate,
        deduplicate_field=req.deduplicate_field,
        min_record_score=req.min_record_score,
        selectors_map=req.selectors_map,
        search_params=req.search_params,
    )
    created = service.create(job)
    return _job_detail(created)


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    service: Annotated[JobService, Depends(_get_service)],
    _=Depends(require_viewer),
):
    """Get a specific job by ID."""
    job = service.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_detail(job)


@router.get("/{job_id}/results")
async def get_job_results(
    job_id: str,
    service: Annotated[JobService, Depends(_get_service)],
    _=Depends(require_viewer),
):
    """Get the results for a specific job."""
    job = service.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"results": job.results, "total": len(job.results)}


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    service: Annotated[JobService, Depends(_get_service)],
    _=Depends(require_operator),
):
    """Cancel a running or pending job."""
    job = service.cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_detail(job)


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    service: Annotated[JobService, Depends(_get_service)],
    _=Depends(require_operator),
):
    """Move a job to the recycle bin."""
    success = service.delete(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "id": job_id}


# ─── Recycle bin ────────────────────────────────────────────────────────


@router.get("/recycle/list")
async def list_recycle(
    service: Annotated[JobService, Depends(_get_service)],
    _=Depends(require_viewer),
):
    """List recycled jobs."""
    jobs = service.list_recycle()
    return {
        "jobs": [_job_summary(j) for j in sorted(jobs, key=lambda x: x.created_at, reverse=True)],
        "total": len(jobs),
    }


@router.post("/recycle/{job_id}/restore")
async def restore_job(
    job_id: str,
    service: Annotated[JobService, Depends(_get_service)],
    _=Depends(require_operator),
):
    """Restore a job from the recycle bin."""
    job = service.restore(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found in recycle bin")
    return _job_detail(job)


@router.delete("/recycle/{job_id}")
async def hard_delete_job(
    job_id: str,
    service: Annotated[JobService, Depends(_get_service)],
    _=Depends(require_operator),
):
    """Permanently delete a job from the recycle bin."""
    success = service.hard_delete(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "permanently_deleted", "id": job_id}


# ─── Helpers ────────────────────────────────────────────────────────────


def _job_summary(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status.value,
        "mode": job.mode.value,
        "total_records": job.total_records,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "error": job.error,
    }


def _job_detail(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status.value,
        "mode": job.mode.value,
        "intent": job.intent,
        "urls": job.urls,
        "topic": job.topic,
        "schema_fields": [sf.model_dump() for sf in job.schema_fields],
        "total_records": job.total_records,
        "filtered_records": job.filtered_records,
        "error": job.error,
        "quality_report": job.quality_report,
        "analysis": job.analysis,
        "warnings": job.warnings,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "estimated_cost_usd": job.estimated_cost_usd,
        "progress_current": job.progress_current,
        "progress_total": job.progress_total,
    }
