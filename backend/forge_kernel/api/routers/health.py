"""
Health router — liveness, readiness, and root path probes for the kernel.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from forge_kernel.config import settings
from forge_kernel.persistence import get_job_repository

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


@router.get("/")
async def root():
    return {"message": "DataForge Kernel v1", "docs": "/docs", "dashboard": "/app"}


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    """Readiness probe — checks storage backend reachability."""
    try:
        repo = get_job_repository()
        backend = getattr(repo, "backend", "sqlite")

        # Simple health check via load
        repo.load_all()

        return {
            "status": "ready",
            "backend": backend,
        }
    except Exception as e:
        content = {"status": "not_ready"}
        if settings.security.ENV.lower() != "production":
            content["error"] = str(e)
        return JSONResponse(status_code=503, content=content)
