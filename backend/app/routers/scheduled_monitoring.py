"""Scheduled Monitoring Router — manage recurring jobs and change detection.

Provides endpoints to create, list, update, and delete scheduled scraping
jobs that run automatically on a defined frequency. Also includes basic
change-detection heuristics to compare snapshots between runs.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models import ScheduledJob, ScheduledJobFrequency
from app.utils.aup import require_aup_accepted
from app.utils.json_file_store import JSONFileStore
from app.utils.rbac import UserRole, can_access_scoped_resource, require_principal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scheduled", tags=["scheduled-monitoring"])

# Best-effort mapping from ScheduledJobFrequency to expected wall-clock
# gap. Used by the change-detection endpoint to flag a job whose
# scheduler cadence has drifted.
_EXPECTED_GAP_SECONDS: dict[str, int] = {
    "hourly": 60 * 60,
    "daily": 60 * 60 * 24,
    "weekly": 60 * 60 * 24 * 7,
    "monthly": 60 * 60 * 24 * 30,
}

# File-backed scheduled-job store shared across uvicorn/gunicorn workers.
# Reads always re-read disk; writes use flock-serialised atomic rename.
_scheduled_jobs = JSONFileStore(
    Path(__file__).resolve().parents[2] / "data" / "scheduled_jobs.json",
)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _write_back(record: dict[str, Any]) -> None:
    """Persist a (possibly-mutated) local copy of a scheduled-job record.

    The store returns deep copies on every read so direct mutation of the
    dict the caller holds does NOT persist; this helper is what makes
    mutations on those copies visible to subsequent reads and to sibling
    workers.
    """
    job_id = str(record.get("id") or "")
    if not job_id:
        msg = "scheduled-job dict missing 'id' before write-back"
        raise RuntimeError(msg)
    _scheduled_jobs.upsert(job_id, record)


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
    _aup_check: Annotated[dict[str, Any], Depends(require_aup_accepted)],
    frequency: ScheduledJobFrequency = ScheduledJobFrequency.DAILY,
    job_name: str = "",
):
    """Create a new scheduled (recurring) scraping job.

    Requires AUP acceptance.
    """
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
    _scheduled_jobs.upsert(job.id, job.model_dump())
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
    _write_back(existing)
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
    if _scheduled_jobs.delete(job_id):
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
    """Report the most recent change signals observed for a scheduled job.

    Real, observable signal: the job record carries a ``last_run_status``,
    ``last_run_records_count``, ``last_run_at`` and a rolling
    ``recent_run_summaries`` list (capped at 10). We compare the two
    most recent summaries and report a small set of derived facts:

    * ``record_count_delta`` — difference in extracted records between
      the most recent and previous run (positive means growth).
    * ``status_changed`` — whether the run-status enum flipped.
    * ``frequency_met`` — whether the wall-clock gap between the two
      runs is at least one ``frequency`` interval (best-effort).
    * ``last_records_count`` / ``previous_records_count`` — convenience
      fields for the UI.

    This is intentionally a thin, deterministic diff over what the
    scheduler already records. A full record-level diff engine is a
    separate milestone (see ``docs/ROADMAP.md``).
    """
    job = _get_visible_scheduled_job(job_id, auth)

    summaries = list(job.get("recent_run_summaries") or [])
    # Newest last; we want the two most recent. Sort defensively.
    summaries.sort(key=lambda s: str(s.get("ran_at") or ""))
    last = summaries[-1] if len(summaries) >= 1 else None
    previous = summaries[-2] if len(summaries) >= 2 else None

    last_count = int((last or {}).get("records_count") or 0)
    prev_count = int((previous or {}).get("records_count") or 0)
    last_status = str((last or {}).get("status") or "")
    prev_status = str((previous or {}).get("status") or "")

    record_count_delta = last_count - prev_count
    status_changed = bool(last_status and prev_status and last_status != prev_status)

    frequency_met: bool | None = None
    if last and previous:
        try:
            last_t = datetime.datetime.fromisoformat(str(last.get("ran_at") or ""))
            prev_t = datetime.datetime.fromisoformat(str(previous.get("ran_at") or ""))
            gap_seconds = (last_t - prev_t).total_seconds()
            expected = _EXPECTED_GAP_SECONDS.get(str(job.get("frequency") or "").lower())
            if expected is not None:
                # Within ±20% of the expected interval counts as met.
                frequency_met = abs(gap_seconds - expected) <= expected * 0.2
        except (TypeError, ValueError):
            frequency_met = None

    changes_detected = bool(record_count_delta != 0 or status_changed)

    return {
        "job_id": job_id,
        "job_name": str(job.get("name") or ""),
        "target_url": str(job.get("target_url") or job.get("url") or ""),
        "frequency": str(job.get("frequency") or ""),
        "changes_detected": changes_detected,
        "last_run_at": str((last or {}).get("ran_at") or job.get("last_run_at") or ""),
        "last_status": last_status or str(job.get("last_run_status") or ""),
        "previous_status": prev_status,
        "last_records_count": last_count,
        "previous_records_count": prev_count,
        "record_count_delta": record_count_delta,
        "status_changed": status_changed,
        "frequency_met": frequency_met,
        "summary_count": len(summaries),
        "message": (
            "No previous run to compare against — first run completed."
            if previous is None
            else "Compared the most recent two runs."
        ),
    }
