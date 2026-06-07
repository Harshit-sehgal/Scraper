"""Production-grade Postgres-backed JobRepository implementation (synchronous psycopg2).

Refactored during Phase C deduplication: CRUD logic moved to
``PostgresRepositoryBase``; this file provides only the psycopg2
connection pool, query execution helpers, and connectivity verification.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2.extras import RealDictCursor

from app.postgres_repository_base import (
    PostgresRepositoryBase,
    get_database_url,
)

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────────────
# Connection pool (thread-safe, synchronous)
# ───────────────────────────────────────────────────────────────────────

_pool: pg_pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> pg_pool.ThreadedConnectionPool:
    """Get or create the psycopg2 connection pool."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from app.config import settings as _settings

                dsn = get_database_url()
                minconn = _settings.PG_MIN_CONN
                maxconn = max(_settings.PG_MAX_CONN, minconn)
                _pool = pg_pool.ThreadedConnectionPool(
                    minconn=minconn,
                    maxconn=maxconn,
                    dsn=dsn,
                )
                logger.info(
                    "Created psycopg2 pool for %s (minconn=%d, maxconn=%d)",
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
                logger.info("Closed psycopg2 pool")


# ───────────────────────────────────────────────────────────────────────
# Repository implementation
# ───────────────────────────────────────────────────────────────────────


class PostgresJobRepository(PostgresRepositoryBase):
    """Production-grade Postgres-backed JobRepository using synchronous psycopg2.

    Uses psycopg2.pool.ThreadedConnectionPool for thread-safe connection management.
    Schema auto-migration runs on first access.
    """

    backend = "postgres"

    def __init__(self, auto_ensure_schema: bool = True) -> None:
        super().__init__(auto_ensure_schema=auto_ensure_schema)

    @contextmanager
    def _conn(self) -> Iterator[psycopg2.extensions.connection]:
        with _db_conn() as conn:
            yield conn

    def _fetch_all(self, conn, sql: str, params=None) -> list[dict]:
        return _db_fetch_all(conn, sql, params)

    def _fetch_one(self, conn, sql: str, params=None) -> dict | None:
        return _db_fetch_one(conn, sql, params)

    def _execute(self, conn, sql: str, params=None):
        return _db_execute(conn, sql, params)


# ───────────────────────────────────────────────────────────────────────
# Module-level connection and query helpers (for backward-compatibility)
# ───────────────────────────────────────────────────────────────────────


@contextmanager
def _db_conn() -> Iterator[psycopg2.extensions.connection]:
    """Acquire a connection from the psycopg2 pool (context manager)."""
    pool = _get_pool()
    conn = pool.getconn()
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
    finally:
        pool.putconn(conn)


def _db_fetch_all(conn, sql: str, params=None) -> list[dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return [dict(r) for r in cur.fetchall()]


def _db_fetch_one(conn, sql: str, params=None) -> dict | None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return dict(row) if row else None


def _db_execute(conn, sql: str, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur


# Backward-compatibility aliases for rate_limiter, worker_queue_postgres, etc.
_conn = _db_conn
_execute = _db_execute
_fetch_all = _db_fetch_all
_fetch_one = _db_fetch_one


# ───────────────────────────────────────────────────────────────────────
# Lifecycle helpers
# ───────────────────────────────────────────────────────────────────────


def create_postgres_repository() -> PostgresJobRepository:
    """Factory: create and return a ready-to-use PostgresJobRepository."""
    repo = PostgresJobRepository()
    repo._ensure()
    return repo


def shutdown_postgres() -> None:
    """Close the Postgres connection pool."""
    _close_pool()


def verify_postgres_connectivity() -> dict:
    """Synchronously verify Postgres is reachable before activating the repository.

    Uses a standalone connection (not the shared pool) so the pool is
    never leaked on failure or left open if the caller falls back to SQLite.

    Returns a dict with 'ok': True / False and optional 'error' message.
    """
    try:
        dsn = get_database_url()
        conn = psycopg2.connect(dsn, connect_timeout=10)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                if result is None:
                    return {"ok": False, "error": "No result from health check query"}
                val = result[0]
                return {"ok": val == 1}
        finally:
            conn.close()
    except ImportError as e:
        return {"ok": False, "error": f"psycopg2 not installed: {e}"}
    except (psycopg2.OperationalError, psycopg2.ProgrammingError) as e:
        return {"ok": False, "error": str(e)}
