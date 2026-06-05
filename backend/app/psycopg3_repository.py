"""Postgres-backed JobRepository implementation using psycopg 3.

This module is an additive, opt-in alternative to ``postgres_repository.py``
(psycopg2). Both implementations satisfy the same ``JobRepository``
contract, so a deployment can switch by changing the
``DATAFORGE_PG_DRIVER`` env var (``psycopg2`` default, ``psycopg3`` for
the new path).

Why psycopg 3:
  * Officially recommended for new code. The psycopg maintainers do not
    recommend ``psycopg2-binary`` for production distribution and
    actively recommend psycopg 3 with ``[binary,pool]`` extras for
    server-side use.
  * First-class connection pool (``psycopg_pool.ConnectionPool``) with
    native async support.
  * Modern type adaptation and better PostgreSQL 15+ feature coverage.

This file is the PHASE A migration target: driver + pool swap only.
Behavioural parity with the psycopg2 implementation is the goal; later
phases can add async-capable repository methods.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.models import Job, JobStatus
from app.storage_interface import JobRepository

logger = logging.getLogger(__name__)

_CURRENT_SCHEMA_VERSION = 4

# ───────────────────────────────────────────────────────────────────────
# Connection pool (thread-safe, synchronous)
# ───────────────────────────────────────────────────────────────────────

_pool = None
_pool_lock = threading.Lock()


def _get_database_url() -> str:
    """Resolve the Postgres DSN from environment or settings.

    Priority: env var > settings > dev fallback.
    """
    from app.config import settings

    url = settings.DATABASE_URL
    if url:
        return url
    env = settings.ENV.strip().lower()
    if env == "development":
        return "postgresql://dataforge:dataforge@localhost:5432/dataforge"
    msg = "DATAFORGE_DATABASE_URL is required in non-development environments. Set it to a valid Postgres connection string."
    raise RuntimeError(msg)


def _get_pool_min_max() -> tuple[int, int]:
    """Read pool sizing from the unified settings layer.

    Honours ``Settings.PG_MIN_CONN`` / ``Settings.PG_MAX_CONN`` (which
    read ``DATAFORGE_PG_MIN_CONN`` / ``DATAFORGE_PG_MAX_CONN``). The
    properties clamp to ``[1, 1000]`` and to ``minconn <= maxconn`` so
    a misconfigured env var can never produce a degenerate pool.
    """
    from app.config import settings as _settings

    minconn = _settings.PG_MIN_CONN
    maxconn = max(_settings.PG_MAX_CONN, minconn)
    return minconn, maxconn


def _get_pool():
    """Get or create a psycopg 3 ``ConnectionPool``."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                # ``ConnectionPool`` is constructed with a DSN string;
                # ``psycopg`` itself is needed by ``verify_psycopg3_connectivity``
                # (imported there) so we don't repeat the import here.
                from psycopg_pool import ConnectionPool

                dsn = _get_database_url()
                minconn, maxconn = _get_pool_min_max()
                _pool = ConnectionPool(
                    conninfo=dsn,
                    min_size=minconn,
                    max_size=maxconn,
                    kwargs={"autocommit": False},
                    open=False,
                )
                _pool.open()
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
                except Exception:  # nosec B110
                    pass
                logger.info("Closed psycopg3 pool")


@contextmanager
def _conn() -> Iterator:
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
            except Exception:  # metrics must never break the caller
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
# Schema management
# ───────────────────────────────────────────────────────────────────────


# Reuse the column list from the psycopg2 module so the two backends
# stay schema-compatible. Importing locally to avoid a hard dependency
# at module import time (psycopg2 may not be installed in psycopg3-only
# deployments in the future).
def _columns_sql() -> list[str]:
    from app.postgres_repository import _JOBS_COLUMNS_SQL

    return list(_JOBS_COLUMNS_SQL)


def _build_create_jobs_sql() -> str:
    cols = ",\n        ".join(_columns_sql())
    return (
        "CREATE TABLE IF NOT EXISTS jobs ("
        "\n        id TEXT PRIMARY KEY,"
        "\n        name TEXT NOT NULL,"
        "\n        status TEXT NOT NULL DEFAULT 'pending',"
        f"\n        {cols}"
        "\n    )"
    )


def _build_create_recycle_bin_sql() -> str:
    cols = ",\n        ".join(_columns_sql())
    return (
        "CREATE TABLE IF NOT EXISTS recycle_bin ("
        "\n        id TEXT PRIMARY KEY,"
        "\n        name TEXT NOT NULL,"
        "\n        status TEXT NOT NULL DEFAULT 'pending',"
        "\n        mode TEXT NOT NULL DEFAULT 'manual',"
        f"\n        {cols}"
        "\n    )"
    )


def _ensure_required_tables(conn) -> None:
    _execute(conn, _build_create_jobs_sql())
    for col_def in _columns_sql():
        try:
            _execute(conn, f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {col_def}")
        except Exception:
            # Mirror the psycopg2 implementation: ignore individual column
            # failures so a partially-migrated DB still loads.
            logger.debug("ALTER TABLE jobs ADD COLUMN %s failed (ignored)", col_def)
    _execute(conn, _build_create_recycle_bin_sql())
    for col_def in _columns_sql():
        try:
            _execute(
                conn,
                f"ALTER TABLE recycle_bin ADD COLUMN IF NOT EXISTS {col_def}",
            )
        except Exception:
            logger.debug(
                "ALTER TABLE recycle_bin ADD COLUMN %s failed (ignored)",
                col_def,
            )
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_recycle_bin_created_at ON recycle_bin(created_at DESC)",
    ]:
        try:
            _execute(conn, idx_sql)
        except Exception:
            logger.debug("CREATE INDEX failed (ignored): %s", idx_sql)


def _ensure_schema() -> None:
    with _conn() as conn:
        _execute(
            conn,
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)",
        )
        row = _fetch_one(conn, "SELECT MAX(version) AS version FROM schema_version")
        current = row["version"] if row and row.get("version") is not None else 0

        _ensure_required_tables(conn)

        if current < _CURRENT_SCHEMA_VERSION:
            if current < 3:
                _execute(
                    conn,
                    """CREATE TABLE IF NOT EXISTS world_state (
                        id TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )""",
                )

            if current < 4:
                # Version 3 -> 4: companion tables for the storage split.
                _execute(
                    conn,
                    """
                    CREATE TABLE IF NOT EXISTS job_results (
                        job_id TEXT NOT NULL,
                        result_index INTEGER NOT NULL,
                        payload TEXT NOT NULL,
                        PRIMARY KEY (job_id, result_index),
                        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                    )
                """,
                )
                _execute(
                    conn,
                    """
                    CREATE TABLE IF NOT EXISTS job_events (
                        event_id BIGSERIAL PRIMARY KEY,
                        job_id TEXT NOT NULL,
                        timestamp TEXT NOT NULL DEFAULT '',
                        level TEXT NOT NULL DEFAULT 'info',
                        message TEXT NOT NULL,
                        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                    )
                """,
                )
                _execute(
                    conn,
                    "CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id, event_id)",
                )
                _execute(
                    conn,
                    "CREATE INDEX IF NOT EXISTS idx_job_results_job_id ON job_results(job_id)",
                )
                _execute(
                    conn,
                    """
                    CREATE TABLE IF NOT EXISTS idempotency_keys (
                        idem_key TEXT PRIMARY KEY,
                        job_id TEXT NOT NULL,
                        request_fingerprint TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                """,
                )
                _execute(
                    conn,
                    "CREATE INDEX IF NOT EXISTS idx_idempotency_keys_created_at ON idempotency_keys(created_at)",
                )

            _execute(conn, "DELETE FROM schema_version")
            _execute(
                conn,
                "INSERT INTO schema_version (version) VALUES (%s)",
                (_CURRENT_SCHEMA_VERSION,),
            )
            logger.info(
                "Postgres (psycopg3) schema migrated to version %d",
                _CURRENT_SCHEMA_VERSION,
            )


# ───────────────────────────────────────────────────────────────────────
# Serialization helpers (reuse psycopg2 helpers to keep the on-disk row
# shape identical between drivers)
# ───────────────────────────────────────────────────────────────────────


def _job_to_row(job: Job) -> dict:
    from app.postgres_repository import _job_to_row

    return _job_to_row(job)


def _row_to_job(row: dict) -> Job | None:
    from app.postgres_repository import _row_to_job

    return _row_to_job(row)


# ───────────────────────────────────────────────────────────────────────
# Repository implementation
# ───────────────────────────────────────────────────────────────────────


class Psycopg3JobRepository(JobRepository):
    """psycopg 3 implementation of the JobRepository contract.

    Behavioural parity with ``PostgresJobRepository`` is the goal in
    phase A (driver + pool swap). Future phases can layer async-capable
    methods on top of the same interface.
    """

    backend = "postgres-psycopg3"

    def __init__(self, auto_ensure_schema: bool = True) -> None:
        self._auto_ensure_schema = auto_ensure_schema
        self._schema_ensured = False

    def _ensure(self) -> None:
        if self._auto_ensure_schema and not self._schema_ensured:
            _ensure_schema()
            self._schema_ensured = True

    # ── Abstract methods ────────────────────────────────────────────────

    def get_job(self, job_id: str) -> Job | None:
        self._ensure()
        with _conn() as conn:
            row = _fetch_one(
                conn,
                "SELECT * FROM jobs WHERE id = %s AND deleted_at IS NULL",
                (job_id,),
            )
            if not row:
                return None
            return _row_to_job(row)

    def list_job_summaries(
        self,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[dict]:
        self._ensure()
        safe_limit = max(1, min(int(limit), 500))
        params: list[object] = []
        sql = (
            "SELECT id, name, status, mode, topic, urls, created_at, started_at, "
            "completed_at, total_records, filtered_records, progress_current, "
            "progress_total, error "
            "FROM jobs WHERE deleted_at IS NULL"
        )
        if cursor:
            sql += " AND created_at < %s"
            params.append(cursor)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(safe_limit)
        with _conn() as conn:
            rows = _fetch_all(conn, sql, tuple(params))
        summaries: list[dict] = []
        for row in rows:
            urls_raw = row.get("urls") or "[]"
            try:
                urls_val = json.loads(urls_raw) if isinstance(urls_raw, str) else (urls_raw or [])
            except (TypeError, ValueError):
                urls_val = []
            summaries.append(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "mode": row.get("mode"),
                    "urls": urls_val,
                    "topic": row.get("topic", "") or "",
                    "status": row.get("status"),
                    "created_at": row.get("created_at"),
                    "started_at": row.get("started_at") or None,
                    "completed_at": row.get("completed_at") or None,
                    "total_records": row.get("total_records", 0) or 0,
                    "filtered_records": row.get("filtered_records", 0) or 0,
                    "progress_current": row.get("progress_current", 0) or 0,
                    "progress_total": row.get("progress_total", 0) or 0,
                    "error": row.get("error") or None,
                },
            )
        return summaries

    # ── Phase-A parity methods (full interface) ─────────────────────────

    def load_jobs(self) -> dict[str, Job]:
        self._ensure()
        with _conn() as conn:
            rows = _fetch_all(conn, "SELECT * FROM jobs WHERE deleted_at IS NULL")
            jobs: dict[str, Job] = {}
            for row in rows:
                job = _row_to_job(row)
                if job:
                    jobs[job.id] = job
            return jobs

    def load_recycle_bin(self) -> dict[str, Job]:
        self._ensure()
        with _conn() as conn:
            rows = _fetch_all(conn, "SELECT * FROM recycle_bin")
            jobs: dict[str, Job] = {}
            for row in rows:
                job = _row_to_job(row)
                if job:
                    jobs[job.id] = job
            return jobs

    def list_recycle_summaries(
        self,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[dict]:
        """Lightweight summary projection for ``GET /api/recycle_bin``.

        Performs a single SELECT against the small summary columns of
        the ``recycle_bin`` table. The ``deleted_at`` column is
        included so the UI can show how long ago the row was
        soft-deleted. The projection shape matches
        :meth:`SQLiteJobRepository.list_recycle_summaries` so the
        ``GET /api/recycle_bin`` endpoint is identical across backends.
        """
        self._ensure()
        safe_limit = max(1, min(int(limit), 500))
        params: list[object] = []
        sql = (
            "SELECT id, name, status, mode, topic, urls, created_at, started_at, "
            "completed_at, total_records, filtered_records, progress_current, "
            "progress_total, error, deleted_at "
            "FROM recycle_bin "
            "WHERE 1=1"
        )
        if cursor:
            sql += " AND created_at < %s"
            params.append(cursor)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(safe_limit)
        with _conn() as conn:
            rows = _fetch_all(conn, sql, tuple(params))
        summaries: list[dict] = []
        for row in rows:
            urls_raw = row.get("urls") or "[]"
            try:
                urls_val = json.loads(urls_raw) if isinstance(urls_raw, str) else (urls_raw or [])
            except (TypeError, ValueError):
                urls_val = []
            summaries.append(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "mode": row.get("mode"),
                    "urls": urls_val,
                    "topic": row.get("topic", "") or "",
                    "status": row.get("status"),
                    "created_at": row.get("created_at"),
                    "started_at": row.get("started_at") or None,
                    "completed_at": row.get("completed_at") or None,
                    "total_records": row.get("total_records", 0) or 0,
                    "filtered_records": row.get("filtered_records", 0) or 0,
                    "progress_current": row.get("progress_current", 0) or 0,
                    "progress_total": row.get("progress_total", 0) or 0,
                    "error": row.get("error") or None,
                    "deleted_at": row.get("deleted_at") or None,
                },
            )
        return summaries

    def load_all(self, recover_in_progress: bool = True) -> tuple[dict[str, Job], dict[str, Job], dict | None]:
        self._ensure()
        with _conn() as conn:
            job_rows = _fetch_all(conn, "SELECT * FROM jobs WHERE deleted_at IS NULL")
            jobs_store: dict[str, Job] = {}
            for row in job_rows:
                job = _row_to_job(row)
                if job:
                    jobs_store[job.id] = job

            if recover_in_progress:
                now_iso = datetime.datetime.now().isoformat()
                dirty_ids = []
                for job in list(jobs_store.values()):
                    if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
                        job.status = JobStatus.FAILED
                        job.error = "Recovered after restart while still in progress."
                        job.completed_at = now_iso
                        job.cancel_requested = False
                        dirty_ids.append(job.id)
                if dirty_ids:
                    _execute(
                        conn,
                        """UPDATE jobs
                           SET status = 'failed',
                               error = 'Recovered after restart while still in progress.',
                               completed_at = %s,
                               cancel_requested = FALSE
                           WHERE id = ANY(%s)""",
                        (now_iso, dirty_ids),
                    )
                    logger.info(
                        "Recovered %d in-progress job(s) in Postgres (psycopg3)",
                        len(dirty_ids),
                    )

            recycle_rows = _fetch_all(conn, "SELECT * FROM recycle_bin")
            recycle_store: dict[str, Job] = {}
            for row in recycle_rows:
                job = _row_to_job(row)
                if job:
                    recycle_store[job.id] = job

            ws_row = _fetch_one(conn, "SELECT payload FROM world_state WHERE id = 'default'")
            world_state_data: dict | None = None
            if ws_row and ws_row.get("payload"):
                try:
                    world_state_data = json.loads(ws_row["payload"])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("Failed to deserialize world_state payload: %s", e)
            return jobs_store, recycle_store, world_state_data

    def save_all(
        self,
        jobs: dict[str, Job],
        recycle_bin: dict[str, Job],
        prune_missing: bool = False,
    ) -> None:
        self._ensure()
        with _conn() as conn:

            def _safe_cols(row):
                for k in row:
                    if not k.isidentifier():
                        msg = f"Unsafe column name in _job_to_row: {k!r}"
                        raise ValueError(msg)
                return list(row.keys())

            for job in jobs.values():
                row = _job_to_row(job)
                safe_keys = _safe_cols(row)
                cols = ", ".join(safe_keys)
                ph = ", ".join("%s" for _ in safe_keys)
                update_cols = ", ".join(f"{k} = EXCLUDED.{k}" for k in safe_keys if k != "id")
                _execute(
                    conn,
                    f"INSERT INTO jobs ({cols}) VALUES ({ph}) ON CONFLICT (id) DO UPDATE SET {update_cols}",  # nosec B608
                    [row[k] for k in safe_keys],
                )
                # Dual-write to companion tables (Schema v4)
                from app.postgres_repository import _sync_job_events, _sync_job_results

                _sync_job_results(conn, job.id, job.results)
                _sync_job_events(conn, job.id, job.logs)
            if prune_missing:
                active_ids = list(jobs.keys())
                _execute(
                    conn,
                    "DELETE FROM jobs WHERE deleted_at IS NULL AND id != ALL(%s)",
                    (active_ids,) if active_ids else (["__no_active_ids__"],),
                )
            for job in recycle_bin.values():
                row = _job_to_row(job)
                now_iso = datetime.datetime.now().isoformat()
                row["deleted_at"] = now_iso
                cols = ", ".join(row.keys())
                ph = ", ".join("%s" for _ in row)
                _execute(
                    conn,
                    f"INSERT INTO recycle_bin ({cols}) VALUES ({ph}) ON CONFLICT (id) DO NOTHING",  # nosec B608
                    list(row.values()),
                )
                _execute(
                    conn,
                    "UPDATE jobs SET deleted_at = %s WHERE id = %s AND deleted_at IS NULL",
                    (now_iso, job.id),
                )
            if prune_missing:
                recycle_ids = list(recycle_bin.keys())
                _execute(
                    conn,
                    "DELETE FROM recycle_bin WHERE id != ALL(%s)",
                    (recycle_ids,) if recycle_ids else (["__no_recycle_ids__"],),
                )

    def read_results(
        self,
        job_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Read a job's results from the ``job_results`` companion table."""
        self._ensure()
        safe_limit = max(1, min(int(limit), 1000))
        safe_offset = max(0, int(offset))
        sql = "SELECT payload FROM job_results WHERE job_id = %s ORDER BY result_index ASC LIMIT %s OFFSET %s"
        try:
            with _conn() as conn:
                rows = _fetch_all(conn, sql, (job_id, safe_limit, safe_offset))
        except Exception:
            return []
        out: list[dict] = []
        for row in rows:
            try:
                out.append(json.loads(row["payload"]))
            except (TypeError, ValueError):
                out.append({"_unparseable": row["payload"]})
        return out

    def lookup_idempotency_key(self, idem_key: str) -> str | None:
        if not idem_key:
            return None
        self._ensure()
        try:
            with _conn() as conn:
                row = _fetch_one(
                    conn,
                    "SELECT job_id FROM idempotency_keys WHERE idem_key = %s",
                    (idem_key,),
                )
                return str(row["job_id"]) if row else None
        except Exception:
            return None

    def record_idempotency_key(
        self,
        idem_key: str,
        job_id: str,
        request_fingerprint: str,
    ) -> None:
        if not idem_key or not job_id:
            return
        self._ensure()
        try:
            with _conn() as conn:
                _execute(
                    conn,
                    """
                    INSERT INTO idempotency_keys
                        (idem_key, job_id, request_fingerprint)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (idem_key) DO UPDATE
                        SET job_id = EXCLUDED.job_id,
                            request_fingerprint = EXCLUDED.request_fingerprint,
                            created_at = NOW()
                    """,
                    (idem_key, job_id, request_fingerprint),
                )
        except Exception:
            logger.exception("Failed to record idempotency key %s", idem_key)

    def prune_idempotency_keys(self, older_than_days: int = 7) -> int:
        self._ensure()
        try:
            with _conn() as conn:
                cur = _execute(
                    conn,
                    "DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL %s",
                    (f"{int(older_than_days)} days",),
                )
                return int(cur.rowcount) if cur.rowcount else 0
        except Exception:
            return 0

    def cleanup_companion_data(self, job_id: str) -> None:
        self._ensure()
        try:
            with _conn() as conn:
                _execute(conn, "DELETE FROM job_results WHERE job_id = %s", (job_id,))
                _execute(conn, "DELETE FROM job_events WHERE job_id = %s", (job_id,))
        except Exception:
            logger.exception("Failed to clean up companion data for job %s", job_id)

    def save_single(self, job: Job) -> None:
        self._ensure()
        with _conn() as conn:
            row = _job_to_row(job)
            cols = ", ".join(row.keys())
            ph = ", ".join("%s" for _ in row)
            update_cols = ", ".join(f"{k} = EXCLUDED.{k}" for k in row if k != "id")
            _execute(
                conn,
                f"INSERT INTO jobs ({cols}) VALUES ({ph}) ON CONFLICT (id) DO UPDATE SET {update_cols}",  # nosec B608
                list(row.values()),
            )
            # Dual-write to companion tables (Schema v4)
            from app.postgres_repository import _sync_job_events, _sync_job_results

            _sync_job_results(conn, job.id, job.results)
            _sync_job_events(conn, job.id, job.logs)

    def read_events(
        self,
        job_id: str,
        limit: int = 200,
        offset: int = 0,
        level_prefix: str | None = None,
    ) -> list[dict]:
        """Read events from the ``job_events`` companion table (psycopg 3).

        Returns ``[]`` when the table is unavailable so the caller can
        fall back to ``Job.logs``.
        """
        self._ensure()
        safe_limit = max(1, min(int(limit), 1000))
        safe_offset = max(0, int(offset))
        sql = "SELECT timestamp, level, message FROM job_events WHERE job_id = %s"
        params: list[object] = [job_id]
        if level_prefix:
            sql += " AND LOWER(level) LIKE %s"
            params.append(f"{level_prefix.lower()}%")
        sql += " ORDER BY event_id ASC LIMIT %s OFFSET %s"
        params.extend([safe_limit, safe_offset])
        try:
            with _conn() as conn:
                rows = _fetch_all(conn, sql, tuple(params))
        except Exception:
            return []
        return [
            {
                "timestamp": (row.get("timestamp") or ""),
                "level": (row.get("level") or "info"),
                "message": (row.get("message") or ""),
            }
            for row in rows
        ]

    def is_cancel_requested(self, job_id: str) -> bool:
        self._ensure()
        with _conn() as conn:
            row = _fetch_one(
                conn,
                "SELECT cancel_requested FROM jobs WHERE id = %s AND deleted_at IS NULL",
                (job_id,),
            )
            return bool(row.get("cancel_requested", False)) if row else False

    def move_to_recycle_bin(self, job_id: str) -> bool:
        self._ensure()
        with _conn() as conn:
            row = _fetch_one(conn, "SELECT * FROM jobs WHERE id = %s AND deleted_at IS NULL", (job_id,))
            if not row:
                return False
            now = datetime.datetime.now().isoformat()
            _execute(conn, "UPDATE jobs SET deleted_at = %s WHERE id = %s", (now, job_id))
            cols_to_copy = [k for k in row if k != "deleted_at"]
            insert_cols = ", ".join(cols_to_copy)
            insert_vals = ", ".join("%s" for _ in cols_to_copy)
            params = [row[k] for k in cols_to_copy] + [now]
            _execute(
                conn,
                f"INSERT INTO recycle_bin ({insert_cols}, deleted_at) VALUES ({{}}, %s) ON CONFLICT (id) DO NOTHING".format(  # nosec B608
                    insert_vals
                ),
                params,
            )
            return True

    def restore_from_recycle_bin(self, job_id: str) -> bool:
        self._ensure()
        with _conn() as conn:
            row = _fetch_one(conn, "SELECT * FROM recycle_bin WHERE id = %s", (job_id,))
            if not row:
                return False
            _execute(conn, "DELETE FROM recycle_bin WHERE id = %s", (job_id,))
            cols = [k for k in row if k != "deleted_at"]
            col_list = ", ".join(cols)
            ph = ", ".join("%s" for _ in cols)
            update_parts = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
            _execute(
                conn,
                f"INSERT INTO jobs ({col_list}) VALUES ({ph}) ON CONFLICT (id) DO UPDATE SET deleted_at = NULL, {update_parts}",  # nosec B608
                [row[k] for k in cols],
            )
            return True

    def hard_delete(self, job_id: str) -> bool:
        self._ensure()
        with _conn() as conn:
            cur = _execute(conn, "DELETE FROM jobs WHERE id = %s", (job_id,))
            deleted = cur.rowcount
            _execute(conn, "DELETE FROM recycle_bin WHERE id = %s", (job_id,))
            # Clean up companion tables (Schema v4)
            _execute(conn, "DELETE FROM job_results WHERE job_id = %s", (job_id,))
            _execute(conn, "DELETE FROM job_events WHERE job_id = %s", (job_id,))
            return deleted > 0

    def clear_terminal_jobs(self, older_than: str | None = None) -> int:
        self._ensure()
        terminal_statuses = (
            "completed",
            "failed",
            "canceled",
            "degraded",
            "empty_result",
        )
        with _conn() as conn:
            rows = _fetch_all(
                conn,
                "SELECT * FROM jobs WHERE status = ANY(%s) AND deleted_at IS NULL"  # nosec B608
                + (" AND completed_at < %s" if older_than else ""),
                (list(terminal_statuses), older_than) if older_than else (list(terminal_statuses),),
            )
            for row in rows:
                now = datetime.datetime.now().isoformat()
                _execute(conn, "UPDATE jobs SET deleted_at = %s WHERE id = %s", (now, row["id"]))
                cols = [k for k in row if k != "deleted_at"]
                col_list = ", ".join(cols)
                ph = ", ".join("%s" for _ in cols)
                _execute(
                    conn,
                    f"INSERT INTO recycle_bin ({col_list}, deleted_at) VALUES ({{}}, %s) ON CONFLICT (id) DO NOTHING".format(ph),  # nosec B608
                    [row[k] for k in cols] + [now],
                )
                # Clean up companion tables (Schema v4)
                _execute(conn, "DELETE FROM job_results WHERE job_id = %s", (row["id"],))
                _execute(conn, "DELETE FROM job_events WHERE job_id = %s", (row["id"],))
            return len(rows)

    def load_world_state(self) -> dict | None:
        self._ensure()
        with _conn() as conn:
            row = _fetch_one(conn, "SELECT payload FROM world_state WHERE id = 'default'")
            if row and row.get("payload"):
                try:
                    return json.loads(row["payload"])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("Failed to deserialize world_state payload: %s", e)
            return None

    def save_world_state(self, payload: dict) -> None:
        self._ensure()
        now = datetime.datetime.now().isoformat()
        payload_json = json.dumps(payload, ensure_ascii=False)
        with _conn() as conn:
            _execute(
                conn,
                """INSERT INTO world_state (id, payload, updated_at)
                   VALUES ('default', %s, %s)
                   ON CONFLICT (id) DO UPDATE SET
                     payload = EXCLUDED.payload,
                     updated_at = EXCLUDED.updated_at""",
                (payload_json, now),
            )

    def health_check(self) -> dict:
        try:
            self._ensure()
            with _conn() as conn:
                row = _fetch_one(conn, "SELECT MAX(version) AS version FROM schema_version")
                version = row["version"] if row else 0
                count_row = _fetch_one(conn, "SELECT COUNT(*) AS cnt FROM jobs WHERE deleted_at IS NULL")
                job_count = count_row["cnt"] if count_row else 0
                recycle_row = _fetch_one(conn, "SELECT COUNT(*) AS cnt FROM recycle_bin")
                recycle_count = recycle_row["cnt"] if recycle_row else 0
                return {
                    "ok": True,
                    "backend": "postgres-psycopg3",
                    "schema_version": version or 0,
                    "expected_version": _CURRENT_SCHEMA_VERSION,
                    "job_count": job_count or 0,
                    "recycle_bin_count": recycle_count or 0,
                }
        except Exception as e:
            logger.exception("Postgres (psycopg3) health check failed: %s")
            return {
                "ok": False,
                "backend": "postgres-psycopg3",
                "error": str(e),
                "schema_version": 0,
                "expected_version": _CURRENT_SCHEMA_VERSION,
            }


# ───────────────────────────────────────────────────────────────────────
# Lifecycle helpers
# ───────────────────────────────────────────────────────────────────────


def shutdown_psycopg3() -> None:
    _close_pool()


def verify_psycopg3_connectivity() -> dict:
    """Synchronously verify Postgres is reachable using psycopg 3."""
    try:
        import psycopg

        dsn = _get_database_url()
        with psycopg.connect(dsn, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                if result is None:
                    return {"ok": False, "error": "No result from health check query"}
                return {"ok": result[0] == 1}
    except ImportError as e:
        return {"ok": False, "error": f"psycopg 3 not installed: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
