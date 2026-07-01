"""Health Router — liveness, readiness, and component-level health probes.

Extracted from main.py as part of Phase 3 refactoring to decouple
health-check concerns from the app factory.

Sub-endpoints:
- ``GET /health`` — liveness (process is alive)
- ``GET /ready`` — readiness (DB backend reachable)
- ``GET /health/worker`` — worker queue status (pending, running, idle capacity)
- ``GET /health/db`` — database connection & migration status
- ``GET /health/browser`` — Playwright browser pool status
"""

from __future__ import annotations

import logging
import re
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.globals import _jobs_store_lock, jobs_store, recycle_bin_store
from app.storage_interface import get_job_repository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])

# Strip absolute file paths from error messages to avoid leaking
# filesystem layout through the /ready endpoint.
_PATH_PATTERN = re.compile(r"/[\w/.\-]+")


def _sanitise_error(msg: str) -> str:
    return _PATH_PATTERN.sub("<path>", msg)


@router.get("/", response_model=dict)
async def root():
    """Root path — API identification.

    In production mode, /docs, /redoc, /openapi.json, and /app are disabled,
    so we omit them from the response to avoid confusing operators and clients.
    The currently-active AUP version is also returned so the dashboard
    can surface an acceptance banner before the user makes any calls.
    """
    from app.config import settings
    from app.saas import CURRENT_AUP_VERSION

    base = {
        "message": "DataForge API v2",
        "experimental_enabled": settings.ENABLE_EXPERIMENTAL_ROUTES,
        "aup_version": CURRENT_AUP_VERSION,
    }
    if settings.ENV.lower() == "production":
        return base
    return {
        **base,
        "docs": "/docs",
        "dashboard": "/app",
    }


@router.get("/health", response_model=dict)
async def health():
    """Liveness probe — always returns 200 if the process is alive."""
    return {"status": "ok"}


@router.get("/ready", response_model=dict)
async def ready():
    """Readiness probe — checks that the configured storage backend is reachable.

    Uses the active JobRepository's health_check() if available (Postgres),
    otherwise falls back to SQLite storage health (SQLite).
    Returns 503 if the backend is unhealthy.
    """
    start_time = time.time()
    repo = get_job_repository()
    try:
        health_info = await run_in_threadpool(repo.health_check)

        duration = time.time() - start_time
        from app.metrics_collector import record_health_check_latency as _rchl

        _rchl(duration)

        if not health_info["ok"]:
            content = {"status": "not_ready"}
            if settings.ENV.lower() != "production":
                content["error"] = _sanitise_error(health_info.get("error", "Backend unhealthy"))
            return JSONResponse(
                status_code=503,
                content=content,
            )

        if settings.ENV.lower() == "production":
            return {"status": "ready"}

        backend = getattr(repo, "backend", "sqlite")
        with _jobs_store_lock:
            job_count = health_info.get("job_count", len(jobs_store))
            recycle_bin_count = health_info.get("recycle_bin_count", len(recycle_bin_store))
        return {
            "status": "ready",
            "backend": backend,
            "storage": "ok",
            "migrations": "ok",
            "schema_version": health_info.get("schema_version", 0),
            "job_count": job_count,
            "recycle_bin_count": recycle_bin_count,
        }
    except (RuntimeError, ValueError, TypeError, OSError, AttributeError, ImportError) as e:
        duration = time.time() - start_time
        from app.metrics_collector import record_health_check_latency

        record_health_check_latency(duration)
        content = {"status": "not_ready"}
        if settings.ENV.lower() != "production":
            content["error"] = _sanitise_error(str(e))
        return JSONResponse(
            status_code=503,
            content=content,
        )


# ── Component-level health sub-endpoints ─────────────────────────────────


@router.get("/health/worker", response_model=dict)
async def health_worker():
    """Worker queue health — pending jobs, running tasks, idle capacity.

    Returns 503 if the worker queue reports zero idle capacity while
    tasks are pending (queue saturation).
    """
    try:
        from app.worker_queue import get_worker_queue

        queue = get_worker_queue()
        # get_status() is synchronous for the in-memory queue backend
        status = queue.get_status()
        pending = status.get("pending", 0)
        running = status.get("running", 0)
        max_concurrency = status.get("max_concurrency", 0)
        idle_capacity = max(0, max_concurrency - running)
        dead_letter = status.get("dead_letter", 0)
        retrying = status.get("retrying", 0)

        saturated = pending > 0 and idle_capacity == 0
        result = {
            "status": "saturated" if saturated else "ok",
            "pending": pending,
            "running": running,
            "idle_capacity": idle_capacity,
            "max_concurrency": max_concurrency,
            "retrying": retrying,
            "dead_letter": dead_letter,
        }
        if saturated:
            return JSONResponse(status_code=503, content=result)
        return result
    except (RuntimeError, ValueError, TypeError, OSError, AttributeError, ImportError) as e:
        logger.debug("[health/worker] Error inspecting worker queue", exc_info=True)
        content: dict = {"status": "error"}
        if settings.ENV.lower() != "production":
            content["error"] = _sanitise_error(str(e))
        return JSONResponse(status_code=503, content=content)


@router.get("/health/db", response_model=dict)
async def health_db():
    """Database health — connection status, migrations, schema version.

    Returns 503 if the database backend reports unhealthy.
    """
    try:
        repo = get_job_repository()
        health_info = await run_in_threadpool(repo.health_check)
        ok = health_info.get("ok", False)
        result: dict = {
            "status": "ok" if ok else "error",
            "backend": getattr(repo, "backend", "sqlite"),
            "migrations": "ok" if health_info.get("schema_version", 0) >= 0 else "unknown",
            "schema_version": health_info.get("schema_version", 0),
        }
        if not ok:
            if settings.ENV.lower() != "production":
                result["error"] = _sanitise_error(health_info.get("error", "Backend unhealthy"))
            return JSONResponse(status_code=503, content=result)
        return result
    except (RuntimeError, ValueError, TypeError, OSError, AttributeError, ImportError) as e:
        logger.debug("[health/db] Error checking database", exc_info=True)
        content = {"status": "error"}
        if settings.ENV.lower() != "production":
            content["error"] = _sanitise_error(str(e))
        return JSONResponse(status_code=503, content=content)


@router.get("/health/browser", response_model=dict)
async def health_browser():
    """Browser pool health — live browser count, context availability, circuit breaker state.

    Returns 503 if the circuit breaker is OPEN (browser pool unavailable)
    or if the browser reports disconnected with active contexts.
    """
    try:
        from app.browser_pool import get_browser_pool_health

        pool_health = await run_in_threadpool(get_browser_pool_health)

        # get_browser_pool_health returns a dict with circuit_breaker + pool metrics
        cb_stats = pool_health.get("circuit_breaker", {})
        pool_metrics = pool_health.get("pool", {})
        cb_state = cb_stats.get("state", "unknown")
        is_open = cb_state == "open"
        connected = pool_metrics.get("connected", False)
        active_contexts = pool_metrics.get("active_contexts", 0)
        reusable_contexts = pool_metrics.get("reusable_contexts", 0)
        isolated_contexts = pool_metrics.get("isolated_contexts", 0)
        active_acquires = pool_metrics.get("active_acquires", 0)
        crash_count = pool_metrics.get("crash_count", 0)
        context_reuse_rate = pool_metrics.get("context_reuse_rate", 0.0)

        unhealthy = is_open or (not connected and (active_contexts > 0 or active_acquires > 0))
        result = {
            "status": "unhealthy" if unhealthy else "ok",
            "circuit_breaker": cb_state,
            "connected": connected,
            "active_contexts": active_contexts,
            "reusable_contexts": reusable_contexts,
            "isolated_contexts": isolated_contexts,
            "active_acquires": active_acquires,
            "crash_count": crash_count,
            "context_reuse_rate": context_reuse_rate,
        }
        if unhealthy:
            return JSONResponse(status_code=503, content=result)
        return result
    except (RuntimeError, ValueError, TypeError, OSError, AttributeError, ImportError) as e:
        logger.debug("[health/browser] Error checking browser pool", exc_info=True)
        content = {"status": "error"}
        if settings.ENV.lower() != "production":
            content["error"] = _sanitise_error(str(e))
        return JSONResponse(status_code=503, content=content)
