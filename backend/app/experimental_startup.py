"""
Experimental Subsystem Initialization (EXPERIMENTAL / RESEARCH ONLY).

Centralizes the startup and shutdown of experimental subsystems that were
previously initialized inline in main.py's lifespan function.

Modules managed here:
- graph_update_scheduler — event cascade scheduling
- recovery_handlers — extraction failure recovery framework
- domain_health_alerts — per-domain health monitoring
- gossip_substrate — peer discovery and state propagation (experimental)
- heartbeat_manager — peer liveness tracking (experimental)
- semantic_world_state — semantic field state (experimental)

All imports are lazy so that missing experimental modules do not prevent
the core app from starting.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def init_graph_scheduler() -> None:
    """Initialize the event cascade scheduler (safe: lazy-created, no circular imports)."""
    try:
        from app.graph_update_scheduler import get_scheduler
        get_scheduler()
        logger.debug("Graph update scheduler initialized")
    except Exception as e:
        logger.warning("Failed to initialize graph update scheduler: %s", e)


def init_recovery_framework() -> None:
    """Register all recovery handlers for extraction failure scenarios."""
    try:
        from app.recovery_handlers import register_all_recovery_handlers
        register_all_recovery_handlers()
        logger.debug("Recovery handlers registered")
    except Exception as e:
        logger.warning("Failed to register recovery handlers: %s", e)


def init_domain_health_monitor() -> None:
    """Initialize the per-domain health monitoring subsystem."""
    try:
        from app.domain_health_alerts import get_domain_health_monitor
        get_domain_health_monitor()
        logger.debug("Domain health monitor initialized")
    except Exception as e:
        logger.warning("Failed to initialize domain health monitor: %s", e)


def init_gossip_and_heartbeat() -> tuple[Any, Any]:
    """Initialize distributed readiness (gossip + heartbeat) subsystems.

    Returns:
        Tuple of (gossip_substrate, heartbeat_manager), or (None, None) if
        initialization fails.
    """
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
    except Exception as e:
        logger.warning("Failed to initialize gossip / heartbeat: %s", e)
    return gossip, heartbeat_mgr


def restore_semantic_world_state(world_state_data: dict | None, state_file_path: str = "") -> None:
    """Restore semantic world state from persisted data."""
    if not world_state_data:
        return
    try:
        from app.semantic_world_state import get_world_state
        get_world_state().from_dict(world_state_data)
        logger.info("Restored semantic world state from %s", state_file_path)
    except Exception as e:
        logger.exception("Failed to restore semantic world state: %s", e)


def persist_semantic_world_state() -> None:
    """Persist semantic world state to repository on shutdown."""
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
    """Close the Postgres connection pool if active."""
    try:
        from app.postgres_repository import shutdown_postgres
        shutdown_postgres()
    except ImportError:
        logger.debug("Postgres support is not installed; no Postgres pool to close")
    except Exception as e:
        logger.warning("Failed to close Postgres connection pool during shutdown: %s", e)


async def schedule_gossip_propagation(gossip: Any, heartbeat_mgr: Any, interval: float = 60.0) -> asyncio.Task | None:
    """Schedule periodic gossip state propagation as a background task.

    Returns the task handle, or None if gossip is not initialized.
    """
    if gossip is None:
        return None

    async def _propagate():
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
