"""Postgres-backed JobRepository implementation using psycopg 3.

Refactored during Phase C deduplication: CRUD logic moved to
``PostgresRepositoryBase``; this file provides only the psycopg 3
connection pool, query execution helpers, and connectivity verification.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING

from app.postgres_repository_base import (
    PostgresRepositoryBase,
    get_database_url,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────────────
# Connection pool (thread-safe, synchronous)
# ───────────────────────────────────────────────────────────────────────

_pool = None
_pool_lock = threading.Lock()


def _get_pool_min_max() -> tuple[int, int]:
    """Read pool sizing from the unified settings layer."""
    from app.config import settings as _settings

    minconn = _settings.PG_MIN_CONN
    maxconn = max(_settings.PG_MAX_CONN, minconn)
    return minconn, maxconn


def _get_pool():
    """Get or create a psycopg 3 ``ConnectionPool``.

    The pool's ``open()`` call blocks until at least ``min_size`` connections
    can be established, so we set a short ``timeout`` to avoid hanging the
    whole process when Postgres is unreachable (for example, when a test
    instantiates ``Psycopg3JobRepository`` with a fake DSN). The 10-second
    per-connection timeout is long enough to ride out a transient blip
    but short enough that an outage surfaces as a real
    ``psycopg_pool.PoolTimeout`` rather than an indefinite hang.
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from psycopg_pool import ConnectionPool

                dsn = get_database_url()
                minconn, maxconn = _get_pool_min_max()
                # The DSN may legitimately be empty in non-development
                # environments when ``DATAFORGE_DATABASE_URL`` is unset.
                # Surface a clear error rather than letting psycopg try
                # to parse ``""`` and hang on a bad connection attempt.
                if not dsn:
                    msg = (
                        "Cannot create psycopg3 pool: DATAFORGE_DATABASE_URL is not set. "
                        "Set it in the environment (e.g. "
                        "postgresql://user:pass@host:5432/dataforge) or switch "
                        "STORAGE_BACKEND to sqlite."
                    )
                    raise RuntimeError(msg)
                _pool = ConnectionPool(
                    conninfo=dsn,
                    min_size=minconn,
                    max_size=maxconn,
                    kwargs={"autocommit": False, "connect_timeout": 10},
                    open=False,
                    timeout=10,
                )
                try:
                    _pool.open()
                except Exception:
                    # Reset the cached pool so the next call retries
                    # instead of holding a half-initialised singleton.
                    with suppress(Exception):
                        _pool.close()
                    _pool = None
                    raise
                logger.info(
                    "Created psycopg3 pool (min=%d, max=%d) for %s",
                    minconn,
                    maxconn,
                    dsn.split("@")[-1] if "@" in dsn else dsn,
                )
    return _pool


def _close_pool() -> None:
    global _pool
    if _pool is not None:
        with _pool_lock:
            pool = _pool
            _pool = None
            if pool is not None:
                try:
                    pool.close()
                except Exception:
                    logger.debug("Failed to close psycopg3 pool during shutdown")
                logger.info("Closed psycopg3 pool")


# ───────────────────────────────────────────────────────────────────────
# Repository implementation
# ───────────────────────────────────────────────────────────────────────


class Psycopg3JobRepository(PostgresRepositoryBase):
    """psycopg 3 implementation of the JobRepository contract.

    Behavioural parity with ``PostgresJobRepository`` is the goal.
    Future phases can layer async-capable methods on top of the same interface.
    """

    backend = "postgres-psycopg3"

    def __init__(self, auto_ensure_schema: bool = True) -> None:  # noqa: FBT001, FBT002
        super().__init__(auto_ensure_schema=auto_ensure_schema)

    @contextmanager
    def _conn(self) -> Iterator:
        """Acquire a connection from the psycopg 3 pool (context manager)."""
        pool = _get_pool()
        with pool.connection() as conn:
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                try:
                    from app.metrics_collector import record_error

                    record_error("database")
                except Exception:  # nosec B110  # noqa: RUF100, S110
                    pass  # nosec B110
                raise

    def _fetch_all(self, conn, sql: str, params=None) -> list[dict]:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            cols = [d.name for d in cur.description] if cur.description else []
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    def _fetch_one(self, conn, sql: str, params=None) -> dict | None:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d.name for d in cur.description] if cur.description else []
            return dict(zip(cols, row, strict=False))

    def _execute(self, conn, sql: str, params=None):
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur


# ───────────────────────────────────────────────────────────────────────
# Lifecycle helpers
# ───────────────────────────────────────────────────────────────────────


def shutdown_psycopg3() -> None:
    _close_pool()


def verify_psycopg3_connectivity() -> dict:
    """Synchronously verify Postgres is reachable using psycopg 3."""
    try:
        import psycopg

        dsn = get_database_url()
        with psycopg.connect(dsn, connect_timeout=10) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()
            if result is None:
                return {"ok": False, "error": "No result from health check query"}
            return {"ok": result[0] == 1}
    except ImportError as e:
        return {"ok": False, "error": f"psycopg 3 not installed: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
