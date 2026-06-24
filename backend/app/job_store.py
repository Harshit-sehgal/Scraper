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
    from app.storage_migrations import maybe_migrate_from_json

    maybe_migrate_from_json(conn, _get_db_path())


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
    from app.storage_migrations import run_sqlite_migrations

    run_sqlite_migrations(conn)


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
    from app.storage_health import check_sqlite_health

    return check_sqlite_health(_get_connection)


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
    from app.storage_health import get_sqlite_status

    return get_sqlite_status(_get_connection, _get_db_path())


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
