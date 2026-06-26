"""Semantic Persistence Hub.
=========================

Single orchestrator for all semantic memory and learned state.
Unifies:
1. Role compatibility (Role Manifold)
2. Boundary decisions (Topological Cohesion)
3. Learning count (experience manifold)
"""

import fcntl
import json
import logging
import os
from pathlib import Path

from app.config import settings
from app.utils.common_persistence import atomic_json_write

logger = logging.getLogger(__name__)

_STATE_LOCK_PATH: str | None = None


def _get_lock_path() -> str:
    global _STATE_LOCK_PATH
    if _STATE_LOCK_PATH is None:
        cache = get_canonical_cache_path()
        _STATE_LOCK_PATH = cache + ".lock"
    return _STATE_LOCK_PATH


def get_canonical_cache_path() -> str:
    return settings.SEMANTIC_STATE_PATH_DYNAMIC


def _acquire_lock():
    path = _get_lock_path()
    if os.path.dirname(path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
    except OSError:
        os.close(fd)
        raise
    return fd


def _release_lock(fd) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    except OSError:
        logger.debug("Failed to release semantic state lock (fd=%s)", fd, exc_info=True)


def load_semantic_state() -> None:
    path = get_canonical_cache_path()
    if not Path(path).exists():
        return

    lock_fd = _acquire_lock()
    try:
        with open(path) as f:
            full_state = json.load(f)
        import app.semantic_world_state

        ws = app.semantic_world_state.get_world_state()
        ws.from_dict(full_state)
        logger.info("Loaded unified semantic state from %s", path)
    except Exception:
        logger.exception("Failed to load semantic state")
    finally:
        _release_lock(lock_fd)


def save_semantic_state() -> None:
    path = get_canonical_cache_path()
    lock_fd = _acquire_lock()
    try:
        import app.semantic_world_state

        ws = app.semantic_world_state.get_world_state()
        full_state = ws.to_dict()
        full_state["version"] = "3.0"
        atomic_json_write(full_state, path)
        logger.info("Saved unified semantic state to %s", path)
    except Exception:
        logger.exception("Failed to save semantic state")
    finally:
        _release_lock(lock_fd)


def clear_semantic_state(clear_file: bool = True) -> None:
    """Reset all learned semantic state."""
    if clear_file:
        path = get_canonical_cache_path()
        if Path(path).exists():
            Path(path).unlink()

    # Reset unified world state
    import app.semantic_world_state

    app.semantic_world_state.get_world_state().clear()

    # Ensure bootstrap values are re-applied if needed (the engines' __init__ handles this if they are re-instantiated,
    # but since they might be singletons, we should be careful. Actually RoleTransitionDetector re-applies it in __init__
    # if it's empty, but if the engine object already exists, we might need to
    # manually re-apply.)
    from app.semantic_boundary_engine import _BOOTSTRAP_TRANSITIONS

    app.semantic_world_state.get_world_state().update_seed_transition(_BOOTSTRAP_TRANSITIONS)
