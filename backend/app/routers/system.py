"""System Router — endpoints for metrics, health, system status, and URL analysis."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import Gauge, Histogram
from prometheus_client.core import CollectorRegistry
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.globals import _jobs_store_lock, config_view, jobs_store, recycle_bin_store
from app.middlewares import rate_limiter as _rate_limiter
from app.models import AuditLogResponse
from app.selector_discovery import analyze_url_for_fields
from app.storage_interface import get_job_repository
from app.url_analyzer import analyze_url as _url_analyze
from app.url_safety import validate_public_http_url
from app.utils.aup import require_aup_accepted
from app.utils.datetime_normalization import parse_datetime
from app.utils.rbac import UserRole, require_principal, require_role

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


class AcquisitionMode(StrEnum):
    STANDARD = "standard"
    AGGRESSIVE = "aggressive"
    DEEP_SCAN = "deep_scan"


class URLPreviewRequest(BaseModel):
    url: str = Field(..., max_length=2048, description="The URL to analyze for data extraction")
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


@router.get("/api/system/storage/status", response_model=dict)
async def storage_status(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Detailed storage backend status. Requires operator or admin."""
    repo = get_job_repository()
    return await run_in_threadpool(repo.get_storage_status)


@router.get("/api/system/status", response_model=dict)
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
    except (AttributeError, ImportError, RuntimeError) as exc:
        logger.warning("Failed to fetch worker health status: %s", exc)

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
    except (AttributeError, ImportError, RuntimeError) as exc:
        logger.warning("Failed to fetch queue status: %s", exc)

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


# ─── Audit Log Endpoint ────────────────────────────────────────────────


@router.get("/api/system/audit-log", response_model=AuditLogResponse)
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
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        logger.debug("metrics_collector not available, skipping CSP violation metric: %s", exc)

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


# ─── Rate Limiter Stats ─────────────────────────────────────────────────


@router.get("/api/system/extraction-health", response_model=dict)
async def extraction_health(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Extraction health dashboard data.

    Returns aggregated extraction success rate, p95 latency by cascade
    layer, and top 10 failing domains over the last hour.

    Requires operator or admin role.
    """
    import datetime as _dt

    from app.metrics_collector import (
        get_domain_extraction_counts,
        get_extraction_failure_counts,
        get_request_latencies,
    )

    now = _dt.datetime.now(_dt.UTC)

    # ── Success rate ───────────────────────────────────────────────────
    domain_counts = get_domain_extraction_counts()
    total_attempted = 0
    total_succeeded = 0
    for _key, counts in domain_counts.items():
        if _key.startswith(("strategy:", "layer:")):
            continue
        att = counts.get("attempted", 0) or 0
        suc = counts.get("succeeded", 0) or counts.get("success", 0) or 0
        total_attempted += att
        total_succeeded += suc

    success_rate = (total_succeeded / total_attempted) if total_attempted > 0 else 1.0

    # ── p95 latency by cascade layer ───────────────────────────────────
    # Per-layer latency is not yet timestamped in metrics_collector, so we
    # approximate from request_latencies with layer metadata stored in
    # domain_extraction_counts as ``layer:<name>`` entries.
    layer_latencies: dict[str, dict[str, float]] = {}
    # Compute a global p95 from request latencies and attribute it to
    # known layers.  When per-layer ring buffers are added later, this
    # can be replaced with direct per-layer p95.
    request_lats = get_request_latencies()
    if request_lats:
        sorted_lats = sorted(request_lats)
        n = len(sorted_lats)
        p95_idx = min(n - 1, int(0.95 * n))
        global_p95 = sorted_lats[p95_idx]
    else:
        global_p95 = 0.0

    for _key, counts in domain_counts.items():
        if _key.startswith("layer:"):
            layer_name = _key[len("layer:") :]
            layer_latencies[layer_name] = {"p95_latency_seconds": global_p95}

    # ── Top 10 failing domains ─────────────────────────────────────────
    domain_failures: list[dict[str, object]] = []
    for _key, counts in domain_counts.items():
        if _key.startswith(("strategy:", "layer:")):
            continue
        fail_count = counts.get("failed", 0) or counts.get("failure", 0) or 0
        if fail_count > 0:
            domain_failures.append({"domain": _key, "failure_count": fail_count})
    domain_failures.sort(key=lambda d: int(str(d["failure_count"])), reverse=True)
    top_failing = domain_failures[:10]

    # ── Failure categories (bonus for the dashboard) ───────────────────
    failure_categories = get_extraction_failure_counts()

    return {
        "window": "1h",
        "generated_at": now.isoformat(),
        "success_rate": round(success_rate, 4),
        "total_attempted": total_attempted,
        "total_succeeded": total_succeeded,
        "p95_latency_by_layer": layer_latencies,
        "top_failing_domains": top_failing,
        "failure_categories": failure_categories,
    }


@router.get("/api/system/extraction-rate", response_model=dict)
async def extraction_rate(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Extraction request rate over multiple intervals.

    Returns req/sec over 1m, 5m, and 15m windows based on the
    timestamped request ring buffer in the metrics collector.

    Requires operator or admin role.
    """
    import datetime as _dt

    from app.metrics_collector import get_request_rate, get_requests_total

    now = _dt.datetime.now(_dt.UTC)
    total = get_requests_total()
    rates: dict[str, float] = {}
    for label, window_secs in [("1m", 60), ("5m", 300), ("15m", 900)]:
        rates[label] = round(get_request_rate(window_secs), 4)

    return {
        "generated_at": now.isoformat(),
        "requests_total": total,
        "rate_per_second": rates,
    }


# ─── Rate Limiter Stats ─────────────────────────────────────────────────


@router.get("/api/system/rate-limit-stats", response_model=dict)
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


@router.post("/api/url/analyze", response_model=dict)
async def analyze_url(
    req: URLPreviewRequest,
    _principal: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
    _aup_check: Annotated[dict[str, Any], Depends(require_aup_accepted)],
):
    """Analyze a URL and auto-detect fields for the authenticated user's schema."""
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
        get_job_durations,
        get_llm_calls,
        get_metrics_collection_errors,
        get_page_fetch_durations,
        get_product_totals,
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

    for counter_name, counter_value in get_product_totals().items():
        lines.append(_basic_metric_line(f"dataforge_{counter_name}", counter_value))

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

                    last_hb_dt = parse_datetime(str(last_hb))
                    age = (_dt.datetime.now(_dt.UTC) - last_hb_dt).total_seconds() if last_hb_dt else -1.0
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

        job_durations = get_job_durations()
        if job_durations:
            lines.append(_basic_metric_line("dataforge_job_duration_seconds_count", len(job_durations)))
            lines.append(_basic_metric_line("dataforge_job_duration_seconds_sum", sum(job_durations)))

        page_fetch_durations = get_page_fetch_durations()
        if page_fetch_durations:
            lines.append(_basic_metric_line("dataforge_page_fetch_duration_seconds_count", len(page_fetch_durations)))
            lines.append(_basic_metric_line("dataforge_page_fetch_duration_seconds_sum", sum(page_fetch_durations)))

    lines.append(_basic_metric_line("dataforge_metrics_collection_error_total", get_metrics_collection_errors()))

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

    # EXPERIMENTAL: domain_runtime_policy is a research-shell module.
    # Surface its metrics only when experimental routes are enabled.
    try:
        if settings.ENABLE_EXPERIMENTAL_ROUTES:
            from app.domain_runtime_policy import get_domain_runtime_policy

            for domain, summary in get_domain_runtime_policy().get_summary().items():
                total_attempts = int(str(summary.get("total_attempts", 0) or 0))
                if total_attempts <= 0:
                    continue
                rate = float(str(summary.get("failure_rate", 0.0) or 0.0))
                lines.append(_basic_metric_line("dataforge_domain_failure_rate", rate, {"domain": domain}))
    except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        logger.debug("Metrics fallback: domain failure-rate collection failed")

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

    # LLM cascade breaker state — alerts on operators' dashboards.
    try:
        from app.llm_bridge import get_silent_failure_counts
        from app.utils.llm_circuit_breaker import get_llm_cascade_breaker

        breaker_snap = get_llm_cascade_breaker().snapshot()
        breaker_state_value = {
            "closed": 0,
            "half_open": 1,
            "open": 2,
        }.get(str(breaker_snap.get("state", "closed")), 0)
        lines.append(
            _basic_metric_line(
                "llm_cascade_state",
                breaker_state_value,
            ),
        )
        lines.append(
            _basic_metric_line(
                "llm_cascade_consecutive_failures_total",
                int(breaker_snap.get("consecutive_failures", 0) or 0),  # type: ignore[call-overload]
            ),
        )
        for name, count in get_silent_failure_counts().items():
            lines.append(
                _basic_metric_line(
                    "llm_silent_failure_total",
                    count,
                    {"function": name},
                ),
            )
    except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        logger.debug("Metrics fallback: LLM cascade metrics collection failed")

    return "\n".join(lines) + "\n"


def _reject_metrics_without_token() -> JSONResponse | None:
    """Pre-flight check: in production, refuse to serve /metrics if METRICS_TOKEN is unset."""
    if not settings.METRICS_TOKEN:
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
    return None


def _authenticate_metrics_request(request: Request) -> JSONResponse | None:
    if not settings.METRICS_TOKEN:
        return None
    auth_header = request.headers.get("Authorization", "")
    api_key_header = request.headers.get("X-API-Key", "")
    bearer_value = ""
    if auth_header:
        scheme, _, _token = auth_header.partition(" ")
        if scheme.lower() == "bearer":
            bearer_value = _token
    if not secrets.compare_digest(bearer_value, settings.METRICS_TOKEN) and not secrets.compare_digest(
        api_key_header,
        settings.METRICS_TOKEN,
    ):
        return JSONResponse(
            status_code=403,
            content={
                "detail": "Invalid or missing metrics token. Provide Authorization: Bearer <token> or X-API-Key header.",
            },
        )
    return None


def _add_job_gauges(registry) -> None:
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
    recycle_gauge = Gauge("dataforge_recycle_bin_total", "Total jobs in recycle bin", registry=registry)
    with _jobs_store_lock:
        recycle_gauge.set(len(recycle_bin_store))


def _add_config_gauges(registry) -> None:
    for key, val in config_view().items():
        g = Gauge(f"dataforge_config_{key}", f"Config value for {key}", registry=registry)
        with contextlib.suppress(TypeError, ValueError):
            g.set(float(val))


def _add_backend_gauges(registry) -> None:
    from app.metrics_collector import record_metrics_collection_error

    backend_ok = 1
    try:
        repo = get_job_repository()
        backend = getattr(repo, "backend", "sqlite")
        backend_gauge = Gauge("dataforge_backend", "Storage backend type", ["backend"], registry=registry)
        backend_gauge.labels(backend=backend).set(1)
    except (AttributeError, ImportError, RuntimeError):
        backend_ok = 0
        record_metrics_collection_error()
        logger.exception("Metrics: backend collection failed")
    backend_ok_gauge = Gauge(
        "dataforge_backend_collection_ok",
        "Whether storage backend metrics collected successfully",
        registry=registry,
    )
    backend_ok_gauge.set(backend_ok)


async def _add_queue_gauges(registry) -> None:
    from app.metrics_collector import record_metrics_collection_error

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
        record_metrics_collection_error()
        logger.exception("Metrics: queue collection failed")
    queue_ok_gauge = Gauge(
        "dataforge_queue_collection_ok",
        "Whether worker queue metrics collected successfully",
        registry=registry,
    )
    queue_ok_gauge.set(queue_ok)


def _add_worker_gauges(registry) -> None:
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


def _add_heartbeat_gauges(registry) -> None:
    import datetime as _dt

    from app.metrics_collector import record_metrics_collection_error

    try:
        repo = get_job_repository()
        worker_healths = repo.get_all_worker_healths(ttl_seconds=60)
        if worker_healths:
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
                        last_hb_dt = parse_datetime(str(last_hb))
                        age = (_dt.datetime.now(_dt.UTC) - last_hb_dt).total_seconds() if last_hb_dt else -1.0
                    except (ValueError, TypeError):
                        age = -1.0
                else:
                    age = -1.0
                hb_age_gauge.labels(worker_id=wid, hostname=hostname, pid=pid).set(age)
    except (AttributeError, ImportError, RuntimeError):
        record_metrics_collection_error()
        logger.debug("Metrics: worker heartbeat collection failed")


def _add_histogram_gauges(registry) -> None:
    from app.metrics_collector import (
        get_health_check_latencies,
        get_job_durations,
        get_page_fetch_durations,
        get_request_latencies,
    )

    if not settings.METRICS_ENABLE_HISTOGRAMS:
        return
    buckets = [float(b.strip()) for b in settings.METRICS_HISTOGRAM_BUCKETS.split(",") if b.strip()]

    req_latencies = get_request_latencies()
    if req_latencies:
        req_hist = Histogram(
            "dataforge_request_duration_seconds",
            "API request duration in seconds",
            buckets=buckets,
            registry=registry,
        )
        for v in req_latencies:
            req_hist.observe(v)

    health_latencies = get_health_check_latencies()
    if health_latencies:
        health_hist = Histogram(
            "dataforge_backend_health_check_duration_seconds",
            "Backend health check duration in seconds",
            buckets=buckets,
            registry=registry,
        )
        for v in health_latencies:
            health_hist.observe(v)

    job_durations = get_job_durations()
    if job_durations:
        job_hist = Histogram(
            "dataforge_job_duration_seconds",
            "Terminal job duration in seconds",
            buckets=buckets,
            registry=registry,
        )
        for v in job_durations:
            job_hist.observe(v)

    page_fetch_durations = get_page_fetch_durations()
    if page_fetch_durations:
        page_fetch_hist = Histogram(
            "dataforge_page_fetch_duration_seconds",
            "Page fetch attempt duration in seconds",
            buckets=buckets,
            registry=registry,
        )
        for v in page_fetch_durations:
            page_fetch_hist.observe(v)


def _add_counter_gauges(registry) -> None:
    from app.metrics_collector import (
        get_errors,
        get_llm_calls,
        get_metrics_collection_errors,
        get_product_totals,
        get_requests_total,
    )

    error_total_gauge = Gauge(
        "dataforge_metrics_collection_error_total",
        "Total collection errors encountered",
        registry=registry,
    )
    error_total_gauge.set(get_metrics_collection_errors())

    errors_dict = get_errors()
    errors_gauge = Gauge("dataforge_errors_total", "Cumulative error count by type", ["type"], registry=registry)
    for err_type, count in errors_dict.items():
        errors_gauge.labels(type=err_type).set(count)
    if "database" not in errors_dict:
        errors_gauge.labels(type="database").set(0)

    llm_gauge = Gauge("dataforge_llm_calls_total", "Cumulative LLM calls count", registry=registry)
    llm_gauge.set(get_llm_calls())

    requests_gauge = Gauge("dataforge_requests_total", "Total requests count", registry=registry)
    requests_gauge.set(get_requests_total())

    for counter_name, counter_value in get_product_totals().items():
        product_gauge = Gauge(
            f"dataforge_{counter_name}",
            f"Product counter {counter_name}",
            registry=registry,
        )
        product_gauge.set(counter_value)


def _add_method_and_classification_gauges(registry) -> None:
    from app.metrics_collector import (
        get_anti_bot_classifications,
        get_browser_launch_outcomes,
        get_export_outcomes,
        get_extraction_method_counts,
        get_ssrf_rejects,
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


def _add_domain_latency_csp_rate_gauges(registry) -> None:
    from app.metrics_collector import (
        get_csp_violations,
        get_rate_limit_global_hits,
        get_rate_limit_per_ip_hits,
        get_repo_query_latencies,
        record_metrics_collection_error,
    )

    # EXPERIMENTAL: domain_runtime_policy is a research-shell module.
    try:
        if settings.ENABLE_EXPERIMENTAL_ROUTES:
            from app.domain_runtime_policy import get_domain_runtime_policy

            domain_summaries = get_domain_runtime_policy().get_summary()
            if domain_summaries:
                domain_failure_gauge = Gauge(
                    "dataforge_domain_failure_rate",
                    "Per-domain failure ratio from recorded fetch attempts",
                    ["domain"],
                    registry=registry,
                )
                for domain, summary in domain_summaries.items():
                    total_attempts = int(str(summary.get("total_attempts", 0) or 0))
                    if total_attempts <= 0:
                        continue
                    rate = float(str(summary.get("failure_rate", 0.0) or 0.0))
                    domain_failure_gauge.labels(domain=domain).set(rate)
    except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        record_metrics_collection_error()
        logger.debug("Metrics: domain failure-rate collection failed")

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


def _add_ops_gauges(registry) -> None:
    from app.metrics_collector import (
        get_auth_profile_ops,
        get_retention_ops,
        get_scheduled_job_ops,
        get_signup_outcomes,
        get_workflow_ops,
    )

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


@router.get("/metrics", response_model=None)
async def metrics(request: Request):
    """Prometheus-formatted metrics endpoint for DataForge scraper."""
    rejection = _reject_metrics_without_token()
    if rejection:
        return rejection
    rejection = _authenticate_metrics_request(request)
    if rejection:
        return rejection

    try:
        from prometheus_client import generate_latest
    except ModuleNotFoundError:
        content = await run_in_threadpool(_render_basic_metrics_text)
        return Response(content=content, media_type="text/plain")

    registry = CollectorRegistry()

    _add_job_gauges(registry)
    _add_config_gauges(registry)
    _add_backend_gauges(registry)
    await _add_queue_gauges(registry)
    _add_worker_gauges(registry)
    _add_heartbeat_gauges(registry)
    _add_histogram_gauges(registry)
    _add_counter_gauges(registry)
    _add_method_and_classification_gauges(registry)
    _add_domain_latency_csp_rate_gauges(registry)
    _add_ops_gauges(registry)

    return Response(content=generate_latest(registry), media_type="text/plain")
