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

from app.models import Job, JobStatus, SourcePolicy

logger = logging.getLogger(__name__)

_DB_LOCK = Lock()
_CURRENT_SCHEMA_VERSION = 4
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
    conn = sqlite3.connect(str(path), timeout=10)
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
        for raw in data.get("jobs", []):
            job = _row_to_job(_job_from_raw(raw))
            if job:
                row_data = _job_to_row(job)
                cols = ", ".join(row_data.keys())
                ph = ", ".join("?" for _ in row_data)
                conn.execute(f"INSERT OR IGNORE INTO jobs ({cols}) VALUES ({ph})", list(row_data.values()))
        for raw in data.get("recycle_bin", []):
            job = _row_to_job(_job_from_raw(raw))
            if job:
                row_data = _job_to_row(job)
                cols = ", ".join(row_data.keys())
                ph = ", ".join("?" for _ in row_data)
                conn.execute(f"INSERT OR IGNORE INTO recycle_bin ({cols}) VALUES ({ph})", list(row_data.values()))
        conn.commit()
        logger.info(
            "Migrated %d jobs + %d recycle-bin entries from JSON to SQLite",
            len(data.get("jobs", [])),
            len(data.get("recycle_bin", [])),
        )
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.warning("JSON-to-SQLite migration skipped: %s", e)


def _job_from_raw(raw: dict) -> dict:
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


def _job_to_row(job: Job) -> dict:
    """Convert a Job model to a flat row dict for SQLite storage."""
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
        "search_params": json.dumps(job.search_params if job.search_params is not None else {}),
        "max_pages": job.max_pages if hasattr(job, "max_pages") else 0,
        "progress_current": job.progress_current or 0,
        "progress_total": job.progress_total or 0,
        "estimated_cost_usd": job.estimated_cost_usd or 0,
        "cancel_requested": 1 if job.cancel_requested else 0,
        "created_at": job.created_at or "",
        "completed_at": job.completed_at if job.completed_at is not None else "",
        "min_record_score": job.min_record_score if job.min_record_score is not None else 0.35,
        "acquisition_mode": (
            job.acquisition_mode.value if hasattr(job.acquisition_mode, "value") else str(job.acquisition_mode or "standard")
        ),
        "search_params_json": json.dumps(job.search_params if job.search_params is not None else {}),
        "location": job.location or "",
        "preferred_domain": job.preferred_domain or "",
        "source_policy": job.source_policy.value if hasattr(job.source_policy, "value") else str(job.source_policy),
        "max_per_domain": job.max_per_domain or 4,
        "origin_location": job.origin_location or "",
        "max_distance_km": job.max_distance_km,
        "pagination": 1 if job.pagination else 0,
        "deduplicate": 1 if job.deduplicate else 0,
        "deduplicate_field": job.deduplicate_field or "",
        "started_at": job.started_at if job.started_at is not None else "",
        "results_on_disk": 1 if job.results_on_disk else 0,
        "results_file_path": job.results_file_path if job.results_file_path is not None else "",
    }


def _row_to_job(row: dict) -> Job | None:
    """Convert a SQLite row dict back to a Job model."""
    try:
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
                "cancel_requested": bool(row.get("cancel_requested", 0)),
                "created_at": row.get("created_at", ""),
                "completed_at": row.get("completed_at") or None,
                "min_record_score": row.get("min_record_score", 0.35),
                "location": row.get("location", ""),
                "preferred_domain": row.get("preferred_domain", ""),
                "source_policy": sp,
                "max_per_domain": row.get("max_per_domain", 4),
                "origin_location": row.get("origin_location", ""),
                "max_distance_km": row.get("max_distance_km"),
                "pagination": bool(row.get("pagination", 0)),
                "deduplicate": bool(row.get("deduplicate", 1)),
                "deduplicate_field": row.get("deduplicate_field", ""),
                "started_at": row.get("started_at") or None,
                "results_on_disk": bool(row.get("results_on_disk", 0)),
                "results_file_path": row.get("results_file_path") or None,
                "warnings": json.loads(row.get("warnings", "[]")),
                "acquisition_mode": row.get("acquisition_mode", "standard"),
            },
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Failed to deserialize job row: %s", e)
        return None


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
                CREATE TABLE recycle_bin (
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
                        conn.execute(f"INSERT OR IGNORE INTO recycle_bin ({cols_str}) VALUES ({placeholders})", vals)
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
                        job.completed_at = datetime.datetime.now().isoformat()
                        job.cancel_requested = False

                        row = _job_to_row(job)
                        columns = ", ".join(row.keys())
                        placeholders = ", ".join("?" for _ in row)
                        values = list(row.values())
                        conn.execute(
                            f"INSERT OR REPLACE INTO jobs ({columns}) VALUES ({placeholders})",
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
            except (json.JSONDecodeError, OSError):  # nosec B110
                pass  # nosec B110

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
                    f"INSERT OR REPLACE INTO jobs ({columns}) VALUES ({placeholders})",
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
                    f"INSERT OR REPLACE INTO recycle_bin ({columns}) VALUES ({placeholders})",
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
                f"INSERT OR REPLACE INTO jobs ({columns}) VALUES ({placeholders})",
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
    results: list,
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
    """Return the ``job_id`` previously associated with ``idem_key``,
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


def get_storage_health() -> dict:
    """Check that SQLite storage is reachable and schema is valid.

    Returns a dict with:
    - ok: True if all checks pass
    - schema_version: current schema version (0 if missing)
    - expected_version: latest schema version
    - error: error message if any check fails
    """
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
    except Exception as e:
        logger.exception("Storage health check failed: %s")
        return {
            "ok": False,
            "error": str(e),
            "schema_version": 0,
            "expected_version": _CURRENT_SCHEMA_VERSION,
        }


def get_storage_status() -> dict:
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
    try:
        conn = _get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        schema_version = row[0] if row and row[0] is not None else 0
        job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        recycle_count = conn.execute("SELECT COUNT(*) FROM recycle_bin").fetchone()[0]
        wal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        db_path = _get_db_path()
        return {
            "backend": "sqlite",
            "db_path": str(db_path),
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


def reset_job_store_for_tests() -> None:
    """Reset the database path migration cache for tests."""
    _MIGRATIONS_RUN_FOR.clear()
