"""Worker identity resolution — shared between HeartbeatManager and healthcheck.

Both the worker process (``worker_heartbeat.py``) and the Docker healthcheck
script (``worker_healthcheck.py``) need to derive the same ``worker_id`` so
the healthcheck can query the correct heartbeat row.

The default identity is ``socket.gethostname()`` (the container ID in Docker).
``DATAFORGE_WORKER_HEARTBEAT_ID`` can be set to override for multi-worker
bare-metal deployments.
"""

from __future__ import annotations

import os
import socket


def resolve_worker_id() -> str:
    """Derive a stable worker identifier.

    Uses hostname only (not hostname-PID) because the Docker healthcheck
    runs as a *separate process* — their PIDs would differ, causing the
    healthcheck to look up the wrong worker_id.  The hostname (container
    ID in Docker) is already unique per container.

    Set ``DATAFORGE_WORKER_HEARTBEAT_ID`` to override for multi-worker
    bare-metal deployments.
    """
    return os.environ.get("DATAFORGE_WORKER_HEARTBEAT_ID") or socket.gethostname()
