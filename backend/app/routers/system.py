"""
System Router — endpoints for metrics, health, system status, diagnostics, and URL analysis.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import secrets
import zipfile
from enum import Enum

from app.config import settings
from app.utils.rbac import UserRole, require_role
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


def get_job_repository():
    import app.main
    return app.main.get_job_repository()
from app.globals import CONFIG, jobs_store, recycle_bin_store
from app.selector_discovery import analyze_url_for_fields
from app.url_safety import validate_public_http_url

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])

class AcquisitionMode(str, Enum):
    STANDARD = "standard"
    AGGRESSIVE = "aggressive"
    DEEP_SCAN = "deep_scan"

class URLPreviewRequest(BaseModel):
    url: str = Field(..., description="The URL to analyze for data extraction")
    search_params: dict[str, str] | None = Field(
        default=None,
        description="Optional search parameters to submit to the site's search form"
    )
    acquisition_mode: AcquisitionMode = Field(
        default=AcquisitionMode.STANDARD,
        description="Acquisition mode: standard, aggressive, or deep_scan"
    )

# ─── System / Storage Status ───────────────────────────────────────────

@router.get("/api/system/storage/status")
async def storage_status():
    """Detailed storage backend status."""
    repo = get_job_repository()
    if hasattr(repo, "health_check"):
        health = repo.health_check()
        return {
            "backend": "postgres",
            "ok": health.get("ok", False),
            "error": health.get("error"),
            "schema_version": health.get("schema_version", 0),
            "expected_version": health.get("expected_version", 0),
            "job_count": health.get("job_count", 0),
            "recycle_bin_count": health.get("recycle_bin_count", 0),
        }
    from app.job_store import get_storage_status
    return get_storage_status()

@router.get("/api/system/status")
async def system_status():
    """Detailed system and active jobs overview."""
    from app.models import JobStatus

    counts = {s.value: 0 for s in JobStatus}
    for job in jobs_store.values():
        status_key = str(job.status.value if isinstance(job.status, JobStatus) else job.status)
        if status_key not in counts:
            counts[status_key] = 0
        counts[status_key] += 1

    active = (
        counts.get(JobStatus.PENDING.value, 0)
        + counts.get(JobStatus.DISCOVERING.value, 0)
        + counts.get(JobStatus.RUNNING.value, 0)
    )

    from app.state_store import get_state_file_path

    repo = get_job_repository()
    backend = getattr(repo, "backend", "sqlite")
    response = {
        "status": "online",
        "backend": backend,
        "jobs": {
            "total": len(jobs_store),
            "active": active,
            "completed": counts.get(JobStatus.COMPLETED.value, 0),
            "degraded": counts.get(JobStatus.DEGRADED.value, 0),
            "empty_result": counts.get(JobStatus.EMPTY_RESULT.value, 0),
            "failed": counts.get(JobStatus.FAILED.value, 0),
            "canceled": counts.get(JobStatus.CANCELED.value, 0),
        },
        "runtime_limits": CONFIG,
    }
    if settings.ENV.lower() != "production":
        response["state_file"] = str(get_state_file_path())
    return response

# ─── Diagnostics ZIP Export ─────────────────────────────────────────────

@router.get("/api/system/diagnostics/export")
async def export_system_diagnostics(_role=Depends(require_role([UserRole.ADMIN]))):
    """Generates and exports an authenticated and sanitized system diagnostics ZIP bundle."""
    # Regular expressions for PII sanitization
    email_regex = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
    phone_regex = re.compile(r"\+?\b\d[\d\s()\-]{8,14}\d\b")
    sensitive_keys = {
        "authorization", "auth", "api_key", "key", "password", "token", "secret",
        "signature", "alert_webhook_url", "credential", "session", "cookie", "bearer",
        "private", "client_secret", "api_secret", "access_key", "secret_key"
    }

    def sanitize_value(val, _depth=0, _max_depth=50):
        if _depth >= _max_depth:
            return val
        if isinstance(val, str):
            val = email_regex.sub("<redacted_email>", val)
            val = phone_regex.sub("<redacted_phone>", val)
            return val
        elif isinstance(val, dict):
            return {
                k: (
                    "********"
                    if any(s in k.lower() for s in sensitive_keys)
                    else sanitize_value(v, _depth=_depth + 1, _max_depth=_max_depth)
                )
                for k, v in val.items()
            }
        elif isinstance(val, list):
            return [sanitize_value(item, _depth=_depth + 1, _max_depth=_max_depth) for item in val]
        else:
            return val

    # 1. anonymized_state.json
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
    except Exception as e:
        logger.exception("Failed to build selector decay snapshots for diagnostics: %s", e)
        selector_decay_snapshots = {"error": {"message": str(e)}}

    # 4. telemetry_snapshots.json
    telemetry_snapshots = []
    try:
        from app.semantic_world_state import get_world_state
        ws = get_world_state()
        if hasattr(ws, "_observability") and ws._observability:
            telemetry_snapshots = sanitize_value(ws._observability.telemetry)
    except Exception as e:
        logger.exception("Failed to build telemetry snapshots for diagnostics: %s", e)
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

# ─── URL Analyzer Endpoint ──────────────────────────────────────────────

@router.post("/api/url/analyze")
async def analyze_url(
    req: URLPreviewRequest, _role: UserRole = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Analyze a URL and auto-detect what data fields can be extracted."""
    try:
        validate_public_http_url(req.url)
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={
                "url": req.url,
                "error": f"URL failed security validation: {e}",
                "page_structure": "unknown",
                "structure_confidence": 0.0,
                "estimated_record_count": 0,
                "item_container": None,
                "suggested_fields": [],
                "anti_bot_score": 0.0,
            },
        )

    URL_ANALYZER_TIMEOUT = settings.URL_ANALYZER_TIMEOUT

    try:
        result = await asyncio.wait_for(
            analyze_url_for_fields(url=req.url, search_params=req.search_params, acquisition_mode=req.acquisition_mode),
            timeout=URL_ANALYZER_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("[URLAnalyzer] Timeout after %ds analyzing %s", URL_ANALYZER_TIMEOUT, req.url)
        return JSONResponse(
            status_code=408,
            content={
                "url": req.url,
                "error": (
                    f"Analysis timed out after {URL_ANALYZER_TIMEOUT} seconds. "
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

    if "error" in result and result["error"]:
        return JSONResponse(status_code=422, content=result)

    return result

# ─── Prometheus /metrics ────────────────────────────────────────────────

METRICS_COLLECTION_ERRORS = 0

def _prometheus_label_text(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    escaped = {key: str(value).replace("\\", "\\\\").replace('"', '\\"') for key, value in labels.items()}
    return "{" + ",".join(f'{key}="{value}"' for key, value in escaped.items()) + "}"

def _basic_metric_line(name: str, value: float | int, labels: dict[str, str] | None = None) -> str:
    return f"{name}{_prometheus_label_text(labels or {})} {value}"

def _render_basic_metrics_text() -> str:
    """Render a minimal Prometheus exposition if prometheus_client is unavailable."""
    from app.metrics_collector import (
        get_errors,
        get_health_check_latencies,
        get_llm_calls,
        get_request_latencies,
        get_requests_total,
        get_worker_failures,
    )
    from app.models import JobStatus

    lines: list[str] = []

    counts = {s.value: 0 for s in JobStatus}
    for job in jobs_store.values():
        status_key = str(job.status.value if isinstance(job.status, JobStatus) else job.status)
        counts[status_key] = counts.get(status_key, 0) + 1
    for status, count in counts.items():
        lines.append(_basic_metric_line("dataforge_jobs_total", count, {"status": status}))

    lines.append(_basic_metric_line("dataforge_recycle_bin_total", len(recycle_bin_store)))

    backend_ok = 1
    try:
        repo = get_job_repository()
        backend = getattr(repo, "backend", "sqlite")
        lines.append(_basic_metric_line("dataforge_backend", 1, {"backend": backend}))
    except Exception as e:
        backend_ok = 0
        logger.error("Metrics fallback: backend collection failed: %s", e)
    lines.append(_basic_metric_line("dataforge_backend_collection_ok", backend_ok))

    queue_ok = 1
    try:
        from app.worker_queue import get_worker_queue
        q_status = get_worker_queue().get_status()
        lines.append(_basic_metric_line("dataforge_queue_pending", q_status.get("pending", 0)))
        lines.append(_basic_metric_line("dataforge_queue_running", q_status.get("running", 0)))
        lines.append(_basic_metric_line("dataforge_queue_dead_letter", q_status.get("dead_letter", 0)))
    except Exception as e:
        queue_ok = 0
        logger.error("Metrics fallback: queue collection failed: %s", e)
    lines.append(_basic_metric_line("dataforge_queue_collection_ok", queue_ok))

    for task_type, count in get_worker_failures().items():
        lines.append(_basic_metric_line("dataforge_worker_failures_total", count, {"task_type": task_type}))

    if settings.METRICS_ENABLE_HISTOGRAMS:
        request_latencies = get_request_latencies()
        if request_latencies:
            lines.append(_basic_metric_line("dataforge_request_duration_seconds_count", len(request_latencies)))
            lines.append(_basic_metric_line("dataforge_request_duration_seconds_sum", sum(request_latencies)))

        health_latencies = get_health_check_latencies()
        if health_latencies:
            lines.append(
                _basic_metric_line("dataforge_backend_health_check_duration_seconds_count", len(health_latencies))
            )
            lines.append(
                _basic_metric_line("dataforge_backend_health_check_duration_seconds_sum", sum(health_latencies))
            )

    lines.append(_basic_metric_line("dataforge_metrics_collection_error_total", METRICS_COLLECTION_ERRORS))

    errors_dict = get_errors()
    for err_type, count in errors_dict.items():
        lines.append(_basic_metric_line("dataforge_errors_total", count, {"type": err_type}))
    if "database" not in errors_dict:
        lines.append(_basic_metric_line("dataforge_errors_total", 0, {"type": "database"}))

    lines.append(_basic_metric_line("dataforge_llm_calls_total", get_llm_calls()))
    lines.append(_basic_metric_line("dataforge_requests_total", get_requests_total()))

    return "\n".join(lines) + "\n"

@router.get("/metrics")
async def metrics(request: Request):
    """Prometheus-formatted metrics endpoint for DataForge scraper."""
    # Auth check
    if settings.METRICS_TOKEN:
        auth_header = request.headers.get("Authorization", "")
        api_key_header = request.headers.get("X-API-Key", "")
        bearer_token = ""
        if auth_header.startswith("Bearer "):
            bearer_token = auth_header[7:]
        if not secrets.compare_digest(bearer_token, settings.METRICS_TOKEN) and not secrets.compare_digest(
            api_key_header, settings.METRICS_TOKEN
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Invalid or missing metrics token. Provide Authorization: Bearer <token> or X-API-Key header."
                },
            )

    global METRICS_COLLECTION_ERRORS
    try:
        from prometheus_client import Gauge, Histogram, generate_latest
    except ModuleNotFoundError:
        return Response(content=_render_basic_metrics_text(), media_type="text/plain")
    from prometheus_client.core import CollectorRegistry

    registry = CollectorRegistry()

    # Job counts by status
    from app.models import JobStatus

    counts = {s.value: 0 for s in JobStatus}
    for job in jobs_store.values():
        status_key = str(job.status.value if isinstance(job.status, JobStatus) else job.status)
        counts[status_key] = counts.get(status_key, 0) + 1

    job_total = Gauge("dataforge_jobs_total", "Total jobs", ["status"], registry=registry)
    for status, count in counts.items():
        job_total.labels(status=status).set(count)

    # Recycle bin count
    recycle_gauge = Gauge("dataforge_recycle_bin_total", "Total jobs in recycle bin", registry=registry)
    recycle_gauge.set(len(recycle_bin_store))

    # Runtime limits
    for key, val in CONFIG.items():
        g = Gauge(f"dataforge_config_{key}", f"Config value for {key}", registry=registry)
        try:
            g.set(float(val))
        except (TypeError, ValueError):
            pass

    # Repository backend
    backend_ok = 1
    try:
        repo = get_job_repository()
        backend = getattr(repo, "backend", "sqlite")
        backend_gauge = Gauge("dataforge_backend", "Storage backend type", ["backend"], registry=registry)
        backend_gauge.labels(backend=backend).set(1)
    except Exception as e:
        backend_ok = 0
        METRICS_COLLECTION_ERRORS += 1
        logger.error("Metrics: backend collection failed: %s", e)

    backend_ok_gauge = Gauge(
        "dataforge_backend_collection_ok", "Whether storage backend metrics collected successfully", registry=registry
    )
    backend_ok_gauge.set(backend_ok)

    # Worker queue stats
    queue_ok = 1
    try:
        from app.worker_queue import get_worker_queue
        q = get_worker_queue()
        q_status = q.get_status()
        queue_pending = Gauge("dataforge_queue_pending", "Pending tasks in worker queue", registry=registry)
        queue_pending.set(q_status.get("pending", 0))
        queue_running = Gauge("dataforge_queue_running", "Running tasks in worker queue", registry=registry)
        queue_running.set(q_status.get("running", 0))
        queue_dead_letter = Gauge("dataforge_queue_dead_letter", "Dead letter queue size", registry=registry)
        queue_dead_letter.set(q_status.get("dead_letter", 0))
    except Exception as e:
        queue_ok = 0
        METRICS_COLLECTION_ERRORS += 1
        logger.error("Metrics: queue collection failed: %s", e)

    queue_ok_gauge = Gauge(
        "dataforge_queue_collection_ok", "Whether worker queue metrics collected successfully", registry=registry
    )
    queue_ok_gauge.set(queue_ok)

    # Worker failure counters
    from app.metrics_collector import get_worker_failures
    failures = get_worker_failures()
    if failures:
        failure_gauge = Gauge(
            "dataforge_worker_failures_total", "Total worker failures by task type", ["task_type"], registry=registry
        )
        for task_type, count in failures.items():
            failure_gauge.labels(task_type=task_type).set(count)

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
        "dataforge_metrics_collection_error_total", "Total collection errors encountered", registry=registry
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

    return Response(content=generate_latest(registry), media_type="text/plain")
