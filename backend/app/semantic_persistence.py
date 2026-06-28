"""Semantic Persistence Hub.
=========================

Single orchestrator for all semantic memory and learned state.
Unifies:
1. Role compatibility (Role Manifold)
2. Boundary decisions (Topological Cohesion)
3. Learning count (experience manifold)

Thread-safety contract
----------------------
The canonical world state is a process-wide mutable singleton
(``app.semantic_world_state._world_state``) shared across async tasks and
any worker threads that perform persistence I/O. Without coordination,
concurrent load/save/clear operations can race on the underlying
subsystem state objects and produce torn reads/writes.

This module guards all access through two layers:

1. A module-level ``threading.Lock`` (``_PERSISTENCE_LOCK``) serializes
   load/save/clear against each other so that, e.g., a ``save`` snapshot
   cannot be interleaved with an in-flight ``load`` that mutates the
   shared singleton.
2. The world-state's own reentrant ``_lock`` is acquired for every
   mutating call (``clear`` / ``update_seed_transition`` / ``from_dict``)
   so that persistence-level writes cannot race with engine-level
   readers and writers running on other tasks.

Additionally, every dict that leaves this module — either as the value
returned to a caller or as the payload serialized to disk — is passed
through ``copy.deepcopy`` so the caller cannot mutate the live shared
state through a shared reference.
"""

import contextlib
import copy
import fcntl
import json
import logging
import os
import threading
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# Serializes load/save/clear against each other. Distinct from the
# per-process file lock (``_acquire_lock`` below) which guards the on-disk
# cache file: this lock additionally guards in-memory mutation of the
# shared world-state singleton.
_PERSISTENCE_LOCK = threading.Lock()

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
    except OSError as exc:
        # Lock release / fd close failures are non-fatal — the fd is likely
        # already invalid (process Exit, NFS reclaim).  Log at debug so
        # operators can still see it without noise.
        logger.debug("Lock release/close failed (fd likely stale): %s", exc)


def load_semantic_state() -> None:
    path = get_canonical_cache_path()
    if not Path(path).exists():
        return

    lock_fd = _acquire_lock()
    try:
        with open(path) as f:
            full_state = json.load(f)
        # CoW: deepcopy the parsed payload so any aliasing attackers
        # (future code accidentally storing ``full_state`` references)
        # can't mutate the dict we hand to ``from_dict``.
        full_state = copy.deepcopy(full_state)

        # Acquire the persistence lock before touching the shared
        # world state so a concurrent save/clear cannot interleave.
        with _PERSISTENCE_LOCK:
            import app.semantic_world_state

            ws = app.semantic_world_state.get_world_state()
            # ``from_dict`` clears and rebuilds subsystem state; acquire
            # the world-state's own lock for the duration so concurrent
            # engine readers can't observe a half-rebuilt state.
            with ws._lock:
                ws.from_dict(full_state)
        logger.info("Loaded unified semantic state from %s", path)
    except Exception:
        logger.exception("Failed to load semantic state")
    finally:
        _release_lock(lock_fd)


def save_semantic_state() -> None:
    path = get_canonical_cache_path()
    lock_fd = _acquire_lock()
    fd: int | None = None
    tmp_path: str | None = None
    try:
        with _PERSISTENCE_LOCK:
            import app.semantic_world_state

            ws = app.semantic_world_state.get_world_state()
            # ``to_dict`` already snapshots under ``ws._lock`` and returns
            # a fresh dict, but we deepcopy defensively so that any future
            # refactor that returns a shared mutable structure cannot
            # leak an in-process alias to disk-serializing code below.
            snapshot = copy.deepcopy(ws.to_dict())
        snapshot["version"] = "3.0"
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        import tempfile

        fd, tmp_path = tempfile.mkstemp(dir=Path(path).parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            fd = None  # ownership transferred to fdopen context manager
            json.dump(snapshot, f, indent=2)
            # Crash-safety: fsync the data to disk BEFORE os.replace so
            # a power failure between write and rename cannot leave the
            # previous valid state replaced with a zero-byte file.
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        tmp_path = None  # ownership transferred via rename
        logger.info("Saved unified semantic state to %s", path)
    except Exception:
        logger.exception("Failed to save semantic state")
        with contextlib.suppress(OSError):
            if fd is not None:
                os.close(fd)
        if tmp_path is not None and os.path.exists(tmp_path):
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
    finally:
        _release_lock(lock_fd)


def clear_semantic_state(clear_file: bool = True) -> None:
    """Reset all learned semantic state."""
    if clear_file:
        path = get_canonical_cache_path()
        if Path(path).exists():
            Path(path).unlink()

    # Mutate the shared world-state singleton only while holding both
    # the persistence lock and the world-state's own lock, so a
    # concurrent load/save can't observe a partially cleared state.
    with _PERSISTENCE_LOCK:
        import app.semantic_world_state

        ws = app.semantic_world_state.get_world_state()
        with ws._lock:
            # Reset unified world state
            ws.clear()

            # Ensure bootstrap values are re-applied if needed (the engines' __init__ handles this if they are re-instantiated,
            # but since they might be singletons, we should be careful. Actually RoleTransitionDetector re-applies it in __init__
            # if it's empty, but if the engine object already exists, we might need to
            # manually re-apply.)
            from app.semantic_boundary_engine import _BOOTSTRAP_TRANSITIONS

            # CoW: deepcopy the bootstrap transitions dict so engines
            # that hold a reference to ``_BOOTSTRAP_TRANSITIONS`` cannot
            # be corrupted by our re-application mutating it.
            ws.update_seed_transition(copy.deepcopy(_BOOTSTRAP_TRANSITIONS))
