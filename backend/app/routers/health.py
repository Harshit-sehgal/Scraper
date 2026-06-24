"""Health Router — liveness, readiness, and root path probes.

Extracted from main.py as part of Phase 3 refactoring to decouple
health-check concerns from the app factory.
"""

from __future__ import annotations

import logging
import re
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.globals import jobs_store, recycle_bin_store
from app.storage_interface import get_job_repository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])

# Strip absolute file paths from error messages to avoid leaking
# filesystem layout through the /ready endpoint.
_PATH_PATTERN = re.compile(r"/[\w/.\-]+")


def _sanitise_error(msg: str) -> str:
    return _PATH_PATTERN.sub("<path>", msg)


@router.get("/")
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


@router.get("/health")
async def health():
    """Liveness probe — always returns 200 if the process is alive."""
    return {"status": "ok"}


@router.get("/ready")
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
        return {
            "status": "ready",
            "backend": backend,
            "storage": "ok",
            "migrations": "ok",
            "schema_version": health_info.get("schema_version", 0),
            "job_count": health_info.get("job_count", len(jobs_store)),
            "recycle_bin_count": health_info.get("recycle_bin_count", len(recycle_bin_store)),
        }
    except Exception as e:
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
