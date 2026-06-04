"""Experimental Subsystem Initialization (EXPERIMENTAL / RESEARCH ONLY).

Centralizes the startup and shutdown of experimental subsystems that were
previously initialized inline in main.py's lifespan function.

Modules managed here:
- graph_update_scheduler — event cascade scheduling
- recovery_handlers — extraction failure recovery framework
- domain_health_alerts — per-domain health monitoring
- gossip_substrate — peer discovery and state propagation (experimental)
- heartbeat_manager — peer liveness tracking (experimental)
- semantic_world_state — semantic field state (experimental)

Boundary contract
-----------------
Every public function in this module is a NO-OP when the
`ENABLE_EXPERIMENTAL_ROUTES` setting is false. This is the import-time
gate that quarantines the research shell from the product kernel.

Callers (lifespan, shutdown) MUST call `experimental_subsystems_enabled()`
once to confirm the gate is open before depending on the return values
of `init_gossip_and_heartbeat()` and `schedule_gossip_propagation()`,
both of which return None / (None, None) when disabled.

All imports remain lazy so that missing experimental modules do not
prevent the core app from starting in either case.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def experimental_subsystems_enabled() -> bool:
    """Return True iff the research subsystems should be initialized.

    Reads `settings.ENABLE_EXPERIMENTAL_ROUTES` on every call so the
    gate is always fresh. Defaults to False; operators must explicitly
    opt-in via the DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES env var.
    """
    try:
        from app.config import settings

        return bool(getattr(settings, "ENABLE_EXPERIMENTAL_ROUTES", False))
    except (ImportError, AttributeError, ValueError):
        logger.warning("Could not read ENABLE_EXPERIMENTAL_ROUTES")
        return False


def init_graph_scheduler() -> None:
    """Initialize the event cascade scheduler (safe: lazy-created, no circular imports)."""
    if not experimental_subsystems_enabled():
        logger.debug("init_graph_scheduler: skipped (experimental subsystems disabled)")
        return
    try:
        from app.graph_update_scheduler import get_scheduler

        get_scheduler()
        logger.debug("Graph update scheduler initialized")
    except ImportError:
        logger.warning("Failed to initialize graph update scheduler (module not available)")


def init_recovery_framework() -> None:
    """Register all recovery handlers for extraction failure scenarios."""
    if not experimental_subsystems_enabled():
        logger.debug("init_recovery_framework: skipped (experimental subsystems disabled)")
        return
    try:
        from app.recovery_handlers import register_all_recovery_handlers

        register_all_recovery_handlers()
        logger.debug("Recovery handlers registered")
    except ImportError:
        logger.warning("Failed to register recovery handlers (module not available)")


def init_domain_health_monitor() -> None:
    """Initialize the per-domain health monitoring subsystem."""
    if not experimental_subsystems_enabled():
        logger.debug("init_domain_health_monitor: skipped (experimental subsystems disabled)")
        return
    try:
        from app.domain_health_alerts import get_domain_health_monitor

        get_domain_health_monitor()
        logger.debug("Domain health monitor initialized")
    except ImportError:
        logger.warning("Failed to initialize domain health monitor (module not available)")


def init_gossip_and_heartbeat() -> tuple[Any, Any]:
    """Initialize distributed readiness (gossip + heartbeat) subsystems.

    Returns:
        Tuple of (gossip_substrate, heartbeat_manager), or (None, None) if
        initialization fails OR if experimental subsystems are disabled.

    """
    if not experimental_subsystems_enabled():
        logger.debug("init_gossip_and_heartbeat: skipped (experimental subsystems disabled)")
        return None, None
    gossip = None
    heartbeat_mgr = None
    try:
        from app.gossip_substrate import get_gossip_substrate
        from app.heartbeat_manager import get_heartbeat_manager

        heartbeat_mgr = get_heartbeat_manager()
        gossip = get_gossip_substrate(node_id="main")
        gossip.integrate_heartbeat(heartbeat_mgr)
        logger.info(
            "Gossip substrate integrated with heartbeat: %d peers registered",
            len(gossip.known_nodes),
        )
    except ImportError:
        logger.warning("Failed to initialize gossip / heartbeat (module not available)")
    return gossip, heartbeat_mgr


def restore_semantic_world_state(world_state_data: dict | None, state_file_path: str = "") -> None:
    """Restore semantic world state from persisted data."""
    if not experimental_subsystems_enabled():
        return
    if not world_state_data:
        return
    try:
        from app.semantic_world_state import get_world_state

        get_world_state().from_dict(world_state_data)
        logger.info("Restored semantic world state from %s", state_file_path)
    except Exception:
        logger.exception("Failed to restore semantic world state: %s")


def persist_semantic_world_state() -> None:
    """Persist semantic world state to repository on shutdown."""
    if not experimental_subsystems_enabled():
        return
    try:
        from app.storage_interface import get_job_repository

        repo = get_job_repository()
        if hasattr(repo, "save_world_state"):
            from app.semantic_world_state import get_world_state

            ws = get_world_state()
            try:
                repo.save_world_state(ws.to_dict())
                logger.info("Semantic world state persisted to repository on shutdown")
            except Exception as e:
                logger.warning("Failed to persist world state on shutdown: %s", e)
    except Exception as e:
        logger.warning("Failed to check repository support for world state during shutdown: %s", e)


def close_postgres_pool() -> None:
    """Close the Postgres connection pool if active.

    This function is intentionally NOT gated by the experimental flag —
    Postgres is a product-kernel storage backend, and its connection
    pool must be closed cleanly regardless of whether experimental
    subsystems are running.
    """
    try:
        from app.postgres_repository import shutdown_postgres

        shutdown_postgres()
    except ImportError:
        logger.debug("Postgres support is not installed; no Postgres pool to close")
    except Exception as e:
        logger.warning("Failed to close Postgres connection pool during shutdown: %s", e)


async def schedule_gossip_propagation(gossip: Any, heartbeat_mgr: Any, interval: float = 60.0) -> asyncio.Task | None:
    """Schedule periodic gossip state propagation as a background task.

    Returns the task handle, or None if gossip is not initialized OR if
    experimental subsystems are disabled.
    """
    if not experimental_subsystems_enabled():
        return None
    if gossip is None:
        return None

    async def _propagate() -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                if gossip is not None:
                    propagated = gossip.propagate_state_via_gossip(heartbeat_manager=heartbeat_mgr)
                    if propagated:
                        logger.debug("Propagated gossip state to %d peers", propagated)
            except Exception as e:
                logger.debug("Gossip propagation skipped: %s", e)

    task = asyncio.create_task(_propagate())
    logger.info("Gossip propagation background task scheduled (interval=%ds)", interval)
    return task
