"""
Lifespan — FastAPI startup / shutdown lifecycle hooks.

Extracted from main.py as part of Phase 3 refactoring to keep the app factory
thin and allow individual lifecycle components to be tested in isolation.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.globals import CONFIG, jobs_store, recycle_bin_store
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
    CONFIG.update(
        {
            "max_discovery_urls": settings.MAX_DISCOVERY_URLS,
            "per_url_timeout_seconds": settings.PER_URL_TIMEOUT_SECONDS,
            "max_job_runtime_seconds": settings.MAX_JOB_RUNTIME_SECONDS,
            "ai_structuring_timeout_seconds": settings.AI_STRUCTURING_TIMEOUT_SECONDS,
            "insight_timeout_seconds": settings.INSIGHT_TIMEOUT_SECONDS,
            "max_job_history": settings.MAX_JOB_HISTORY,
            "max_recycle_bin_history": settings.MAX_RECYCLE_BIN_HISTORY,
        }
    )

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


def schedule_background_task(coro):
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


def persist_single_wrapper(job_id: str, critical: bool = False) -> None:
    """Persist a single job to the configured backend."""
    job = jobs_store.get(job_id)
    if job:
        try:
            get_job_repository().save_single(job)
        except Exception as e:
            logger.error("Failed to persist single job %s: %s", job_id, e)
            if critical:
                raise


async def run_job_wrapper(job_id: str):
    """Run a job with all standard options wired from CONFIG."""
    import app.main as main_mod

    persist_fn = getattr(main_mod, "_persist_state_wrapper", persist_state_wrapper)
    persist_single_fn = getattr(main_mod, "_persist_single_wrapper", persist_single_wrapper)

    await run_job(
        job_id=job_id,
        jobs_store=jobs_store,
        persist_state_fn=persist_fn,
        max_discovery_urls=CONFIG["max_discovery_urls"],
        max_job_runtime_seconds=CONFIG["max_job_runtime_seconds"],
        per_url_scrape_timeout_seconds=CONFIG["per_url_timeout_seconds"],
        ai_structuring_timeout_seconds=CONFIG["ai_structuring_timeout_seconds"],
        insight_timeout_seconds=CONFIG["insight_timeout_seconds"],
        persist_state_single_fn=lambda: persist_single_fn(job_id, critical=False),
        persist_state_single_critical_fn=lambda: persist_single_fn(job_id, critical=True),
    )


def persist_state_wrapper():
    """Persist all jobs and recycle bin to the configured backend."""
    repo = get_job_repository()
    repo.save_all(jobs=jobs_store, recycle_bin=recycle_bin_store)
