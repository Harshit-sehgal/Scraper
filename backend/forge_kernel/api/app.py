"""Kernel FastAPI app factory — creates a FastAPI application with middleware,
routers, and lifespan for the product kernel.

This is the clean-room equivalent of the existing app.main.create_app().
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from forge_kernel.api.deps import get_jobs_store, get_recycle_bin_store
from forge_kernel.api.middleware import configure_middleware
from forge_kernel.api.routers import (
    exports_router,
    health_router,
    jobs_router,
    system_router,
)
from forge_kernel.config import settings
from forge_kernel.services.job_service import JobService

logger = logging.getLogger(__name__)

_background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifespan handler — initialize state from persistent store on startup."""
    # Load state from repository
    jobs_store = get_jobs_store()
    recycle_bin_store = get_recycle_bin_store()
    svc = JobService(jobs_store=jobs_store, recycle_bin_store=recycle_bin_store)
    svc.load_all()
    logger.info("Kernel initialized: %d jobs loaded", len(jobs_store))

    yield

    # Persist state on shutdown
    try:
        svc._persist()
    except Exception as e:
        logger.warning("Failed to persist state on shutdown: %s", e)

    for t in _background_tasks:
        t.cancel()
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    _background_tasks.clear()


def configure_static(app: FastAPI) -> None:
    """Mount static frontend files if directory exists."""
    frontend_dir = Path(__file__).parent.parent.parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/app", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
        dashboard_dir = frontend_dir / "dashboard"
        if dashboard_dir.exists():
            app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")


def configure_routes(app: FastAPI) -> None:
    """Include all kernel routers."""
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(exports_router)
    app.include_router(system_router)


def create_app() -> FastAPI:
    """Create the kernel FastAPI application."""
    sec = settings.security
    _docs_url = None if sec.ENV.lower() == "production" else "/docs"

    app_instance = FastAPI(
        title="DataForge Kernel — Web Extraction Service",
        description="Clean-room product kernel for web data extraction",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=_docs_url,
        redoc_url=None if sec.ENV.lower() == "production" else "/redoc",
        openapi_url=None if sec.ENV.lower() == "production" else "/openapi.json",
    )

    configure_middleware(app_instance)
    configure_static(app_instance)
    configure_routes(app_instance)

    return app_instance
