"""Dialect-specific database migrations for SQLite and Postgres.

Extracted from ``job_store.py`` and ``postgres_repository_base.py``
to isolate schema management and DDL operations.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.storage_interface import _JOBS_COLUMNS_SQL
from app.storage_mapper import job_to_row, row_to_job

logger = logging.getLogger(__name__)

SQLITE_SCHEMA_VERSION = 9
POSTGRES_SCHEMA_VERSION = 8

# ───────────────────────────────────────────────────────────────────────
# SQLite migrations
# ───────────────────────────────────────────────────────────────────────


def _job_from_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw JSON job dict to the format expected by row_to_job."""
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


def maybe_migrate_from_json(conn: sqlite3.Connection, db_path: Path) -> None:
    """One-time migration: import existing JSON state into SQLite."""
    json_path = db_path.with_suffix(".json")
    if not json_path.exists():
        return
    row = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
    if row and row[0] > 0:
        return  # Already have data, skip migration
    try:
        data = json.loads(json_path.read_text())
        conn.execute("BEGIN IMMEDIATE")
        try:
            for raw in data.get("jobs", []):
                job = row_to_job(_job_from_raw(raw))
                if job:
                    row_data = job_to_row(job)
                    cols = ", ".join(row_data.keys())
                    ph = ", ".join("?" for _ in row_data)
                    conn.execute(
                        f"INSERT OR IGNORE INTO jobs ({cols}) VALUES ({ph})",
                        list(row_data.values()),
                    )
            for raw in data.get("recycle_bin", []):
                job = row_to_job(_job_from_raw(raw))
                if job:
                    row_data = job_to_row(job)
                    cols = ", ".join(row_data.keys())
                    ph = ", ".join("?" for _ in row_data)
                    conn.execute(
                        f"INSERT OR IGNORE INTO recycle_bin ({cols}) VALUES ({ph})",
                        list(row_data.values()),
                    )
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


def run_sqlite_migrations(conn: sqlite3.Connection) -> None:
    """Run SQLite database migrations."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        )
    """)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] if row and row[0] is not None else 0

    if current < SQLITE_SCHEMA_VERSION:
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
            try:
                cursor = conn.execute("PRAGMA table_info(recycle_bin)")
                existing_cols = [r["name"] for r in cursor.fetchall()]
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
                cursor = conn.execute("PRAGMA table_info(recycle_bin)")
                new_cols = [r["name"] for r in cursor.fetchall()]
                overlapping_cols = [col for col in existing_cols if col in new_cols]
                if overlapping_cols:
                    cols_str = ", ".join(overlapping_cols)
                    placeholders = ", ".join("?" for _ in overlapping_cols)
                    for r in existing:
                        vals = [r.get(col) for col in overlapping_cols]
                        conn.execute(
                            f"INSERT OR IGNORE INTO recycle_bin ({cols_str}) VALUES ({placeholders})",
                            vals,
                        )
            current = 2

        if current < 3:
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id, event_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_job_results_job_id ON job_results(job_id)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idem_key TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_idempotency_keys_created_at ON idempotency_keys(created_at)")
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
                conn.execute("DROP TABLE worker_heartbeats")
                conn.execute("ALTER TABLE worker_heartbeats_v5_backup RENAME TO worker_heartbeats")
                raise
            conn.execute("DROP TABLE worker_heartbeats_v5_backup")
            current = 6

        if current < 7:
            for table_name in ["jobs", "recycle_bin"]:
                cursor = conn.execute(f"PRAGMA table_info({table_name})")
                v7_cols: set[str] = {r["name"] for r in cursor.fetchall()}
                if "created_by" not in v7_cols:
                    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN created_by TEXT DEFAULT ''")
            current = 7

        if current < 8:
            for table_name in ["jobs", "recycle_bin"]:
                cursor = conn.execute(f"PRAGMA table_info({table_name})")
                v8_cols: set[str] = {r["name"] for r in cursor.fetchall()}
                if "org_id" not in v8_cols:
                    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN org_id TEXT DEFAULT ''")
                if "project_id" not in v8_cols:
                    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN project_id TEXT DEFAULT ''")
            current = 8

        if current < 9:
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_workflows_user_id ON workflows(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_workflows_org_id ON workflows(org_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_workflows_project_id ON workflows(project_id)")
            current = 9

        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (current,))
        conn.commit()
        logger.info("SQLite schema migrated to version %d", current)

    # Hot-path indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recycle_bin_created_at ON recycle_bin(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_by ON jobs(created_by)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_org_id ON jobs(org_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id)")


# ───────────────────────────────────────────────────────────────────────
# Postgres migrations
# ───────────────────────────────────────────────────────────────────────


def columns_sql() -> list[str]:
    """Return canonical column definitions."""
    return list(_JOBS_COLUMNS_SQL)


def build_create_jobs_sql() -> str:
    """Build the CREATE TABLE statement for Postgres jobs."""
    cols = ",\n        ".join(columns_sql())
    return (
        "CREATE TABLE IF NOT EXISTS jobs ("
        "\n        id TEXT PRIMARY KEY,"
        "\n        name TEXT NOT NULL,"
        "\n        status TEXT NOT NULL DEFAULT 'pending',"
        f"\n        {cols}"
        "\n    )"
    )


def build_create_recycle_bin_sql() -> str:
    """Build the CREATE TABLE statement for Postgres recycle_bin."""
    cols = ",\n        ".join(columns_sql())
    return (
        "CREATE TABLE IF NOT EXISTS recycle_bin ("
        "\n        id TEXT PRIMARY KEY,"
        "\n        name TEXT NOT NULL,"
        "\n        status TEXT NOT NULL DEFAULT 'pending',"
        f"\n        {cols}"
        "\n    )"
    )


def ensure_required_tables(conn, execute_fn: Callable) -> None:
    """Create Postgres tables and default columns/indexes if missing."""
    execute_fn(conn, build_create_jobs_sql())
    for col_def in columns_sql():
        try:
            execute_fn(conn, f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {col_def}")
        except Exception:
            logger.debug("ALTER TABLE jobs ADD COLUMN %s failed (ignored)", col_def)
    execute_fn(conn, build_create_recycle_bin_sql())
    for col_def in columns_sql():
        try:
            execute_fn(conn, f"ALTER TABLE recycle_bin ADD COLUMN IF NOT EXISTS {col_def}")
        except Exception:
            logger.debug("ALTER TABLE recycle_bin ADD COLUMN %s failed (ignored)", col_def)

    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_created_by ON jobs(created_by)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_org_id ON jobs(org_id)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_recycle_bin_created_at ON recycle_bin(created_at DESC)",
    ]:
        try:
            execute_fn(conn, idx_sql)
        except Exception:
            logger.debug("CREATE INDEX failed (ignored): %s", idx_sql)


def migrate_worker_heartbeats_v6(conn, execute_fn: Callable, fetch_one_fn: Callable) -> None:
    """Schema v6: composite primary key on worker_heartbeats."""
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
            logger.exception("worker_heartbeats v5→v6 migration failed")
            raise
        else:
            cur.execute("RELEASE SAVEPOINT migrate_wh_v6")


def run_postgres_migrations(conn, execute_fn: Callable, fetch_one_fn: Callable) -> None:
    """Run schema migrations for Postgres."""
    execute_fn(
        conn,
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)",
    )
    row = fetch_one_fn(conn, "SELECT MAX(version) AS version FROM schema_version")
    current = row["version"] if row and row.get("version") is not None else 0

    ensure_required_tables(conn, execute_fn)

    if current < POSTGRES_SCHEMA_VERSION:
        if current < 3:
            execute_fn(
                conn,
                """CREATE TABLE IF NOT EXISTS world_state (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )""",
            )

        if current < 4:
            execute_fn(
                conn,
                """CREATE TABLE IF NOT EXISTS job_results (
                    job_id TEXT NOT NULL,
                    result_index INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (job_id, result_index),
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                )""",
            )
            execute_fn(
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
            execute_fn(conn, "CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id, event_id)")
            execute_fn(conn, "CREATE INDEX IF NOT EXISTS idx_job_results_job_id ON job_results(job_id)")
            execute_fn(
                conn,
                """CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idem_key TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )""",
            )
            execute_fn(conn, "CREATE INDEX IF NOT EXISTS idx_idempotency_keys_created_at ON idempotency_keys(created_at)")

        if current < 5:
            execute_fn(
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
            migrate_worker_heartbeats_v6(conn, execute_fn, fetch_one_fn)

        if current < 7:
            for col in ["org_id", "project_id"]:
                try:
                    execute_fn(conn, f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {col} TEXT DEFAULT ''")
                except Exception:
                    logger.debug("ALTER TABLE jobs ADD COLUMN %s failed", col)
                try:
                    execute_fn(conn, f"ALTER TABLE recycle_bin ADD COLUMN IF NOT EXISTS {col} TEXT DEFAULT ''")
                except Exception:
                    logger.debug("ALTER TABLE recycle_bin ADD COLUMN %s failed", col)

        if current < 8:
            execute_fn(
                conn,
                """CREATE TABLE IF NOT EXISTS workflows (
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
                )""",
            )
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_workflows_user_id ON workflows(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_workflows_org_id ON workflows(org_id)",
                "CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status)",
                "CREATE INDEX IF NOT EXISTS idx_workflows_project_id ON workflows(project_id)",
            ]:
                try:
                    execute_fn(conn, idx_sql)
                except Exception:
                    logger.debug("CREATE INDEX failed: %s", idx_sql)

        execute_fn(conn, "DELETE FROM schema_version")
        execute_fn(conn, "INSERT INTO schema_version (version) VALUES (%s)", (POSTGRES_SCHEMA_VERSION,))
        logger.info("Postgres schema migrated to version %d", POSTGRES_SCHEMA_VERSION)
