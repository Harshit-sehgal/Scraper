"""Export routes — CSV, JSON, and Excel export endpoints for the kernel."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from forge_kernel.api.deps import get_jobs_store, get_recycle_bin_store, require_viewer
from forge_kernel.services.export_service import ExportService
from forge_kernel.services.job_service import JobService

if TYPE_CHECKING:
    from forge_kernel.contracts.job import Job

logger = logging.getLogger(__name__)
router = APIRouter(tags=["exports"])

_export_service = ExportService()


def _get_service(
    jobs_store: dict[str, Job] = Depends(get_jobs_store),
    recycle_bin: dict[str, Job] = Depends(get_recycle_bin_store),
) -> JobService:
    return JobService(jobs_store=jobs_store, recycle_bin_store=recycle_bin)


@router.get("/api/jobs/{job_id}/export/csv")
async def export_csv(
    job_id: str,
    service: Annotated[JobService, Depends(_get_service)],
    _=Depends(require_viewer),
):
    """Export job results as CSV."""
    job = service.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    records = job.results
    field_names = [sf.name for sf in job.schema_fields]
    csv_content = _export_service.to_csv(records, field_names)

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={job_id}.csv"},
    )


@router.get("/api/jobs/{job_id}/export/json")
async def export_json(
    job_id: str,
    service: Annotated[JobService, Depends(_get_service)],
    _=Depends(require_viewer),
):
    """Export job results as JSON."""
    job = service.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    json_content = _export_service.to_json(job.results)

    return Response(
        content=json_content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={job_id}.json"},
    )


@router.get("/api/jobs/{job_id}/export/xlsx")
async def export_xlsx(
    job_id: str,
    service: Annotated[JobService, Depends(_get_service)],
    _=Depends(require_viewer),
):
    """Export job results as Excel (XLSX)."""
    job = service.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    field_names = [sf.name for sf in job.schema_fields]
    xlsx_bytes = _export_service.to_xlsx(job.results, field_names)

    if xlsx_bytes is None:
        raise HTTPException(
            status_code=501,
            detail="XLSX export requires openpyxl: pip install openpyxl",
        )

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={job_id}.xlsx"},
    )
