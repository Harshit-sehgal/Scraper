"""Scheduled Monitoring Router — manage recurring jobs and change detection.

Provides endpoints to create, list, update, and delete scheduled scraping
jobs that run automatically on a defined frequency. Also includes basic
change-detection heuristics to compare snapshots between runs.
"""

from __future__ import annotations

import datetime
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models import ScheduledJob, ScheduledJobFrequency
from app.utils.rbac import UserRole, can_access_scoped_resource, require_principal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scheduled", tags=["scheduled-monitoring"])

# In-memory scheduled job store (mirrors _workflows pattern)
_scheduled_jobs: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _can_access_scheduled_job(item: dict[str, Any], auth: tuple[UserRole, str, str, str]) -> bool:
    role, user_id, org_id, project_id = auth
    return can_access_scoped_resource(
        role,
        user_id,
        org_id,
        project_id,
        resource_owner_id=str(item.get("user_id") or ""),
        resource_org_id=str(item.get("org_id") or ""),
        resource_project_id=str(item.get("project_id") or ""),
    )


def _get_visible_scheduled_job(job_id: str, auth: tuple[UserRole, str, str, str]) -> dict[str, Any]:
    item = _scheduled_jobs.get(job_id)
    if item is None or not _can_access_scheduled_job(item, auth):
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    return item


@router.post("", status_code=201)
async def create_scheduled_job(
    name: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    frequency: ScheduledJobFrequency = ScheduledJobFrequency.DAILY,
    job_name: str = "",
):
    """Create a new scheduled (recurring) scraping job."""
    _role, user_id, org_id, project_id = auth
    job = ScheduledJob(
        name=name.strip(),
        user_id=user_id,
        org_id=org_id,
        project_id=project_id,
        frequency=frequency,
        job_name=job_name.strip() or f"Scheduled: {name}",
        next_run_at=_now_iso(),
    )
    _scheduled_jobs[job.id] = job.model_dump()
    logger.info("Scheduled job created: %s (%s)", job.name, job.id)
    return job.model_dump()


@router.get("", status_code=200)
async def list_scheduled_jobs(
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    enabled_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """List scheduled jobs with optional filtering."""
    items = [item for item in _scheduled_jobs.values() if _can_access_scheduled_job(item, auth)]
    if enabled_only:
        items = [j for j in items if j.get("enabled")]
    total = len(items)
    return {"total": total, "limit": limit, "offset": offset, "items": items[offset : offset + limit]}


@router.get("/{job_id}", status_code=200)
async def get_scheduled_job(
    job_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """Get a single scheduled job by ID."""
    return _get_visible_scheduled_job(job_id, auth)


@router.put("/{job_id}", status_code=200)
async def update_scheduled_job(
    job_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    name: str | None = None,
    frequency: ScheduledJobFrequency | None = None,
    enabled: bool | None = None,
):
    """Update an existing scheduled job."""
    existing = _get_visible_scheduled_job(job_id, auth)
    if name is not None:
        existing["name"] = name.strip()
    if frequency is not None:
        existing["frequency"] = frequency.value
    if enabled is not None:
        existing["enabled"] = enabled
    existing["updated_at"] = _now_iso()
    return existing


@router.delete("/{job_id}", status_code=204)
async def delete_scheduled_job(
    job_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """Delete a scheduled job permanently."""
    _get_visible_scheduled_job(job_id, auth)
    del _scheduled_jobs[job_id]
    logger.info("Scheduled job deleted: %s", job_id)


# ─── Change Detection ─────────────────────────────────────────────────────


@router.get("/{job_id}/changes", status_code=200)
async def detect_changes(
    job_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """Compare the latest two snapshots for a scheduled job and report changes.

    Placeholder — full diff engine would compare extracted records,
    schema coverage, and page structure.
    """
    _get_visible_scheduled_job(job_id, auth)

    return {
        "job_id": job_id,
        "changes_detected": False,
        "message": "Change detection is a placeholder — full diff engine to be implemented in a future milestone.",
        "last_snapshot": None,
        "previous_snapshot": None,
        "diff_stats": {},
    }
