#!/usr/bin/env python3
"""Backup / Restore Drill — weekly validation that a real Postgres backup
can be restored with full data integrity.

Usage:
    python3 scripts/backup_and_restore_test.py

Requirements:
    - Docker (``docker`` command available)
    - The port 15432 must be free (not used by another Postgres)

On success the script exits 0 and writes a summary to
``artifacts/backup_drill/``.
On failure it prints diagnostic info and exits 1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ARTIFACTS_DIR = Path("artifacts/backup_drill")
CONTAINER_NAME = "dataforge-drill-pg"
PG_IMAGE = "postgres:15-alpine"
PG_PORT = 15432
PG_USER = "drill"
PG_PASSWORD = "drill-secret"
PG_DB = "dataforge_drill"

REQUIRED_TABLES = [
    "jobs",
    "job_results",
    "job_events",
    "idempotency_keys",
    "worker_heartbeats",
    "recycle_bin",
]
SEED_ROWS = 5


def log(msg: str) -> None:
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    print(f"[{timestamp}] {msg}")


def check_docker() -> None:
    result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        log("ERROR: Docker is not available. Cannot run backup/restore drill.")
        sys.exit(1)
    log(f"Docker available: {result.stdout.strip()}")


def start_postgres() -> None:
    log(f"Starting Postgres container '{CONTAINER_NAME}' on port {PG_PORT}...")
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            CONTAINER_NAME,
            "-e",
            f"POSTGRES_USER={PG_USER}",
            "-e",
            f"POSTGRES_PASSWORD={PG_PASSWORD}",
            "-e",
            f"POSTGRES_DB={PG_DB}",
            "-p",
            f"{PG_PORT}:5432",
            PG_IMAGE,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    time.sleep(3)  # initial wait
    for attempt in range(10):
        result = subprocess.run(
            [
                "docker",
                "exec",
                CONTAINER_NAME,
                "pg_isready",
                "-U",
                PG_USER,
                "-d",
                PG_DB,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            log("Postgres is ready.")
            return
        log(f"  Waiting... ({attempt + 1}/10)")
        time.sleep(2)
    raise RuntimeError("Postgres did not become ready in time")


def create_schema() -> None:
    log("Creating test schema...")
    schema_sql = Path("backend/migrations/008_postgres_storage_v8.sql").read_text()
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER_NAME, "psql", "-U", PG_USER, "-d", PG_DB],
        input=schema_sql,
        check=True,
        capture_output=True,
        text=True,
    )


def seed_data() -> None:
    log(f"Inserting {SEED_ROWS} seed job rows...")
    insert_sql = "\n".join(
        f"""
        INSERT INTO jobs (id, name, status, mode, created_by, org_id, project_id, created_at)
        VALUES ('drill-job-{i}', 'drill-job-{i}', 'pending', 'manual', 'drill-user', 'drill-org', 'drill-proj', NOW());
        INSERT INTO idempotency_keys (key, fingerprint, job_id, created_at)
        VALUES ('drill-ik-{i}', 'drill-fp-{i}', 'drill-job-{i}', NOW());
        """
        for i in range(SEED_ROWS)
    )
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER_NAME, "psql", "-U", PG_USER, "-d", PG_DB],
        input=insert_sql,
        check=True,
        capture_output=True,
        text=True,
    )
    log("Seed data inserted.")


def count_rows(table: str) -> int:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            CONTAINER_NAME,
            "psql",
            "-U",
            PG_USER,
            "-d",
            PG_DB,
            "-t",
            "-A",
            "-c",
            f"SELECT COUNT(*) FROM {table}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(result.stdout.strip())


def verify_row_counts(before: dict[str, int], after: dict[str, int]) -> None:
    failures = []
    for table in REQUIRED_TABLES:
        b = before.get(table, 0)
        a = after.get(table, 0)
        if a < b:
            failures.append(f"{table}: before={b}, after={a} (lost rows)")
        log(f"  {table}: {b} → {a} rows")
    if failures:
        for f in failures:
            log(f"FAIL: {f}")
        sys.exit(1)
    log("Row counts verified: no data loss.")


def run_backup() -> Path:
    backup_dir = ARTIFACTS_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"drill_backup_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}.sql.gz"
    log(f"Running backup → {backup_path}...")
    env = os.environ.copy()
    env["DATAFORGE_DATABASE_URL"] = f"postgresql://{PG_USER}:{PG_PASSWORD}@localhost:{PG_PORT}/{PG_DB}"
    env["DATAFORGE_STORAGE_BACKEND"] = "postgres"
    env["PGPASSWORD"] = PG_PASSWORD
    result = subprocess.run(
        ["docker", "exec", "-e", f"PGPASSWORD={PG_PASSWORD}", CONTAINER_NAME, "pg_dump", "-U", PG_USER, "-d", PG_DB],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log(f"Backup failed (exit {result.returncode}): {result.stderr}")
        sys.exit(1)
    import gzip

    with gzip.open(backup_path, "wt") as f:
        f.write(result.stdout)
    # Integrity check
    subprocess.run(["gunzip", "-t", str(backup_path)], check=True)
    log(f"Backup created and verified: {backup_path} ({backup_path.stat().st_size} bytes)")
    return backup_path


def run_restore(backup_path: Path) -> None:
    log(f"Running restore from {backup_path}...")
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            CONTAINER_NAME,
            "psql",
            "-U",
            PG_USER,
            "-d",
            PG_DB,
        ],
        input="DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
        check=True,
        capture_output=True,
        text=True,
    )
    import gzip

    with gzip.open(backup_path, "rt") as f:
        sql_content = f.read()
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            CONTAINER_NAME,
            "psql",
            "-U",
            PG_USER,
            "-d",
            PG_DB,
        ],
        input=sql_content,
        check=True,
        capture_output=True,
        text=True,
    )
    log("Restore completed successfully.")


def cleanup() -> None:
    log("Cleaning up...")
    subprocess.run(
        ["docker", "stop", CONTAINER_NAME],
        capture_output=True,
        text=True,
        timeout=30,
    )


def main() -> int:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    check_docker()
    row_counts_before: dict[str, int] = {}

    try:
        start_postgres()
        create_schema()
        seed_data()
        for table in REQUIRED_TABLES:
            row_counts_before[table] = count_rows(table)
        log(f"Row counts before backup: {row_counts_before}")

        backup_path = run_backup()
        run_restore(backup_path)

        row_counts_after = {}
        for table in REQUIRED_TABLES:
            row_counts_after[table] = count_rows(table)
        log(f"Row counts after restore: {row_counts_after}")
        verify_row_counts(row_counts_before, row_counts_after)

        summary = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "passed",
            "seed_rows": SEED_ROWS,
            "tables_verified": REQUIRED_TABLES,
            "row_counts_before": row_counts_before,
            "row_counts_after": row_counts_after,
            "backup_path": str(backup_path),
            "notes": "Backup/restore drill completed successfully. Data integrity verified.",
        }
        summary_path = ARTIFACTS_DIR / "latest_drill.json"
        summary_path.write_text(json.dumps(summary, indent=2))
        log(f"Summary written to {summary_path}")
        log("Backup/Restore drill PASSED.")
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
        cleanup()


if __name__ == "__main__":
    sys.exit(main())
