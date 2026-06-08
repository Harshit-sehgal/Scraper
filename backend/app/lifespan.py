"""Lifespan — FastAPI startup / shutdown lifecycle hooks.

Extracted from main.py as part of Phase 3 refactoring to keep the app factory
thin and allow individual lifecycle components to be tested in isolation.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from app.config import settings
from app.globals import jobs_store, recycle_bin_store
from app.services.job_runner import run_job
from app.state_store import get_state_file_path
from app.storage_interface import get_job_repository

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Repository is resolved lazily inside lifespan()
job_repo = None
gossip = None
heartbeat_mgr = None
_background_tasks: list[asyncio.Task] = []


def reset_lifespan_state() -> None:
    """Clear the module-level lifespan state.

    Used by tests that drive the app through multiple lifespan cycles
    in the same process. Without this reset, the second startup would
    inherit the gossip/heartbeat_mgr/_background_tasks from the first
    cycle, leading to double-registered asyncio tasks and stale
    references.

    This is a backstop for test isolation; production code should
    not call it.
    """
    global job_repo, gossip, heartbeat_mgr, _background_tasks
    job_repo = None
    gossip = None
    heartbeat_mgr = None
    _background_tasks = []


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001, C901, PLR0912, PLR0915, RUF100
    """Lifespan event handler for FastAPI startup / shutdown.

    Handles all initialization: recovery framework, domain health,
    distributed readiness (gossip / heartbeat), state loading,
    and background task scheduling.
    """
    global gossip, heartbeat_mgr

    # Strict Production Security Check
    if settings.ENV.lower() == "production":
        if not settings.CORS_ORIGINS or "*" in settings.CORS_ORIGINS:
            msg = (
                "CORS_ORIGINS contains wildcard '*' or is empty. In production environment, "
                "CORS_ORIGINS must be locked down to trusted domains for safety."
            )
            raise ValueError(
                msg,
            )
        from app.utils.prod_security_validator import validate_production_credentials

        validate_production_credentials(settings)

    # Initialize experimental subsystems (research-only).
    # The functions in `experimental_startup` self-gate on
    # `settings.ENABLE_EXPERIMENTAL_ROUTES`, but we still skip the
    # imports / calls entirely when the flag is off to keep the
    # import graph free of research modules at startup.
    from app.experimental_startup import (
        experimental_subsystems_enabled,
        init_domain_health_monitor,
        init_gossip_and_heartbeat,
        init_graph_scheduler,
        init_recovery_framework,
    )

    if experimental_subsystems_enabled():
        logger.info("Experimental subsystems ENABLED — initializing research shell")
        init_graph_scheduler()
        init_recovery_framework()
        init_domain_health_monitor()
        gossip, heartbeat_mgr = init_gossip_and_heartbeat()
    else:
        logger.info(
            "Experimental subsystems DISABLED — research shell will not initialize "
            "(set DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true to enable)",
        )
        gossip, heartbeat_mgr = None, None

    # Runtime safety rails — driven by centralized config.
    # The legacy ``CONFIG`` mapping is re-synced here so any back-compat
    # reader (e.g. ``run_job_wrapper`` reading ``CONFIG["..."]``) sees
    # the current settings values.
    from app.globals import rebuild_config_from_settings

    rebuild_config_from_settings()

    # Resolve the repository lazily
    global job_repo
    job_repo = get_job_repository()

    # SSRF transport self-check: confirm the safe-transport factory still
    # injects a SafeAsyncNetworkBackend into the httpx connection pool.
    # The check is non-fatal at import time but hard-fails in production
    # so a silent upgrade of httpx/httpcore cannot degrade SSRF posture.
    from app.url_safety import verify_ssrf_self_check

    ssrf_check = verify_ssrf_self_check()
    if not ssrf_check.get("ok"):
        msg = (
            f"SSRF self-check failed: {ssrf_check.get('reason', 'unknown')}. "
            f"httpx={ssrf_check.get('httpx_version')} "
            f"httpcore={ssrf_check.get('httpcore_version')}. "
            "Pin supported versions in backend/requirements.lock.txt."
        )
        if settings.ENV.lower() in ("production", "staging"):
            raise RuntimeError(msg)
        logger.warning(msg)
    else:
        logger.info(
            "SSRF self-check passed: httpx=%s httpcore=%s anyio_backend=%s sync_backend=%s",
            ssrf_check.get("httpx_version"),
            ssrf_check.get("httpcore_version"),
            ssrf_check.get("has_anyio_backend"),
            ssrf_check.get("has_sync_backend"),
        )

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

    # Schedule periodic rate_limits table pruning (DB-backed counters).
    # Independently of the middleware's per-request pruning (every 300s),
    # this background task ensures stale rows are cleaned up even when
    # there is no API traffic.
    if settings.RATE_LIMIT_PRUNE_INTERVAL > 0:
        prune_task = schedule_background_task(_rate_limit_prune_loop())
        _background_tasks.append(prune_task)

    yield
    # ─── SHUTDOWN ─────────────────────────────────────────────────────

    # Cancel all background tasks
    for t in _background_tasks:
        t.cancel()
    if _background_tasks:
        _done, pending = await asyncio.wait(_background_tasks, timeout=10)
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    _background_tasks.clear()
    logger.info("Background tasks cleaned up")

    # Persist semantic world state
    from app.experimental_startup import persist_semantic_world_state

    persist_semantic_world_state()

    # Flush any pending background state writes
    try:
        from app.state_store import flush_state_writes

        flush_state_writes()
    except (ImportError, OSError) as e:
        logger.warning("Failed to flush state writes during shutdown: %s", e)

    # Close Postgres connection pool
    from app.experimental_startup import close_postgres_pool

    close_postgres_pool()

    # Close browser pool to prevent zombie chromium processes
    try:
        from app.browser_pool import get_browser_pool

        await get_browser_pool().close()
        logger.info("Browser pool closed successfully")
    except Exception as e:
        logger.warning("Failed to close browser pool during shutdown: %s", e)

    # Close Telegram notifier HTTP client to prevent leaked sockets
    try:
        from app.services.notifications import get_telegram_notifier

        _notifier = get_telegram_notifier()
        if _notifier is not None:
            await _notifier.close()
            logger.info("Telegram notifier closed successfully")
    except Exception as e:
        logger.warning("Failed to close Telegram notifier during shutdown: %s", e)


def schedule_background_task(coro):
    """Schedule a background task with error handling."""
    task = asyncio.create_task(coro)

    def _handle_task_result(t: asyncio.Task) -> None:
        try:
            t.result()
        except asyncio.CancelledError:
            pass  # nosec B110
        except Exception:
            logger.exception("Background task failed")

    task.add_done_callback(_handle_task_result)
    return task


def persist_single_wrapper(job_id: str, critical: bool = False) -> None:  # noqa: FBT001, FBT002
    """Persist a single job to the configured backend."""
    job = jobs_store.get(job_id)
    if job:
        try:
            get_job_repository().save_single(job)
        except Exception:
            logger.exception("Failed to persist single job %s", job_id)
            if critical:
                raise


async def run_job_wrapper(job_id: str) -> None:
    """Run a job with all standard options wired from settings."""
    import app.main as main_mod

    persist_fn = getattr(main_mod, "_persist_state_wrapper", persist_state_wrapper)
    persist_single_fn = getattr(main_mod, "_persist_single_wrapper", persist_single_wrapper)

    await run_job(
        job_id=job_id,
        jobs_store=jobs_store,
        persist_state_fn=persist_fn,
        max_discovery_urls=settings.MAX_DISCOVERY_URLS,
        max_job_runtime_seconds=settings.MAX_JOB_RUNTIME_SECONDS,
        per_url_scrape_timeout_seconds=settings.PER_URL_TIMEOUT_SECONDS,
        ai_structuring_timeout_seconds=settings.AI_STRUCTURING_TIMEOUT_SECONDS,
        insight_timeout_seconds=settings.INSIGHT_TIMEOUT_SECONDS,
        persist_state_single_fn=lambda: persist_single_fn(job_id, critical=False),
        persist_state_single_critical_fn=lambda: persist_single_fn(job_id, critical=True),
    )


async def _rate_limit_prune_loop() -> None:
    """Periodically prune stale rows from the ``rate_limits`` table.

    Runs on the ``RATE_LIMIT_PRUNE_INTERVAL`` (default 3600s). Catches
    all exceptions so a transient DB error never kills the loop. The
    loop is cancelled by the lifespan shutdown handler which cancels
    all ``_background_tasks``.

    The method is idempotent and safe to call even when the
    ``rate_limits`` table has never been created (the DELETE is
    silently ignored by both SQLite and Postgres).
    """
    from app.rate_limiter import DatabaseSlidingWindowCounter

    while True:
        try:
            await asyncio.sleep(settings.RATE_LIMIT_PRUNE_INTERVAL)
            DatabaseSlidingWindowCounter.prune_all()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Rate limit table pruning background task failed (non-blocking)")


def persist_state_wrapper() -> None:
    """Persist all jobs and recycle bin to the configured backend."""
    repo = get_job_repository()
    repo.save_all(jobs=jobs_store, recycle_bin=recycle_bin_store)
