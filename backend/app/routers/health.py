"""Health Router — liveness, readiness, and root path probes.

Extracted from main.py as part of Phase 3 refactoring to decouple
health-check concerns from the app factory.
"""

from __future__ import annotations

import logging
import time

from app.config import settings
from app.globals import jobs_store, recycle_bin_store
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


def get_job_repository():
    import app.main

    return app.main.get_job_repository()


@router.get("/")
async def root():
    """Root path — API identification."""
    return {"message": "DataForge API v2", "docs": "/docs", "dashboard": "/app"}


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
        if getattr(repo, "backend", "") == "postgres":
            health_info = repo.health_check()
        else:
            from app.job_store import get_storage_health

            health_info = get_storage_health()

        duration = time.time() - start_time
        from app.metrics_collector import record_health_check_latency as _rchl

        _rchl(duration)

        if not health_info["ok"]:
            content = {"status": "not_ready"}
            if settings.ENV.lower() != "production":
                content["error"] = health_info.get("error", "Backend unhealthy")
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
    except Exception as e:  # noqa: BLE001
        duration = time.time() - start_time
        from app.metrics_collector import record_health_check_latency

        record_health_check_latency(duration)
        content = {"status": "not_ready"}
        if settings.ENV.lower() != "production":
            content["error"] = str(e)
        return JSONResponse(
            status_code=503,
            content=content,
        )
