"""Database health and status checks for SQLite and Postgres.

Extracted from ``job_store.py`` and ``postgres_repository_base.py``
to decouple monitoring from CRUD operations.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.storage_migrations import POSTGRES_SCHEMA_VERSION, SQLITE_SCHEMA_VERSION

# ───────────────────────────────────────────────────────────────────────
# SQLite Health & Status
# ───────────────────────────────────────────────────────────────────────


def check_sqlite_health(
    conn_factory: Callable[[], sqlite3.Connection],
) -> dict[str, Any]:
    """Check that SQLite storage is reachable and schema is valid."""
    conn = None
    try:
        conn = conn_factory()
        schema_row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        schema_version = schema_row[0] if schema_row and schema_row[0] is not None else 0
        jobs_ok = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone() is not None
        recycle_ok = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='recycle_bin'").fetchone() is not None
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
    except Exception as e:
        return {
            "ok": False,
            "error": f"Connection check failed: {e}",
            "schema_version": 0,
            "expected_version": SQLITE_SCHEMA_VERSION,
        }
    finally:
        if conn:
            conn.close()

    if schema_version == 0:
        return {
            "ok": False,
            "error": "Schema version table is empty or missing",
            "schema_version": 0,
            "expected_version": SQLITE_SCHEMA_VERSION,
        }
    if schema_version < SQLITE_SCHEMA_VERSION:
        return {
            "ok": False,
            "error": f"Schema version {schema_version} is older than expected {SQLITE_SCHEMA_VERSION}",
            "schema_version": schema_version,
            "expected_version": SQLITE_SCHEMA_VERSION,
        }
    if not jobs_ok:
        return {
            "ok": False,
            "error": "jobs table is missing",
            "schema_version": schema_version,
            "expected_version": SQLITE_SCHEMA_VERSION,
        }
    if not recycle_ok:
        return {
            "ok": False,
            "error": "recycle_bin table is missing",
            "schema_version": schema_version,
            "expected_version": SQLITE_SCHEMA_VERSION,
        }
    if not companion_ok:
        return {
            "ok": False,
            "error": f"{companion_missing} table is missing",
            "schema_version": schema_version,
            "expected_version": SQLITE_SCHEMA_VERSION,
        }

    return {
        "ok": True,
        "schema_version": schema_version,
        "expected_version": SQLITE_SCHEMA_VERSION,
    }


def get_sqlite_status(
    conn_factory: Callable[[], sqlite3.Connection],
    db_path: Path,
) -> dict[str, Any]:
    """Return detailed SQLite storage status."""
    conn = None
    try:
        conn = conn_factory()
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        schema_version = row[0] if row and row[0] is not None else 0
        job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        recycle_count = conn.execute("SELECT COUNT(*) FROM recycle_bin").fetchone()[0]
        wal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        return {
            "ok": True,
            "backend": "sqlite",
            "db_path": str(db_path.name) if hasattr(db_path, "name") else str(db_path).rsplit("/", 1)[-1],
            "schema_version": schema_version,
            "latest_schema_version": SQLITE_SCHEMA_VERSION,
            "job_count": job_count,
            "recycle_bin_count": recycle_count,
            "wal_mode": wal_mode,
        }
    except Exception as e:
        return {
            "ok": False,
            "backend": "sqlite",
            "error": str(e),
            "schema_version": 0,
            "latest_schema_version": SQLITE_SCHEMA_VERSION,
            "job_count": -1,
            "recycle_bin_count": -1,
            "wal_mode": "unknown",
        }
    finally:
        if conn:
            conn.close()


# ───────────────────────────────────────────────────────────────────────
# Postgres Health & Status
# ───────────────────────────────────────────────────────────────────────


def check_postgres_health(
    conn,
    backend_name: str,
    fetch_one_fn: Callable,
) -> dict[str, Any]:
    """Check that Postgres storage is reachable and schema is valid."""
    row = fetch_one_fn(conn, "SELECT MAX(version) AS version FROM schema_version")
    version = row["version"] if row else 0
    count_row = fetch_one_fn(conn, "SELECT COUNT(*) AS cnt FROM jobs WHERE deleted_at IS NULL")
    job_count = count_row["cnt"] if count_row else 0
    recycle_row = fetch_one_fn(conn, "SELECT COUNT(*) AS cnt FROM recycle_bin")
    recycle_count = recycle_row["cnt"] if recycle_row else 0
    return {
        "ok": True,
        "backend": backend_name,
        "schema_version": version or 0,
        "expected_version": POSTGRES_SCHEMA_VERSION,
        "job_count": job_count or 0,
        "recycle_bin_count": recycle_count or 0,
    }


def get_postgres_status(
    conn,
    backend_name: str,
    fetch_one_fn: Callable,
    db_url: str,
) -> dict[str, Any]:
    """Return detailed Postgres storage status."""
    try:
        row = fetch_one_fn(conn, "SELECT MAX(version) AS version FROM schema_version")
        version = row["version"] if row else 0
        job_count = fetch_one_fn(conn, "SELECT COUNT(*) AS cnt FROM jobs WHERE deleted_at IS NULL")["cnt"]
        recycle_count = fetch_one_fn(conn, "SELECT COUNT(*) AS cnt FROM recycle_bin")["cnt"]
        # Safely parse host/dbname from database URL
        host = db_url.rsplit("@", maxsplit=1)[-1].split("/", maxsplit=1)[0] if "@" in db_url else db_url
        return {
            "ok": True,
            "backend": backend_name,
            "db_path": host,
            "schema_version": version or 0,
            "latest_schema_version": POSTGRES_SCHEMA_VERSION,
            "job_count": job_count or 0,
            "recycle_bin_count": recycle_count or 0,
            "wal_mode": "n/a",
        }
    except Exception as e:
        return {
            "ok": False,
            "backend": backend_name,
            "error": str(e),
            "schema_version": 0,
            "latest_schema_version": POSTGRES_SCHEMA_VERSION,
            "job_count": -1,
            "recycle_bin_count": -1,
            "wal_mode": "unknown",
        }
