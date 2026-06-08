"""Postgres-backed Worker Queue — psycopg2 driver (legacy).

The actual queue logic (enqueue/dequeue/complete/fail/cancel/etc.) lives in
``app.worker_queue_postgres_base``. This module provides the
psycopg2-specific connection pool, the four driver helpers
(``_conn``, ``_execute``, ``_fetch_one``, ``_fetch_all``), and a
``PostgresWorkerQueue`` class that subclasses the base.

The public ``get_postgres_worker_queue()`` factory lives here for
backward compatibility. It selects the right driver (psycopg2 or psycopg 3)
based on ``DATAFORGE_PG_DRIVER``.

The psycopg2 import is intentionally deferred so the module can be
imported in psycopg2-blocked environments (e.g. production images that
ship only psycopg 3) — the dispatcher still needs to be importable so
that ``get_postgres_worker_queue()`` can return the psycopg 3
implementation. Each driver function imports psycopg2 lazily.

Usage:
    queue = get_postgres_worker_queue()
    await queue.enqueue("scrape_job", {"job_id": "abc"}, priority=Priority.HIGH)
    task = await queue.dequeue()
    await queue.complete(task.id)
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager

from app.config import settings as _settings
from app.worker_queue_postgres_base import (
    PostgresWorkerQueueBase,
    _ensure_schema_via,
)

logger = logging.getLogger(__name__)


def _require_psycopg2():
    """Lazily import psycopg2 — only needed at function call time, not at import.

    Production images ship only psycopg 3; psycopg2-binary is a dev-only
    optional dependency. Keeping the import lazy lets the dispatcher
    (and the module itself) be importable in psycopg2-absent environments.
    """
    import psycopg2
    from psycopg2 import pool as pg_pool
    from psycopg2.extras import RealDictCursor

    return psycopg2, pg_pool, RealDictCursor


# ───────────────────────────────────────────────────────────────────────
# Connection pool (thread-safe, synchronous, psycopg2)
# ───────────────────────────────────────────────────────────────────────

_pool = None
_pool_lock = __import__("threading").Lock()


def _get_pool():
    """Get or create the psycopg2 connection pool."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _, pg_pool, _ = _require_psycopg2()
                from app.postgres_repository import get_database_url

                dsn = get_database_url()
                minconn = _settings.PG_MIN_CONN
                maxconn = max(_settings.PG_MAX_CONN, minconn)
                _pool = pg_pool.ThreadedConnectionPool(
                    minconn=minconn,
                    maxconn=maxconn,
                    dsn=dsn,
                )
                logger.info(
                    "Created psycopg2 worker queue pool for %s (minconn=%d, maxconn=%d)",
                    dsn.split("@")[-1] if "@" in dsn else dsn,
                    minconn,
                    maxconn,
                )
    return _pool


def _close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        with _pool_lock:
            pool = _pool
            _pool = None
            if pool is not None:
                pool.closeall()
                logger.info("Closed psycopg2 worker queue pool")


# ───────────────────────────────────────────────────────────────────────
# Driver hooks — psycopg2
# ───────────────────────────────────────────────────────────────────────


def _db_conn():
    """Acquire a connection from the psycopg2 pool (context manager)."""
    psycopg2, _, _ = _require_psycopg2()
    from app.metrics_collector import record_error

    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        from contextlib import suppress

        with suppress(Exception):
            record_error("database")
        raise
    finally:
        pool.putconn(conn)
    _ = psycopg2  # keep the symbol referenced (helps pyflakes / static analysers)


def _db_fetch_all(conn, sql: str, params=None) -> list[dict]:
    _, _, RealDictCursor = _require_psycopg2()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return [dict(r) for r in cur.fetchall()]


def _db_fetch_one(conn, sql: str, params=None) -> dict | None:
    _, _, RealDictCursor = _require_psycopg2()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return dict(row) if row else None


def _db_execute(conn, sql: str, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur


# ───────────────────────────────────────────────────────────────────────
# Module-level connection and query helpers (for backward-compatibility)
# These names are imported by other modules and tests.
# ───────────────────────────────────────────────────────────────────────


@__import__("contextlib").contextmanager
def _conn():
    """Backward-compat alias for ``_db_conn`` context manager."""
    yield from _db_conn()


def _execute(conn, sql: str, params=None):
    return _db_execute(conn, sql, params)


def _fetch_one(conn, sql: str, params=None) -> dict | None:
    return _db_fetch_one(conn, sql, params)


def _fetch_all(conn, sql: str, params=None) -> list[dict]:
    return _db_fetch_all(conn, sql, params)


def _ensure_schema() -> None:
    """Create queue tables and run schema migrations."""
    with _conn() as conn:
        _ensure_schema_via(conn, _fetch_one, _execute)


# ───────────────────────────────────────────────────────────────────────
# Repository implementation (psycopg2)
# ───────────────────────────────────────────────────────────────────────


class PostgresWorkerQueue(PostgresWorkerQueueBase):
    """Worker queue backed by Postgres via the psycopg2 driver (legacy).

    Mirrors the WorkerQueue (SQLite) interface so callers are interchangeable.
    """

    def __init__(self, max_concurrency: int = 5, poll_interval: float = 1.0) -> None:
        super().__init__(max_concurrency=max_concurrency, poll_interval=poll_interval)

    def _ensure_schema(self) -> None:
        """Ensure schema exists (psycopg2-specific)."""
        with self._conn() as conn:
            _ensure_schema_via(conn, self._fetch_one, self._execute)

    @contextmanager
    def _conn(self):
        """Acquire a connection from the psycopg2 pool (context manager)."""
        import app.worker_queue_postgres as wqp

        with wqp._conn() as conn:
            yield conn

    def _fetch_all(self, conn, sql: str, params=None) -> list[dict]:
        import app.worker_queue_postgres as wqp

        return wqp._fetch_all(conn, sql, params)

    def _fetch_one(self, conn, sql: str, params=None) -> dict | None:
        import app.worker_queue_postgres as wqp

        return wqp._fetch_one(conn, sql, params)

    def _execute(self, conn, sql: str, params=None):
        import app.worker_queue_postgres as wqp

        return wqp._execute(conn, sql, params)


# ───────────────────────────────────────────────────────────────────────
# Factory and reset helpers (driver-aware)
# ───────────────────────────────────────────────────────────────────────

import threading

_queue_instance: PostgresWorkerQueueBase | None = None
_queue_lock = threading.Lock()


def get_postgres_worker_queue():
    """Get or create the global PostgresWorkerQueue instance.

    Selects the driver based on ``DATAFORGE_PG_DRIVER``. Default is psycopg2.
    """
    global _queue_instance
    if _queue_instance is None:
        with _queue_lock:
            if _queue_instance is None:
                pg_driver = os.environ.get("DATAFORGE_PG_DRIVER", "").strip().lower()
                if pg_driver == "psycopg3":
                    try:
                        from app.worker_queue_postgres_psycopg3 import (
                            PostgresWorkerQueuePsycopg3,
                        )

                        _queue_instance = PostgresWorkerQueuePsycopg3()
                    except ImportError as e:
                        raise RuntimeError(  # noqa: TRY003
                            f"Failed to import psycopg3 worker queue: {e}. "
                            "Install psycopg 3 with: pip install 'psycopg[binary,pool]>=3.2'"
                        ) from e
                else:
                    _queue_instance = PostgresWorkerQueue()
    return _queue_instance


def reset_postgres_worker_queue() -> None:
    """Reset the global queue instance (for testing)."""
    global _queue_instance
    _queue_instance = None
