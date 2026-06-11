"""Shared Postgres repository base — common CRUD, schema, and serialization logic.

Extracted from ``postgres_repository.py`` and ``psycopg3_repository.py``
during Phase C deduplication. Both driver-specific implementations
inherit from ``PostgresRepositoryBase`` and provide only:

- Connection pool management
- Low-level ``_fetch_all``, ``_fetch_one``, ``_execute`` helpers
- Connectivity verification
"""

from __future__ import annotations

import datetime
import json
import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from app.models import Job, JobStatus
from app.storage_interface import JobRepository

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

_CURRENT_SCHEMA_VERSION = 6

# ───────────────────────────────────────────────────────────────────────
# Database URL resolution (shared between driver implementations)
# ───────────────────────────────────────────────────────────────────────


def get_database_url() -> str:
    """Resolve the Postgres DSN from environment or settings.

    Priority:
    1. settings.DATABASE_URL (from .env file or pydantic-settings)
    2. Development fallback default (only in dev mode)
    """
    from app.config import settings

    url = settings.DATABASE_URL
    if url:
        return url
    msg = (
        "DATAFORGE_DATABASE_URL is required. "
        "Set it in your .env file or environment. "
        "Example: postgresql://user:password@localhost:5432/dataforge"
    )
    raise RuntimeError(msg)


# ───────────────────────────────────────────────────────────────────────
# Schema SQL builders (shared)
# ───────────────────────────────────────────────────────────────────────


def _columns_sql() -> list[str]:
    """Return column definitions shared across both driver implementations.

    Re-exported from ``storage_interface`` so both drivers use the same
    column list and the two backends stay schema-compatible.
    """
    from app.storage_interface import _JOBS_COLUMNS_SQL

    return list(_JOBS_COLUMNS_SQL)


def build_create_jobs_sql() -> str:
    """Build the full CREATE TABLE statement for the jobs table."""
    cols = ",\n        ".join(_columns_sql())
    return (
        "CREATE TABLE IF NOT EXISTS jobs ("
        "\n        id TEXT PRIMARY KEY,"
        "\n        name TEXT NOT NULL,"
        "\n        status TEXT NOT NULL DEFAULT 'pending',"
        f"\n        {cols}"
        "\n    )"
    )


def build_create_recycle_bin_sql() -> str:
    """Build the full CREATE TABLE statement for the recycle_bin table."""
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


# ───────────────────────────────────────────────────────────────────────
# Serialization helpers (shared between driver implementations)
# ───────────────────────────────────────────────────────────────────────


def job_to_row(job: Job) -> dict[str, Any]:
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
        "updated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "deleted_at": None,
    }


def row_to_job(row: dict[str, Any]) -> Job | None:
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
# Companion-table helpers (shared)
# ───────────────────────────────────────────────────────────────────────


def sync_job_results(conn, job_id: str, results: list[Any]) -> None:
    """Replace the ``job_results`` rows for ``job_id`` with ``results``."""
    execute(conn, "DELETE FROM job_results WHERE job_id = %s", (job_id,))
    if results:
        for idx, res in enumerate(results):
            execute(
                conn,
                "INSERT INTO job_results (job_id, result_index, payload) VALUES (%s, %s, %s)",
                (job_id, idx, json.dumps(res, default=str)),
            )


def sync_job_events(conn, job_id: str, logs) -> None:
    """Replace the ``job_events`` rows for ``job_id`` with ``logs``."""
    execute(conn, "DELETE FROM job_events WHERE job_id = %s", (job_id,))
    for entry in logs or []:
        if hasattr(entry, "model_dump"):
            try:
                entry_dict = entry.model_dump()
            except Exception:
                entry_dict = {"timestamp": "", "level": "info", "message": str(entry)}
        elif isinstance(entry, dict):
            entry_dict = entry
        else:
            entry_dict = {"timestamp": "", "level": "info", "message": str(entry)}
        execute(
            conn,
            "INSERT INTO job_events (job_id, timestamp, level, message) VALUES (%s, %s, %s, %s)",
            (
                job_id,
                str(entry_dict.get("timestamp") or ""),
                str(entry_dict.get("level") or "info"),
                str(entry_dict.get("message") or ""),
            ),
        )


# ───────────────────────────────────────────────────────────────────────
# Schema management (shared)
# ───────────────────────────────────────────────────────────────────────


def ensure_required_tables(conn) -> None:
    """Create required tables if they do not exist."""
    execute(conn, build_create_jobs_sql())
    for col_def in _columns_sql():
        try:
            execute(conn, f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {col_def}")
        except Exception:
            logger.debug("ALTER TABLE jobs ADD COLUMN %s failed (ignored)", col_def)
    execute(conn, build_create_recycle_bin_sql())
    for col_def in _columns_sql():
        try:
            execute(conn, f"ALTER TABLE recycle_bin ADD COLUMN IF NOT EXISTS {col_def}")
        except Exception:
            logger.debug("ALTER TABLE recycle_bin ADD COLUMN %s failed (ignored)", col_def)
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_recycle_bin_created_at ON recycle_bin(created_at DESC)",
    ]:
        try:
            execute(conn, idx_sql)
        except Exception:
            logger.debug("CREATE INDEX failed (ignored): %s", idx_sql)


def _migrate_worker_heartbeats_v6(conn) -> None:
    """Schema v6: make worker_heartbeats primary key composite (worker_id, pid).

    The original v5 schema used ``worker_id TEXT PRIMARY KEY``. When two
    workers on the same host share the same resolved ``worker_id``
    (hostname), the second worker's heartbeat would overwrite the
    first worker's row, leaving the healthcheck with stale data and
    the wrong worker reported as alive.

    The migration:
      1. Renames the old table to a backup.
      2. Creates a new table with a composite (worker_id, pid) PK.
      3. Copies the most recent heartbeat per (worker_id, pid) into the new
         table. If the old table had two rows for the same (worker_id,
         pid) — impossible under the v5 schema, but defensive — the most
         recent ``last_heartbeat`` wins.
      4. Drops the backup.

    The whole migration runs inside a SAVEPOINT so a failure rolls back
    to the v5 schema state cleanly.
    """
    with conn.cursor() as cur:
        cur.execute("SAVEPOINT migrate_wh_v6")
        try:
            cur.execute("ALTER TABLE worker_heartbeats RENAME TO worker_heartbeats_v5_backup")
            cur.execute(
                """
                CREATE TABLE worker_heartbeats (
                    worker_id TEXT NOT NULL,
                    last_heartbeat TEXT NOT NULL,
                    hostname TEXT NOT NULL DEFAULT '',
                    pid INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (worker_id, pid)
                )
                """,
            )
            # Carry the most recent row per (worker_id, pid) forward.
            # DISTINCT ON is the cleanest Postgres-only way to do this
            # without a window function.
            cur.execute(
                """
                INSERT INTO worker_heartbeats
                    (worker_id, last_heartbeat, hostname, pid, started_at)
                SELECT worker_id, last_heartbeat, hostname, pid, started_at
                FROM (
                    SELECT DISTINCT ON (worker_id, pid)
                        worker_id, last_heartbeat, hostname, pid, started_at
                    FROM worker_heartbeats_v5_backup
                    ORDER BY worker_id, pid, last_heartbeat DESC
                ) latest
                """,
            )
            cur.execute("DROP TABLE worker_heartbeats_v5_backup")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT migrate_wh_v6")
            logger.exception(
                "worker_heartbeats v5→v6 migration failed; the table is "
                "left in its previous state. Heartbeat writes will continue "
                "to work but two workers on the same host will collide.",
            )
            raise
        else:
            cur.execute("RELEASE SAVEPOINT migrate_wh_v6")


def ensure_schema(conn) -> None:
    """Run schema migrations to ensure tables exist and are up to date."""
    execute(
        conn,
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)",
    )
    row = _fetch_one(conn, "SELECT MAX(version) AS version FROM schema_version")
    current = row["version"] if row and row.get("version") is not None else 0

    ensure_required_tables(conn)

    if current < _CURRENT_SCHEMA_VERSION:
        if current < 3:
            execute(
                conn,
                """CREATE TABLE IF NOT EXISTS world_state (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )""",
            )

        if current < 4:
            execute(
                conn,
                """CREATE TABLE IF NOT EXISTS job_results (
                    job_id TEXT NOT NULL,
                    result_index INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (job_id, result_index),
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                )""",
            )
            execute(
                conn,
                """CREATE TABLE IF NOT EXISTS job_events (
                    event_id BIGSERIAL PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL DEFAULT '',
                    level TEXT NOT NULL DEFAULT 'info',
                    message TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                )""",
            )
            execute(conn, "CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id, event_id)")
            execute(conn, "CREATE INDEX IF NOT EXISTS idx_job_results_job_id ON job_results(job_id)")
            execute(
                conn,
                """CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idem_key TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )""",
            )
            execute(conn, "CREATE INDEX IF NOT EXISTS idx_idempotency_keys_created_at ON idempotency_keys(created_at)")

        if current < 5:
            execute(
                conn,
                """CREATE TABLE IF NOT EXISTS worker_heartbeats (
                    worker_id TEXT PRIMARY KEY,
                    last_heartbeat TEXT NOT NULL,
                    hostname TEXT NOT NULL DEFAULT '',
                    pid INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL DEFAULT ''
                )""",
            )

        if current < 6:
            # v6: Make the worker_heartbeats primary key composite
            # (worker_id, pid) so two workers on the same host — sharing
            # the same resolved worker_id (hostname) — do not overwrite
            # each other's heartbeat. The old single-column PK is dropped
            # and a composite PK is added. Existing rows are preserved;
            # any historical collision (where the same worker_id had two
            # pids) is resolved by keeping the most recent row per pid.
            _migrate_worker_heartbeats_v6(conn)

        execute(conn, "DELETE FROM schema_version")
        execute(conn, "INSERT INTO schema_version (version) VALUES (%s)", (_CURRENT_SCHEMA_VERSION,))
        logger.info("Postgres schema migrated to version %d", _CURRENT_SCHEMA_VERSION)


# ───────────────────────────────────────────────────────────────────────
# Module-level query helpers (shared, driver-agnostic via parameterised SQL)
# These are imported by the schema functions above; they delegate to the
# driver-specific implementations via the abstract methods on the base class.
# ───────────────────────────────────────────────────────────────────────

# Note: _fetch_all, _fetch_one, execute are defined at module level for
# backward compatibility with schema helpers. They are NOT called directly
# by the repository methods — those use self._fetch_all etc. for driver
# dispatch. Instead they use the module-level variants below which raise
# a clear error if called before __init__ has set the driver callbacks.

_driver_fetch_all = None
_driver_fetch_one = None
_driver_execute = None


def _set_driver_functions(
    fetch_all_fn,
    fetch_one_fn,
    execute_fn,
) -> None:
    """Set the module-level query functions used by schema helpers.

    Called by each driver implementation's ``__init__`` after pool setup,
    so that the shared schema functions (``ensure_required_tables``,
    ``ensure_schema``) can issue SQL without knowing which driver is active.
    """
    global _driver_fetch_all, _driver_fetch_one, _driver_execute
    _driver_fetch_all = fetch_all_fn
    _driver_fetch_one = fetch_one_fn
    _driver_execute = execute_fn


def _fetch_all(conn, sql: str, params=None) -> list[dict]:
    """Module-level wrapper delegating to the current driver's _fetch_all."""
    fn = _driver_fetch_all
    if fn is None:
        msg = "Postgres driver not initialised — call _set_driver_functions first"
        raise RuntimeError(msg)
    return fn(conn, sql, params)


def _fetch_one(conn, sql: str, params=None) -> dict | None:
    fn = _driver_fetch_one
    if fn is None:
        msg = "Postgres driver not initialised — call _set_driver_functions first"
        raise RuntimeError(msg)
    return fn(conn, sql, params)


def execute(conn, sql: str, params=None):
    fn = _driver_execute
    if fn is None:
        msg = "Postgres driver not initialised — call _set_driver_functions first"
        raise RuntimeError(msg)
    return fn(conn, sql, params)


# ───────────────────────────────────────────────────────────────────────
# Abstract base class
# ───────────────────────────────────────────────────────────────────────


class PostgresRepositoryBase(JobRepository, ABC):
    """Abstract Postgres repository base with all shared CRUD logic.

    Subclasses must implement:
    - ``_conn()`` — context manager yielding a database connection
    - ``self._fetch_all(conn, sql, params)`` — execute query, return list[dict]
    - ``self._fetch_one(conn, sql, params)`` — execute query, return dict | None
    - ``self._execute(conn, sql, params)`` — execute statement, return cursor
    """

    backend: str = "postgres"

    def __init__(self, auto_ensure_schema: bool = True) -> None:
        self._auto_ensure_schema = auto_ensure_schema
        self._schema_ensured = False

    # ── Abstract methods (driver-specific) ─────────────────────────────

    @abstractmethod
    @contextmanager
    def _conn(self) -> Iterator:
        """Acquire a connection (context manager)."""

    @abstractmethod
    def _fetch_all(self, conn, sql: str, params=None) -> list[dict]:
        """Execute a query and return all rows as dicts."""

    @abstractmethod
    def _fetch_one(self, conn, sql: str, params=None) -> dict | None:
        """Execute a query and return the first row as a dict, or None."""

    @abstractmethod
    def _execute(self, conn, sql: str, params=None):
        """Execute a statement and return the cursor."""

    # ── Schema management ──────────────────────────────────────────────

    def _ensure(self) -> None:
        if self._auto_ensure_schema and not self._schema_ensured:
            with self._conn() as conn:
                # Use the instance methods for the schema check, not
                # the module-level wrappers.
                # Temporarily set module-level driver functions for the
                # schema helpers that import them.
                _set_driver_functions(self._fetch_all, self._fetch_one, self._execute)
                ensure_schema(conn)
                self._schema_ensured = True

    # ── Repository interface ───────────────────────────────────────────

    def load_jobs(self) -> dict[str, Job]:
        self._ensure()
        with self._conn() as conn:
            rows = self._fetch_all(conn, "SELECT * FROM jobs WHERE deleted_at IS NULL")
            jobs: dict[str, Job] = {}
            for row in rows:
                job = row_to_job(row)
                if job:
                    jobs[job.id] = job
            return jobs

    def get_job(self, job_id: str) -> Job | None:
        self._ensure()
        with self._conn() as conn:
            row = self._fetch_one(
                conn,
                "SELECT * FROM jobs WHERE id = %s AND deleted_at IS NULL",
                (job_id,),
            )
            if not row:
                return None
            return row_to_job(row)

    def list_job_summaries(self, limit: int = 100, cursor: str | None = None) -> list[dict]:
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
        with self._conn() as conn:
            rows = self._fetch_all(conn, sql, tuple(params))
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

    def count_jobs_by_status(self, include_deleted: bool = False) -> dict[str, int]:
        """Return a ``{status_value: count}`` mapping for all jobs.

        Implemented as a single ``GROUP BY status`` query so it stays
        O(distinct statuses) even on million-row tables. The previous
        approach of calling ``list_job_summaries(limit=5000)`` was
        silently capped to 500 by the storage layer and produced wrong
        counts for any store with more than 500 jobs.
        """
        self._ensure()
        sql = "SELECT status, COUNT(*) AS cnt FROM jobs"
        if not include_deleted:
            sql += " WHERE deleted_at IS NULL"
        sql += " GROUP BY status"
        try:
            with self._conn() as conn:
                rows = self._fetch_all(conn, sql)
        except Exception:
            logger.exception("count_jobs_by_status failed")
            return {}
        return {str(row["status"]): int(row["cnt"]) for row in rows}

    def load_recycle_bin(self) -> dict[str, Job]:
        self._ensure()
        with self._conn() as conn:
            rows = self._fetch_all(conn, "SELECT * FROM recycle_bin")
            jobs: dict[str, Job] = {}
            for row in rows:
                job = row_to_job(row)
                if job:
                    jobs[job.id] = job
            return jobs

    def list_recycle_summaries(self, limit: int = 100, cursor: str | None = None) -> list[dict]:
        self._ensure()
        safe_limit = max(1, min(int(limit), 500))
        params: list[object] = []
        sql = (
            "SELECT id, name, status, mode, topic, urls, created_at, started_at, "
            "completed_at, total_records, filtered_records, progress_current, "
            "progress_total, error, deleted_at "
            "FROM recycle_bin WHERE 1=1"
        )
        if cursor:
            sql += " AND created_at < %s"
            params.append(cursor)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(safe_limit)
        with self._conn() as conn:
            rows = self._fetch_all(conn, sql, tuple(params))
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
        with self._conn() as conn:
            # Cross-replica recovery contract: when more than one API
            # replica starts up at the same time (rolling deploy, blue/
            # green swap, K8s scaling event), each replica would
            # independently observe in-progress jobs and race to mark
            # them as failed. The second writer's UPDATE would clobber
            # the first writer's, but the in-memory job objects
            # (carrying the recovery error message) would diverge and
            # any subsequent ``save_all`` from either replica would
            # re-persist the *other* replica's state. We hold a
            # Postgres advisory lock for the duration of the
            # recovery sweep so only one replica mutates the rows at
            # a time. The constant ``8675309`` is arbitrary; any
            # fixed int64 that no other subsystem uses is fine.
            # ``pg_advisory_unlock`` is called explicitly in the
            # ``finally`` block so the lock is released even if the
            # recovery code raises.
            lock_acquired = False
            try:
                self._execute(conn, "SELECT pg_try_advisory_lock(8675309)")
                lock_row = self._fetch_one(conn, "SELECT 1 AS held")
                # ``pg_try_advisory_lock`` returns boolean; the
                # function-call-as-query form loses that return value
                # for some drivers, so we re-check by inspecting
                # ``pg_locks`` directly.
                held_row = self._fetch_one(
                    conn,
                    "SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND objid = 8675309 AND pid = pg_backend_pid()",
                )
                if held_row is not None:
                    lock_acquired = True
                # ``lock_row`` is intentionally unused — kept for
                # future assertions if a driver begins surfacing the
                # boolean return value directly.
                del lock_row
                job_rows = self._fetch_all(conn, "SELECT * FROM jobs WHERE deleted_at IS NULL")
                jobs_store: dict[str, Job] = {}
                for row in job_rows:
                    job = row_to_job(row)
                    if job:
                        jobs_store[job.id] = job

                if recover_in_progress:
                    now_iso = datetime.datetime.now(datetime.UTC).isoformat()
                    dirty_ids = []
                    for job in list(jobs_store.values()):
                        if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
                            job.status = JobStatus.FAILED
                            job.error = "Recovered after restart while still in progress."
                            job.completed_at = now_iso
                            job.cancel_requested = False
                            dirty_ids.append(job.id)
                    if dirty_ids:
                        self._execute(
                            conn,
                            "UPDATE jobs SET status = 'failed',"
                            " error = 'Recovered after restart while still in progress.',"
                            " completed_at = %s, cancel_requested = FALSE WHERE id = ANY(%s)",
                            (now_iso, dirty_ids),
                        )
                        logger.info("Recovered %d in-progress job(s) in Postgres", len(dirty_ids))

                recycle_rows = self._fetch_all(conn, "SELECT * FROM recycle_bin")
                recycle_store: dict[str, Job] = {}
                for row in recycle_rows:
                    job = row_to_job(row)
                    if job:
                        recycle_store[job.id] = job

                ws_row = self._fetch_one(conn, "SELECT payload FROM world_state WHERE id = 'default'")
                world_state_data: dict | None = None
                if ws_row and ws_row.get("payload"):
                    try:
                        world_state_data = json.loads(ws_row["payload"])
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning("Failed to deserialize world_state payload: %s", e)
                return jobs_store, recycle_store, world_state_data
            finally:
                if lock_acquired:
                    # Best-effort unlock; if it fails the lock will
                    # be released when the session ends.
                    try:
                        self._execute(conn, "SELECT pg_advisory_unlock(8675309)")
                    except Exception:
                        logger.debug("pg_advisory_unlock(8675309) failed; will be released at session end")

    def save_all(self, jobs: dict[str, Job], recycle_bin: dict[str, Job], prune_missing: bool = False) -> None:
        self._ensure()
        with self._conn() as conn:

            def _safe_cols(row):
                for k in row:
                    if not k.isidentifier():
                        msg = f"Unsafe column name in job_to_row: {k!r}"
                        raise ValueError(msg)
                return list(row.keys())

            for job in jobs.values():
                row = job_to_row(job)
                safe_keys = _safe_cols(row)
                cols = ", ".join(safe_keys)
                ph = ", ".join("%s" for _ in safe_keys)
                update_cols = ", ".join(f"{k} = EXCLUDED.{k}" for k in safe_keys if k != "id")
                self._execute(
                    conn,
                    f"INSERT INTO jobs ({cols}) VALUES ({ph}) ON CONFLICT (id) DO UPDATE SET {update_cols}",  # nosec B608  # noqa: RUF100, S608
                    [row[k] for k in safe_keys],
                )
                sync_job_results(conn, job.id, job.results)
                sync_job_events(conn, job.id, job.logs)

            if prune_missing:
                active_ids = list(jobs.keys())
                self._execute(
                    conn,
                    "DELETE FROM jobs WHERE deleted_at IS NULL AND id != ALL(%s)",
                    (active_ids,) if active_ids else (["__no_active_ids__"],),
                )

            for job in recycle_bin.values():
                row = job_to_row(job)
                now_iso = datetime.datetime.now(datetime.UTC).isoformat()
                row["deleted_at"] = now_iso
                cols = ", ".join(row.keys())
                ph = ", ".join("%s" for _ in row)
                self._execute(
                    conn,
                    f"INSERT INTO recycle_bin ({cols}) VALUES ({ph}) ON CONFLICT (id) DO NOTHING",  # nosec B608  # noqa: RUF100, S608
                    list(row.values()),
                )
                self._execute(
                    conn,
                    "UPDATE jobs SET deleted_at = %s WHERE id = %s AND deleted_at IS NULL",
                    (now_iso, job.id),
                )

            if prune_missing:
                recycle_ids = list(recycle_bin.keys())
                self._execute(
                    conn,
                    "DELETE FROM recycle_bin WHERE id != ALL(%s)",
                    (recycle_ids,) if recycle_ids else (["__no_recycle_ids__"],),
                )

    def save_single(self, job: Job) -> None:
        self._ensure()
        with self._conn() as conn:
            row = job_to_row(job)
            cols = ", ".join(row.keys())
            ph = ", ".join("%s" for _ in row)
            update_cols = ", ".join(f"{k} = EXCLUDED.{k}" for k in row if k != "id")
            self._execute(
                conn,
                f"INSERT INTO jobs ({cols}) VALUES ({ph}) ON CONFLICT (id) DO UPDATE SET {update_cols}",  # nosec B608  # noqa: RUF100, S608
                list(row.values()),
            )
            sync_job_results(conn, job.id, job.results)
            sync_job_events(conn, job.id, job.logs)

    def read_results(self, job_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        self._ensure()
        safe_limit = max(1, min(int(limit), 1000))
        safe_offset = max(0, int(offset))
        sql = "SELECT payload FROM job_results WHERE job_id = %s ORDER BY result_index ASC LIMIT %s OFFSET %s"
        try:
            with self._conn() as conn:
                rows = self._fetch_all(conn, sql, (job_id, safe_limit, safe_offset))
        except Exception:
            logger.exception("read_results failed for job %s", job_id)
            return []
        out: list[dict] = []
        for row in rows:
            try:
                out.append(json.loads(row["payload"]))
            except (TypeError, ValueError):
                out.append({"_unparseable": row["payload"]})
        return out

    def count_results(self, job_id: str) -> int:
        """Return the total number of result rows for a job.

        This is a separate, indexed ``COUNT(*)`` query so the pagination
        ``total`` field on ``GET /api/jobs/{id}/results`` is accurate even
        when only one page of results is fetched.
        """
        self._ensure()
        try:
            with self._conn() as conn:
                row = self._fetch_one(
                    conn,
                    "SELECT COUNT(*) AS cnt FROM job_results WHERE job_id = %s",
                    (job_id,),
                )
            return int(row["cnt"]) if row else 0
        except Exception:
            logger.exception("count_results failed for job %s", job_id)
            return 0

    def read_events(self, job_id: str, limit: int = 200, offset: int = 0, level_prefix: str | None = None) -> list[dict]:
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
            with self._conn() as conn:
                rows = self._fetch_all(conn, sql, tuple(params))
        except Exception:
            logger.exception("read_events failed for job %s", job_id)
            return []
        return [
            {
                "timestamp": (row.get("timestamp") or ""),
                "level": (row.get("level") or "info"),
                "message": (row.get("message") or ""),
            }
            for row in rows
        ]

    def lookup_idempotency_key(self, idem_key: str) -> str | None:
        if not idem_key:
            return None
        self._ensure()
        try:
            with self._conn() as conn:
                row = self._fetch_one(
                    conn,
                    "SELECT job_id FROM idempotency_keys WHERE idem_key = %s",
                    (idem_key,),
                )
                return str(row["job_id"]) if row else None
        except Exception:
            logger.debug("idempotency key lookup failed for %s", idem_key, exc_info=True)
            return None

    def lookup_idempotency_fingerprint(self, idem_key: str) -> str | None:
        if not idem_key:
            return None
        self._ensure()
        try:
            with self._conn() as conn:
                row = self._fetch_one(
                    conn,
                    "SELECT request_fingerprint FROM idempotency_keys WHERE idem_key = %s",
                    (idem_key,),
                )
                return str(row["request_fingerprint"]) if row else None
        except Exception:
            logger.debug("idempotency fingerprint lookup failed for %s", idem_key, exc_info=True)
            return None

    def record_idempotency_key(self, idem_key: str, job_id: str, request_fingerprint: str) -> None:
        if not idem_key or not job_id:
            return
        self._ensure()
        try:
            with self._conn() as conn:
                self._execute(
                    conn,
                    """INSERT INTO idempotency_keys (idem_key, job_id, request_fingerprint)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (idem_key) DO UPDATE
                         SET job_id = EXCLUDED.job_id,
                             request_fingerprint = EXCLUDED.request_fingerprint,
                             created_at = NOW()""",
                    (idem_key, job_id, request_fingerprint),
                )
        except Exception:
            logger.exception("Failed to record idempotency key %s", idem_key)

    def prune_idempotency_keys(self, older_than_days: int = 7) -> int:
        if older_than_days <= 0:
            return 0
        self._ensure()
        try:
            with self._conn() as conn:
                cur = self._execute(
                    conn,
                    "DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL %s",
                    (f"{int(older_than_days)} days",),
                )
                return int(cur.rowcount) if cur.rowcount else 0
        except Exception:
            logger.exception("prune_idempotency_keys failed")
            return 0

    def cleanup_companion_data(self, job_id: str) -> None:
        self._ensure()
        try:
            with self._conn() as conn:
                self._execute(conn, "DELETE FROM job_results WHERE job_id = %s", (job_id,))
                self._execute(conn, "DELETE FROM job_events WHERE job_id = %s", (job_id,))
        except Exception:
            logger.exception("Failed to clean up companion data for job %s", job_id)

    def is_cancel_requested(self, job_id: str) -> bool:
        self._ensure()
        with self._conn() as conn:
            row = self._fetch_one(
                conn,
                "SELECT cancel_requested FROM jobs WHERE id = %s AND deleted_at IS NULL",
                (job_id,),
            )
            return bool(row.get("cancel_requested", False)) if row else False

    def move_to_recycle_bin(self, job_id: str) -> bool:
        self._ensure()
        with self._conn() as conn:
            row = self._fetch_one(conn, "SELECT * FROM jobs WHERE id = %s AND deleted_at IS NULL", (job_id,))
            if not row:
                return False
            now = datetime.datetime.now(datetime.UTC).isoformat()
            self._execute(conn, "UPDATE jobs SET deleted_at = %s WHERE id = %s", (now, job_id))
            cols_to_copy = [k for k in row if k != "deleted_at"]
            insert_cols = ", ".join(cols_to_copy)
            insert_vals = ", ".join("%s" for _ in cols_to_copy)
            params = [row[k] for k in cols_to_copy] + [now]
            self._execute(
                conn,
                f"INSERT INTO recycle_bin ({insert_cols}, deleted_at) VALUES ({insert_vals}, %s) ON CONFLICT (id) DO NOTHING",  # nosec B608  # noqa: RUF100, S608
                params,
            )
            return True

    def restore_from_recycle_bin(self, job_id: str) -> bool:
        self._ensure()
        with self._conn() as conn:
            row = self._fetch_one(conn, "SELECT * FROM recycle_bin WHERE id = %s", (job_id,))
            if not row:
                return False
            self._execute(conn, "DELETE FROM recycle_bin WHERE id = %s", (job_id,))
            cols = [k for k in row if k != "deleted_at"]
            col_list = ", ".join(cols)
            ph = ", ".join("%s" for _ in cols)
            update_parts = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
            self._execute(
                conn,
                f"INSERT INTO jobs ({col_list}) VALUES ({ph}) ON CONFLICT (id) DO UPDATE SET deleted_at = NULL, {update_parts}",  # nosec B608  # noqa: RUF100, S608
                [row[k] for k in cols],
            )
            return True

    def hard_delete(self, job_id: str) -> bool:
        self._ensure()
        with self._conn() as conn:
            cur = self._execute(conn, "DELETE FROM jobs WHERE id = %s", (job_id,))
            deleted = cur.rowcount
            self._execute(conn, "DELETE FROM recycle_bin WHERE id = %s", (job_id,))
            self._execute(conn, "DELETE FROM job_results WHERE job_id = %s", (job_id,))
            self._execute(conn, "DELETE FROM job_events WHERE job_id = %s", (job_id,))
            return deleted > 0

    def clear_terminal_jobs(self, older_than: str | None = None) -> int:
        self._ensure()
        terminal_statuses = ("completed", "failed", "canceled", "degraded", "empty_result")
        with self._conn() as conn:
            rows = self._fetch_all(
                conn,
                "SELECT * FROM jobs WHERE status = ANY(%s) AND deleted_at IS NULL"  # nosec B608  # noqa: RUF100, S608
                + (" AND completed_at < %s" if older_than else ""),  # nosec B608  # noqa: RUF100, S608
                (list(terminal_statuses), older_than) if older_than else (list(terminal_statuses),),
            )
            for row in rows:
                now = datetime.datetime.now(datetime.UTC).isoformat()
                self._execute(conn, "UPDATE jobs SET deleted_at = %s WHERE id = %s", (now, row["id"]))
                cols = [k for k in row if k != "deleted_at"]
                col_list = ", ".join(cols)
                ph = ", ".join("%s" for _ in cols)
                self._execute(
                    conn,
                    f"INSERT INTO recycle_bin ({col_list}, deleted_at) VALUES ({ph}, %s) ON CONFLICT (id) DO NOTHING",  # nosec B608  # noqa: RUF100, S608
                    [row[k] for k in cols] + [now],
                )
                self._execute(conn, "DELETE FROM job_results WHERE job_id = %s", (row["id"],))
                self._execute(conn, "DELETE FROM job_events WHERE job_id = %s", (row["id"],))
            return len(rows)

    def load_world_state(self) -> dict | None:
        self._ensure()
        with self._conn() as conn:
            row = self._fetch_one(conn, "SELECT payload FROM world_state WHERE id = 'default'")
            if row and row.get("payload"):
                try:
                    return json.loads(row["payload"])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("Failed to deserialize world_state payload: %s", e)
            return None

    def save_world_state(self, payload: dict[str, Any]) -> None:
        self._ensure()
        now = datetime.datetime.now(datetime.UTC).isoformat()
        payload_json = json.dumps(payload, ensure_ascii=False)
        with self._conn() as conn:
            self._execute(
                conn,
                "INSERT INTO world_state (id, payload, updated_at) VALUES ('default', %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = EXCLUDED.updated_at",
                (payload_json, now),
            )

    # ── Worker heartbeat ───────────────────────────────────────────────

    def record_worker_heartbeat(self, worker_id: str, hostname: str, pid: int) -> None:
        self._ensure()
        now = datetime.datetime.now(datetime.UTC).isoformat()
        with self._conn() as conn:
            # The composite primary key (worker_id, pid) — see schema v6 —
            # lets two workers on the same host coexist. The v5 schema
            # used ``ON CONFLICT (worker_id)`` which silently overwrote
            # a co-resident worker's heartbeat.
            self._execute(
                conn,
                """INSERT INTO worker_heartbeats (worker_id, last_heartbeat, hostname, pid, started_at)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (worker_id, pid) DO UPDATE SET
                     last_heartbeat = EXCLUDED.last_heartbeat,
                     hostname = EXCLUDED.hostname,
                     started_at = CASE
                       WHEN worker_heartbeats.pid = EXCLUDED.pid
                         THEN worker_heartbeats.started_at
                       ELSE EXCLUDED.started_at
                     END""",
                (worker_id, now, hostname, pid, now),
            )

    def get_worker_health(self, worker_id: str, ttl_seconds: int = 60) -> dict[str, Any]:
        self._ensure()
        with self._conn() as conn:
            # When multiple pids share a worker_id, return the freshest
            # heartbeat and mark the worker alive if any of its pids are
            # within the TTL. This matches the contract that the
            # healthcheck expects: ``alive=True`` means "at least one
            # worker process with this worker_id is up".
            row = self._fetch_one(
                conn,
                """SELECT last_heartbeat, hostname, pid, started_at
                   FROM worker_heartbeats
                   WHERE worker_id = %s
                   ORDER BY last_heartbeat DESC
                   LIMIT 1""",
                (worker_id,),
            )
        if not row:
            return {
                "alive": False,
                "worker_id": worker_id,
                "last_heartbeat": None,
                "hostname": None,
                "pid": None,
            }
        last_heartbeat = row.get("last_heartbeat")
        alive = False
        if last_heartbeat:
            try:
                delta = datetime.datetime.now(datetime.UTC) - datetime.datetime.fromisoformat(last_heartbeat)
                alive = delta.total_seconds() < ttl_seconds
            except (ValueError, TypeError):
                alive = False
        return {
            "alive": alive,
            "worker_id": worker_id,
            "last_heartbeat": last_heartbeat,
            "hostname": row.get("hostname"),
            "pid": row.get("pid"),
        }

    def get_all_worker_healths(self, ttl_seconds: int = 60) -> list[dict]:
        self._ensure()
        with self._conn() as conn:
            rows = self._fetch_all(conn, "SELECT worker_id, last_heartbeat, hostname, pid FROM worker_heartbeats")
        results: list[dict] = []
        for row in rows:
            wid = row.get("worker_id")
            last_hb = row.get("last_heartbeat")
            alive = False
            if last_hb:
                try:
                    delta = datetime.datetime.now(datetime.UTC) - datetime.datetime.fromisoformat(last_hb)
                    alive = delta.total_seconds() < ttl_seconds
                except (ValueError, TypeError):
                    alive = False
            results.append(
                {
                    "alive": alive,
                    "worker_id": wid,
                    "last_heartbeat": last_hb,
                    "hostname": row.get("hostname"),
                    "pid": row.get("pid"),
                },
            )
        return results

    def health_check(self) -> dict[str, Any]:
        try:
            self._ensure()
            with self._conn() as conn:
                row = self._fetch_one(conn, "SELECT MAX(version) AS version FROM schema_version")
                version = row["version"] if row else 0
                count_row = self._fetch_one(conn, "SELECT COUNT(*) AS cnt FROM jobs WHERE deleted_at IS NULL")
                job_count = count_row["cnt"] if count_row else 0
                recycle_row = self._fetch_one(conn, "SELECT COUNT(*) AS cnt FROM recycle_bin")
                recycle_count = recycle_row["cnt"] if recycle_row else 0
                return {
                    "ok": True,
                    "backend": self.backend,
                    "schema_version": version or 0,
                    "expected_version": _CURRENT_SCHEMA_VERSION,
                    "job_count": job_count or 0,
                    "recycle_bin_count": recycle_count or 0,
                }
        except Exception as e:
            logger.exception("Postgres health check failed")
            return {
                "ok": False,
                "backend": self.backend,
                "error": str(e),
                "schema_version": 0,
                "expected_version": _CURRENT_SCHEMA_VERSION,
            }
