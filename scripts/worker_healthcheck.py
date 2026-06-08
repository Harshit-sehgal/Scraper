#!/usr/bin/env python3
"""Worker healthcheck — verifies the worker is alive via database heartbeat.

A durable DB-backed heartbeat is used: the worker periodically writes
a heartbeat timestamp, and this script queries the database to
verify the heartbeat is recent.

The worker_id is derived from the hostname (e.g. container ID in
Docker), which is the same for the worker process and the
healthcheck process since they run in the same container. An
optional override is available via
``DATAFORGE_WORKER_HEARTBEAT_ID``.

Exit code 0 = healthy, 1 = unhealthy.

A DB outage (e.g. Postgres unreachable) will also return 1 — this is
intentional. The docker healthcheck's ``retries: 3`` and ``start_period``
mean a transient DB blip will not restart the worker, but a sustained
DB outage will. Operators should treat a worker that is restarting
with a DB-outage stderr line as a database problem, not a worker
problem, and look at Postgres health before paging the worker host.

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

# Explicitly set environment for pydantic-settings before any import.
# Pydantic reads .env at instantiation time, so a production worker
# that exports env vars at the command line works without a .env file,
# but the test/dev paths rely on .env being read.
_ENV_FILE = os.getenv("DATAFORGE_DOTENV_PATH", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k = _k.strip()
                _v = _v.strip().strip("\"'")
                if _k.startswith(("DATAFORGE_", "GROQ_")):
                    os.environ.setdefault(_k, _v)


def _parse_ttl() -> int:
    """Parse ``DATAFORGE_WORKER_HEARTBEAT_TTL`` and validate the result.

    Returns:
        The TTL in seconds (always >= 1).

    Exits:
        ``sys.exit(1)`` on a parse failure or non-positive value — the
        previous code silently fell back to 60 which masked
        misconfigurations in production.
    """
    raw = os.environ.get("DATAFORGE_WORKER_HEARTBEAT_TTL", "60")
    try:
        ttl = int(raw)
    except (ValueError, TypeError):
        print(
            f"HEALTHCHECK FAILED: DATAFORGE_WORKER_HEARTBEAT_TTL={raw!r} is not an integer",
            file=sys.stderr,
        )
        sys.exit(1)
    if ttl < 1:
        print(
            f"HEALTHCHECK FAILED: DATAFORGE_WORKER_HEARTBEAT_TTL={ttl} must be >= 1",
            file=sys.stderr,
        )
        sys.exit(1)
    return ttl


def _check_db_heartbeat(worker_id: str, ttl_seconds: int) -> tuple[bool, str]:
    """Return (alive, error_reason) for the DB-backed heartbeat.

    A non-alive result here can be a worker problem (heartbeat is
    stale) or a database problem (query failed). The caller treats
    both as unhealthy for the worker container; the error_reason is
    logged to stderr so the operator can distinguish the two.
    """
    try:
        from app.storage_interface import get_job_repository

        repo = get_job_repository()
        health = repo.get_worker_health(worker_id, ttl_seconds=ttl_seconds)
    except Exception as exc:
        return False, f"db heartbeat check raised: {exc}"
    if health.get("alive"):
        return True, ""
    return False, f"heartbeat is older than {ttl_seconds}s"


def _main() -> int:
    from app.utils.worker_id import resolve_worker_id

    worker_id = resolve_worker_id()
    ttl = _parse_ttl()

    alive, reason = _check_db_heartbeat(worker_id, ttl)
    if alive:
        return 0

    print(f"HEALTHCHECK FAILED: {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(_main())
