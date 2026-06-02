"""
System routes — status, metrics, and diagnostics for the kernel API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from forge_kernel.api.deps import get_jobs_store, get_recycle_bin_store, require_viewer
from forge_kernel.contracts.job import Job, JobStatus
from forge_kernel.services.job_service import JobService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/system", tags=["system"])


def _get_service(
    jobs_store: dict[str, Job] = Depends(get_jobs_store),
    recycle_bin: dict[str, Job] = Depends(get_recycle_bin_store),
) -> JobService:
    return JobService(jobs_store=jobs_store, recycle_bin_store=recycle_bin)


@router.get("/status")
async def system_status(
    service: JobService = Depends(_get_service),
    _=Depends(require_viewer),
):
    """Detailed system status with job counts and runtime limits."""
    jobs = service.list_all()
    counts = {s.value: 0 for s in JobStatus}
    for j in jobs:
        counts[j.status.value] = counts.get(j.status.value, 0) + 1

    active = (
        counts.get(JobStatus.PENDING.value, 0)
        + counts.get(JobStatus.RUNNING.value, 0)
        + counts.get(JobStatus.DISCOVERING.value, 0)
    )

    return {
        "status": "online",
        "backend": "kernel",
        "jobs": {
            "total": len(jobs),
            "active": active,
            "completed": counts.get(JobStatus.COMPLETED.value, 0),
            "failed": counts.get(JobStatus.FAILED.value, 0),
            "canceled": counts.get(JobStatus.CANCELED.value, 0),
            "degraded": counts.get(JobStatus.DEGRADED.value, 0),
            "empty_result": counts.get(JobStatus.EMPTY_RESULT.value, 0),
        },
    }
