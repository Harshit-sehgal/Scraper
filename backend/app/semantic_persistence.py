
"""
Semantic Persistence Hub
=========================
Single orchestrator for all semantic memory and learned state.
Unifies:
1. Role compatibility (RoleEmbeddingEngine)
2. Boundary decisions (SemanticBoundaryEngine)
3. Successful motifs (SemanticMemory)
"""

import json
import logging
import os
import fcntl

from app.semantic_world_state import get_world_state


_STATE_LOCK_PATH: str | None = None


def _get_lock_path() -> str:
    global _STATE_LOCK_PATH
    if _STATE_LOCK_PATH is None:
        cache = os.environ.get('SEMANTIC_STATE_PATH', '/tmp/semantic_state_v2.json')
        _STATE_LOCK_PATH = cache + '.lock'
    return _STATE_LOCK_PATH


def get_canonical_cache_path() -> str:
    return os.environ.get('SEMANTIC_STATE_PATH', '/tmp/semantic_state_v2.json')


def _acquire_lock():
    path = _get_lock_path()
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _release_lock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    except OSError:
        pass


def load_semantic_state():
    path = get_canonical_cache_path()
    if not os.path.exists(path):
        return

    lock_fd = _acquire_lock()
    try:
        with open(path, 'r') as f:
            full_state = json.load(f)
        ws = get_world_state()
        ws.from_dict(full_state)
        logging.getLogger(__name__).info("Loaded unified semantic state from %s", path)
    except Exception as e:
        logging.getLogger(__name__).error("Failed to load semantic state: %s", e)
    finally:
        _release_lock(lock_fd)


def save_semantic_state():
    path = get_canonical_cache_path()
    lock_fd = _acquire_lock()
    try:
        ws = get_world_state()
        full_state = ws.to_dict()
        full_state["version"] = "3.0"
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w') as f:
            json.dump(full_state, f, indent=2)
        logging.getLogger(__name__).info("Saved unified semantic state to %s", path)
    except Exception as e:
        logging.getLogger(__name__).error("Failed to save semantic state: %s", e)
    finally:
        _release_lock(lock_fd)


def clear_semantic_state(clear_file: bool = True):
    """Reset all learned semantic state."""
    if clear_file:
        path = get_canonical_cache_path()
        if os.path.exists(path):
            os.remove(path)
    
    # Reset unified world state
    get_world_state().clear()
    
    # Ensure bootstrap values are re-applied if needed (the engines' __init__ handles this if they are re-instantiated, 
    # but since they might be singletons, we should be careful. Actually RoleTransitionDetector re-applies it in __init__ 
    # if it's empty, but if the engine object already exists, we might need to manually re-apply.)
    from app.semantic_boundary_engine import _BOOTSTRAP_TRANSITIONS
    get_world_state().transition_probs.update(_BOOTSTRAP_TRANSITIONS)
