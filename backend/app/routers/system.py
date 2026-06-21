"""System Router — endpoints for metrics, health, system status, diagnostics, and URL analysis."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import os
import re
import secrets
import threading
import zipfile
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.globals import _jobs_store_lock, config_view, jobs_store, recycle_bin_store
from app.middlewares import rate_limiter as _rate_limiter
from app.selector_discovery import analyze_url_for_fields
from app.storage_interface import get_job_repository
from app.url_analyzer import analyze_url as _url_analyze
from app.url_safety import validate_public_http_url
from app.utils.rbac import UserRole, require_role

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


class AcquisitionMode(StrEnum):
    STANDARD = "standard"
    AGGRESSIVE = "aggressive"
    DEEP_SCAN = "deep_scan"


class URLPreviewRequest(BaseModel):
    url: str = Field(..., description="The URL to analyze for data extraction")
    fetch_preview: bool = Field(
        default=False,
        description="When false, return URL-only guidance without fetching the target page.",
    )
    search_params: dict[str, str] | None = Field(
        default=None,
        description="Optional search parameters to submit to the site's search form",
    )
    acquisition_mode: AcquisitionMode = Field(
        default=AcquisitionMode.STANDARD,
        description="Acquisition mode: standard, aggressive, or deep_scan",
    )


# ─── System / Storage Status ───────────────────────────────────────────


@router.get("/api/system/storage/status")
async def storage_status(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Detailed storage backend status. Requires operator or admin."""
    repo = get_job_repository()
    backend = getattr(repo, "backend", "")
    if backend and backend.startswith("postgres"):
        health = await run_in_threadpool(repo.health_check)
        return {
            "backend": backend,
            "ok": health.get("ok", False),
            "error": health.get("error"),
            "schema_version": health.get("schema_version", 0),
            "expected_version": health.get("expected_version", 0),
            "job_count": health.get("job_count", 0),
            "recycle_bin_count": health.get("recycle_bin_count", 0),
        }
    from app.job_store import get_storage_status

    return await run_in_threadpool(get_storage_status)


@router.get("/api/system/manifest")
async def system_manifest(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER]))],
):
    """Live module/version manifest for the dashboard help section.

    Returns the project's metadata, runtime configuration, and the
    currently-active AUP version so the help panel can show
    version-aware information without hardcoding values in JS.
    """
    from app.config import settings
    from app.saas import CURRENT_AUP_VERSION
    from app.utils.encryption import _get_key_version

    pyproject_path = Path(__file__).resolve().parents[3] / "pyproject.toml"
    project_version = "unknown"
    if pyproject_path.exists():
        try:
            import tomllib  # type: ignore[import-not-found]

            with pyproject_path.open("rb") as f:
                data = tomllib.load(f)
            project_version = str(
                data.get("project", {}).get("version") or data.get("tool", {}).get("poetry", {}).get("version") or "unknown",
            )
        except (OSError, KeyError, ValueError):
            project_version = "unknown"

    return {
        "project": "DataForge Scraper",
        "version": project_version,
        "env": str(getattr(settings, "ENV", "development")),
        "aup_version": CURRENT_AUP_VERSION,
        "encryption_key_version": _get_key_version(),
        "experimental_routes_enabled": bool(
            getattr(settings, "ENABLE_EXPERIMENTAL_ROUTES", False),
        ),
        "storage_backend": str(getattr(settings, "STORAGE_BACKEND", "sqlite")),
        "pg_driver": os.environ.get("DATAFORGE_PG_DRIVER", "psycopg2"),
    }


@router.get("/api/system/status")
async def system_status(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Detailed system and active jobs overview. Requires operator or admin.

    In worker mode (multi-process deployment), queries the persistent
    repository for job counts rather than relying on the API process's
    in-memory store, which may be stale or empty.
    """
    from app.models import JobStatus
    from app.routers.jobs_state import is_worker_mode

    repo = get_job_repository()
    backend = getattr(repo, "backend", "sqlite")

    if is_worker_mode():
        # In worker mode, the API's in-memory jobs_store may be stale
        # because the worker process updates jobs independently. Query
        # the persistent store for accurate counts.
        try:
            # Use health_check for total counts (efficient, single query)
            health = await run_in_threadpool(repo.health_check)
            job_total = health.get("job_count", 0)
            recycle_count = health.get("recycle_bin_count", 0)

            # Use a single ``GROUP BY status`` query for per-status counts.
            # The previous approach called ``list_job_summaries(limit=5000)``
            # which the storage layer silently clamped to 500, producing
            # wrong counts whenever the store held more than 500 jobs.
            counts = await run_in_threadpool(repo.count_jobs_by_status)
            # Backfill any missing JobStatus values with 0 so the response
            # always has the same shape.
            counts = {s.value: counts.get(s.value, 0) for s in JobStatus}

            active = (
                counts.get(JobStatus.PENDING.value, 0)
                + counts.get(JobStatus.DISCOVERING.value, 0)
                + counts.get(JobStatus.RUNNING.value, 0)
            )
        except (AttributeError, ImportError, RuntimeError):
            logger.debug("Failed to query repo for system status, falling back to in-memory")
            # Fall back to in-memory stores (imported from app.globals)
            counts = _compute_job_counts()
            job_total = sum(counts.values())
            with _jobs_store_lock:
                recycle_count = len(recycle_bin_store)
            active = (
                counts.get(JobStatus.PENDING.value, 0)
                + counts.get(JobStatus.DISCOVERING.value, 0)
                + counts.get(JobStatus.RUNNING.value, 0)
            )
    else:
        # Single-process mode: use in-memory stores (fast path)
        counts = _compute_job_counts()
        active = (
            counts.get(JobStatus.PENDING.value, 0)
            + counts.get(JobStatus.DISCOVERING.value, 0)
            + counts.get(JobStatus.RUNNING.value, 0)
        )
        with _jobs_store_lock:
            job_total = len(jobs_store)
            recycle_count = len(recycle_bin_store)

    response: dict[str, Any] = {
        "status": "online",
        "backend": backend,
        "worker_mode": is_worker_mode(),
        "jobs": {
            "total": job_total,
            "active": active,
            "completed": counts.get(JobStatus.COMPLETED.value, 0),
            "degraded": counts.get(JobStatus.DEGRADED.value, 0),
            "empty_result": counts.get(JobStatus.EMPTY_RESULT.value, 0),
            "failed": counts.get(JobStatus.FAILED.value, 0),
            "canceled": counts.get(JobStatus.CANCELED.value, 0),
        },
        "recycle_bin_count": recycle_count,
        "runtime_limits": config_view(),
    }

    # Worker health: show registered workers and their heartbeat status
    try:
        worker_healths = await run_in_threadpool(repo.get_all_worker_healths, 60)
        if worker_healths:
            response["workers"] = worker_healths
    except (AttributeError, ImportError, RuntimeError):
        pass

    # Queue status
    try:
        from app.worker_queue import get_worker_queue

        q_status = await run_in_threadpool(get_worker_queue().get_status)
        response["queue"] = {
            "pending": q_status.get("pending", 0),
            "running": q_status.get("running", 0),
            "dead_letter": q_status.get("dead_letter", 0),
            "max_concurrency": q_status.get("max_concurrency", 0),
        }
    except (AttributeError, ImportError, RuntimeError):
        pass

    if settings.ENV.lower() != "production":
        from app.state_store import get_state_file_path

        response["state_file"] = str(get_state_file_path())
    return response


def _compute_job_counts() -> dict[str, Any]:
    """Compute per-status job counts from the in-memory jobs_store.

    Reads ``jobs_store`` under the project-wide ``_jobs_store_lock`` so
    a concurrent mutation cannot cause ``RuntimeError: dictionary
    changed size during iteration`` or skew the per-status counts.
    """
    from app.models import JobStatus

    counts = {s.value: 0 for s in JobStatus}
    with _jobs_store_lock:
        for job in jobs_store.values():
            status_key = str(job.status.value if isinstance(job.status, JobStatus) else job.status)
            if status_key not in counts:
                counts[status_key] = 0
            counts[status_key] += 1
    return counts


# ─── Diagnostics ZIP Export ─────────────────────────────────────────────


@router.get("/api/system/diagnostics/export")
async def export_system_diagnostics(_role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))]):  # noqa: B008, C901, PLR0912, PLR0915, RUF100
    """Generates and exports an authenticated and sanitized system diagnostics ZIP bundle."""
    # Regular expressions for PII sanitization
    email_regex = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
    phone_regex = re.compile(r"\+?\b\d[\d\s()\-]{8,14}\d\b")
    sensitive_keys = {
        "authorization",
        "auth",
        "api_key",
        "key",
        "password",
        "token",
        "secret",
        "signature",
        "alert_webhook_url",
        "credential",
        "session",
        "cookie",
        "bearer",
        "private",
        "client_secret",
        "api_secret",
        "access_key",
        "secret_key",
    }

    def sanitize_value(val, _depth=0, _max_depth=50):
        if _depth >= _max_depth:
            return val
        if isinstance(val, str):
            val = email_regex.sub("<redacted_email>", val)
            return phone_regex.sub("<redacted_phone>", val)
        if isinstance(val, dict):
            return {
                k: (
                    "********"
                    if any(s in k.lower() for s in sensitive_keys)
                    else sanitize_value(v, _depth=_depth + 1, _max_depth=_max_depth)
                )
                for k, v in val.items()
            }
        if isinstance(val, list):
            return [sanitize_value(item, _depth=_depth + 1, _max_depth=_max_depth) for item in val]
        return val

    # 1. anonymized_state.json
    with _jobs_store_lock:
        anonymized_jobs = {}
        for j_id, job in jobs_store.items():
            if hasattr(job, "model_dump"):
                job_dict = job.model_dump()
            elif hasattr(job, "dict"):
                job_dict = job.dict()
            else:
                job_dict = dict(job)
            anonymized_jobs[j_id] = sanitize_value(job_dict)

        anonymized_recycle = {}
        for j_id, job in recycle_bin_store.items():
            if hasattr(job, "model_dump"):
                job_dict = job.model_dump()
            elif hasattr(job, "dict"):
                job_dict = job.dict()
            else:
                job_dict = dict(job)
            anonymized_recycle[j_id] = sanitize_value(job_dict)

    anonymized_state = {"jobs": anonymized_jobs, "recycle_bin": anonymized_recycle}

    # 2. active_settings.json
    settings_dict = {}
    if hasattr(settings, "model_dump"):
        settings_dict = settings.model_dump()
    elif hasattr(settings, "dict"):
        settings_dict = settings.dict()
    else:
        settings_dict = dict(settings)

    masked_settings = {}
    for k, v in settings_dict.items():
        if any(s in k.lower() for s in sensitive_keys):
            masked_settings[k] = "********"
        else:
            masked_settings[k] = sanitize_value(v)

    # 3. selector_decay_snapshots.json
    selector_decay_snapshots = {}
    try:
        from app.selector_memory import get_selector_memory

        memory = get_selector_memory()
        if memory and hasattr(memory, "_memory"):
            for domain, entry in memory._memory.items():
                conf = memory._compute_confidence(entry)
                selector_decay_snapshots[domain] = {
                    "selectors": entry.get("selectors"),
                    "success_count": entry.get("success_count", 0),
                    "failure_count": entry.get("failure_count", 0),
                    "first_seen": entry.get("first_seen"),
                    "last_success": entry.get("last_success"),
                    "confidence": {
                        "raw_confidence": conf.raw_confidence,
                        "age_factor": conf.age_factor,
                        "freshness_factor": conf.freshness_factor,
                        "final_score": conf.final_score,
                        "reason": conf.reason,
                    },
                }
    except (AttributeError, ImportError, RuntimeError) as e:
        logger.exception("Failed to build selector decay snapshots for diagnostics")
        selector_decay_snapshots = {"error": {"message": str(e)}}

    # 4. telemetry_snapshots.json
    telemetry_snapshots = []
    try:
        from app.semantic_world_state import get_world_state

        ws = get_world_state()
        if hasattr(ws, "_observability") and ws._observability:
            telemetry_snapshots = sanitize_value(ws._observability.telemetry)
    except (AttributeError, ImportError, RuntimeError) as e:
        logger.exception("Failed to build telemetry snapshots for diagnostics")
        telemetry_snapshots = [{"error": str(e)}]

    # Create ZIP archive in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("anonymized_state.json", json.dumps(anonymized_state, indent=2))
        zip_file.writestr("active_settings.json", json.dumps(masked_settings, indent=2))
        zip_file.writestr("selector_decay_snapshots.json", json.dumps(selector_decay_snapshots, indent=2))
        zip_file.writestr("telemetry_snapshots.json", json.dumps(telemetry_snapshots, indent=2))

    zip_buffer.seek(0)
    headers = {"Content-Disposition": "attachment; filename=dataforge_diagnostics.zip"}
    return Response(zip_buffer.getvalue(), media_type="application/zip", headers=headers)


# ─── Audit Log Endpoint ────────────────────────────────────────────────


@router.get("/api/system/audit-log")
async def get_audit_log(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    category: Annotated[
        str | None,
        Query(description="Filter by event category: auth, rbac, admin, data_access, job, system"),
    ] = None,
) -> dict[str, Any]:
    """Return recent audit-log events parsed from the log file.

    Admin-only because the audit log can include user IDs, IP addresses,
    and admin-action payloads. ``limit`` caps the number of events
    returned; ``category`` is a coarse filter on the event ``category``
    field. Events that fail to parse are silently skipped (the logger
    falls back to the original line).
    """
    from app.audit_logger import get_recent_events

    events = get_recent_events(count=limit)
    if category:
        events = [e for e in events if str(e.get("category") or "").lower() == category.lower()]
    return {
        "total": len(events),
        "limit": limit,
        "category": category or "",
        "items": events,
    }


@router.post("/api/system/csp-violations")
async def csp_violations(request: Request):
    """Receive a Content-Security-Policy violation report from a browser.

    The browser POSTs a JSON body of shape
    ``{"csp-report": {"violated-directive": "script-src 'self'", ...}}`` when
    any directive in the report-only policy attached by
    ``csp_report_only_middleware`` is violated. This endpoint normalises the
    directive label and increments ``dataforge_csp_violations_total{directive=...}``.

    The endpoint is unauthenticated on purpose — the browser cannot carry the
    API key — but it is rate-limited by the global /api/* middleware. The
    body is bounded by the body-size middleware (5 MB) so an attacker cannot
    flood the metrics counters.
    """
    # Validate Content-Type to prevent log injection via arbitrary POSTs
    ctype = request.headers.get("content-type", "").lower()
    if not ctype.startswith(("application/json", "application/csp-report")):
        return JSONResponse(status_code=204, content=None)

    try:
        payload = await request.json()
    except (ValueError, TypeError):
        # Browsers occasionally send the report as ``application/csp-report``
        # with the fields at the top level. Accept both shapes.
        try:
            body_bytes = await request.body()
            payload = json.loads(body_bytes.decode("utf-8", errors="replace")) if body_bytes else {}
        except (ValueError, TypeError, UnicodeDecodeError):
            return JSONResponse(status_code=204, content=None)

    # Normalise: the spec wraps the actual report under ``csp-report``; some
    # browsers omit the wrapper and put fields at the top level.
    csp_report = payload.get("csp-report") if isinstance(payload, dict) else None
    if not isinstance(csp_report, dict):
        csp_report = payload if isinstance(payload, dict) else {}

    directive = csp_report.get("violated-directive") or csp_report.get("effective-directive") or csp_report.get("original-policy")
    directive_label = "unspecified"
    if isinstance(directive, str):
        first_token = directive.strip().split(" ", 1)[0]
        if first_token:
            directive_label = first_token.lower()[:64] or "unspecified"

    try:
        from app.metrics_collector import record_csp_violation

        record_csp_violation(directive_label)
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

    # Sanitise log values: truncate and remove newlines to prevent log injection
    def _sanitise(val: object, max_len: int = 120) -> str:
        s = str(val)[:max_len]
        return s.replace("\n", " ").replace("\r", " ")

    logger.info(
        "CSP violation: directive=%s blocked=%s document-uri=%s",
        directive_label,
        _sanitise(csp_report.get("blocked-uri")),
        _sanitise(csp_report.get("document-uri")),
    )
    return JSONResponse(status_code=204, content=None)


# ─── Data Retention ──────────────────────────────────────────────────────


@router.post("/api/system/retention/enforce", status_code=200)
async def enforce_data_retention(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    dry_run: Annotated[bool, Query(
        description="When true, report what would be deleted without deleting.",
    )] = True,
) -> dict[str, Any]:
    """Enforce the data retention policy, purging data older than the configured TTL.

    By default this runs as a dry-run (reports only). Pass ``?dry_run=false``
    to actually delete expired data.

    Returns:
        - ``jobs_purged``: completed/terminal jobs deleted
        - ``recycle_purged``: recycle-bin items deleted
        - ``jobs_skipped``: completed jobs within retention window
        - ``recycle_skipped``: recycle items within retention window
        - ``idempotency_keys_purged``: stale idempotency keys deleted
        - ``config``: current retention policy in days
    """
    from app.globals import _jobs_store_lock, jobs_store, recycle_bin_store
    from app.utils.data_retention import enforce_idempotency_retention, enforce_retention, get_retention_config

    with _jobs_store_lock:
        result: dict[str, Any] = dict(
            enforce_retention(
                jobs_store,
                recycle_bin_store,
                dry_run=dry_run,
            )
        )
    result["idempotency_keys_purged"] = enforce_idempotency_retention(dry_run=dry_run)
    result["config"] = get_retention_config()
    result["dry_run"] = dry_run

    # Persist the in-memory deletions to the database
    if not dry_run and (result["jobs_purged"] > 0 or result["recycle_purged"] > 0):
        try:
            from app.job_store import save_state

            with _jobs_store_lock:
                save_state(jobs_store, recycle_bin_store, prune_missing=True)
        except (ImportError, RuntimeError) as e:
            logger.warning("Failed to persist retention deletions: %s", e)
            result["persist_error"] = str(e)

    return result


@router.get("/api/system/retention/config", status_code=200)
async def get_retention_config_endpoint(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
) -> dict[str, Any]:
    """Return the current data retention policy configuration."""
    from app.utils.data_retention import get_retention_config

    return {"config": get_retention_config()}


# ─── Rate Limiter Stats ─────────────────────────────────────────────────


@router.get("/api/system/rate-limit-stats")
async def rate_limit_stats(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Return current rate limiter configuration and active counter stats.

    Exposes the rate limiter's internal state for operational debugging:
    - ``enabled`` — whether any tier (global or per-IP) is active
    - ``global_limit_per_window`` / ``global_window_seconds`` — aggregate cap
    - ``per_ip_enabled`` / ``per_ip_limit_per_window`` / ``per_ip_window_seconds`` — fair-share cap
    - ``active_keys`` — how many distinct counter keys are currently tracked
    - ``route_limits`` — per-route override limits (max + window per prefix)

    Requires operator or admin role.
    """
    try:
        return _rate_limiter.get_stats()
    except (AttributeError, RuntimeError, ImportError) as e:
        logger.warning("Failed to get rate limiter stats: %s", e)
        return JSONResponse(
            status_code=503,
            content={"detail": "Rate limiter stats unavailable."},
        )


# ─── URL Analyzer Endpoint ──────────────────────────────────────────────


@router.post("/api/url/analyze")
async def analyze_url(
    req: URLPreviewRequest,
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Analyze a URL and auto-detect what data fields can be extracted."""
    intelligence = _url_analyze(req.url)
    redacted_url = intelligence.to_dict()["url"]
    try:
        validate_public_http_url(req.url)
    except ValueError as e:
        return JSONResponse(
            status_code=200,
            content=intelligence.to_guided_dict(safe_to_fetch=False, safety_error=str(e)),
        )

    if not req.fetch_preview:
        return intelligence.to_guided_dict(safe_to_fetch=True)

    url_analyzer_timeout = settings.URL_ANALYZER_TIMEOUT

    try:
        result = await asyncio.wait_for(
            analyze_url_for_fields(url=req.url, search_params=req.search_params, acquisition_mode=req.acquisition_mode),
            timeout=url_analyzer_timeout,
        )
    except TimeoutError:
        logger.warning("[URLAnalyzer] Timeout after %ds analyzing %s", url_analyzer_timeout, redacted_url)
        return JSONResponse(
            status_code=408,
            content={
                "url": redacted_url,
                "error": (
                    f"Analysis timed out after {url_analyzer_timeout} seconds. "
                    "The page may be too slow, heavy, or protected by anti-bot measures."
                ),
                "redirect_info": None,
                "content_quality": None,
                "page_structure": "unknown",
                "structure_confidence": 0.0,
                "estimated_record_count": 0,
                "item_container": None,
                "suggested_fields": [],
                "anti_bot_score": 0.0,
            },
        )

    if result.get("error"):
        return JSONResponse(status_code=422, content=result)

    result["url_intelligence"] = intelligence.to_guided_dict(safe_to_fetch=True)

    return result


# ─── Prometheus /metrics ────────────────────────────────────────────────

METRICS_COLLECTION_ERRORS = 0
_METRICS_ERRORS_LOCK = threading.Lock()
_METRICS_TOKEN_WARN_EMITTED = False


def _warn_metrics_token_unset_once() -> None:
    """Log a one-time warning that ``METRICS_TOKEN`` is unset in dev.

    In production the ``/metrics`` endpoint refuses to serve without a
    token, so we never reach this helper. In development the endpoint
    stays open for convenience, but the operator should still be told
    that the deployment is shipping metrics to anyone who can reach the
    port. The warning is emitted at most once per process to avoid
    log spam on every scrape.
    """
    global _METRICS_TOKEN_WARN_EMITTED
    if _METRICS_TOKEN_WARN_EMITTED:
        return
    _METRICS_TOKEN_WARN_EMITTED = True
    logger.warning(
        "DATAFORGE_METRICS_TOKEN is not set; /metrics is publicly readable. "
        "Set a token before deploying outside of local development.",
    )


def _prometheus_label_text(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    escaped = {key: str(value).replace("\\", "\\\\").replace('"', '\\"') for key, value in labels.items()}
    return "{" + ",".join(f'{key}="{value}"' for key, value in escaped.items()) + "}"


def _basic_metric_line(name: str, value: float, labels: dict[str, str] | None = None) -> str:
    return f"{name}{_prometheus_label_text(labels or {})} {value}"


def _render_basic_metrics_text() -> str:
    """Render a minimal Prometheus exposition if prometheus_client is unavailable."""
    from app.metrics_collector import (
        get_anti_bot_classifications,
        get_auth_profile_ops,
        get_browser_launch_outcomes,
        get_csp_violations,
        get_errors,
        get_export_outcomes,
        get_extraction_method_counts,
        get_health_check_latencies,
        get_llm_calls,
        get_rate_limit_global_hits,
        get_rate_limit_per_ip_hits,
        get_repo_query_latencies,
        get_request_latencies,
        get_requests_total,
        get_retention_ops,
        get_scheduled_job_ops,
        get_signup_outcomes,
        get_ssrf_rejects,
        get_worker_failures,
        get_workflow_ops,
    )
    from app.models import JobStatus

    lines: list[str] = []

    counts = {s.value: 0 for s in JobStatus}
    with _jobs_store_lock:
        for job in jobs_store.values():
            status_key = str(job.status.value if isinstance(job.status, JobStatus) else job.status)
            counts[status_key] = counts.get(status_key, 0) + 1
        lines.append(_basic_metric_line("dataforge_recycle_bin_total", len(recycle_bin_store)))
    for status, count in counts.items():
        lines.append(_basic_metric_line("dataforge_jobs_total", count, {"status": status}))

    # Auth profile operations
    for op_action, op_count in get_auth_profile_ops().items():
        lines.append(_basic_metric_line("dataforge_auth_profile_ops_total", op_count, {"action": op_action}))

    # Workflow operations
    for wf_action, wf_count in get_workflow_ops().items():
        lines.append(_basic_metric_line("dataforge_workflow_ops_total", wf_count, {"action": wf_action}))

    # Signup outcomes
    for signup_outcome, signup_count in get_signup_outcomes().items():
        lines.append(
            _basic_metric_line(
                "dataforge_signup_outcomes_total",
                signup_count,
                {"outcome": signup_outcome},
            ),
        )

    # Scheduled job operations
    for sched_action, sched_count in get_scheduled_job_ops().items():
        lines.append(
            _basic_metric_line(
                "dataforge_scheduled_job_ops_total",
                sched_count,
                {"action": sched_action},
            ),
        )

    # Retention operations
    for ret_action, ret_count in get_retention_ops().items():
        lines.append(
            _basic_metric_line(
                "dataforge_retention_ops_total",
                ret_count,
                {"action": ret_action},
            ),
        )

    backend_ok = 1
    try:
        repo = get_job_repository()
        backend = getattr(repo, "backend", "sqlite")
        lines.append(_basic_metric_line("dataforge_backend", 1, {"backend": backend}))
    except (AttributeError, ImportError, RuntimeError):
        backend_ok = 0
        logger.exception("Metrics fallback: backend collection failed")
    lines.append(_basic_metric_line("dataforge_backend_collection_ok", backend_ok))

    queue_ok = 1
    try:
        from app.worker_queue import get_worker_queue

        q_status = get_worker_queue().get_status()
        lines.append(_basic_metric_line("dataforge_queue_pending", q_status.get("pending", 0)))
        lines.append(_basic_metric_line("dataforge_queue_running", q_status.get("running", 0)))
        lines.append(_basic_metric_line("dataforge_queue_dead_letter", q_status.get("dead_letter", 0)))
    except (AttributeError, ImportError, RuntimeError):
        queue_ok = 0
        logger.exception("Metrics fallback: queue collection failed")
    lines.append(_basic_metric_line("dataforge_queue_collection_ok", queue_ok))

    for task_type, count in get_worker_failures().items():
        lines.append(_basic_metric_line("dataforge_worker_failures_total", count, {"task_type": task_type}))

    # Worker heartbeat health metrics
    try:
        repo = get_job_repository()
        worker_healths = repo.get_all_worker_healths(ttl_seconds=60)
        for wh in worker_healths:
            wid = str(wh.get("worker_id", "unknown"))
            hostname = str(wh.get("hostname", ""))
            pid = str(wh.get("pid") or "unknown")
            alive = 1 if wh.get("alive") else 0
            lines.append(
                _basic_metric_line(
                    "dataforge_worker_heartbeat_alive",
                    alive,
                    {"worker_id": wid, "hostname": hostname, "pid": pid},
                ),
            )
            last_hb = wh.get("last_heartbeat")
            if last_hb:
                try:
                    import datetime as _dt

                    age = (_dt.datetime.now(_dt.UTC) - _dt.datetime.fromisoformat(str(last_hb))).total_seconds()
                except (ValueError, TypeError):
                    age = -1.0
            else:
                age = -1.0
            lines.append(
                _basic_metric_line(
                    "dataforge_worker_heartbeat_age_seconds",
                    age,
                    {"worker_id": wid, "hostname": hostname, "pid": pid},
                ),
            )
    except (AttributeError, ImportError, RuntimeError):
        logger.debug("Metrics fallback: worker heartbeat collection failed")

    if settings.METRICS_ENABLE_HISTOGRAMS:
        request_latencies = get_request_latencies()
        if request_latencies:
            lines.append(_basic_metric_line("dataforge_request_duration_seconds_count", len(request_latencies)))
            lines.append(_basic_metric_line("dataforge_request_duration_seconds_sum", sum(request_latencies)))

        health_latencies = get_health_check_latencies()
        if health_latencies:
            lines.append(_basic_metric_line("dataforge_backend_health_check_duration_seconds_count", len(health_latencies)))
            lines.append(_basic_metric_line("dataforge_backend_health_check_duration_seconds_sum", sum(health_latencies)))

    lines.append(_basic_metric_line("dataforge_metrics_collection_error_total", METRICS_COLLECTION_ERRORS))

    errors_dict = get_errors()
    for err_type, count in errors_dict.items():
        lines.append(_basic_metric_line("dataforge_errors_total", count, {"type": err_type}))
    if "database" not in errors_dict:
        lines.append(_basic_metric_line("dataforge_errors_total", 0, {"type": "database"}))

    lines.append(_basic_metric_line("dataforge_llm_calls_total", get_llm_calls()))
    lines.append(_basic_metric_line("dataforge_requests_total", get_requests_total()))

    # New gauges — observability targets.
    for method, count in get_extraction_method_counts().items():
        lines.append(_basic_metric_line("dataforge_extraction_method_total", count, {"method": method}))
    for cls, count in get_anti_bot_classifications().items():
        lines.append(_basic_metric_line("dataforge_anti_bot_classifications_total", count, {"classification": cls}))
    for fmt, outcomes in get_export_outcomes().items():
        for outcome, count in outcomes.items():
            lines.append(
                _basic_metric_line(
                    "dataforge_export_outcomes_total",
                    count,
                    {"format": fmt, "outcome": outcome},
                ),
            )
    for outcome, count in get_browser_launch_outcomes().items():
        lines.append(_basic_metric_line("dataforge_browser_launch_total", count, {"outcome": outcome}))
    for reason, count in get_ssrf_rejects().items():
        lines.append(_basic_metric_line("dataforge_ssrf_rejects_total", count, {"reason": reason}))

    repo_latencies = get_repo_query_latencies()
    if repo_latencies:
        sorted_lat = sorted(repo_latencies)
        n = len(sorted_lat)
        p50 = sorted_lat[min(n - 1, int(0.50 * n))]
        p95 = sorted_lat[min(n - 1, int(0.95 * n))]
        lines.append(
            _basic_metric_line("dataforge_repo_query_latency_seconds", p50, {"quantile": "0.5"}),
        )
        lines.append(
            _basic_metric_line("dataforge_repo_query_latency_seconds", p95, {"quantile": "0.95"}),
        )

    for directive, count in get_csp_violations().items():
        lines.append(
            _basic_metric_line("dataforge_csp_violations_total", count, {"directive": directive}),
        )

    # Rate limit hit counters
    lines.append(
        _basic_metric_line("dataforge_rate_limit_global_hits_total", get_rate_limit_global_hits()),
    )
    lines.append(
        _basic_metric_line("dataforge_rate_limit_per_ip_hits_total", get_rate_limit_per_ip_hits()),
    )

    return "\n".join(lines) + "\n"


@router.get("/metrics")
async def metrics(request: Request):
    """Prometheus-formatted metrics endpoint for DataForge scraper."""
    # Auth check
    if not settings.METRICS_TOKEN:
        # Fail-secure: in production, an unset METRICS_TOKEN would
        # expose queue depths, error rates, job counts, and the host's
        # worker roster to anyone who can reach the port. Reject the
        # request outright. In development we keep the open behavior
        # so local scrapers can scrape without a token — but we log a
        # one-time warning on the first call so the operator knows.
        #
        # The check is intentionally case-insensitive on whitespace-
        # trimmed input. Operators regularly set ``DATAFORGE_ENV`` to
        # ``Production`` or ``PRODUCTION`` from copy-pasted deployment
        # docs; an exact-match would silently let the dev open
        # behavior run in production and expose the metrics.
        if (settings.ENV or "").strip().lower() == "production":
            return JSONResponse(
                status_code=503,
                content={
                    "detail": (
                        "DATAFORGE_METRICS_TOKEN is not configured. The "
                        "/metrics endpoint refuses to serve without a token "
                        "in production. Set DATAFORGE_METRICS_TOKEN in the "
                        "environment to enable scraping."
                    ),
                },
            )
        _warn_metrics_token_unset_once()
    if settings.METRICS_TOKEN:
        auth_header = request.headers.get("Authorization", "")
        api_key_header = request.headers.get("X-API-Key", "")
        bearer_token = ""  # nosec B105
        # Case-insensitive scheme match (matches api_key_middleware in
        # app.middlewares) so ``bearer <token>`` and ``BEARER <token>``
        # both authenticate consistently.
        if auth_header:
            scheme, _, _token = auth_header.partition(" ")
            if scheme.lower() == "bearer":
                bearer_token = _token
        if not secrets.compare_digest(bearer_token, settings.METRICS_TOKEN) and not secrets.compare_digest(
            api_key_header,
            settings.METRICS_TOKEN,
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Invalid or missing metrics token. Provide Authorization: Bearer <token> or X-API-Key header.",
                },
            )

    global METRICS_COLLECTION_ERRORS
    try:
        from prometheus_client import Gauge, Histogram, generate_latest
    except ModuleNotFoundError:
        content = await run_in_threadpool(_render_basic_metrics_text)
        return Response(content=content, media_type="text/plain")
    from prometheus_client.core import CollectorRegistry

    registry = CollectorRegistry()

    # Job counts by status
    from app.models import JobStatus

    counts = {s.value: 0 for s in JobStatus}
    with _jobs_store_lock:
        snapshot = list(jobs_store.values())
    for job in snapshot:
        status_key = str(job.status.value if isinstance(job.status, JobStatus) else job.status)
        counts[status_key] = counts.get(status_key, 0) + 1

    job_total = Gauge("dataforge_jobs_total", "Total jobs", ["status"], registry=registry)
    for status, count in counts.items():
        job_total.labels(status=status).set(count)

    # Recycle bin count
    recycle_gauge = Gauge("dataforge_recycle_bin_total", "Total jobs in recycle bin", registry=registry)
    with _jobs_store_lock:
        recycle_gauge.set(len(recycle_bin_store))

    # Runtime limits
    for key, val in config_view().items():
        g = Gauge(f"dataforge_config_{key}", f"Config value for {key}", registry=registry)
        with contextlib.suppress(TypeError, ValueError):
            g.set(float(val))

    # Repository backend
    backend_ok = 1
    try:
        repo = get_job_repository()
        backend = getattr(repo, "backend", "sqlite")
        backend_gauge = Gauge("dataforge_backend", "Storage backend type", ["backend"], registry=registry)
        backend_gauge.labels(backend=backend).set(1)
    except (AttributeError, ImportError, RuntimeError):
        backend_ok = 0
        with _METRICS_ERRORS_LOCK:
            METRICS_COLLECTION_ERRORS += 1
        logger.exception("Metrics: backend collection failed")

    backend_ok_gauge = Gauge(
        "dataforge_backend_collection_ok",
        "Whether storage backend metrics collected successfully",
        registry=registry,
    )
    backend_ok_gauge.set(backend_ok)

    # Worker queue stats
    queue_ok = 1
    try:
        from app.worker_queue import get_worker_queue

        q = get_worker_queue()
        q_status = await run_in_threadpool(q.get_status)
        queue_pending = Gauge("dataforge_queue_pending", "Pending tasks in worker queue", registry=registry)
        queue_pending.set(q_status.get("pending", 0))
        queue_running = Gauge("dataforge_queue_running", "Running tasks in worker queue", registry=registry)
        queue_running.set(q_status.get("running", 0))
        queue_dead_letter = Gauge("dataforge_queue_dead_letter", "Dead letter queue size", registry=registry)
        queue_dead_letter.set(q_status.get("dead_letter", 0))
    except (AttributeError, ImportError, RuntimeError):
        queue_ok = 0
        with _METRICS_ERRORS_LOCK:
            METRICS_COLLECTION_ERRORS += 1
        logger.exception("Metrics: queue collection failed")

    queue_ok_gauge = Gauge(
        "dataforge_queue_collection_ok",
        "Whether worker queue metrics collected successfully",
        registry=registry,
    )
    queue_ok_gauge.set(queue_ok)

    # Worker failure counters
    from app.metrics_collector import get_worker_failures

    failures = get_worker_failures()
    if failures:
        failure_gauge = Gauge(
            "dataforge_worker_failures_total",
            "Total worker failures by task type",
            ["task_type"],
            registry=registry,
        )
        for task_type, count in failures.items():
            failure_gauge.labels(task_type=task_type).set(count)

    # Worker heartbeat health gauges
    try:
        repo = get_job_repository()
        worker_healths = repo.get_all_worker_healths(ttl_seconds=60)
        if worker_healths:
            # ``pid`` is part of the label set so multiple workers
            # sharing the same ``hostname`` (a common pattern when
            # scaling up within a single host, or when the same host
            # name appears under different PIDs in tests) do not
            # collide on the (worker_id, hostname) tuple. The
            # ``worker_heartbeats`` row already carries a ``pid``
            # column (see ``record_worker_heartbeat``) so we just
            # project it through here.
            hb_alive_gauge = Gauge(
                "dataforge_worker_heartbeat_alive",
                "Whether a worker has a recent heartbeat (1=alive, 0=dead)",
                ["worker_id", "hostname", "pid"],
                registry=registry,
            )
            hb_age_gauge = Gauge(
                "dataforge_worker_heartbeat_age_seconds",
                "Seconds since the last worker heartbeat (-1 if never received)",
                ["worker_id", "hostname", "pid"],
                registry=registry,
            )
            for wh in worker_healths:
                wid = str(wh.get("worker_id", "unknown"))
                hostname = str(wh.get("hostname", ""))
                pid = str(wh.get("pid") or "unknown")
                hb_alive_gauge.labels(worker_id=wid, hostname=hostname, pid=pid).set(1 if wh.get("alive") else 0)
                last_hb = wh.get("last_heartbeat")
                if last_hb:
                    try:
                        import datetime as _dt

                        age = (_dt.datetime.now(_dt.UTC) - _dt.datetime.fromisoformat(str(last_hb))).total_seconds()
                    except (ValueError, TypeError):
                        age = -1.0
                else:
                    age = -1.0
                hb_age_gauge.labels(worker_id=wid, hostname=hostname, pid=pid).set(age)
    except (AttributeError, ImportError, RuntimeError):
        with _METRICS_ERRORS_LOCK:
            METRICS_COLLECTION_ERRORS += 1
        logger.debug("Metrics: worker heartbeat collection failed")

    # Request duration histogram
    from app.metrics_collector import get_health_check_latencies, get_request_latencies

    if settings.METRICS_ENABLE_HISTOGRAMS:
        req_latencies = get_request_latencies()
        if req_latencies:
            buckets = [float(b.strip()) for b in settings.METRICS_HISTOGRAM_BUCKETS.split(",") if b.strip()]
            req_hist = Histogram(
                "dataforge_request_duration_seconds",
                "API request duration in seconds",
                buckets=buckets,
                registry=registry,
            )
            for v in req_latencies:
                req_hist.observe(v)

    # Backend health check latency histogram
    if settings.METRICS_ENABLE_HISTOGRAMS:
        health_latencies = get_health_check_latencies()
        if health_latencies:
            buckets = [float(b.strip()) for b in settings.METRICS_HISTOGRAM_BUCKETS.split(",") if b.strip()]
            health_hist = Histogram(
                "dataforge_backend_health_check_duration_seconds",
                "Backend health check duration in seconds",
                buckets=buckets,
                registry=registry,
            )
            for v in health_latencies:
                health_hist.observe(v)

    # Cumulative collection errors
    error_total_gauge = Gauge(
        "dataforge_metrics_collection_error_total",
        "Total collection errors encountered",
        registry=registry,
    )
    error_total_gauge.set(METRICS_COLLECTION_ERRORS)

    # Cumulative error counts
    from app.metrics_collector import get_errors, get_llm_calls, get_requests_total

    errors_dict = get_errors()
    errors_gauge = Gauge("dataforge_errors_total", "Cumulative error count by type", ["type"], registry=registry)
    for err_type, count in errors_dict.items():
        errors_gauge.labels(type=err_type).set(count)
    if "database" not in errors_dict:
        errors_gauge.labels(type="database").set(0)

    # Cumulative LLM calls count
    llm_gauge = Gauge("dataforge_llm_calls_total", "Cumulative LLM calls count", registry=registry)
    llm_gauge.set(get_llm_calls())

    # Cumulative requests count
    requests_gauge = Gauge("dataforge_requests_total", "Total requests count", registry=registry)
    requests_gauge.set(get_requests_total())

    # Extraction-method distribution. One row per method so a
    # spike in ``regex`` is visible alongside the structured
    # methods.
    from app.metrics_collector import (
        get_anti_bot_classifications,
        get_auth_profile_ops,
        get_browser_launch_outcomes,
        get_csp_violations,
        get_export_outcomes,
        get_extraction_method_counts,
        get_rate_limit_global_hits,
        get_rate_limit_per_ip_hits,
        get_repo_query_latencies,
        get_retention_ops,
        get_scheduled_job_ops,
        get_signup_outcomes,
        get_ssrf_rejects,
        get_workflow_ops,
    )

    method_counts = get_extraction_method_counts()
    if method_counts:
        method_gauge = Gauge(
            "dataforge_extraction_method_total",
            "Extraction method distribution",
            ["method"],
            registry=registry,
        )
        for method, count in method_counts.items():
            method_gauge.labels(method=method).set(count)

    # Anti-bot classification counts.
    classifications = get_anti_bot_classifications()
    if classifications:
        cls_gauge = Gauge(
            "dataforge_anti_bot_classifications_total",
            "Anti-bot classification counts",
            ["classification"],
            registry=registry,
        )
        for cls, count in classifications.items():
            cls_gauge.labels(classification=cls).set(count)

    # Export generation outcomes by format and outcome.
    export_outcomes = get_export_outcomes()
    if export_outcomes:
        export_gauge = Gauge(
            "dataforge_export_outcomes_total",
            "Export generation outcomes by format",
            ["format", "outcome"],
            registry=registry,
        )
        for fmt, outcomes in export_outcomes.items():
            for outcome, count in outcomes.items():
                export_gauge.labels(format=fmt, outcome=outcome).set(count)

    # Browser launch outcomes.
    browser_outcomes = get_browser_launch_outcomes()
    if browser_outcomes:
        browser_gauge = Gauge(
            "dataforge_browser_launch_total",
            "Playwright browser launch outcomes",
            ["outcome"],
            registry=registry,
        )
        for outcome, count in browser_outcomes.items():
            browser_gauge.labels(outcome=outcome).set(count)

    # SSRF validation rejects.
    ssrf_rejects = get_ssrf_rejects()
    if ssrf_rejects:
        ssrf_gauge = Gauge(
            "dataforge_ssrf_rejects_total",
            "SSRF validation rejects by reason",
            ["reason"],
            registry=registry,
        )
        for reason, count in ssrf_rejects.items():
            ssrf_gauge.labels(reason=reason).set(count)

    # Repository query latencies — p50 / p95 derived from the ring buffer.
    repo_latencies = get_repo_query_latencies()
    if repo_latencies:
        sorted_lat = sorted(repo_latencies)
        n = len(sorted_lat)
        p50 = sorted_lat[min(n - 1, int(0.50 * n))]
        p95 = sorted_lat[min(n - 1, int(0.95 * n))]
        repo_gauge = Gauge(
            "dataforge_repo_query_latency_seconds",
            "Repository query latency percentiles (p50, p95)",
            ["quantile"],
            registry=registry,
        )
        repo_gauge.labels(quantile="0.5").set(p50)
        repo_gauge.labels(quantile="0.95").set(p95)

    # CSP violations.
    csp_violations = get_csp_violations()
    if csp_violations:
        csp_gauge = Gauge(
            "dataforge_csp_violations_total",
            "CSP violation counts by directive",
            ["directive"],
            registry=registry,
        )
        for directive, count in csp_violations.items():
            csp_gauge.labels(directive=directive).set(count)

    # Rate limit hit counters
    rl_global = Gauge(
        "dataforge_rate_limit_global_hits_total",
        "Cumulative rate limit hits by the aggregate global tier",
        registry=registry,
    )
    rl_global.set(get_rate_limit_global_hits())
    rl_per_ip = Gauge(
        "dataforge_rate_limit_per_ip_hits_total",
        "Cumulative rate limit hits by the per-IP fair-sharing tier",
        registry=registry,
    )
    rl_per_ip.set(get_rate_limit_per_ip_hits())

    # Auth profile operations
    auth_profile_ops = get_auth_profile_ops()
    if auth_profile_ops:
        apo_gauge = Gauge(
            "dataforge_auth_profile_ops_total",
            "Auth profile operation counts by action",
            ["action"],
            registry=registry,
        )
        for action, count in auth_profile_ops.items():
            apo_gauge.labels(action=action).set(count)

    # Workflow operations
    workflow_ops = get_workflow_ops()
    if workflow_ops:
        wo_gauge = Gauge(
            "dataforge_workflow_ops_total",
            "Workflow operation counts by action",
            ["action"],
            registry=registry,
        )
        for action, count in workflow_ops.items():
            wo_gauge.labels(action=action).set(count)

    # Signup outcomes
    signup_outcomes = get_signup_outcomes()
    if signup_outcomes:
        so_gauge = Gauge(
            "dataforge_signup_outcomes_total",
            "Signup outcome counts",
            ["outcome"],
            registry=registry,
        )
        for outcome, count in signup_outcomes.items():
            so_gauge.labels(outcome=outcome).set(count)

    # Scheduled job operations
    scheduled_job_ops = get_scheduled_job_ops()
    if scheduled_job_ops:
        sjo_gauge = Gauge(
            "dataforge_scheduled_job_ops_total",
            "Scheduled job operation counts by action",
            ["action"],
            registry=registry,
        )
        for action, count in scheduled_job_ops.items():
            sjo_gauge.labels(action=action).set(count)

    # Retention operations
    retention_ops = get_retention_ops()
    if retention_ops:
        ro_gauge = Gauge(
            "dataforge_retention_ops_total",
            "Data retention operation counts by action",
            ["action"],
            registry=registry,
        )
        for action, count in retention_ops.items():
            ro_gauge.labels(action=action).set(count)

    return Response(content=generate_latest(registry), media_type="text/plain")
