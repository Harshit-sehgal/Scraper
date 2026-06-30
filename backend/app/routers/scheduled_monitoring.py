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

from app.audit_logger import log_rbac_event
from app.config import settings
from app.models import (
    ScheduledJob,
    ScheduledJobChangesResponse,
    ScheduledJobFrequency,
    ScrapeMode,
)
from app.url_safety import validate_public_http_url
from app.utils.aup import require_aup_accepted
from app.utils.cron_parser import is_valid as is_valid_cron_expression
from app.utils.datetime_normalization import parse_datetime
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
    Path(settings.DATA_DIR) / "scheduled_jobs.json",
)


def _validate_urls(urls: list[str]) -> list[str]:
    """Strip, deduplicate, and SSRF-validate a list of URLs.

    Raises HTTPException 400 if any URL fails the public-URL check, or
    if the input list exceeds ``_MAX_URLS_PER_SCHEDULE`` (bounded to
    prevent a single request from triggering tens of thousands of
    sequential DNS resolutions, which would block a worker thread for
    many seconds).
    """
    if urls is None:
        return []
    if len(urls) > _MAX_URLS_PER_SCHEDULE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Too many URLs in a single schedule (max {_MAX_URLS_PER_SCHEDULE}, "
                f"got {len(urls)}). Split into multiple schedules."
            ),
        )
    cleaned: list[str] = []
    seen: set[str] = set()
    for u in urls:
        u = u.strip()
        if not u or u in seen:
            continue
        seen.add(u)
        try:
            validate_public_http_url(u)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"URL failed security check: {exc}") from exc
        cleaned.append(u)
    return cleaned


_MAX_URLS_PER_SCHEDULE = 100
"""Hard cap on URL count per single scheduled job.

A higher value would let a single POST block a FastAPI worker on
sequential DNS resolutions for many seconds. 100 is well above the
typical use case (single-page recurring scrapes) and prevents DoS via
oversized request bodies.
"""


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


# Per-job cron-fallback counters keyed by job id. Used to detect and
# disable jobs whose cron expressions reject on every dispatch (hot-loop
# indicator). When a job's counter exceeds ``_CRON_LOOP_THRESHOLD`` we
# emit a single CRITICAL log + audit event to alert operators. The
# counter is in-process only — restart resets it; combined with the
# empty next_run_at returned above, the worst case is at most one
# extra fallback per process restart, never an unbounded hot loop.
_cron_fallback_counts: dict[str, int] = {}
_CRON_LOOP_THRESHOLD = 5


def _record_cron_fallback(*, job_id: str) -> None:
    """Track cron-expression rejections per job and trip a circuit on hot loops.

    ``next_after`` raises on malformed input. Without this counter, the
    scheduler would re-run the broken job every loop tick forever. With
    this counter + the validation guard above, we (1) refuse to set a
    next-run timestamp on bad expressions, and (2) alert operators when
    a single job repeatedly fails to produce one.
    """
    if not job_id:
        return
    key = str(job_id)
    count = _cron_fallback_counts.get(key, 0) + 1
    _cron_fallback_counts[key] = count
    if count == _CRON_LOOP_THRESHOLD:
        logger.critical(
            "Scheduled job %s has triggered cron fallback %d times — likely a malformed expression. "
            "The job will not be re-scheduled; please review the cron_expression field.",
            key,
            count,
        )
        from app.audit_logger import log_admin_action

        log_admin_action(
            actor="system",
            action="scheduled_job_cron_loop_detected",
            resource="scheduled_jobs",
            details={"job_id": key, "fallback_count": count},
        )


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


def _compute_next_run(job: ScheduledJob) -> str:
    """Compute the ISO-8601 next-run-at timestamp for a newly created scheduled job."""
    from app.utils.cron_parser import is_valid as is_valid_cron
    from app.utils.cron_parser import next_after as cron_next_after

    now = datetime.datetime.now(datetime.UTC)
    cron_expr = (job.cron_expression or "").strip()
    if cron_expr:
        # Validate the expression upfront. ``next_after`` accepts a wide
        # input surface and a deeply malformed expression would otherwise
        # raise at every loop tick — producing an apparent hot-loop where
        # the scheduler picks up the job, runs it, recomputes "now", and
        # dispatches again immediately. Validating here lets the
        # creation/PUT path reject those expressions and we fall through
        # to a sane frequency-based fallback (or reject outright when no
        # frequency is provided).
        if not is_valid_cron(cron_expr):
            logger.warning(
                "Scheduled job %s has invalid cron expression %r — refusing to schedule",
                getattr(job, "id", "<unknown>"),
                cron_expr,
            )
            _record_cron_fallback(job_id=getattr(job, "id", "<unknown>"))
            return ""  # Scheduler loop will treat empty next_run_at as "do not re-run"
        try:
            nxt = cron_next_after(now, cron_expr)
            return nxt.isoformat()
        except (ValueError, TypeError):
            logger.warning("Cron expression %r failed; falling back to 'now'", cron_expr)
            _record_cron_fallback(job_id=getattr(job, "id", "<unknown>"))
    # Fallback: run immediately (the processor loop will respect frequency deltas)
    return now.isoformat()


def _compute_next_from_record(record: dict[str, Any]) -> str:
    """Recompute next_run_at for an existing record (after a parameter change)."""
    from app.utils.cron_parser import is_valid as is_valid_cron
    from app.utils.cron_parser import next_after as cron_next_after

    now = datetime.datetime.now(datetime.UTC)
    cron_expr = str(record.get("cron_expression") or "").strip()
    if cron_expr:
        if not is_valid_cron(cron_expr):
            logger.warning(
                "Scheduled record %s has invalid cron expression %r — leaving next_run_at blank",
                record.get("id", "<unknown>"),
                cron_expr,
            )
            _record_cron_fallback(job_id=record.get("id", "<unknown>"))
            return ""
        try:
            nxt = cron_next_after(now, cron_expr)
            return nxt.isoformat()
        except (ValueError, TypeError):
            logger.warning("Cron expression %r failed; falling back to 'now'", cron_expr)
            _record_cron_fallback(job_id=record.get("id", "<unknown>"))
    # Frequency-based: compute from hardcoded deltas
    from datetime import timedelta

    _DELTAS: dict[str, timedelta] = {
        "hourly": timedelta(hours=1),
        "daily": timedelta(days=1),
        "weekly": timedelta(weeks=1),
        "monthly": timedelta(days=30),
    }
    freq = str(record.get("frequency") or "daily").lower()
    delta = _DELTAS.get(freq, timedelta(days=1))
    return (now + delta).isoformat()


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
    if item is None:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    if not _can_access_scheduled_job(item, auth):
        _role, user_id, _org_id, _project_id = auth
        log_rbac_event(
            actor=user_id,
            action="get_scheduled_job",
            resource=f"scheduled:{job_id}",
            role=_role.value,
            outcome="denied",
            details={
                "owner_id": item.get("user_id", ""),
                "org_id": item.get("org_id", ""),
                "project_id": item.get("project_id", ""),
                "policy": "scoped_resource_or_saas_org_project",
            },
        )
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    return item


@router.post("", status_code=201, response_model=dict)
async def create_scheduled_job(
    name: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    _aup_check: Annotated[dict[str, Any], Depends(require_aup_accepted)],
    frequency: ScheduledJobFrequency = ScheduledJobFrequency.DAILY,
    job_name: str = "",
    urls: Annotated[list[str] | None, Query()] = None,
    cron_expression: str | None = None,
    timezone: str = "UTC",
):
    """Create a new scheduled (recurring) scraping job.

    Requires AUP acceptance.  Every URL in *urls* is validated
    against the project's SSRF guard before it is stored.

    When ``cron_expression`` is provided it takes precedence over
    ``frequency`` for computing next-run times.  The expression
    follows standard 5-field cron syntax (minute hour dom month dow).
    """
    if cron_expression is not None:
        cron_expression = cron_expression.strip()
        if cron_expression and not is_valid_cron_expression(cron_expression):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cron expression: {cron_expression!r}",
            )
    _role, user_id, org_id, project_id = auth
    validated_urls = _validate_urls(urls or [])
    job = ScheduledJob(  # type: ignore[call-arg]
        name=name.strip(),
        user_id=user_id,
        org_id=org_id,
        project_id=project_id,
        frequency=frequency,
        cron_expression=cron_expression or None,
        timezone=timezone or "UTC",
        job_name=job_name.strip() or f"Scheduled: {name}",
        urls=validated_urls,
        mode=ScrapeMode.MANUAL if validated_urls else ScrapeMode.AUTO,
    )
    record = job.model_dump()
    # next_run_at is a runtime scheduling field stored alongside the
    # model data but not part of the Pydantic schema.
    record["next_run_at"] = _compute_next_run(job)
    _scheduled_jobs.upsert(job.id, record)
    logger.info("Scheduled job created: %s (%s)", job.name, job.id)
    return record


@router.get("", status_code=200, response_model=dict)
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


@router.get("/{job_id}", status_code=200, response_model=dict)
async def get_scheduled_job(
    job_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """Get a single scheduled job by ID."""
    return _get_visible_scheduled_job(job_id, auth)


@router.put("/{job_id}", status_code=200, response_model=dict)
async def update_scheduled_job(
    job_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    name: str | None = None,
    frequency: ScheduledJobFrequency | None = None,
    enabled: bool | None = None,
    urls: Annotated[list[str] | None, Query()] = None,
    cron_expression: str | None = None,
    timezone: str | None = None,
):
    """Update an existing scheduled job.

    If *urls* is provided, each URL is SSRF-validated before being
    stored on the scheduled job record.

    When ``cron_expression`` is provided it takes precedence over
    ``frequency`` for computing next-run times.  Pass an empty string
    to clear a previously set cron expression.
    """
    if cron_expression is not None:
        cron_expression = cron_expression.strip()
        if cron_expression and not is_valid_cron_expression(cron_expression):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cron expression: {cron_expression!r}",
            )
    existing = _get_visible_scheduled_job(job_id, auth)
    if name is not None:
        existing["name"] = name.strip()
    if frequency is not None:
        existing["frequency"] = frequency.value
    if enabled is not None:
        existing["enabled"] = enabled
    if urls is not None:
        existing["urls"] = _validate_urls(urls)
        existing["mode"] = ScrapeMode.MANUAL.value if existing["urls"] else ScrapeMode.AUTO.value
    if cron_expression is not None:
        # Empty string → clear the cron expression; revert to frequency-based.
        existing["cron_expression"] = cron_expression or None
    if timezone is not None:
        existing["timezone"] = timezone or "UTC"
    existing["updated_at"] = _now_iso()
    # Recompute next_run_at when scheduling parameters change
    if cron_expression is not None or frequency is not None or timezone is not None:
        existing["next_run_at"] = _compute_next_from_record(existing)
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


@router.get("/{job_id}/changes", status_code=200, response_model=ScheduledJobChangesResponse)
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
    separate milestone tracked in `AGENTS.md` / `artifacts/audit/ISSUE_LEDGER.md`.
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
            last_t = parse_datetime(str(last.get("ran_at") or ""))
            prev_t = parse_datetime(str(previous.get("ran_at") or ""))
            if last_t is None or prev_t is None:
                # Missing/unparseable timestamps: leave frequency_met None
                # so the caller can distinguish "unknown" from "definitively unmet".
                _unparseable = "unparseable ran_at"
                raise ValueError(_unparseable)
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
