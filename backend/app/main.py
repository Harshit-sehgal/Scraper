"""
FastAPI Main Server — DataForge General-Purpose Web Scraper API.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.globals import CONFIG, jobs_store, recycle_bin_store
from app.routers.experimental import router as experimental_router
from app.routers.exports import create_exports_router
from app.routers.jobs import create_jobs_router
from app.routers.operator import router as operator_router
from app.routers.scraper import router as scraper_router
from app.routers.system import router as system_router
from app.services.job_runner import run_job
from app.state_store import get_state_file_path
from app.storage_interface import get_job_repository

logger = logging.getLogger(__name__)

# Repository is resolved lazily inside lifespan()
job_repo = None
gossip = None
heartbeat_mgr = None
_background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for FastAPI startup / shutdown.

    Handles all initialization: recovery framework, domain health,
    distributed readiness (gossip / heartbeat), state loading,
    and background task scheduling.
    """
    global gossip, heartbeat_mgr

    # Strict Production Security Check
    if settings.ENV.lower() == "production":
        if not settings.CORS_ORIGINS or "*" in settings.CORS_ORIGINS:
            raise ValueError(
                "CORS_ORIGINS contains wildcard '*' or is empty. In production environment, "
                "CORS_ORIGINS must be locked down to trusted domains for safety."
            )
        from app.utils.prod_security_validator import validate_production_credentials

        validate_production_credentials(settings)

    # Initialize experimental subsystems (research-only)
    from app.experimental_startup import (
        init_domain_health_monitor,
        init_gossip_and_heartbeat,
        init_graph_scheduler,
        init_recovery_framework,
    )

    init_graph_scheduler()
    init_recovery_framework()
    init_domain_health_monitor()
    gossip, heartbeat_mgr = init_gossip_and_heartbeat()

    # Runtime safety rails — driven by centralized config
    CONFIG.update({
        "max_discovery_urls": settings.MAX_DISCOVERY_URLS,
        "per_url_timeout_seconds": settings.PER_URL_TIMEOUT_SECONDS,
        "max_job_runtime_seconds": settings.MAX_JOB_RUNTIME_SECONDS,
        "ai_structuring_timeout_seconds": settings.AI_STRUCTURING_TIMEOUT_SECONDS,
        "insight_timeout_seconds": settings.INSIGHT_TIMEOUT_SECONDS,
        "max_job_history": settings.MAX_JOB_HISTORY,
        "max_recycle_bin_history": settings.MAX_RECYCLE_BIN_HISTORY,
    })

    # Resolve the repository lazily
    global job_repo
    job_repo = get_job_repository()

    # Durable job store & semantic field state — single DB read on startup
    loaded_jobs, loaded_recycle, world_state_data = job_repo.load_all()
    jobs_store.clear()
    jobs_store.update(loaded_jobs)
    recycle_bin_store.clear()
    recycle_bin_store.update(loaded_recycle)

    # Restore semantic world state
    from app.experimental_startup import restore_semantic_world_state
    restore_semantic_world_state(world_state_data, str(get_state_file_path()))

    # Schedule periodic gossip propagation
    from app.experimental_startup import schedule_gossip_propagation

    gossip_task = await schedule_gossip_propagation(gossip, heartbeat_mgr, interval=settings.GOSSIP_PROPAGATION_INTERVAL)
    if gossip_task:
        _background_tasks.append(gossip_task)

    yield
    # ─── SHUTDOWN ─────────────────────────────────────────────────────

    # Cancel all background tasks
    for t in _background_tasks:
        t.cancel()
    await asyncio.gather(*_background_tasks, return_exceptions=True)
    _background_tasks.clear()
    logger.info("Background tasks cleaned up")

    # Persist semantic world state
    from app.experimental_startup import persist_semantic_world_state
    persist_semantic_world_state()

    # Flush any pending background state writes
    try:
        from app.state_store import flush_state_writes

        flush_state_writes()
    except Exception as e:
        logger.warning("Failed to flush state writes during shutdown: %s", e)

    # Close Postgres connection pool
    from app.experimental_startup import close_postgres_pool
    close_postgres_pool()


def _schedule_background_task(coro):
    """Schedule a background task with error handling."""
    task = asyncio.create_task(coro)

    def _handle_task_result(t: asyncio.Task):
        try:
            t.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Background task failed: %s", e, exc_info=True)

    task.add_done_callback(_handle_task_result)
    return task


def _persist_single_wrapper(job_id: str, critical: bool = False) -> None:
    """Persist a single job to the configured backend."""
    job = jobs_store.get(job_id)
    if job:
        try:
            get_job_repository().save_single(job)
        except Exception as e:
            logger.error("Failed to persist single job %s: %s", job_id, e)
            if critical:
                raise


async def _run_job_wrapper(job_id: str):
    await run_job(
        job_id=job_id,
        jobs_store=jobs_store,
        persist_state_fn=_persist_state_wrapper,
        max_discovery_urls=CONFIG["max_discovery_urls"],
        max_job_runtime_seconds=CONFIG["max_job_runtime_seconds"],
        per_url_scrape_timeout_seconds=CONFIG["per_url_timeout_seconds"],
        ai_structuring_timeout_seconds=CONFIG["ai_structuring_timeout_seconds"],
        insight_timeout_seconds=CONFIG["insight_timeout_seconds"],
        persist_state_single_fn=lambda: _persist_single_wrapper(job_id, critical=False),
        persist_state_single_critical_fn=lambda: _persist_single_wrapper(job_id, critical=True),
    )


def _persist_state_wrapper():
    repo = get_job_repository()
    repo.save_all(jobs=jobs_store, recycle_bin=recycle_bin_store)


# ─── Middlewares ───────────────────────────────────────────────────────────

from app.middlewares import (
    api_key_middleware,
    body_size_middleware,
    latency_tracking_middleware,
    rate_limiter,
)

# ─── App Factory and Configuration ─────────────────────────────────────────


def configure_middleware(app: FastAPI):
    """Configure CORS, body size limit, API key auth, rate limiter, and latency tracking middlewares."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(body_size_middleware)
    app.middleware("http")(api_key_middleware)
    app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limiter.middleware)
    app.middleware("http")(latency_tracking_middleware)


def configure_static(app: FastAPI):
    """Configure static frontend and dashboard mounts if directories exist."""
    FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
    if FRONTEND_DIR.exists():
        app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
        DASHBOARD_DIR = FRONTEND_DIR / "dashboard"
        if DASHBOARD_DIR.exists():
            app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")


def configure_routes(app: FastAPI):
    """Include API routers and configure base path probes."""
    app.include_router(
        create_jobs_router(
            jobs_store=jobs_store,
            recycle_bin_store=recycle_bin_store,
            persist_state_fn=_persist_state_wrapper,
            schedule_task_fn=_schedule_background_task,
            run_job_coro_fn=_run_job_wrapper,
            config=CONFIG,
        )
    )
    app.include_router(create_exports_router(jobs_store=jobs_store))
    app.include_router(scraper_router)
    app.include_router(operator_router)
    app.include_router(experimental_router)
    app.include_router(system_router)

    @app.get("/")
    async def root():
        return {"message": "DataForge API v2", "docs": "/docs", "dashboard": "/app"}

    @app.get("/health")
    async def health():
        """Liveness probe — always returns 200 if the process is alive."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        """Readiness probe — checks that the configured storage backend is reachable.

        Uses the active JobRepository's health_check() if available (Postgres),
        otherwise falls back to SQLite storage health (SQLite).
        Returns 503 if the backend is unhealthy.
        """
        start_time = time.time()
        repo = get_job_repository()
        try:
            if hasattr(repo, "health_check"):
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
        except Exception as e:
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


def configure_exception_handlers(app: FastAPI):
    """Configure custom application exception handlers."""
    pass


def configure_lifespan(app: FastAPI):
    """Configure lifespan settings (handled in FastAPI initialization)."""
    pass


def create_app() -> FastAPI:
    """FastAPI App Factory."""
    _docs_url = None if settings.ENV.lower() == "production" else "/docs"
    _redoc_url = None if settings.ENV.lower() == "production" else "/redoc"
    _openapi_url = None if settings.ENV.lower() == "production" else "/openapi.json"

    app_instance = FastAPI(
        title="DataForge — General-Purpose Web Scraper",
        description="Web extraction backend for supported accessible pages",
        version="2.0.0",
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
