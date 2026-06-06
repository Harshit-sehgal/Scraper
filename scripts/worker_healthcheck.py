#!/usr/bin/env python3
"""Worker healthcheck — verifies the worker is alive via database heartbeat.

Replaces the PID-based process-signal approach with a durable DB-backed
heartbeat: the worker periodically writes a heartbeat timestamp, and this
script queries the database to verify the heartbeat is recent.

The worker_id is derived from the hostname (e.g. container ID in Docker),
which is the same for the worker process and the healthcheck process
since they run in the same container. An optional override is available
via ``DATAFORGE_WORKER_HEARTBEAT_ID``.

Exit code 0 = healthy, 1 = unhealthy.

Usage (docker-compose.prod.yml)::

    healthcheck:
      test: ["CMD", "python", "/app/scripts/worker_healthcheck.py"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
"""

import os
import sys

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Explicitly set environment for pydantic-settings before any import
_ENV_FILE = os.getenv("DATAFORGE_DOTENV_PATH", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k = _k.strip()
                _v = _v.strip().strip("\"'")
                if _k.startswith("DATAFORGE_") or _k.startswith("GROQ_"):
                    os.environ.setdefault(_k, _v)

from app.utils.worker_id import resolve_worker_id as _resolve_worker_id


def _main() -> int:
    worker_id = _resolve_worker_id()

    try:
        ttl = int(os.environ.get("DATAFORGE_WORKER_HEARTBEAT_TTL", "60"))
    except (ValueError, TypeError):
        ttl = 60
    if ttl < 1:
        ttl = 60

    try:
        from app.storage_interface import get_job_repository

        repo = get_job_repository()
        health = repo.get_worker_health(worker_id, ttl_seconds=ttl)
        return 0 if health.get("alive") else 1
    except Exception as exc:
        print(f"HEALTHCHECK FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
