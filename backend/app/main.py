"""FastAPI Main Server — DataForge General-Purpose Web Scraper API.

Thin app factory: imports and composes middleware, routers, and lifespan
from dedicated modules. Keeps backward-compatible re-exports so existing
tests and scripts continue to work.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.globals import CONFIG, jobs_store, recycle_bin_store
from app.lifespan import (
    lifespan,
    persist_single_wrapper,
    persist_state_wrapper,
    run_job_wrapper,
    schedule_background_task,
)
from app.middlewares import (
    api_key_middleware,
    body_size_middleware,
    csp_report_only_middleware,
    latency_tracking_middleware,
    rate_limiter,
)

# NOTE: app.routers.experimental is intentionally NOT imported at module
# load time. It is imported lazily inside configure_routes() so that the
# research router module (and its transitive research imports) is never
# loaded at startup when ENABLE_EXPERIMENTAL_ROUTES is False.
from app.routers.exports import create_exports_router
from app.routers.health import router as health_router
from app.routers.jobs import create_jobs_router
from app.routers.operator import router as operator_router
from app.routers.scraper import router as scraper_router
from app.routers.system import router as system_router
from app.services.job_runner import run_job
from app.storage_interface import get_job_repository

logger = logging.getLogger(__name__)

# ─── Backward-compatible re-exports ─────────────────────────────────────
# These are imported from app.main by tests and other modules.
# Keep them here so existing imports keep working after refactoring.
_persist_state_wrapper = persist_state_wrapper
_run_job_wrapper = run_job_wrapper
_schedule_background_task = schedule_background_task
_persist_single_wrapper = persist_single_wrapper
run_job = run_job

__all__ = [
    "CONFIG",
    "_persist_single_wrapper",
    "_persist_state_wrapper",
    "_run_job_wrapper",
    "_schedule_background_task",
    "app",
    "get_job_repository",
    "jobs_store",
    "lifespan",
    "recycle_bin_store",
    "run_job",
]

# ─── App Factory and Configuration ─────────────────────────────────────────


def configure_middleware(app: FastAPI) -> None:
    """Configure CORS, body size limit, API key auth, rate limiter, latency tracking, and CSP report-only middlewares."""
    # Refuse to start with CORS_ORIGINS=["*"] when credentials are
    # allowed — Starlette silently accepts this combination but it is
    # a credential-leak catastrophe (any origin can issue authenticated
    # cross-site requests). Fail closed in production.
    if "*" in settings.CORS_ORIGINS and settings.ENV.lower() == "production":
        raise RuntimeError(  # noqa: TRY003
            "CORS_ORIGINS cannot contain '*' in production when allow_credentials=True",
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(csp_report_only_middleware)
    app.middleware("http")(body_size_middleware)
    app.middleware("http")(api_key_middleware)
    app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limiter.middleware)
    app.middleware("http")(latency_tracking_middleware)


def configure_static(app: FastAPI) -> None:
    """Configure static frontend and dashboard mounts if directories exist and not in production."""
    from app.config import settings

    if settings.ENV.lower() == "production":
        return

    FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
    if FRONTEND_DIR.exists():
        app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
        DASHBOARD_DIR = FRONTEND_DIR / "dashboard"
        if DASHBOARD_DIR.exists():
            app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")


def configure_routes(app: FastAPI) -> None:
    """Include API routers.

    The experimental / research router is conditionally mounted: it is
    only included when `settings.ENABLE_EXPERIMENTAL_ROUTES` is True.
    When False (the default), `/api/system/topology`, `/api/system/crystalline`,
    and the other research endpoints return 404. This is the HTTP-level
    complement to the import-time gate in `experimental_startup`.
    """
    app.include_router(
        create_jobs_router(
            jobs_store=jobs_store,
            recycle_bin_store=recycle_bin_store,
            persist_state_fn=_persist_state_wrapper,
            schedule_task_fn=_schedule_background_task,
            run_job_coro_fn=_run_job_wrapper,
        ),
    )
    app.include_router(create_exports_router(jobs_store=jobs_store))
    app.include_router(scraper_router)
    app.include_router(operator_router)
    app.include_router(system_router)
    app.include_router(health_router)

    # Experimental / research routes — gated on the same flag that gates
    # the import-time subsystem initialization. Including this router
    # while subsystems are disabled would expose endpoints that lazily
    # import research modules; both gates must agree.
    if settings.ENABLE_EXPERIMENTAL_ROUTES:
        if settings.ENV.lower() == "production":
            logger.warning(
                "EXPERIMENTAL ROUTES ENABLED IN PRODUCTION — research-only endpoints are exposed. This is not recommended.",
            )
        # Lazy import: the experimental router module and its transitive
        # research dependencies are only loaded when we are actually
        # about to mount the router. This keeps the default-mode
        # import graph free of research modules.
        from app.routers.experimental import router as experimental_router

        app.include_router(experimental_router)
        logger.info("Experimental / research router mounted")
    else:
        logger.info("Experimental / research router NOT mounted (set DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true to enable)")


def configure_exception_handlers(app: FastAPI) -> None:
    """Configure custom application exception handlers."""


def configure_lifespan(app: FastAPI) -> None:
    """Configure lifespan settings (handled in FastAPI initialization)."""


def create_app() -> FastAPI:
    """FastAPI App Factory."""
    _docs_url = None if settings.ENV.lower() == "production" else "/docs"
    _redoc_url = None if settings.ENV.lower() == "production" else "/redoc"
    _openapi_url = None if settings.ENV.lower() == "production" else "/openapi.json"

    app_instance = FastAPI(
        title="DataForge — General-Purpose Web Scraper",
        description=(
            "Web extraction backend for supported accessible pages. "
            "Supports manual, discovery, and AI-assisted extraction modes "
            "with optional browser rendering, anti-bot detection, and "
            "content-quality scoring. See `docs/API.md` for the full "
            "endpoint reference."
        ),
        version="0.1.0",
        contact={
            "name": "DataForge Engineering",
            "url": "https://github.com/Harshit-sehgal/Scraper/issues",
        },
        license_info={
            "name": "MIT",
            "url": "https://github.com/Harshit-sehgal/Scraper/blob/main/LICENSE",
        },
        lifespan=lifespan,
        docs_url=_docs_url,
        redoc_url=_redoc_url,
        openapi_url=_openapi_url,
    )
    configure_middleware(app_instance)
    configure_static(app_instance)
    configure_routes(app_instance)
    configure_exception_handlers(app_instance)
    configure_lifespan(app_instance)
    return app_instance


app = create_app()
