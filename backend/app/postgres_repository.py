"""Production-grade Postgres-backed JobRepository implementation (synchronous psycopg2).

Provides:
- Connection pooling via psycopg2.pool.ThreadedConnectionPool
- Schema auto-migration
- Transactional batch writes
- Same interface as SQLiteJobRepository (via JobRepository ABC)
- Configurable via DATAFORGE_DATABASE_URL env var

Usage:
    repo = PostgresJobRepository()
    jobs, recycle, ws = repo.load_all()
"""

import datetime
import json
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2.extras import RealDictCursor

from app.models import Job, JobStatus
from app.storage_interface import JobRepository

logger = logging.getLogger(__name__)

_CURRENT_SCHEMA_VERSION = 4

# ───────────────────────────────────────────────────────────────────────
# Connection pool (thread-safe, synchronous)
# ───────────────────────────────────────────────────────────────────────

_pool: pg_pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_database_url() -> str:
    """Resolve the Postgres DSN from environment or settings.

    In non-development environments, the DSN MUST be explicitly configured.
    The fallback default only applies in development.

    Priority:
    1. DATAFORGE_DATABASE_URL env var (checked first so runtime / test
       overrides work even after pydantic-settings has cached its value)
    2. settings.DATABASE_URL (from .env file or pydantic-settings)
    3. Development fallback default
    """
    from app.config import settings

    url = settings.DATABASE_URL
    if url:
        return url
    # Only allow fallback default in development mode
    env = settings.ENV.strip().lower()
    if env == "development":
        return "postgresql://dataforge:dataforge@localhost:5432/dataforge"
    msg = "DATAFORGE_DATABASE_URL is required in non-development environments. Set it to a valid Postgres connection string."
    raise RuntimeError(
        msg,
    )


def _get_pool() -> pg_pool.ThreadedConnectionPool:
    """Get or create the psycopg2 connection pool.

    Pool sizing is configurable via ``DATAFORGE_PG_MIN_CONN`` and
    ``DATAFORGE_PG_MAX_CONN`` (defaults: 1 and 10 — matches the prior
    hard-coded values plus the new ``Settings.PG_MIN_CONN`` /
    ``Settings.PG_MAX_CONN`` properties so single-source-of-truth
    configuration is honoured).
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from app.config import settings as _settings

                dsn = _get_database_url()
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


@contextmanager
def _conn() -> Iterator[psycopg2.extensions.connection]:
    """Acquire a connection from the pool (context manager)."""
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
        except Exception:  # metrics must never break the caller
            pass  # nosec B110
        raise
    finally:
        pool.putconn(conn)


def _fetch_all(conn, sql: str, params=None) -> list[dict]:
    """Execute a query and return all rows as dicts."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return [dict(r) for r in cur.fetchall()]


def _fetch_one(conn, sql: str, params=None) -> dict | None:
    """Execute a query and return the first row as a dict, or None."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return dict(row) if row else None


def _execute(conn, sql: str, params=None):
    """Execute a statement and return the cursor (for rowcount)."""
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur


# ───────────────────────────────────────────────────────────────────────
# Schema management
# ───────────────────────────────────────────────────────────────────────


_JOBS_COLUMNS_SQL = [
    "mode TEXT DEFAULT 'manual'",
    "topic TEXT DEFAULT ''",
    "intent TEXT DEFAULT ''",
    "urls TEXT DEFAULT '[]'",
    "schema_fields TEXT DEFAULT '[]'",
    "filters TEXT DEFAULT '[]'",
    "results TEXT DEFAULT '[]'",
    "logs TEXT DEFAULT '[]'",
    "total_records INTEGER DEFAULT 0",
    "filtered_records INTEGER DEFAULT 0",
    "total_llm_calls INTEGER DEFAULT 0",
    "error TEXT DEFAULT ''",
    "warnings TEXT DEFAULT ''",
    "quality_report TEXT DEFAULT '{}'",
    "analysis TEXT DEFAULT ''",
    "discovered_urls TEXT DEFAULT '[]'",
    "selectors_map TEXT DEFAULT '{}'",
    "search_params TEXT DEFAULT '{}'",
    "max_pages INTEGER DEFAULT 0",
    "progress_current INTEGER DEFAULT 0",
    "progress_total INTEGER DEFAULT 0",
    "estimated_cost_usd REAL DEFAULT 0",
    "cancel_requested BOOLEAN DEFAULT FALSE",
    "created_at TEXT DEFAULT ''",
    "completed_at TEXT DEFAULT ''",
    "min_record_score REAL DEFAULT 0.35",
    "acquisition_mode TEXT DEFAULT 'standard'",
    "location TEXT DEFAULT ''",
    "preferred_domain TEXT DEFAULT ''",
    "source_policy TEXT DEFAULT 'all_sources'",
    "max_per_domain INTEGER DEFAULT 4",
    "origin_location TEXT DEFAULT ''",
    "max_distance_km REAL DEFAULT NULL",
    "pagination BOOLEAN DEFAULT FALSE",
    "deduplicate BOOLEAN DEFAULT TRUE",
    "deduplicate_field TEXT DEFAULT ''",
    "started_at TEXT DEFAULT ''",
    "results_on_disk BOOLEAN DEFAULT FALSE",
    "results_file_path TEXT DEFAULT ''",
    "updated_at TEXT DEFAULT ''",
    "deleted_at TEXT DEFAULT NULL",
]

_JOBS_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'{extra_cols}
    )
"""

_RECYCLE_BIN_SQL = """
    CREATE TABLE IF NOT EXISTS recycle_bin (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        mode TEXT NOT NULL DEFAULT 'manual'{recycle_cols}
    )
"""


def _build_create_jobs_sql() -> str:
    """Build the full CREATE TABLE statement for the jobs table."""
    cols = ""
    for col_def in _JOBS_COLUMNS_SQL:
        cols += f",\n        {col_def}"
    return _JOBS_TABLE_SQL.format(extra_cols=cols)


def _build_create_recycle_bin_sql() -> str:
    """Build the full CREATE TABLE statement for the recycle_bin table."""
    # recycle_bin uses the same columns as jobs, minus status (already in
    # skeleton) plus deleted_at
    cols = ""
    for col_def in _JOBS_COLUMNS_SQL:
        # Skip the fields already defined in the skeleton
        if col_def.startswith("mode"):
            continue
        cols += f",\n        {col_def}"
    return _RECYCLE_BIN_SQL.format(recycle_cols=cols)


def _ensure_required_tables(conn) -> None:
    """Create required tables if they do not exist. Runs on every schema check."""
    _execute(conn, _build_create_jobs_sql())

    # Add extra columns that may have been added in later migrations
    for col_def in _JOBS_COLUMNS_SQL:
        # Use savepoints so individual column failures don't abort the
        # transaction
        try:
            _execute(conn, "SAVEPOINT alter_jobs_col")
            _execute(conn, f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {col_def}")
            _execute(conn, "RELEASE SAVEPOINT alter_jobs_col")
        except Exception:
            _execute(conn, "ROLLBACK TO SAVEPOINT alter_jobs_col")

    _execute(conn, _build_create_recycle_bin_sql())

    for col_def in _JOBS_COLUMNS_SQL:
        try:
            _execute(conn, "SAVEPOINT alter_recycle_col")
            _execute(conn, f"ALTER TABLE recycle_bin ADD COLUMN IF NOT EXISTS {col_def}")
            _execute(conn, "RELEASE SAVEPOINT alter_recycle_col")
        except Exception:
            _execute(conn, "ROLLBACK TO SAVEPOINT alter_recycle_col")

    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_recycle_bin_created_at ON recycle_bin(created_at DESC)",
    ]:
        try:
            _execute(conn, "SAVEPOINT create_index")
            _execute(conn, idx_sql)
            _execute(conn, "RELEASE SAVEPOINT create_index")
        except Exception:
            _execute(conn, "ROLLBACK TO SAVEPOINT create_index")


def _ensure_schema() -> None:
    """Run schema migrations to ensure tables exist and are up to date.

    Always runs _ensure_required_tables() to repair missing tables even when
    schema_version is already current (handles databases created by older
    broken versions that skipped recycle_bin creation).
    """
    with _conn() as conn:
        _execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """,
        )
        row = _fetch_one(conn, "SELECT MAX(version) AS version FROM schema_version")
        current = row["version"] if row and row.get("version") is not None else 0

        # ── Repair step: always ensure required tables exist ─────────────
        # This handles databases with schema_version = 1 that were created by
        # an older broken version which may have skipped recycle_bin creation.
        _ensure_required_tables(conn)

        if current < _CURRENT_SCHEMA_VERSION:
            if current < 1:
                # Version 0 -> 1: intentionally empty — _ensure_required_tables above
                # already creates both tables with the full column set.
                pass

            if current < 2:
                # Version 1 -> 2: intentionally empty — _ensure_required_tables above
                # already ensures all columns and the recycle_bin table exist.
                pass

            if current < 3:
                # Version 2 -> 3: add world_state table for semantic state
                # persistence
                _execute(
                    conn,
                    """
                    CREATE TABLE IF NOT EXISTS world_state (
                        id TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """,
                )

            if current < 4:
                # Version 3 -> 4: companion tables for the storage split.
                # ``job_results`` holds each extracted result as a dedicated
                # row so summary queries don't deserialize the entire JSON
                # blob. ``job_events`` holds lifecycle events similarly.
                # ``idempotency_keys`` supports Idempotency-Key headers on
                # ``POST /api/jobs``.
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
            _execute(conn, "INSERT INTO schema_version (version) VALUES (%s)", (_CURRENT_SCHEMA_VERSION,))
            logger.info("Postgres schema migrated to version %d", _CURRENT_SCHEMA_VERSION)
        else:
            logger.debug("Postgres schema already at version %d", _CURRENT_SCHEMA_VERSION)


# ───────────────────────────────────────────────────────────────────────
# Serialization helpers
# ───────────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────────
# Companion-table dual-write helpers (Schema v4)
# ───────────────────────────────────────────────────────────────────────


def _sync_job_results(conn, job_id: str, results: list) -> None:
    """Replace the ``job_results`` rows for ``job_id`` with ``results``.

    Dual-write helper called by ``save_single`` and ``save_all``.
    The legacy JSON column in ``jobs`` is still populated; this is an
    additive write for the new per-row reader path.
    """
    _execute(conn, "DELETE FROM job_results WHERE job_id = %s", (job_id,))
    for idx, payload in enumerate(results):
        try:
            encoded = json.dumps(payload, default=str)
        except (TypeError, ValueError):
            encoded = json.dumps(str(payload))
        _execute(
            conn,
            "INSERT INTO job_results (job_id, result_index, payload) VALUES (%s, %s, %s)",
            (job_id, idx, encoded),
        )


def _sync_job_events(conn, job_id: str, logs) -> None:
    """Replace the ``job_events`` rows for ``job_id`` with ``logs``.

    Dual-write helper called by ``save_single`` and ``save_all``.
    """
    _execute(conn, "DELETE FROM job_events WHERE job_id = %s", (job_id,))
    for entry in logs or []:
        if hasattr(entry, "model_dump"):
            try:
                entry_dict = entry.model_dump()
            except Exception:
                entry_dict = {
                    "timestamp": "",
                    "level": "info",
                    "message": str(entry),
                }
        elif isinstance(entry, dict):
            entry_dict = entry
        else:
            entry_dict = {
                "timestamp": "",
                "level": "info",
                "message": str(entry),
            }
        _execute(
            conn,
            "INSERT INTO job_events (job_id, timestamp, level, message) VALUES (%s, %s, %s, %s)",
            (
                job_id,
                str(entry_dict.get("timestamp") or ""),
                str(entry_dict.get("level") or "info"),
                str(entry_dict.get("message") or ""),
            ),
        )


def _job_to_row(job: Job) -> dict:
    """Convert a Job model to a flat row dict for Postgres storage."""
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "mode": job.mode.value if hasattr(job.mode, "value") else str(job.mode),
        "topic": job.topic or "",
        "intent": job.intent or "",
        "urls": json.dumps(job.urls or []),
        "schema_fields": json.dumps([f.model_dump() if hasattr(f, "model_dump") else f for f in (job.schema_fields or [])]),
        "filters": (
            json.dumps([f.model_dump() if hasattr(f, "model_dump") else f for f in (job.filters or [])])
            if hasattr(job, "filters")
            else "[]"
        ),
        "results": json.dumps(job.results or []),
        "logs": json.dumps([log.model_dump() if hasattr(log, "model_dump") else log for log in (job.logs or [])]),
        "total_records": job.total_records or 0,
        "filtered_records": job.filtered_records or 0,
        "total_llm_calls": job.total_llm_calls or 0,
        "error": job.error if job.error is not None else "",
        "warnings": json.dumps(job.warnings or []),
        "quality_report": json.dumps(job.quality_report if hasattr(job, "quality_report") else {}),
        "analysis": job.analysis if job.analysis is not None else "",
        "discovered_urls": json.dumps(job.discovered_urls if hasattr(job, "discovered_urls") else []),
        "selectors_map": json.dumps(job.selectors_map if hasattr(job, "selectors_map") else {}),
        "search_params": json.dumps(job.search_params if hasattr(job, "search_params") and job.search_params is not None else {}),
        "max_pages": job.max_pages if hasattr(job, "max_pages") else 0,
        "progress_current": job.progress_current or 0,
        "progress_total": job.progress_total or 0,
        "estimated_cost_usd": job.estimated_cost_usd or 0,
        "cancel_requested": job.cancel_requested,
        "created_at": job.created_at or "",
        "completed_at": job.completed_at if job.completed_at is not None else "",
        "min_record_score": job.min_record_score if job.min_record_score is not None else 0.35,
        "acquisition_mode": (
            job.acquisition_mode.value if hasattr(job.acquisition_mode, "value") else str(job.acquisition_mode or "standard")
        ),
        "location": job.location or "",
        "preferred_domain": job.preferred_domain or "",
        "source_policy": job.source_policy.value if hasattr(job.source_policy, "value") else str(job.source_policy),
        "max_per_domain": job.max_per_domain or 4,
        "origin_location": job.origin_location or "",
        "max_distance_km": job.max_distance_km,
        "pagination": job.pagination,
        "deduplicate": job.deduplicate,
        "deduplicate_field": job.deduplicate_field or "",
        "started_at": job.started_at if job.started_at is not None else "",
        "results_on_disk": job.results_on_disk,
        "results_file_path": job.results_file_path if job.results_file_path is not None else "",
        "updated_at": datetime.datetime.now().isoformat(),
        # Explicitly set deleted_at = NULL for active jobs so that
        # ON CONFLICT (id) DO UPDATE restores visibility of previously
        # soft-deleted rows with the same ID.
        "deleted_at": None,
    }


def _row_to_job(row: dict) -> Job | None:
    """Convert a Postgres row dict back to a Job model."""
    try:
        from app.models import SourcePolicy

        source_policy_str = row.get("source_policy", "all_sources")
        try:
            sp = SourcePolicy(source_policy_str)
        except (ValueError, KeyError):
            sp = SourcePolicy.ALL_SOURCES

        return Job.model_validate(
            {
                "id": row["id"],
                "name": row["name"],
                "status": row["status"],
                "mode": row.get("mode", "manual"),
                "topic": row.get("topic", ""),
                "intent": row.get("intent", ""),
                "urls": json.loads(row.get("urls", "[]")),
                "schema_fields": json.loads(row.get("schema_fields", "[]")),
                "filters": json.loads(row.get("filters", "[]")),
                "results": json.loads(row.get("results", "[]")),
                "logs": json.loads(row.get("logs", "[]")),
                "total_records": row.get("total_records", 0),
                "filtered_records": row.get("filtered_records", 0),
                "total_llm_calls": row.get("total_llm_calls", 0),
                "error": row.get("error") or None,
                "quality_report": json.loads(row.get("quality_report", "{}")),
                "analysis": row.get("analysis") or None,
                "discovered_urls": json.loads(row.get("discovered_urls", "[]")),
                "selectors_map": json.loads(row.get("selectors_map", "{}")),
                "search_params": json.loads(row.get("search_params", "{}")) or None,
                "max_pages": row.get("max_pages", 0),
                "progress_current": row.get("progress_current", 0),
                "progress_total": row.get("progress_total", 0),
                "estimated_cost_usd": row.get("estimated_cost_usd", 0),
                "cancel_requested": bool(row.get("cancel_requested", False)),
                "created_at": row.get("created_at", ""),
                "completed_at": row.get("completed_at") or None,
                "min_record_score": row.get("min_record_score", 0.35),
                "location": row.get("location", ""),
                "preferred_domain": row.get("preferred_domain", ""),
                "source_policy": sp,
                "max_per_domain": row.get("max_per_domain", 4),
                "origin_location": row.get("origin_location", ""),
                "max_distance_km": row.get("max_distance_km"),
                "pagination": bool(row.get("pagination", False)),
                "deduplicate": bool(row.get("deduplicate", True)),
                "deduplicate_field": row.get("deduplicate_field", ""),
                "started_at": row.get("started_at") or None,
                "results_on_disk": bool(row.get("results_on_disk", False)),
                "results_file_path": row.get("results_file_path") or None,
                "warnings": json.loads(row.get("warnings", "[]")),
                "acquisition_mode": row.get("acquisition_mode", "standard"),
            },
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Failed to deserialize Postgres job row: %s", e)
        return None


# ───────────────────────────────────────────────────────────────────────
# Repository implementation (fully synchronous)
# ───────────────────────────────────────────────────────────────────────


class PostgresJobRepository(JobRepository):
    """Production-grade Postgres-backed JobRepository using synchronous psycopg2.

    Uses psycopg2.pool.ThreadedConnectionPool for thread-safe connection management.
    Schema auto-migration runs on first access.
    """

    backend = "postgres"

    def __init__(self, auto_ensure_schema: bool = True) -> None:
        self._auto_ensure_schema = auto_ensure_schema
        self._schema_ensured = False

    def _ensure(self) -> None:
        if self._auto_ensure_schema and not self._schema_ensured:
            _ensure_schema()
            self._schema_ensured = True

    # ─── Repository interface (sync, no async wrappers needed) ──────────

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

    def get_job(self, job_id: str) -> Job | None:
        """Targeted read: single active job by primary key.

        Avoids the full ``SELECT *`` performed by ``load_jobs()`` on
        single-item read paths. Soft-deleted rows are excluded.
        """
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
        """Lightweight summary projection for ``GET /api/jobs``.

        Avoids deserializing JSON blobs (``results``, ``logs``,
        ``selectors_map``) so list endpoints stay cheap. The ``urls``
        column is JSONB in spirit (stored as TEXT) — the decoded list
        matches the SQLite implementation.
        """
        self._ensure()
        safe_limit = max(1, min(int(limit), 500))
        params: list[object] = []
        sql = (
            "SELECT id, name, status, mode, topic, urls, created_at, started_at, "
            "completed_at, total_records, filtered_records, progress_current, "
            "progress_total, error "
            "FROM jobs "
            "WHERE deleted_at IS NULL"
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

    def read_results(
        self,
        job_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Read a job's results from the ``job_results`` companion table.

        Returns results in insertion order. Returns ``[]`` when the
        companion table is empty (pre-v4 or results on disk) so the
        caller can fall back to ``Job.results``.
        """
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
        """Lookup an idempotency key in Postgres."""
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
        """Persist an idempotency-key → job_id mapping in Postgres."""
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
        """Delete idempotency keys older than ``older_than_days`` in Postgres."""
        self._ensure()
        try:
            with _conn() as conn:
                cur = _execute(
                    conn,
                    "DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL %s",
                    (f"{int(older_than_days)} days",),
                )
                deleted = cur.rowcount
                return int(deleted) if deleted else 0
        except Exception:
            return 0

    def cleanup_companion_data(self, job_id: str) -> None:
        """Remove companion-table rows for a job in Postgres."""
        self._ensure()
        try:
            with _conn() as conn:
                _execute(conn, "DELETE FROM job_results WHERE job_id = %s", (job_id,))
                _execute(conn, "DELETE FROM job_events WHERE job_id = %s", (job_id,))
        except Exception:
            logger.exception("Failed to clean up companion data for job %s", job_id)

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
            # Load jobs
            job_rows = _fetch_all(conn, "SELECT * FROM jobs WHERE deleted_at IS NULL")
            jobs_store: dict[str, Job] = {}
            for row in job_rows:
                job = _row_to_job(row)
                if job:
                    jobs_store[job.id] = job

            if recover_in_progress:
                # Recover in-progress jobs (same as SQLite behavior)
                now_iso = datetime.datetime.now().isoformat()
                dirty_ids = []
                for job in list(jobs_store.values()):
                    if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
                        job.status = JobStatus.FAILED
                        job.error = "Recovered after restart while still in progress."
                        job.completed_at = now_iso
                        job.cancel_requested = False
                        dirty_ids.append(job.id)

                # Persist recovery to DB
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
                    logger.info("Recovered %d in-progress job(s) in Postgres", len(dirty_ids))

            # Load recycle bin
            recycle_rows = _fetch_all(conn, "SELECT * FROM recycle_bin")
            recycle_store: dict[str, Job] = {}
            for row in recycle_rows:
                job = _row_to_job(row)
                if job:
                    recycle_store[job.id] = job

            # Load world state
            ws_row = _fetch_one(conn, "SELECT payload FROM world_state WHERE id = 'default'")
            world_state_data: dict | None = None
            if ws_row and ws_row.get("payload"):
                try:
                    world_state_data = json.loads(ws_row["payload"])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("Failed to deserialize world_state payload: %s", e)

            return jobs_store, recycle_store, world_state_data

    def save_all(self, jobs: dict[str, Job], recycle_bin: dict[str, Job], prune_missing: bool = False) -> None:
        """Save all jobs and recycle bin entries using UPSERT semantics.

        Uses INSERT ... ON CONFLICT DO UPDATE instead of DELETE+INSERT to avoid
        destroying data that was concurrently written by other processes (e.g.
        worker single-job saves).

        Only removes stale rows when ``prune_missing=True``. In multi-process
        production (API + separate worker), keep this ``False`` to prevent
        one process from deleting jobs created by another process. Use
        ``save_single()`` for individual job updates in production.
        """
        self._ensure()
        with _conn() as conn:
            # Upsert jobs — do NOT delete first
            # Safety: validate column names to avoid SQL injection.
            # Row keys come from the internal _job_to_row serializer and
            # should never contain user input, but we verify anyway.
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
                    f"INSERT INTO jobs ({cols}) VALUES ({ph}) ON CONFLICT (id) DO UPDATE SET {update_cols}",  # nosec B608 — validated as valid identifiers
                    [row[k] for k in safe_keys],
                )
                # Dual-write to companion tables (Schema v4)
                _sync_job_results(conn, job.id, job.results)
                _sync_job_events(conn, job.id, job.logs)

            # Only remove stale rows when explicitly requested (single-process
            # mode)
            if prune_missing:
                active_ids = list(jobs.keys())
                _execute(
                    conn,
                    "DELETE FROM jobs WHERE deleted_at IS NULL AND id != ALL(%s)",
                    (active_ids,) if active_ids else (["__no_active_ids__"],),
                )

            # Upsert recycle bin — do NOT delete first
            for job in recycle_bin.values():
                row = _job_to_row(job)
                now_iso = datetime.datetime.now().isoformat()
                row["deleted_at"] = now_iso
                cols = ", ".join(row.keys())
                ph = ", ".join("%s" for _ in row)
                _execute(
                    conn,
                    f"INSERT INTO recycle_bin ({cols}) VALUES ({ph}) ON CONFLICT (id) DO NOTHING",  # nosec B608 — cols are model field names, not user input
                    list(row.values()),
                )
                # Also soft-delete the job from the jobs table so it no
                # longer appears in load_all() queries (WHERE deleted_at IS
                # NULL).
                _execute(
                    conn,
                    "UPDATE jobs SET deleted_at = %s WHERE id = %s AND deleted_at IS NULL",
                    (now_iso, job.id),
                )

            # Only remove stale recycle bin entries when explicitly requested
            if prune_missing:
                recycle_ids = list(recycle_bin.keys())
                _execute(
                    conn,
                    "DELETE FROM recycle_bin WHERE id != ALL(%s)",
                    (recycle_ids,) if recycle_ids else (["__no_recycle_ids__"],),
                )

    def save_single(self, job: Job) -> None:
        self._ensure()
        with _conn() as conn:
            row = _job_to_row(job)
            cols = ", ".join(row.keys())
            ph = ", ".join("%s" for _ in row)
            update_cols = ", ".join(f"{k} = EXCLUDED.{k}" for k in row if k != "id")
            _execute(
                conn,
                f"INSERT INTO jobs ({cols}) VALUES ({ph}) ON CONFLICT (id) DO UPDATE SET {update_cols}",  # nosec B608 — cols/update_cols are model field names, not user input
                list(row.values()),
            )
            # Dual-write to companion tables (Schema v4). The legacy JSON
            # columns in ``jobs`` are still populated; this is additive.
            _sync_job_results(conn, job.id, job.results)
            _sync_job_events(conn, job.id, job.logs)

    def read_events(
        self,
        job_id: str,
        limit: int = 200,
        offset: int = 0,
        level_prefix: str | None = None,
    ) -> list[dict]:
        """Read lifecycle events from the ``job_events`` companion table.

        Returns ``[]`` when the table has not been populated (the
        dual-write is opt-in for non-SQLite deployments) so the
        caller can fall back to the in-memory ``Job.logs`` list.
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
            # Companion table may not exist yet on this deployment; the
            # caller falls back to in-memory logs.
            return []
        return [
            {
                "timestamp": (row.get("timestamp") or ""),
                "level": (row.get("level") or "info"),
                "message": (row.get("message") or ""),
            }
            for row in rows
        ]

    # ─── Individual repository operations (avoid full-state rewrites) ────

    def is_cancel_requested(self, job_id: str) -> bool:
        """Check from Postgres whether a job has a pending cancellation request.

        Required for cross-process cancellation: the worker polls this method
        during long-running operations to detect cancellations requested by
        the API process.
        """
        self._ensure()
        with _conn() as conn:
            row = _fetch_one(
                conn,
                "SELECT cancel_requested FROM jobs WHERE id = %s AND deleted_at IS NULL",
                (job_id,),
            )
            if row:
                return bool(row.get("cancel_requested", False))
            return False

    def move_to_recycle_bin(self, job_id: str) -> bool:
        """Move a job to the recycle bin by soft-deleting it and copying to recycle_bin table."""
        self._ensure()
        with _conn() as conn:
            row = _fetch_one(conn, "SELECT * FROM jobs WHERE id = %s AND deleted_at IS NULL", (job_id,))
            if not row:
                return False
            now = datetime.datetime.now().isoformat()
            _execute(conn, "UPDATE jobs SET deleted_at = %s WHERE id = %s", (now, job_id))
            # Upsert into recycle_bin
            cols_to_copy = [k for k in row if k != "deleted_at"]
            insert_cols = ", ".join(cols_to_copy)
            insert_vals = ", ".join("%s" for _ in cols_to_copy)
            params = [row[k] for k in cols_to_copy] + [now]
            _execute(
                conn,
                f"INSERT INTO recycle_bin ({insert_cols}, deleted_at) VALUES ({insert_vals}, %s) ON CONFLICT (id) DO NOTHING",  # nosec B608 — insert_cols are model field names, not user input
                params,
            )
            return True

    def restore_from_recycle_bin(self, job_id: str) -> bool:
        """Restore a job from the recycle bin back to active jobs."""
        self._ensure()
        with _conn() as conn:
            row = _fetch_one(conn, "SELECT * FROM recycle_bin WHERE id = %s", (job_id,))
            if not row:
                return False
            # Remove from recycle_bin and restore to jobs
            _execute(conn, "DELETE FROM recycle_bin WHERE id = %s", (job_id,))
            # Restore with deleted_at=NULL
            cols = [k for k in row if k != "deleted_at"]
            col_list = ", ".join(cols)
            ph = ", ".join("%s" for _ in cols)
            update_parts = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
            _execute(
                conn,
                f"INSERT INTO jobs ({col_list}) VALUES ({ph}) ON CONFLICT (id) DO UPDATE SET deleted_at = NULL, {update_parts}",  # nosec B608 — col_list/update_parts are model field names, not user input
                [row[k] for k in cols],
            )
            return True

    def hard_delete(self, job_id: str) -> bool:
        """Permanently delete a job from all tables."""
        self._ensure()
        with _conn() as conn:
            cur = _execute(conn, "DELETE FROM jobs WHERE id = %s", (job_id,))
            deleted = cur.rowcount
            _execute(conn, "DELETE FROM recycle_bin WHERE id = %s", (job_id,))
            # Clean up companion tables (Schema v4)
            _execute(conn, "DELETE FROM job_results WHERE job_id = %s", (job_id,))
            _execute(conn, "DELETE FROM job_events WHERE job_id = %s", (job_id,))
            return deleted > 0  # type: ignore[no-any-return]

    def clear_terminal_jobs(self, older_than: str | None = None) -> int:
        """Remove terminal-status jobs older than the given timestamp.
        Only removes jobs that are completed, failed, canceled, degraded, or empty_result.
        Moves them to recycle_bin before deletion.
        """
        self._ensure()
        terminal_statuses = ("completed", "failed", "canceled", "degraded", "empty_result")
        with _conn() as conn:
            rows = _fetch_all(
                conn,
                "SELECT * FROM jobs WHERE status = ANY(%s) AND deleted_at IS NULL"
                + (" AND completed_at < %s" if older_than else ""),  # nosec B608 — concatenation uses controlled boolean, not user input
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
                    f"INSERT INTO recycle_bin ({col_list}, deleted_at) VALUES ({ph}, %s) ON CONFLICT (id) DO NOTHING",  # nosec B608 — col_list are model field names, not user input
                    [row[k] for k in cols] + [now],
                )
                # Clean up companion tables (Schema v4)
                _execute(conn, "DELETE FROM job_results WHERE job_id = %s", (row["id"],))
                _execute(conn, "DELETE FROM job_events WHERE job_id = %s", (row["id"],))
            return len(rows)

    # ─── World state persistence ────────────────────────────────────────

    def load_world_state(self) -> dict | None:
        """Load semantic world state from Postgres."""
        self._ensure()
        with _conn() as conn:
            row = _fetch_one(conn, "SELECT payload FROM world_state WHERE id = 'default'")
            if row and row.get("payload"):
                try:
                    return json.loads(row["payload"])  # type: ignore[no-any-return]
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("Failed to deserialize world_state payload: %s", e)
            return None

    def save_world_state(self, payload: dict) -> None:
        """Save semantic world state to Postgres."""
        self._ensure()
        now = datetime.datetime.now().isoformat()
        payload_json = json.dumps(payload, ensure_ascii=False)
        with _conn() as conn:
            _execute(
                conn,
                """INSERT INTO world_state (id, payload, updated_at)
                   VALUES ('default', %s, %s)
                   ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = EXCLUDED.updated_at""",
                (payload_json, now),
            )

    def health_check(self) -> dict:
        """Check Postgres connectivity and schema health."""
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
                    "backend": "postgres",
                    "schema_version": version or 0,
                    "expected_version": _CURRENT_SCHEMA_VERSION,
                    "job_count": job_count or 0,
                    "recycle_bin_count": recycle_count or 0,
                }
        except Exception as e:
            logger.exception("Postgres health check failed: %s")
            return {
                "ok": False,
                "backend": "postgres",
                "error": str(e),
                "schema_version": 0,
                "expected_version": _CURRENT_SCHEMA_VERSION,
            }


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
        dsn = _get_database_url()
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
