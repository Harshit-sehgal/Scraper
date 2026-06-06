"""Unit tests for ``app.utils.worker_id.resolve_worker_id()``.

Tests the shared worker identity resolution used by both
:mod:`app.worker_heartbeat` and :file:`scripts/worker_healthcheck.py`.
"""

from __future__ import annotations

import os
import socket


def test_resolve_worker_id_defaults_to_hostname() -> None:
    """Without DATAFORGE_WORKER_HEARTBEAT_ID, returns socket.gethostname()."""
    from app.utils.worker_id import resolve_worker_id

    sentinel = os.environ.pop("DATAFORGE_WORKER_HEARTBEAT_ID", None)
    try:
        worker_id = resolve_worker_id()
        assert worker_id == socket.gethostname(), f"Expected {socket.gethostname()!r}, got {worker_id!r}"
    finally:
        if sentinel is not None:
            os.environ["DATAFORGE_WORKER_HEARTBEAT_ID"] = sentinel


def test_resolve_worker_id_honours_env_override() -> None:
    """When DATAFORGE_WORKER_HEARTBEAT_ID is set, returns that value."""
    from app.utils.worker_id import resolve_worker_id

    old = os.environ.pop("DATAFORGE_WORKER_HEARTBEAT_ID", None)
    expected = "my-custom-worker"
    try:
        os.environ["DATAFORGE_WORKER_HEARTBEAT_ID"] = expected
        worker_id = resolve_worker_id()
        assert worker_id == expected, f"Expected {expected!r}, got {worker_id!r}"
    finally:
        os.environ.pop("DATAFORGE_WORKER_HEARTBEAT_ID", None)
        if old is not None:
            os.environ["DATAFORGE_WORKER_HEARTBEAT_ID"] = old


def test_resolve_worker_id_falls_back_on_empty_env() -> None:
    """An empty-string override falls back to hostname (``or`` semantics)."""
    from app.utils.worker_id import resolve_worker_id

    old = os.environ.pop("DATAFORGE_WORKER_HEARTBEAT_ID", None)
    try:
        os.environ["DATAFORGE_WORKER_HEARTBEAT_ID"] = ""
        worker_id = resolve_worker_id()
        assert worker_id == socket.gethostname(), f"Expected hostname {socket.gethostname()!r}, got {worker_id!r}"
    finally:
        os.environ.pop("DATAFORGE_WORKER_HEARTBEAT_ID", None)
        if old is not None:
            os.environ["DATAFORGE_WORKER_HEARTBEAT_ID"] = old
