"""SQLite-backed job storage with transactional safety and schema migrations.

Replaces JSON persistence with durable SQLite storage. Provides:
- Transactional writes (atomic commits)
- Schema versioning and migrations
- Shutdown flush for pending writes
- Same API surface as state_store.py (load_state, save_state, persist_state_fn)

Schema v4 introduces two companion tables — ``job_results`` and
``job_events`` — that hold the heavy per-job payloads (``results``
list and ``logs`` list) in dedicated rows. The original ``jobs`` /
``recycle_bin`` tables continue to carry the lightweight summary
columns and the embedded ``results`` / ``logs`` JSON for backward
compatibility. Writes are dual (the new tables and the legacy JSON
column both get the same data) so existing readers keep working
while new readers can opt into the cheaper per-row queries.
"""

import datetime
import json
import logging
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

from app.models import Job, JobStatus

logger = logging.getLogger(__name__)

_DB_LOCK = Lock()
_CURRENT_SCHEMA_VERSION = 9
_MIGRATIONS_RUN_FOR: set[Path] = set()


def _get_db_path() -> Path:
    from app.config import settings

    if settings.STATE_FILE_PATH_DYNAMIC:
        base = Path(settings.STATE_FILE_PATH_DYNAMIC).expanduser()
    else:
        base = Path(__file__).resolve().parent.parent / "data" / "jobs_state.json"
    return base.with_suffix(".db")


def _get_connection() -> sqlite3.Connection:
    path = _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    # Check if database tables are actually present to handle dynamic dev /
    # test deletions
    has_schema = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()

    if path not in _MIGRATIONS_RUN_FOR or not has_schema:
        _run_migrations(conn)
        _MIGRATIONS_RUN_FOR.add(path)
    return conn


def _maybe_migrate_from_json(conn: sqlite3.Connection) -> None:
    """One-time migration: import existing JSON state into SQLite."""
    json_path = _get_db_path().with_suffix(".json")
    if not json_path.exists():
        return
    row = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
    if row and row[0] > 0:
        return  # Already have data, skip migration
    try:
        import json as _json

        data = _json.loads(json_path.read_text())
        conn.execute("BEGIN IMMEDIATE")
        try:
            for raw in data.get("jobs", []):
                job = _row_to_job(_job_from_raw(raw))
                if job:
                    row_data = _job_to_row(job)
                    cols = ", ".join(row_data.keys())
                    ph = ", ".join("?" for _ in row_data)
                    conn.execute(f"INSERT OR IGNORE INTO jobs ({cols}) VALUES ({ph})", list(row_data.values()))  # noqa: RUF100, S608
            for raw in data.get("recycle_bin", []):
                job = _row_to_job(_job_from_raw(raw))
                if job:
                    row_data = _job_to_row(job)
                    cols = ", ".join(row_data.keys())
                    ph = ", ".join("?" for _ in row_data)
                    conn.execute(f"INSERT OR IGNORE INTO recycle_bin ({cols}) VALUES ({ph})", list(row_data.values()))  # noqa: RUF100, S608
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        logger.info(
            "Migrated %d jobs + %d recycle-bin entries from JSON to SQLite",
            len(data.get("jobs", [])),
            len(data.get("recycle_bin", [])),
        )
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.warning("JSON-to-SQLite migration skipped: %s", e)


def _job_from_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw JSON job dict to the format expected by _row_to_job."""
    out = dict(raw)
    for field in [
        "urls",
        "schema_fields",
        "filters",
        "results",
        "logs",
        "warnings",
        "quality_report",
        "discovered_urls",
        "selectors_map",
        "search_params",
    ]:
        if field in out and not isinstance(out[field], str):
            out[field] = json.dumps(out[field])
    return out


# ── Serialization — delegated to the shared mapper module ──────────────
# ARCH-004: Both SQLite and Postgres backends use the same canonical
# job_to_row / row_to_job from app.storage_mapper.  We re-export under
# the private names that callers within this file expect.
from app.storage_mapper import job_to_row as _job_to_row
from app.storage_mapper import row_to_job as _row_to_job


def _run_migrations(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        )
    """)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] if row and row[0] is not None else 0

    if current < _CURRENT_SCHEMA_VERSION:
        if current < 1:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    mode TEXT NOT NULL DEFAULT 'manual',
                    topic TEXT DEFAULT '',
                    intent TEXT DEFAULT '',
                    urls TEXT NOT NULL DEFAULT '[]',
                    schema_fields TEXT NOT NULL DEFAULT '[]',
                    filters TEXT DEFAULT '[]',
                    results TEXT DEFAULT '[]',
                    logs TEXT DEFAULT '[]',
                    total_records INTEGER DEFAULT 0,
                    filtered_records INTEGER DEFAULT 0,
                    total_llm_calls INTEGER DEFAULT 0,
                    error TEXT DEFAULT '',
                    warnings TEXT DEFAULT '',
                    quality_report TEXT DEFAULT '{}',
                    analysis TEXT DEFAULT '',
                    discovered_urls TEXT DEFAULT '[]',
                    selectors_map TEXT DEFAULT '{}',
                    search_params TEXT DEFAULT '{}',
                    max_pages INTEGER DEFAULT 0,
                    progress_current INTEGER DEFAULT 0,
                    progress_total INTEGER DEFAULT 0,
                    estimated_cost_usd REAL DEFAULT 0,
                    cancel_requested INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT '',
                    completed_at TEXT DEFAULT '',
                    min_record_score REAL DEFAULT 0.35,
                    acquisition_mode TEXT DEFAULT 'standard',
                    search_params_json TEXT DEFAULT '{}',
                    location TEXT DEFAULT '',
                    preferred_domain TEXT DEFAULT '',
                    source_policy TEXT DEFAULT 'all_sources',
                    max_per_domain INTEGER DEFAULT 4,
                    origin_location TEXT DEFAULT '',
                    max_distance_km REAL DEFAULT NULL,
                    pagination INTEGER DEFAULT 0,
                    deduplicate INTEGER DEFAULT 1,
                    deduplicate_field TEXT DEFAULT '',
                    started_at TEXT DEFAULT '',
                    results_on_disk INTEGER DEFAULT 0,
                    results_file_path TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recycle_bin (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'manual',
                    topic TEXT DEFAULT '',
                    intent TEXT DEFAULT '',
                    urls TEXT NOT NULL DEFAULT '[]',
                    schema_fields TEXT NOT NULL DEFAULT '[]',
                    filters TEXT DEFAULT '[]',
                    results TEXT DEFAULT '[]',
                    logs TEXT DEFAULT '[]',
                    total_records INTEGER DEFAULT 0,
                    filtered_records INTEGER DEFAULT 0,
                    total_llm_calls INTEGER DEFAULT 0,
                    error TEXT DEFAULT '',
                    warnings TEXT DEFAULT '',
                    quality_report TEXT DEFAULT '{}',
                    analysis TEXT DEFAULT '',
                    discovered_urls TEXT DEFAULT '[]',
                    selectors_map TEXT DEFAULT '{}',
                    search_params TEXT DEFAULT '{}',
                    max_pages INTEGER DEFAULT 0,
                    progress_current INTEGER DEFAULT 0,
                    progress_total INTEGER DEFAULT 0,
                    estimated_cost_usd REAL DEFAULT 0,
                    cancel_requested INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT '',
                    completed_at TEXT DEFAULT '',
                    deleted_at TEXT DEFAULT '',
                    min_record_score REAL DEFAULT 0.35,
                    acquisition_mode TEXT DEFAULT 'standard',
                    search_params_json TEXT DEFAULT '{}',
                    location TEXT DEFAULT '',
                    preferred_domain TEXT DEFAULT '',
                    source_policy TEXT DEFAULT 'all_sources',
                    max_per_domain INTEGER DEFAULT 4,
                    origin_location TEXT DEFAULT '',
                    max_distance_km REAL DEFAULT NULL,
                    pagination INTEGER DEFAULT 0,
                    deduplicate INTEGER DEFAULT 1,
                    deduplicate_field TEXT DEFAULT '',
                    started_at TEXT DEFAULT '',
                    results_on_disk INTEGER DEFAULT 0,
                    results_file_path TEXT DEFAULT ''
                )
            """)
            current = 1

        if current < 2:
            # Preserve existing recycle_bin data dynamically during migration
            try:
                # 1. Identify existing columns of the old recycle_bin table
                cursor = conn.execute("PRAGMA table_info(recycle_bin)")
                existing_cols = [r["name"] for r in cursor.fetchall()]
                # 2. Fetch all existing records and convert each sqlite3.Row to
                # a dict immediately
                existing = [dict(row) for row in conn.execute("SELECT * FROM recycle_bin").fetchall()]
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                existing_cols = []
                existing = []

            conn.execute("DROP TABLE IF EXISTS recycle_bin")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recycle_bin (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'manual',
                    topic TEXT DEFAULT '',
                    intent TEXT DEFAULT '',
                    urls TEXT NOT NULL DEFAULT '[]',
                    schema_fields TEXT NOT NULL DEFAULT '[]',
                    filters TEXT DEFAULT '[]',
                    results TEXT DEFAULT '[]',
                    logs TEXT DEFAULT '[]',
                    total_records INTEGER DEFAULT 0,
                    filtered_records INTEGER DEFAULT 0,
                    total_llm_calls INTEGER DEFAULT 0,
                    error TEXT DEFAULT '',
                    warnings TEXT DEFAULT '',
                    quality_report TEXT DEFAULT '{}',
                    analysis TEXT DEFAULT '',
                    discovered_urls TEXT DEFAULT '[]',
                    selectors_map TEXT DEFAULT '{}',
                    search_params TEXT DEFAULT '{}',
                    max_pages INTEGER DEFAULT 0,
                    progress_current INTEGER DEFAULT 0,
                    progress_total INTEGER DEFAULT 0,
                    estimated_cost_usd REAL DEFAULT 0,
                    cancel_requested INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT '',
                    completed_at TEXT DEFAULT '',
                    deleted_at TEXT DEFAULT '',
                    min_record_score REAL DEFAULT 0.35,
                    acquisition_mode TEXT DEFAULT 'standard',
                    search_params_json TEXT DEFAULT '{}',
                    location TEXT DEFAULT '',
                    preferred_domain TEXT DEFAULT '',
                    source_policy TEXT DEFAULT 'all_sources',
                    max_per_domain INTEGER DEFAULT 4,
                    origin_location TEXT DEFAULT '',
                    max_distance_km REAL DEFAULT NULL,
                    pagination INTEGER DEFAULT 0,
                    deduplicate INTEGER DEFAULT 1,
                    deduplicate_field TEXT DEFAULT '',
                    started_at TEXT DEFAULT '',
                    results_on_disk INTEGER DEFAULT 0,
                    results_file_path TEXT DEFAULT ''
                )
            """)

            if existing and existing_cols:
                # 3. Identify new columns of the recreated recycle_bin table
                cursor = conn.execute("PRAGMA table_info(recycle_bin)")
                new_cols = [r["name"] for r in cursor.fetchall()]
                # 4. Filter for overlapping columns
                overlapping_cols = [col for col in existing_cols if col in new_cols]
                if overlapping_cols:
                    cols_str = ", ".join(overlapping_cols)
                    placeholders = ", ".join("?" for _ in overlapping_cols)
                    for r in existing:
                        vals = [r.get(col) for col in overlapping_cols]
                        conn.execute(f"INSERT OR IGNORE INTO recycle_bin ({cols_str}) VALUES ({placeholders})", vals)  # noqa: RUF100, S608
            current = 2

        if current < 3:
            # Dynamically add any missing columns in both tables to prevent
            # data-loss or crashes in existing databases
            for table_name in ["jobs", "recycle_bin"]:
                cursor = conn.execute(f"PRAGMA table_info({table_name})")
                v3_cols: set[str] = {r["name"] for r in cursor.fetchall()}
                new_fields = {
                    "location": "TEXT DEFAULT ''",
                    "preferred_domain": "TEXT DEFAULT ''",
                    "source_policy": "TEXT DEFAULT 'all_sources'",
                    "max_per_domain": "INTEGER DEFAULT 4",
                    "origin_location": "TEXT DEFAULT ''",
                    "max_distance_km": "REAL DEFAULT NULL",
                    "pagination": "INTEGER DEFAULT 0",
                    "deduplicate": "INTEGER DEFAULT 1",
                    "deduplicate_field": "TEXT DEFAULT ''",
                    "started_at": "TEXT DEFAULT ''",
                    "results_on_disk": "INTEGER DEFAULT 0",
                    "results_file_path": "TEXT DEFAULT ''",
                }
                for col_name, col_def in new_fields.items():
                    if col_name not in v3_cols:
                        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")
            current = 3

        if current < 4:
            # v4: split the heavy per-job payloads out of the main
            # ``jobs`` row. ``job_results`` and ``job_events`` are
            # populated by dual-write from ``save_single`` / ``save_state``
            # and remain the source of truth for new endpoints that
            # only need results or logs (e.g. ``/api/jobs/{id}/events``).
            # The legacy JSON columns in ``jobs`` are preserved for
            # back-compat with the single-row reader.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_results (
                    job_id TEXT NOT NULL,
                    result_index INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (job_id, result_index)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL DEFAULT '',
                    level TEXT NOT NULL DEFAULT 'info',
                    message TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id, event_id)",
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_results_job_id ON job_results(job_id)",
            )
            # v4.1 (still in the v4 migration window): idempotency-key
            # tracking. A client that retries a ``POST /api/jobs`` with
            # the same ``Idempotency-Key`` header receives the
            # originally-created job_id instead of a duplicate. The
            # table is additive; older deployments ignore it.
            #
            # The ``job_id`` column is intentionally NOT a foreign key
            # because we want the idempotency record to survive even
            # after the underlying job is hard-deleted (otherwise a
            # retry of a deleted job would 404 even though the
            # client thought it was the same logical request).
            conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idem_key TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_idempotency_keys_created_at ON idempotency_keys(created_at)",
            )
            current = 4

        if current < 5:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS worker_heartbeats (
                    worker_id TEXT PRIMARY KEY,
                    last_heartbeat TEXT NOT NULL,
                    hostname TEXT NOT NULL DEFAULT '',
                    pid INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL DEFAULT ''
                )
            """)
            current = 5

        if current < 6:
            # v6: make worker_heartbeats primary key composite (worker_id, pid)
            # so two workers on the same host (same resolved worker_id) do
            # not overwrite each other's heartbeat. The v5 schema used
            # ``worker_id TEXT PRIMARY KEY`` which silently lost one
            # worker's row when a second started on the same host.
            # SQLite has limited ALTER TABLE support; we rebuild the
            # table by renaming, creating, copying (with deduplication
            # by last_heartbeat), and dropping the backup.
            #
            # Safety: each DDL statement is its own implicit transaction
            # in SQLite, so a bare try/except rollback would only undo
            # the INSERT...SELECT (DML). If the INSERT fails we
            # explicitly DROP the half-built v6 table and RENAME the
            # v5 backup back so the connection is left in the v5
            # state — not the broken intermediate state.
            conn.execute("ALTER TABLE worker_heartbeats RENAME TO worker_heartbeats_v5_backup")
            conn.execute("""
                CREATE TABLE worker_heartbeats (
                    worker_id TEXT NOT NULL,
                    last_heartbeat TEXT NOT NULL,
                    hostname TEXT NOT NULL DEFAULT '',
                    pid INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (worker_id, pid)
                )
            """)
            # SQLite's INSERT...SELECT supports GROUP BY but not DISTINCT ON
            # (Postgres). We pick the most recent heartbeat per (worker_id,
            # pid) via an aggregate.
            try:
                conn.execute(
                    """
                    INSERT INTO worker_heartbeats
                        (worker_id, last_heartbeat, hostname, pid, started_at)
                    SELECT worker_id, last_heartbeat, hostname, pid, started_at
                    FROM (
                        SELECT
                            worker_id, last_heartbeat, hostname, pid, started_at,
                            ROW_NUMBER() OVER (
                                PARTITION BY worker_id, pid
                                ORDER BY last_heartbeat DESC
                            ) AS rn
                        FROM worker_heartbeats_v5_backup
                    ) latest
                    WHERE rn = 1
                    """,
                )
            except Exception:
                # Roll back to the v5 state: drop the half-built v6
                # table and rename the backup back to the original
                # name. Without this, the next call to ensure_schema
                # would see ``worker_heartbeats_v5_backup`` (no
                # current row) and try to re-run the migration,
                # re-raising the same error.
                conn.execute("DROP TABLE worker_heartbeats")
                conn.execute("ALTER TABLE worker_heartbeats_v5_backup RENAME TO worker_heartbeats")
                raise
            conn.execute("DROP TABLE worker_heartbeats_v5_backup")
            current = 6

        if current < 7:
            # v7: add created_by column for data isolation / multi-tenancy
            for table_name in ["jobs", "recycle_bin"]:
                cursor = conn.execute(f"PRAGMA table_info({table_name})")
                v7_cols: set[str] = {r["name"] for r in cursor.fetchall()}
                if "created_by" not in v7_cols:
                    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN created_by TEXT DEFAULT ''")
            current = 7

        if current < 8:
            # v8: SaaS identity columns for P0-SAAS-001. Persistent API
            # keys (issued by app.saas.ApiKeyService) bind jobs to an
            # org and a project; the legacy ``created_by`` fingerprint
            # remains for env-backed API keys. The index is conditional
            # on the table having the column to keep this safe to run
            # on partially-migrated dev databases.
            for table_name in ["jobs", "recycle_bin"]:
                cursor = conn.execute(f"PRAGMA table_info({table_name})")
                v8_cols: set[str] = {r["name"] for r in cursor.fetchall()}
                if "org_id" not in v8_cols:
                    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN org_id TEXT DEFAULT ''")
                if "project_id" not in v8_cols:
                    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN project_id TEXT DEFAULT ''")
            current = 8

        if current < 9:
            # v9: workflow persistence (Prompt 9 — CAND-P1-WORKFLOW-STORAGE-001).
            # Workflows were previously stored in-memory with best-effort JSON
            # file backup. This table provides durable, transactional persistence
            # with owner/org/project isolation matching the jobs table.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    description TEXT DEFAULT '',
                    user_id TEXT DEFAULT '',
                    org_id TEXT DEFAULT '',
                    project_id TEXT DEFAULT '',
                    mode TEXT DEFAULT 'workflow_replay',
                    domain TEXT DEFAULT '',
                    start_url TEXT DEFAULT '',
                    original_url TEXT DEFAULT '',
                    search_params TEXT DEFAULT '{}',
                    steps TEXT DEFAULT '[]',
                    extraction_schema TEXT DEFAULT '[]',
                    pagination_config TEXT DEFAULT '{}',
                    auth_profile_id TEXT DEFAULT NULL,
                    status TEXT DEFAULT 'draft',
                    version INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT '',
                    updated_at TEXT DEFAULT '',
                    last_run_at TEXT DEFAULT '',
                    last_success_at TEXT DEFAULT '',
                    last_failure_reason TEXT DEFAULT '',
                    last_run_job_id TEXT DEFAULT '',
                    total_runs INTEGER DEFAULT 0
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_user_id ON workflows(user_id)",
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_org_id ON workflows(org_id)",
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status)",
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_project_id ON workflows(project_id)",
            )
            current = 9

        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (current,))
        conn.commit()
        logger.info("SQLite schema migrated to version %d", current)

    # ── Hot-path indexes (run unconditionally for existing v4+ databases) ──
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at)",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_recycle_bin_created_at ON recycle_bin(created_at)",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_created_by ON jobs(created_by)",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_org_id ON jobs(org_id)",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id)",
    )


def load_state(recover_in_progress: bool = True) -> tuple[dict[str, Job], dict[str, Job], dict | None]:
    """Load jobs and recycle bin from SQLite.

    Args:
        recover_in_progress: Mark pending/running jobs failed during startup
            recovery. Set False for normal worker/API reads.

    """
    with _DB_LOCK:
        conn = _get_connection()
        try:
            _maybe_migrate_from_json(conn)

            jobs_store: dict[str, Job] = {}
            for row in conn.execute("SELECT * FROM jobs").fetchall():
                job = _row_to_job(dict(row))
                if job:
                    jobs_store[job.id] = job

            recycle_bin_store: dict[str, Job] = {}
            for row in conn.execute("SELECT * FROM recycle_bin").fetchall():
                job = _row_to_job(dict(row))
                if job:
                    recycle_bin_store[job.id] = job

            if recover_in_progress:
                dirty_recovery = False
                for job in jobs_store.values():
                    if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
                        job.status = JobStatus.FAILED
                        job.error = "Recovered after restart while still in progress."
                        job.completed_at = datetime.datetime.now(datetime.UTC).isoformat()
                        job.cancel_requested = False

                        row = _job_to_row(job)
                        columns = ", ".join(row.keys())
                        placeholders = ", ".join("?" for _ in row)
                        values = list(row.values())
                        conn.execute(
                            f"INSERT OR REPLACE INTO jobs ({columns}) VALUES ({placeholders})",  # noqa: RUF100, S608
                            values,
                        )
                        dirty_recovery = True

                if dirty_recovery:
                    conn.commit()

            world_state_data = None
            try:
                ws_path = _get_db_path().parent / "world_state.json"
                if ws_path.exists():
                    world_state_data = json.loads(ws_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

            return jobs_store, recycle_bin_store, world_state_data
        finally:
            conn.close()


def save_state(jobs_store: dict[str, Job], recycle_bin_store: dict[str, Job], prune_missing: bool = False) -> None:
    """Persist all jobs and recycle bin to SQLite transactionally.

    Args:
        jobs_store: Current in-memory jobs dict.
        recycle_bin_store: Current in-memory recycle bin dict.
        prune_missing: If True, delete rows from the DB that are not present
            in ``jobs_store`` / ``recycle_bin_store`` *before* upserting.
            Default False — prevents accidental data loss when the in-memory
            snapshot differs from the persistent store (e.g. multi-process).
            Only set True when a complete state replacement is explicitly desired.

    """
    path = _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with _DB_LOCK:
        conn = _get_connection()
        try:
            if prune_missing:
                conn.execute("DELETE FROM jobs")
                conn.execute("DELETE FROM job_results")
                conn.execute("DELETE FROM job_events")

            for job in jobs_store.values():
                row = _job_to_row(job)
                columns = ", ".join(row.keys())
                placeholders = ", ".join("?" for _ in row)
                conn.execute(
                    f"INSERT OR REPLACE INTO jobs ({columns}) VALUES ({placeholders})",  # noqa: RUF100, S608
                    list(row.values()),
                )
                _sync_job_results(conn, job.id, job.results)
                _sync_job_events(conn, job.id, job.logs)

            if prune_missing:
                conn.execute("DELETE FROM recycle_bin")

            for job in recycle_bin_store.values():
                row = _job_to_row(job)
                columns = ", ".join(row.keys())
                placeholders = ", ".join("?" for _ in row)
                conn.execute(
                    f"INSERT OR REPLACE INTO recycle_bin ({columns}) VALUES ({placeholders})",  # noqa: RUF100, S608
                    list(row.values()),
                )
                _sync_job_results(conn, job.id, job.results)
                _sync_job_events(conn, job.id, job.logs)

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def persist_state_single(job: Job) -> None:
    """Persist a single job row (upsert) — used for frequent progress updates.

    Dual-writes the heavy payloads (``results``, ``logs``) into the
    dedicated ``job_results`` and ``job_events`` companion tables so
    that future readers do not have to parse the entire JSON blob in
    the main ``jobs`` row. The legacy JSON columns are still kept
    in sync for back-compat with the existing single-row reader.
    """
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = _job_to_row(job)
            columns = ", ".join(row.keys())
            placeholders = ", ".join("?" for _ in row)
            values = list(row.values())
            conn.execute(
                f"INSERT OR REPLACE INTO jobs ({columns}) VALUES ({placeholders})",  # noqa: RUF100, S608
                values,
            )
            _sync_job_results(conn, job.id, job.results)
            _sync_job_events(conn, job.id, job.logs)
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("Failed to persist single job %s", job.id)
            raise
        finally:
            conn.close()


def _sync_job_results(
    conn: sqlite3.Connection,
    job_id: str,
    results: list[Any],
) -> None:
    """Replace the ``job_results`` rows for ``job_id`` with ``results``.

    Dual-write helper used by ``persist_state_single`` and ``save_state``.
    """
    conn.execute("DELETE FROM job_results WHERE job_id = ?", (job_id,))
    for idx, payload in enumerate(results):
        try:
            encoded = json.dumps(payload, default=str)
        except (TypeError, ValueError):
            encoded = json.dumps(str(payload))
        conn.execute(
            "INSERT INTO job_results (job_id, result_index, payload) VALUES (?, ?, ?)",
            (job_id, idx, encoded),
        )


def _sync_job_events(
    conn: sqlite3.Connection,
    job_id: str,
    logs,
) -> None:
    """Replace the ``job_events`` rows for ``job_id`` with ``logs``.

    ``logs`` may be a list of Pydantic ``LogEntry`` objects or a list
    of dicts with ``timestamp`` / ``level`` / ``message`` keys.
    """
    conn.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
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
        conn.execute(
            "INSERT INTO job_events (job_id, timestamp, level, message) VALUES (?, ?, ?, ?)",
            (
                job_id,
                str(entry_dict.get("timestamp") or ""),
                str(entry_dict.get("level") or "info"),
                str(entry_dict.get("message") or ""),
            ),
        )


def flush_state() -> None:
    """Ensure all pending writes are flushed (no-op for SQLite — writes are synchronous)."""


def shutdown() -> None:
    """Clean shutdown — ensure all connections are closed."""
    logger.info("SQLite job store shutdown complete")


# ─── Companion-table readers (v4 schema) ─────────────────────────────────


def read_job_results(job_id: str) -> list[dict]:
    """Read a job's results from the dedicated ``job_results`` table.

    Returns a list of dicts in the original ``results`` order. If the
    companion table is empty (e.g. a pre-v4 database that has not
    been backfilled) the returned list is empty — the caller is
    responsible for falling back to the JSON column on the ``jobs``
    row if it needs the legacy view.
    """
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT payload FROM job_results WHERE job_id = ? ORDER BY result_index ASC",
                (job_id,),
            ).fetchall()
        finally:
            conn.close()
    out: list[dict] = []
    for row in rows:
        try:
            out.append(json.loads(row["payload"]))
        except (TypeError, ValueError):
            out.append({"_unparseable": row["payload"]})
    return out


def read_job_results_paginated(job_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """Read a job's results with limit and offset from the dedicated ``job_results`` table."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT payload FROM job_results WHERE job_id = ? ORDER BY result_index ASC LIMIT ? OFFSET ?",
                (job_id, limit, offset),
            ).fetchall()
        finally:
            conn.close()
    out: list[dict] = []
    for row in rows:
        try:
            out.append(json.loads(row["payload"]))
        except (TypeError, ValueError):
            out.append({"_unparseable": row["payload"]})
    return out


def read_job_events(
    job_id: str,
    limit: int = 200,
    offset: int = 0,
    level_prefix: str | None = None,
) -> list[dict]:
    """Read a job's lifecycle events from the dedicated ``job_events`` table.

    Returns ``[{timestamp, level, message}, ...]`` ordered by ``event_id``
    ascending (insertion order). Supports keyset pagination via
    ``offset`` and optional ``level_prefix`` filtering.
    """
    safe_limit = max(1, min(int(limit), 1000))
    safe_offset = max(0, int(offset))
    sql = "SELECT timestamp, level, message FROM job_events WHERE job_id = ?"
    params: list[object] = [job_id]
    if level_prefix:
        sql += " AND LOWER(level) LIKE ?"
        params.append(f"{level_prefix.lower()}%")
    sql += " ORDER BY event_id ASC LIMIT ? OFFSET ?"
    params.extend([safe_limit, safe_offset])
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(sql, tuple(params)).fetchall()
        finally:
            conn.close()
    return [
        {
            "timestamp": row["timestamp"] or "",
            "level": row["level"] or "info",
            "message": row["message"] or "",
        }
        for row in rows
    ]


def count_job_events(job_id: str) -> int:
    """Return the number of events currently stored in ``job_events``."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM job_events WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        finally:
            conn.close()
    return int(row["n"]) if row else 0


def lookup_idempotency_key(idem_key: str) -> str | None:
    """Return the ``job_id`` previously associated with ``idem_key``.

    or ``None`` if the key has never been seen.
    """
    if not idem_key:
        return None
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT job_id FROM idempotency_keys WHERE idem_key = ?",
                (idem_key,),
            ).fetchone()
        finally:
            conn.close()
    return str(row["job_id"]) if row else None


def lookup_idempotency_fingerprint(idem_key: str) -> str | None:
    """Return the ``request_fingerprint`` previously associated with ``idem_key``.

    or ``None`` if the key has never been seen.
    """
    if not idem_key:
        return None
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT request_fingerprint FROM idempotency_keys WHERE idem_key = ?",
                (idem_key,),
            ).fetchone()
        finally:
            conn.close()
    return str(row["request_fingerprint"]) if row else None


def record_idempotency_key(
    idem_key: str,
    job_id: str,
    request_fingerprint: str,
) -> None:
    """Persist an idempotency-key → job_id mapping.

    A repeat ``POST /api/jobs`` with the same ``Idempotency-Key``
    returns the original ``job_id`` rather than creating a duplicate.
    A conflicting ``request_fingerprint`` is ignored (the new request
    wins); a future tightening could reject it instead.
    """
    if not idem_key or not job_id:
        return
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO idempotency_keys
                    (idem_key, job_id, request_fingerprint)
                VALUES (?, ?, ?)
                ON CONFLICT(idem_key) DO UPDATE
                    SET job_id = excluded.job_id,
                        request_fingerprint = excluded.request_fingerprint,
                        created_at = datetime('now')
                """,
                (idem_key, job_id, request_fingerprint),
            )
            conn.commit()
        finally:
            conn.close()


def prune_idempotency_keys(older_than_days: int = 7) -> int:
    """Delete idempotency keys older than ``older_than_days``.

    Returns the number of rows deleted. Operators can call this from a
    scheduled task to keep the table small; the default 7-day window
    is more than enough for a client retry loop.
    """
    if older_than_days <= 0:
        return 0

    with _DB_LOCK:
        conn = _get_connection()
        try:
            cur = conn.execute(
                """
                DELETE FROM idempotency_keys
                WHERE created_at < datetime('now', ?)
                """,
                (f"-{int(older_than_days)} days",),
            )
            deleted = cur.rowcount
            conn.commit()
        finally:
            conn.close()
    return int(deleted)


def get_storage_health() -> dict[str, Any]:
    """Check that SQLite storage is reachable and schema is valid.

    Returns a dict with:
    - ok: True if all checks pass
    - schema_version: current schema version (0 if missing)
    - expected_version: latest schema version
    - error: error message if any check fails
    """
    conn = None
    try:
        conn = _get_connection()
        conn.row_factory = sqlite3.Row
        schema_row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        schema_version = schema_row[0] if schema_row and schema_row[0] is not None else 0
        jobs_ok = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone() is not None
        recycle_ok = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='recycle_bin'").fetchone() is not None
        # v4 companion tables must be present and have a matching row.
        companion_ok = True
        companion_missing: str | None = None
        for companion in ("job_results", "job_events", "idempotency_keys"):
            present = (
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (companion,),
                ).fetchone()
                is not None
            )
            if not present:
                companion_ok = False
                companion_missing = companion
                break
    finally:
        if conn:
            conn.close()

    if schema_version == 0:
        return {
            "ok": False,
            "error": "Schema version table is empty or missing",
            "schema_version": 0,
            "expected_version": _CURRENT_SCHEMA_VERSION,
        }
    if schema_version < _CURRENT_SCHEMA_VERSION:
        return {
            "ok": False,
            "error": f"Schema version {schema_version} is older than expected {_CURRENT_SCHEMA_VERSION}",
            "schema_version": schema_version,
            "expected_version": _CURRENT_SCHEMA_VERSION,
        }
    if not jobs_ok:
        return {
            "ok": False,
            "error": "jobs table is missing",
            "schema_version": schema_version,
            "expected_version": _CURRENT_SCHEMA_VERSION,
        }
    if not recycle_ok:
        return {
            "ok": False,
            "error": "recycle_bin table is missing",
            "schema_version": schema_version,
            "expected_version": _CURRENT_SCHEMA_VERSION,
        }
    if not companion_ok:
        return {
            "ok": False,
            "error": f"{companion_missing} table is missing",
            "schema_version": schema_version,
            "expected_version": _CURRENT_SCHEMA_VERSION,
        }

    return {
        "ok": True,
        "schema_version": schema_version,
        "expected_version": _CURRENT_SCHEMA_VERSION,
    }


def count_jobs_by_status(include_deleted: bool = False) -> dict[str, int]:
    """Return a ``{status_value: count}`` mapping for all jobs.

    This is a single ``GROUP BY status`` query and is O(distinct statuses)
    rather than O(rows), so it stays cheap even when the store has
    millions of jobs. The previous approach was to call
    ``list_job_summaries(limit=5000)`` and count in Python, but the
    storage layer silently capped the limit to 500, producing a wrong
    count whenever the store held more than 500 jobs.

    Args:
        include_deleted: If True, soft-deleted rows
            (from the recycle_bin table) are included.

    """
    counts: dict[str, int] = {}
    with _DB_LOCK:
        conn = _get_connection()
        try:
            # SQLite stores active jobs in the 'jobs' table (which has no deleted_at column)
            # and soft-deleted jobs in the 'recycle_bin' table.
            rows = conn.execute("SELECT status, COUNT(*) AS cnt FROM jobs GROUP BY status").fetchall()
            for row in rows:
                key = str(row["status"])
                counts[key] = int(row["cnt"])

            if include_deleted:
                rb_rows = conn.execute("SELECT status, COUNT(*) AS cnt FROM recycle_bin GROUP BY status").fetchall()
                for row in rb_rows:
                    key = str(row["status"])
                    counts[key] = counts.get(key, 0) + int(row["cnt"])
        finally:
            conn.close()
    return counts


def get_storage_status() -> dict[str, Any]:
    """Return detailed storage backend status.

    Returns:
        backend: Always "sqlite"
        db_path: Path to the database file
        schema_version: Current schema version
        latest_schema_version: Expected schema version
        job_count: Number of jobs in the jobs table
        recycle_bin_count: Number of jobs in recycle_bin
        wal_mode: Whether WAL journaling is active

    """
    conn = None
    try:
        conn = _get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        schema_version = row[0] if row and row[0] is not None else 0
        job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        recycle_count = conn.execute("SELECT COUNT(*) FROM recycle_bin").fetchone()[0]
        wal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        db_path = _get_db_path()
        return {
            "backend": "sqlite",
            "db_path": str(db_path.name) if hasattr(db_path, "name") else str(db_path).rsplit("/", 1)[-1],
            "schema_version": schema_version,
            "latest_schema_version": _CURRENT_SCHEMA_VERSION,
            "job_count": job_count,
            "recycle_bin_count": recycle_count,
            "wal_mode": wal_mode,
        }
    except Exception as e:
        return {
            "backend": "sqlite",
            "error": str(e),
            "schema_version": 0,
            "latest_schema_version": _CURRENT_SCHEMA_VERSION,
            "job_count": -1,
            "recycle_bin_count": -1,
            "wal_mode": "unknown",
        }
    finally:
        if conn:
            conn.close()


# ─── Worker heartbeat ───────────────────────────────────────────────────


def record_worker_heartbeat(worker_id: str, hostname: str, pid: int) -> None:
    """Record a heartbeat from a worker process.

    Upserts the worker's heartbeat timestamp so the healthcheck
    can verify the worker is alive by checking recency.

    The v5 schema used ``ON CONFLICT(worker_id)`` which silently
    overwrote a co-resident worker's heartbeat on the same host.
    The v6 schema has a composite primary key ``(worker_id, pid)``
    so two workers on the same host can coexist. See the v6
    migration in :func:`_ensure_schema`.
    """
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """INSERT INTO worker_heartbeats
                   (worker_id, last_heartbeat, hostname, pid, started_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(worker_id, pid) DO UPDATE SET
                     last_heartbeat = excluded.last_heartbeat,
                     hostname = excluded.hostname,
                     pid = excluded.pid""",
                (worker_id, now, hostname, pid, now),
            )
            conn.commit()
        finally:
            conn.close()


def get_worker_health(worker_id: str, ttl_seconds: int = 60) -> dict[str, Any]:
    """Return health info for a specific worker.

    Returns a dict with:
    - alive: bool — True if a heartbeat exists and is within ttl_seconds
    - last_heartbeat: str | None
    - hostname: str | None
    - pid: int | None
    - worker_id: str

    When multiple pids share a ``worker_id`` (multiple workers on the
    same host), the freshest heartbeat is returned and the worker is
    reported ``alive=True`` if any of its pids are within the TTL.
    """
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                """SELECT last_heartbeat, hostname, pid
                   FROM worker_heartbeats
                   WHERE worker_id = ?
                   ORDER BY last_heartbeat DESC
                   LIMIT 1""",
                (worker_id,),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return {
            "alive": False,
            "worker_id": worker_id,
            "last_heartbeat": None,
            "hostname": None,
            "pid": None,
        }
    last_heartbeat = row["last_heartbeat"] if row else None
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
        "hostname": row["hostname"] if row else None,
        "pid": row["pid"] if row else None,
    }


def get_all_worker_healths(ttl_seconds: int = 60) -> list[dict]:
    """Return health info for all registered workers."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT worker_id, last_heartbeat, hostname, pid FROM worker_heartbeats",
            ).fetchall()
        except sqlite3.OperationalError:
            # The ``worker_heartbeats`` table may not exist if the
            # database was created without going through the full
            # migration path (e.g. ephemeral test databases). Return
            # an empty list instead of crashing the caller.
            return []
        finally:
            conn.close()
    results: list[dict] = []
    for row in rows:
        wid = row["worker_id"]
        last_hb = row["last_heartbeat"]
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
                "hostname": row["hostname"],
                "pid": row["pid"],
            },
        )
    return results


def reset_job_store_for_tests() -> None:
    """Reset the database path migration cache for tests."""
    _MIGRATIONS_RUN_FOR.clear()
