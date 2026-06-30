"""Lifespan — FastAPI startup / shutdown lifecycle hooks.

Extracted from main.py as part of Phase 3 refactoring to keep the app factory
thin and allow individual lifecycle components to be tested in isolation.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.globals import _jobs_store_lock, jobs_store, recycle_bin_store
from app.services.job_runner import run_job
from app.state_store import get_state_file_path
from app.storage_interface import get_job_repository

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Exceptions that cleanup/shutdown handlers should tolerate rather than
# allowing to propagate. This covers the most likely operational errors
# (missing modules, OS issues, bad state) without masking programming
# errors like NameError or SyntaxError.
_SHUTDOWN_EXCEPTIONS = (RuntimeError, OSError, ImportError, AttributeError, TypeError, ValueError)

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


def _verify_production_startup() -> None:
    """Strict production security checks — fail fast with clear messages."""
    if settings.ENV.lower() != "production":
        return
    if not settings.CORS_ORIGINS or "*" in settings.CORS_ORIGINS:
        _cors_msg = (
            "CORS_ORIGINS contains wildcard '*' or is empty. In production environment, "
            "CORS_ORIGINS must be locked down to trusted domains for safety."
        )
        raise ValueError(_cors_msg)
    from app.utils.prod_security_validator import validate_production_credentials

    validate_production_credentials(settings)
    if getattr(settings, "SMOKE_TEST_MODE", False):
        _smoke_msg = (
            "SMOKE_TEST_MODE is ENABLED in production — this bypasses "
            "SSRF host-allowlist checks and allows internal-network "
            "access.  Set DATAFORGE_SMOKE_TEST_MODE=false before "
            "deploying to production."
        )
        raise ValueError(_smoke_msg)


def _warn_empty_api_keys() -> None:
    """Log a warning if all API keys are empty in non-production environments."""
    if (
        settings.ENV.lower() != "production"
        and not settings.API_KEY
        and not settings.ADMIN_API_KEY
        and not settings.OPERATOR_API_KEY
    ):
        logger.warning(
            "ALL API keys are empty — API endpoints are UNAUTHENTICATED. "
            "Set DATAFORGE_API_KEY, DATAFORGE_ADMIN_API_KEY, or DATAFORGE_OPERATOR_API_KEY "
            "to enable authentication.",
        )


def _validate_startup_config() -> None:
    """Best-effort startup config validation; does not raise in dev/test."""
    try:
        from app.utils.env_validation import validate_startup_config

        validate_startup_config()
    except Exception as exc:
        logger.debug("Startup config validation skipped: %s", exc)


def _init_experimental_subsystems() -> tuple[Any, Any]:
    """Initialize research-only subsystems if the experimental flag is set."""
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
        return init_gossip_and_heartbeat()
    logger.info(
        "Experimental subsystems DISABLED — research shell will not initialize "
        "(set DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true to enable)",
    )
    return None, None


def _verify_schema_version() -> None:
    """Check that the connected DB schema matches the code's expected version."""
    try:
        from app.storage_migrations import POSTGRES_SCHEMA_VERSION, SQLITE_SCHEMA_VERSION

        if job_repo is not None:
            backend = getattr(job_repo, "backend", None) or "unknown"
            fencer = getattr(job_repo, "get_storage_status", None) or getattr(job_repo, "health_check", None)
            if callable(fencer):
                status = fencer()
                actual_version = status.get("schema_version") if isinstance(status, dict) else None
                expected_version = status.get("expected_version") if isinstance(status, dict) else None
                # Use expected_version from storage status if available;
                # fall back to backend-appropriate constant.
                if expected_version is None:
                    expected_version = SQLITE_SCHEMA_VERSION if backend == "sqlite" else POSTGRES_SCHEMA_VERSION
                if actual_version is not None and int(actual_version) != int(expected_version):
                    msg = (
                        f"DB schema version mismatch on backend={backend}: "
                        f"connected schema_version={actual_version}, expected "
                        f"{expected_version}. Refusing to start to avoid "
                        f"data corruption."
                    )
                    if settings.ENV.lower() in ("production", "staging"):
                        raise RuntimeError(msg)
                    logger.error(
                        "%s — continuing in dev mode; fix in prod by running the migration before deploying.",
                        msg,
                    )
                else:
                    logger.info(
                        "Schema version fence passed (backend=%s version=%s)",
                        backend,
                        actual_version,
                    )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.debug("Schema version fence skipped: %s", exc)


def _verify_ssrf_transport() -> None:
    """Confirm the safe httpx transport factory still works."""
    from app.url_safety import verify_ssrf_self_check

    ssrf_check = verify_ssrf_self_check()
    if not ssrf_check.get("ok"):
        msg = (
            f"SSRF self-check failed: {ssrf_check.get('reason', 'unknown')}. "
            f"httpx={ssrf_check.get('httpx_version')} "
            f"httpcore={ssrf_check.get('httpcore_version')}. "
            "Pin supported versions in pyproject.toml."
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


def _load_persisted_state(world_state_data: Any) -> None:
    """Restore job store and semantic world state from persistence."""
    from app.experimental_startup import restore_semantic_world_state

    restore_semantic_world_state(world_state_data, str(get_state_file_path()))


async def _schedule_all_background_tasks(gossip: Any, heartbeat_mgr: Any) -> list[asyncio.Task]:
    """Schedule all periodic background tasks."""
    tasks: list[asyncio.Task] = []

    # Gossip propagation (experimental)
    from app.experimental_startup import schedule_gossip_propagation

    gossip_task = await schedule_gossip_propagation(gossip, heartbeat_mgr, interval=settings.GOSSIP_PROPAGATION_INTERVAL)
    if gossip_task:
        tasks.append(gossip_task)

    # Rate limits table pruning
    if settings.RATE_LIMIT_PRUNE_INTERVAL > 0:
        tasks.append(schedule_background_task(_rate_limit_prune_loop()))

    # Scheduled job processing
    tasks.append(schedule_background_task(_scheduled_job_processor_loop()))

    # Data retention enforcement
    tasks.append(schedule_background_task(_data_retention_loop()))

    return tasks


async def _cancel_all_background_tasks(tasks: list[asyncio.Task]) -> None:
    """Cancel all background tasks with a 10s timeout."""
    for t in tasks:
        t.cancel()
    if tasks:
        _done, pending = await asyncio.wait(tasks, timeout=10)
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    tasks.clear()
    logger.info("Background tasks cleaned up")


async def _shutdown_cleanup() -> None:
    """Shut down all runtime services gracefully."""
    # Persist semantic world state
    from app.experimental_startup import persist_semantic_world_state

    persist_semantic_world_state()

    # Flush state writes
    try:
        from app.state_store import flush_state_writes

        flush_state_writes()
    except (ImportError, OSError) as e:
        logger.warning("Failed to flush state writes during shutdown: %s", e)

    # Close Postgres connection pool
    from app.experimental_startup import close_postgres_pool

    close_postgres_pool()

    # Close browser pool
    try:
        from app.browser_pool import get_browser_pool

        await get_browser_pool().close()
        logger.info("Browser pool closed successfully")
    except _SHUTDOWN_EXCEPTIONS as e:
        logger.warning("Failed to close browser pool during shutdown: %s", e)

    # Close Telegram notifier
    try:
        from app.services.notifications import get_telegram_notifier

        _notifier = get_telegram_notifier()
        if _notifier is not None:
            await _notifier.close()
            logger.info("Telegram notifier closed successfully")
    except _SHUTDOWN_EXCEPTIONS as e:
        logger.warning("Failed to close Telegram notifier during shutdown: %s", e)

    # Shut down log persistence executor
    try:
        from app.services.job_runner import shutdown_log_persist_executor

        shutdown_log_persist_executor()
        logger.info("Log persistence executor shut down")
    except _SHUTDOWN_EXCEPTIONS as e:
        logger.warning("Failed to shut down log persistence executor: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for FastAPI startup / shutdown."""
    global gossip, heartbeat_mgr

    _verify_production_startup()
    _validate_startup_config()
    _warn_empty_api_keys()

    from app.runtime_deps import check_runtime_deps

    check_runtime_deps(fail_on_missing=(settings.ENV.lower() == "production"))

    gossip, heartbeat_mgr = _init_experimental_subsystems()

    from app.globals import rebuild_config_from_settings

    rebuild_config_from_settings()

    global job_repo
    job_repo = get_job_repository()

    _verify_schema_version()
    _verify_ssrf_transport()

    loaded_jobs, loaded_recycle, world_state_data = job_repo.load_all()
    with _jobs_store_lock:
        jobs_store.clear()
        jobs_store.update(loaded_jobs)
        recycle_bin_store.clear()
        recycle_bin_store.update(loaded_recycle)

    _load_persisted_state(world_state_data)

    _background_tasks = await _schedule_all_background_tasks(gossip, heartbeat_mgr)

    yield

    await _cancel_all_background_tasks(_background_tasks)
    await _shutdown_cleanup()


def schedule_background_task(coro):
    """Schedule a background task with error handling."""
    task = asyncio.create_task(coro)

    def _handle_task_result(t: asyncio.Task) -> None:
        try:
            t.result()
        except asyncio.CancelledError as exc:
            logger.debug("Background task cancelled: %s", exc)
        except _SHUTDOWN_EXCEPTIONS:
            logger.exception("Background task failed")

    task.add_done_callback(_handle_task_result)
    return task


def persist_single_wrapper(job_id: str, critical: bool = False) -> None:
    """Persist a single job to the configured backend."""
    with _jobs_store_lock:
        job = jobs_store.get(job_id)
    if job:
        try:
            get_job_repository().save_single(job)
        except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
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


async def _scheduled_job_processor_loop() -> None:
    """Periodically check for due scheduled jobs and enqueue them.

    Reads the file-backed scheduled job store every 60 seconds, finds
    enabled jobs whose ``next_run_at`` has passed, creates a new scrape
    job from the template, and updates the schedule's next run time.

    This loop is cancelled by the lifespan shutdown handler which
    cancels all ``_background_tasks``.
    """
    _SCHEDULED_POLL_INTERVAL = 60  # seconds
    while True:
        try:
            await asyncio.sleep(_SCHEDULED_POLL_INTERVAL)
        except asyncio.CancelledError:
            break

        try:
            await _process_due_scheduled_jobs()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Scheduled job processor loop failed (non-blocking)")


async def _process_due_scheduled_jobs() -> None:
    """Find and execute all due scheduled jobs."""
    from datetime import UTC, datetime, timedelta

    from app.routers.scheduled_monitoring import _scheduled_jobs, _write_back

    now_iso = datetime.now(UTC).isoformat()
    now_dt = datetime.now(UTC)

    # Frequency to timedelta mapping for computing next_run_at
    _FREQUENCY_DELTAS: dict[str, timedelta] = {
        "hourly": timedelta(hours=1),
        "daily": timedelta(days=1),
        "weekly": timedelta(weeks=1),
        "monthly": timedelta(days=30),
    }

    due_jobs: list[dict[str, Any]] = []
    for item in _scheduled_jobs.values():
        if not item.get("enabled", True):
            continue
        next_run = str(item.get("next_run_at") or "")
        if next_run and next_run <= now_iso:
            due_jobs.append(item)

    if not due_jobs:
        return

    logger.info("Found %d due scheduled job(s) to process", len(due_jobs))

    for scheduled in due_jobs:
        sched_id = str(scheduled.get("id") or "")
        try:
            # Build a job from the scheduled template
            from app.models import Job, ScrapeMode

            urls = list(scheduled.get("urls") or [])
            mode_str = str(scheduled.get("mode") or "manual")
            mode = ScrapeMode.MANUAL if mode_str == "manual" else ScrapeMode.AUTO

            # Create a new job record (not via the API, directly)
            from app.globals import jobs_store
            from app.routers.jobs_state import save_job

            job_name = str(scheduled.get("job_name") or scheduled.get("name") or "Scheduled Job")
            job = Job(  # type: ignore[call-arg]
                name=f"{job_name} (scheduled {now_dt.strftime('%Y-%m-%d %H:%M')})",
                mode=mode,
                urls=urls,
                topic=str(scheduled.get("topic") or ""),
                location=str(scheduled.get("location") or ""),
                schema_fields=list(scheduled.get("schema_fields") or []),
                filters=list(scheduled.get("filters") or []),
                pagination=bool(scheduled.get("pagination", False)),
                max_pages=int(scheduled.get("max_pages", 10)),
                deduplicate=bool(scheduled.get("deduplicate", True)),
                min_record_score=float(scheduled.get("min_record_score", 0.35)),
                created_by=str(scheduled.get("user_id") or ""),
                org_id=str(scheduled.get("org_id") or ""),
                project_id=str(scheduled.get("project_id") or ""),
            )
            with _jobs_store_lock:
                jobs_store[job.id] = job
            await save_job(job)

            # Execute the job
            await run_job_wrapper(job.id)

            # Update next_run_at — prefer cron expression, fall back to frequency delta
            cron_expr = str(scheduled.get("cron_expression") or "").strip()
            if cron_expr:
                try:
                    from app.utils.cron_parser import next_after as cron_next_after

                    next_run_dt = cron_next_after(now_dt, cron_expr)
                except Exception:
                    logger.warning("Cron %r failed; falling back to frequency delta", cron_expr)
                    frequency = str(scheduled.get("frequency") or "daily").lower()
                    delta = _FREQUENCY_DELTAS.get(frequency, timedelta(days=1))
                    next_run_dt = now_dt + delta
            else:
                frequency = str(scheduled.get("frequency") or "daily").lower()
                delta = _FREQUENCY_DELTAS.get(frequency, timedelta(days=1))
                next_run_dt = now_dt + delta
            scheduled["next_run_at"] = next_run_dt.isoformat()
            scheduled["last_run_at"] = now_iso
            scheduled["last_run_status"] = "completed"
            scheduled["last_run_records_count"] = len(job.results) if hasattr(job, "results") else 0
            scheduled["total_executions"] = int(scheduled.get("total_executions", 0)) + 1
            scheduled["successful_executions"] = int(scheduled.get("successful_executions", 0)) + 1

            # Add to recent_run_summaries (capped at 10)
            summaries = list(scheduled.get("recent_run_summaries") or [])
            summaries.append(
                {
                    "ran_at": now_iso,
                    "status": "completed",
                    "records_count": len(job.results) if hasattr(job, "results") else 0,
                    "job_id": job.id,
                }
            )
            scheduled["recent_run_summaries"] = summaries[-10:]

            # Persist the updated schedule
            _write_back(scheduled)

            logger.info(
                "Scheduled job %s (%s) executed, next run at %s",
                scheduled.get("name", ""),
                sched_id,
                scheduled["next_run_at"],
            )
        except Exception:
            logger.exception("Failed to process scheduled job %s", sched_id)


async def _data_retention_loop() -> None:
    """Periodically enforce data retention policy.

    Runs every 12 hours (configurable via ``DATAFORGE_RETENTION_INTERVAL``
    or ``retention_run_interval_seconds`` in settings). Removes completed
    jobs and recycle-bin items older than the configured TTL by calling
    ``enforce_retention`` with ``dry_run=False``.

    The loop is cancelled by the lifespan shutdown handler which cancels
    all ``_background_tasks``.
    """
    retention_interval = getattr(settings, "retention_run_interval_seconds", None) or (
        int(os.environ.get("DATAFORGE_RETENTION_INTERVAL", "43200"))
    )
    while True:
        try:
            await asyncio.sleep(retention_interval)
        except asyncio.CancelledError:
            break

        try:
            from app.globals import _jobs_store_lock, jobs_store, recycle_bin_store
            from app.utils.data_retention import (
                enforce_idempotency_retention,
                enforce_retention,
            )
            from app.utils.retention_monitoring import record_retention_run

            with _jobs_store_lock:
                result = enforce_retention(jobs_store, recycle_bin_store, dry_run=False)
            idem_deleted = enforce_idempotency_retention(dry_run=False)

            # Persist the deletions to the database
            if result["jobs_purged"] > 0 or result["recycle_purged"] > 0:
                try:
                    from app.storage_interface import get_job_repository

                    repo = get_job_repository()
                    with _jobs_store_lock:
                        repo.save_all(jobs=dict(jobs_store), recycle_bin=dict(recycle_bin_store), prune_missing=True)
                except (ImportError, RuntimeError) as e:
                    logger.warning("Retention background task failed to persist: %s", e)

            # Record success for monitoring
            record_retention_run(result)

            total_purged = result["jobs_purged"] + result["recycle_purged"] + idem_deleted
            if total_purged > 0:
                logger.info(
                    "Data retention: purged %d jobs, %d recycle items, %d idempotency keys",
                    result["jobs_purged"],
                    result["recycle_purged"],
                    idem_deleted,
                )

        except asyncio.CancelledError:
            break
        except Exception as e:
            from app.utils.retention_monitoring import record_retention_run

            record_retention_run(result=None, error=e)
            logger.exception("Data retention background task failed (non-blocking)")


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
        except _SHUTDOWN_EXCEPTIONS:
            logger.exception("Rate limit table pruning background task failed (non-blocking)")


def persist_state_wrapper() -> None:
    """Persist all jobs and recycle bin to the configured backend."""
    repo = get_job_repository()
    # Snapshot the dicts under the lock so a concurrent mutation cannot
    # observe a torn/empty dict during save_all().
    with _jobs_store_lock:
        repo.save_all(jobs=dict(jobs_store), recycle_bin=dict(recycle_bin_store))
