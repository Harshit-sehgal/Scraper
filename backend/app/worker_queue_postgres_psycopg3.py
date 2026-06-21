"""Postgres-backed Worker Queue — psycopg 3 driver (production).

This module is the psycopg 3 implementation of the Postgres worker queue.
The shared logic (enqueue/dequeue/complete/fail/cancel/worker loop)
lives in :mod:`app.worker_queue_postgres_base`. This file provides the
psycopg 3 connection pool and the four driver hooks.

The production image ships only psycopg 3 (``psycopg[binary,pool]``); the
legacy ``psycopg2-binary`` is a dev-only optional dependency. With
``DATAFORGE_PG_DRIVER=psycopg3`` (or in environments where ``psycopg2`` is
absent), the dispatcher in :func:`app.worker_queue_postgres.get_postgres_worker_queue`
selects this implementation.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from app.config import settings as _settings
from app.postgres_repository_base import get_database_url
from app.worker_queue_postgres_base import (
    PostgresWorkerQueueBase,
    _ensure_schema_via,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────────────
# Connection pool (thread-safe, synchronous, psycopg 3)
# ───────────────────────────────────────────────────────────────────────

_pool: Any = None
_pool_lock = threading.Lock()


def _get_pool_min_max() -> tuple[int, int]:
    """Read pool sizing from the unified settings layer."""
    minconn = _settings.PG_MIN_CONN
    maxconn = max(_settings.PG_MAX_CONN, minconn)
    return minconn, maxconn


def _get_pool():
    """Get or create a psycopg 3 ``ConnectionPool``."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from psycopg_pool import ConnectionPool

                dsn = get_database_url()
                minconn, maxconn = _get_pool_min_max()
                _pool = ConnectionPool(
                    conninfo=dsn,
                    min_size=minconn,
                    max_size=maxconn,
                    kwargs={
                        "autocommit": False,
                        "keepalives": 1,
                        "keepalives_idle": 30,
                        "keepalives_interval": 10,
                        "keepalives_count": 5,
                    },
                    open=False,
                )
                _pool.open()
                logger.info(
                    "Created psycopg3 worker queue pool (min=%d, max=%d) for %s",
                    minconn,
                    maxconn,
                    dsn.split("@")[-1] if "@" in dsn else dsn,
                )
    return _pool


def _close_pool() -> None:
    """Close the psycopg 3 connection pool."""
    global _pool
    if _pool is not None:
        with _pool_lock:
            pool = _pool
            _pool = None
            if pool is not None:
                try:
                    pool.close()
                except (RuntimeError, OSError, ValueError, TypeError):
                    logger.debug("Failed to close psycopg3 worker queue pool during shutdown")
                logger.info("Closed psycopg3 worker queue pool")


# ───────────────────────────────────────────────────────────────────────
# Driver hooks — psycopg 3
# ───────────────────────────────────────────────────────────────────────


@contextmanager
def _conn() -> Iterator:
    """Acquire a connection from the psycopg 3 pool (context manager)."""
    pool = _get_pool()
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            try:
                from app.metrics_collector import record_error

                record_error("database")
            except (RuntimeError, ValueError, TypeError):  # nosec B110  # noqa: RUF100, S110
                pass
            raise


def _fetch_all(conn, sql: str, params=None) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        cols = [d.name for d in cur.description] if cur.description else []
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]


def _fetch_one(conn, sql: str, params=None) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d.name for d in cur.description] if cur.description else []
        return dict(zip(cols, row, strict=False))


def _execute(conn, sql: str, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur


# ───────────────────────────────────────────────────────────────────────
# Repository implementation (psycopg 3)
# ───────────────────────────────────────────────────────────────────────


class PostgresWorkerQueuePsycopg3(PostgresWorkerQueueBase):
    """Worker queue backed by Postgres via the psycopg 3 driver."""

    def __init__(self, max_concurrency: int = 5, poll_interval: float = 1.0) -> None:
        super().__init__(max_concurrency=max_concurrency, poll_interval=poll_interval)

    def _ensure_schema(self) -> None:
        """Ensure schema exists (psycopg 3-specific)."""
        with self._conn() as conn:
            _ensure_schema_via(conn, self._fetch_one, self._execute)

    @contextmanager
    def _conn(self) -> Iterator:
        """Acquire a connection from the psycopg 3 pool (context manager)."""
        pool = _get_pool()
        with pool.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                try:
                    from app.metrics_collector import record_error

                    record_error("database")
                except (RuntimeError, ValueError, TypeError):  # nosec B110  # noqa: RUF100, S110
                    pass
                raise

    def _fetch_all(self, conn, sql: str, params=None) -> list[dict]:
        import app.worker_queue_postgres_psycopg3 as wqp3

        return wqp3._fetch_all(conn, sql, params)

    def _fetch_one(self, conn, sql: str, params=None) -> dict | None:
        import app.worker_queue_postgres_psycopg3 as wqp3

        return wqp3._fetch_one(conn, sql, params)

    def _execute(self, conn, sql: str, params=None):
        import app.worker_queue_postgres_psycopg3 as wqp3

        return wqp3._execute(conn, sql, params)


# ───────────────────────────────────────────────────────────────────────
# Lifecycle helpers
# ───────────────────────────────────────────────────────────────────────


def shutdown_psycopg3_worker_queue() -> None:
    """Close the psycopg 3 connection pool."""
    _close_pool()


def get_postgres_worker_queue_psycopg3() -> PostgresWorkerQueuePsycopg3:
    """Factory: create and return a fresh psycopg 3 worker queue instance."""
    return PostgresWorkerQueuePsycopg3()
