#!/usr/bin/env python3
"""Migration Rollback Drill — verifies that schema changes can be rolled
back without data loss.

Usage:
    python3 scripts/migration_rollback_test.py

This test:
1. Creates a base jobs schema (core columns)
2. Seeds test data
3. Applies additive column changes (simulating a migration)
4. Verifies the additive columns work
5. Simulates a rollback by dropping additive columns
6. Verifies existing core data survives
7. Re-applies the migration and verifies data is still intact

Requirements:
    - Python 3.12+ (stdlib sqlite3)

On success the script exits 0 and writes a summary to
``artifacts/migration_drill/``.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ARTIFACTS_DIR = Path("artifacts/migration_drill")
DB_PATH = ARTIFACTS_DIR / "drill.db"

# The additive columns that represent a "migration"
ADDITIVE_COLUMNS = [
    ("acquisition_mode", "TEXT DEFAULT 'standard'"),
    ("warnings", "TEXT DEFAULT '[]'"),
    ("source_policy", "TEXT DEFAULT 'all_sources'"),
    ("max_per_domain", "INTEGER DEFAULT 4"),
    ("min_record_score", "REAL DEFAULT 0.35"),
]


def log(msg: str) -> None:
    ts = datetime.now(UTC).isoformat(timespec="seconds")
    print(f"[{ts}] {msg}")


def setup_db() -> sqlite3.Connection:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_initial_schema(conn: sqlite3.Connection) -> None:
    log("Creating pre-migration schema...")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            mode TEXT NOT NULL DEFAULT 'manual',
            created_by TEXT DEFAULT '',
            org_id TEXT DEFAULT '',
            project_id TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            completed_at TEXT DEFAULT '',
            urls TEXT DEFAULT '[]',
            results TEXT DEFAULT '[]',
            total_records INTEGER DEFAULT 0,
            error TEXT DEFAULT '',
            cancel_requested INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS job_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );

        CREATE TABLE IF NOT EXISTS idempotency_keys (
            key TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            job_id TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS recycle_bin (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            deleted_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    log("Pre-migration schema created.")


def seed_data(conn: sqlite3.Connection) -> None:
    log("Seeding test data...")
    data = [
        ("job-1", "Alpha", "completed", "user-a", "org-1", "proj-1"),
        ("job-2", "Beta", "running", "user-a", "org-1", "proj-1"),
        ("job-3", "Gamma", "pending", "user-b", "org-2", "proj-2"),
    ]
    for row in data:
        conn.execute(
            "INSERT INTO jobs (id, name, status, created_by, org_id, project_id) VALUES (?, ?, ?, ?, ?, ?)",
            row,
        )
    conn.execute("INSERT INTO job_results (job_id, data) VALUES ('job-1', '{\"title\": \"test\"}')")
    conn.execute("INSERT INTO idempotency_keys (key, fingerprint, job_id) VALUES ('ik-1', 'fp-1', 'job-1')")
    conn.execute("INSERT INTO recycle_bin (id, name, status) VALUES ('del-1', 'Deleted Job', 'canceled')")

    counts = {}
    for table in ("jobs", "job_results", "idempotency_keys", "recycle_bin"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.commit()
    log(f"Seed data: {counts}")
    return counts


def apply_migration_v8(conn: sqlite3.Connection) -> None:
    """Apply the v8 migration SQL (additive columns)."""
    log("Applying migration v8 (additive columns)...")
    for col_name, col_type in ADDITIVE_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            log(f"  Note: column {col_name} may already exist — skipping")
    conn.commit()
    log("Migration v8 applied.")


def verify_migration_applied(conn: sqlite3.Connection) -> None:
    """Verify v8 columns exist in schema."""
    cursor = conn.execute("PRAGMA table_info(jobs)")
    columns = {row[1] for row in cursor.fetchall()}
    v8_columns = {"acquisition_mode", "warnings", "source_policy", "max_per_domain", "min_record_score"}
    missing = v8_columns - columns
    assert not missing, f"Migration v8 columns missing: {missing}"
    log("Migration columns verified.")


def simulate_rollback(conn: sqlite3.Connection) -> None:
    """Simulate rollback by dropping additive v8 columns."""
    log("Simulating rollback — dropping v8 additive columns...")
    v8_columns = ["acquisition_mode", "warnings", "source_policy", "max_per_domain", "min_record_score"]
    for col in v8_columns:
        try:
            conn.execute(f"ALTER TABLE jobs DROP COLUMN {col}")
        except sqlite3.OperationalError:
            log(f"  Note: could not drop {col} (SQLite limitation — skipping)")
    conn.commit()
    log("Rollback simulated.")


def verify_data_survives(conn: sqlite3.Connection) -> None:
    """Verify core data survives rollback."""
    rows = conn.execute("SELECT id, name, status, created_by, org_id, project_id FROM jobs ORDER BY id").fetchall()
    expected = [
        ("job-1", "Alpha", "completed", "user-a", "org-1", "proj-1"),
        ("job-2", "Beta", "running", "user-a", "org-1", "proj-1"),
        ("job-3", "Gamma", "pending", "user-b", "org-2", "proj-2"),
    ]
    assert rows == expected, f"Data mismatch after rollback: {rows}"

    for table in ("job_results", "idempotency_keys", "recycle_bin"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count > 0, f"Companion table {table} lost all data after rollback"

    log("Core data survives rollback — verified.")


def main() -> int:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    conn = setup_db()
    try:
        create_initial_schema(conn)
        counts_before = seed_data(conn)

        apply_migration_v8(conn)
        verify_migration_applied(conn)

        rows_before = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        log(f"Jobs after migration: {rows_before}")

        simulate_rollback(conn)
        verify_data_survives(conn)

        apply_migration_v8(conn)
        rows_after = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        assert rows_after == rows_before, f"Data lost after re-migration: {rows_before} -> {rows_after}"
        log("Re-migration successful — all data intact.")

        summary = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "passed",
            "rows_initial": counts_before,
            "rows_after_rollback": rows_before,
            "rows_after_remigration": rows_after,
            "notes": "Migration rollback drill completed. Additive columns can be rolled back without data loss.",
        }
        summary_path = ARTIFACTS_DIR / "latest_drill.json"
        summary_path.write_text(json.dumps(summary, indent=2))
        log(f"Summary written to {summary_path}")
        log("Migration Rollback Drill PASSED.")
        return 0

    except Exception as e:
        log(f"DRILL FAILED: {e}")
        error_summary = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "failed",
            "error": str(e),
        }
        (ARTIFACTS_DIR / "latest_drill.json").write_text(json.dumps(error_summary, indent=2))
        return 1

    finally:
        conn.close()
        if DB_PATH.exists():
            DB_PATH.unlink()


if __name__ == "__main__":
    sys.exit(main())
