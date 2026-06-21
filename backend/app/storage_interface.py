import logging
import os
import threading
from abc import ABC, abstractmethod
from typing import Any

from app.models import Job

logger = logging.getLogger(__name__)
_REPOSITORY_LOCK = threading.Lock()

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
    "created_by TEXT DEFAULT ''",
    "org_id TEXT DEFAULT ''",
    "project_id TEXT DEFAULT ''",
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


class JobRepository(ABC):
    """Generic repository interface to support SQLite, Postgres, or other databases.

    Provides abstract methods to decouple job state persistence from the underlying DB engine.
    """

    @abstractmethod
    def load_jobs(self) -> dict[str, Job]:
        """Load all active jobs from the persistent store."""

    @abstractmethod
    def load_recycle_bin(self) -> dict[str, Job]:
        """Load all deleted / recycled jobs from the persistent store."""

    @abstractmethod
    def get_job(self, job_id: str) -> Job | None:
        """Load a single active job by id.

        Targeted read for hot paths that previously called ``load_jobs()`` and
        filtered client-side. Implementations should issue a primary-key
        lookup that avoids deserializing unrelated rows.
        """

    @abstractmethod
    def list_job_summaries(
        self,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[dict]:
        """Return lightweight job summaries for API list views.

        Each dict contains the same projection used by
        ``GET /api/jobs`` / ``GET /api/recycle_bin``: id, name, mode, urls,
        topic, status, created_at, started_at, completed_at, total_records,
        filtered_records, progress_current, progress_total, error. Heavy
        fields like ``results``, ``logs``, ``selectors_map`` are deliberately
        excluded.

        Args:
            limit: Maximum number of summaries to return. Implementations
                should clamp to a safe upper bound.
            cursor: Opaque cursor for keyset pagination. For the initial
                cut this is treated as an ISO timestamp string; the API
                returns ``created_at`` values that callers can pass back.

        """

    def count_jobs_by_status(self, include_deleted: bool = False) -> dict[str, int]:
        """Return a ``{status_value: count}`` mapping for all jobs.

        This is the authoritative per-status count for the system
        dashboard. It is implemented as a single ``GROUP BY status`` query
        on the backend (SQLite + Postgres) so it is O(distinct statuses)
        rather than O(rows). Subclasses MUST override this; the base
        implementation raises ``NotImplementedError`` to avoid the
        previous behaviour of silently capping ``list_job_summaries`` to
        500 rows and returning a wrong count when the store held more.

        Args:
            include_deleted: If True, soft-deleted rows
                (``deleted_at IS NOT NULL``) are included. Default False
                matches the behaviour of ``GET /api/system/status``.

        """
        msg = f"{self.__class__.__name__} must implement count_jobs_by_status()"
        raise NotImplementedError(
            msg,
        )

    @abstractmethod
    def list_recycle_summaries(
        self,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[dict]:
        """Return lightweight summaries for soft-deleted jobs.

        Targeted read for ``GET /api/recycle_bin`` that avoids
        deserializing every row in the recycle bin just to project a
        handful of summary columns. Returns the same projection shape as
        :meth:`list_job_summaries` (id, name, mode, urls, topic, status,
        created_at, started_at, completed_at, total_records,
        filtered_records, progress_current, progress_total, error) with
        an additional ``deleted_at`` field.

        Args:
            limit: Maximum number of summaries to return. Implementations
                should clamp to a safe upper bound.
            cursor: Opaque cursor for keyset pagination. Treated as an
                ISO timestamp string; callers should pass back a
                ``created_at`` value from a previous page.

        """

    @abstractmethod
    def load_all(self, recover_in_progress: bool = True) -> tuple[dict[str, Job], dict[str, Job], dict | None]:
        """Load active jobs, recycled jobs, and world state in a single DB read pass.

        Args:
            recover_in_progress: When True, pending/running jobs are marked failed as
                startup recovery. Worker hot-path reads must pass False.

        """

    @abstractmethod
    def save_all(self, jobs: dict[str, Job], recycle_bin: dict[str, Job], prune_missing: bool = False) -> None:
        """Atomically persist the entire state to the persistent store.

        Args:
            jobs: Current in-memory jobs dict.
            recycle_bin: Current in-memory recycle bin dict.
            prune_missing: If True, delete rows from the persistent store that are not
                present in the provided dicts before upserting. Default False — prevents
                accidental data loss in multi-process scenarios.

        """

    @abstractmethod
    def read_events(
        self,
        job_id: str,
        limit: int = 200,
        offset: int = 0,
        level_prefix: str | None = None,
    ) -> list[dict]:
        """Return lifecycle events for a job from the dedicated events table.

        Companion to :meth:`list_job_summaries` for endpoints that only
        need the event stream (e.g. ``GET /api/jobs/{id}/events``).
        Implementations should return ``[{timestamp, level, message}, ...]``
        ordered by insertion / ``event_id`` ascending. The
        ``level_prefix`` argument is an optional case-insensitive
        prefix filter (e.g. ``"err"`` matches ``error`` / ``error:``).

        Implementations are expected to return ``[]`` for missing jobs
        or when the companion table is unavailable; the caller can
        fall back to the ``Job.logs`` field of the in-memory job.
        """

    @abstractmethod
    def read_results(
        self,
        job_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Return a job's extracted results from the companion table.

        The storage-split (v4+) stores each result as a dedicated row in
        ``job_results``. This method reads them back in insertion order.
        Returns ``[]`` when the companion table is unavailable so the
        caller can fall back to the ``Job.results`` list.
        """

    def count_results(self, job_id: str) -> int:
        """Return the total number of result rows for a job.

        Subclasses that back the storage-split (v4+) table MUST override
        this so the pagination ``total`` field on ``GET /api/jobs/{id}/results``
        is accurate. The base implementation raises ``NotImplementedError``;
        older backends that read from ``Job.results`` will not reach this
        code path because the caller falls back to ``len(job.results)`` first.
        """
        msg = f"{self.__class__.__name__} must implement count_results()"
        raise NotImplementedError(
            msg,
        )

    @abstractmethod
    def save_single(self, job: Job) -> None:
        """Atomically upsert or save a single job's status, progress, or logs."""

    # ─── Idempotency-key support ───────────────────────────────────────
    # These methods are used by ``POST /api/jobs`` so that repeat
    # submissions with the same ``Idempotency-Key`` header return the
    # originally-created ``job_id`` instead of creating a duplicate.

    @abstractmethod
    def lookup_idempotency_key(self, idem_key: str) -> str | None:
        """Return the ``job_id`` previously associated with ``idem_key``.

        Returns ``None`` if the key has never been seen (or the
        backend does not support idempotency keys).
        """

    @abstractmethod
    def lookup_idempotency_fingerprint(self, idem_key: str) -> str | None:
        """Return the ``request_fingerprint`` previously associated with ``idem_key``.

        Returns ``None`` if the key has never been seen (or the
        backend does not support idempotency keys).
        """

    @abstractmethod
    def record_idempotency_key(
        self,
        idem_key: str,
        job_id: str,
        request_fingerprint: str,
    ) -> None:
        """Persist an idempotency-key → job_id mapping.

        A repeat ``POST /api/jobs`` with the same ``Idempotency-Key``
        returns the original ``job_id`` rather than creating a duplicate.
        """

    def prune_idempotency_keys(self, older_than_days: int = 7) -> int:  # noqa: ARG002, RUF100
        """Delete idempotency keys older than ``older_than_days``.

        Returns the number of rows deleted. Default no-op for backends
        without idempotency-key support; override to implement.
        """
        return 0

    def health_check(self) -> dict[str, Any]:
        """Check repository health. Returns a dict with 'ok' key and backend info."""
        return {"ok": True, "backend": self.__class__.__name__}

    # ─── Worker heartbeat ────────────────────────────────────────────

    def record_worker_heartbeat(self, worker_id: str, hostname: str, pid: int) -> None:
        """Record a heartbeat from a worker process.

        Upserts the worker's heartbeat timestamp so the healthcheck
        can verify the worker is alive by checking recency.

        Subclasses MUST override this — the base implementation raises
        ``NotImplementedError`` so missing backends fail loudly rather than
        silently dropping heartbeats.
        """
        msg = f"{self.__class__.__name__} must implement record_worker_heartbeat()"
        raise NotImplementedError(
            msg,
        )

    def get_worker_health(self, worker_id: str, ttl_seconds: int = 60) -> dict[str, object]:
        """Return health info for a specific worker.

        Returns a dict with:
        - alive: bool — True if a heartbeat exists and is within ttl_seconds
        - last_heartbeat: str | None — ISO timestamp of last heartbeat
        - hostname: str | None
        - pid: int | None
        - worker_id: str

        Subclasses MUST override this — the base implementation raises
        ``NotImplementedError`` so missing backends fail loudly.
        """
        msg = f"{self.__class__.__name__} must implement get_worker_health()"
        raise NotImplementedError(
            msg,
        )

    def get_all_worker_healths(self, ttl_seconds: int = 60) -> list[dict[str, object]]:
        """Return health info for all registered workers.

        Returns a list of dicts, each with the same shape as
        :meth:`get_worker_health`.

        Subclasses MUST override this — the base implementation raises
        ``NotImplementedError`` so missing backends fail loudly.
        """
        msg = f"{self.__class__.__name__} must implement get_all_worker_healths()"
        raise NotImplementedError(
            msg,
        )

    # ─── Individual repository operations (avoid full-state rewrites) ────

    def is_cancel_requested(self, job_id: str) -> bool:  # noqa: ARG002, RUF100
        """Check from the persistent store whether a job has a pending cancellation request.

        Required for cross-process cancellation: the worker polls this method
        during long-running operations to detect cancellations requested by
        the API process. Returns True if the cancellation flag is set.
        """
        return False

    def move_to_recycle_bin(self, job_id: str) -> bool:
        """Move a job to the recycle bin. Returns True if the job was moved."""
        raise NotImplementedError

    def restore_from_recycle_bin(self, job_id: str) -> bool:
        """Restore a job from the recycle bin. Returns True if restored."""
        raise NotImplementedError

    def hard_delete(self, job_id: str) -> bool:
        """Permanently delete a job. Returns True if deleted."""
        raise NotImplementedError

    def clear_terminal_jobs(self, older_than: str | None = None) -> int:
        """Remove terminal-status jobs older than the given timestamp. Returns count removed."""
        raise NotImplementedError

    def cleanup_companion_data(self, job_id: str) -> None:
        """Remove companion-table rows (``job_results``, ``job_events``)
        for a given job. Called during hard-delete or recycle-bin move.
        Default no-op; override in backends that support companion tables.
        """

    # ─── World state persistence ────────────────────────────────────────

    def load_world_state(self) -> dict | None:
        """Load semantic world state from the persistent store."""
        return None

    def save_world_state(self, payload: dict[str, Any]) -> None:
        """Save semantic world state to the persistent store."""


class SQLiteJobRepository(JobRepository):
    """SQLite-backed implementation of the JobRepository interface.

    Delegates to the optimized app.job_store functions.
    """

    backend = "sqlite"

    # ─── Worker heartbeat ────────────────────────────────────────────

    def record_worker_heartbeat(self, worker_id: str, hostname: str, pid: int) -> None:
        from app.job_store import record_worker_heartbeat as _record_hb

        _record_hb(worker_id, hostname, pid)

    def get_worker_health(self, worker_id: str, ttl_seconds: int = 60) -> dict[str, object]:
        from app.job_store import get_worker_health as _get_health

        return _get_health(worker_id, ttl_seconds=ttl_seconds)

    def get_all_worker_healths(self, ttl_seconds: int = 60) -> list[dict[str, object]]:
        from app.job_store import get_all_worker_healths as _get_all

        return _get_all(ttl_seconds=ttl_seconds)

    def count_jobs_by_status(self, include_deleted: bool = False) -> dict[str, int]:
        from app.job_store import count_jobs_by_status as _count

        return _count(include_deleted=include_deleted)

    def health_check(self) -> dict[str, Any]:
        """Check the SQLite backend's health and schema state.

        Returns a dict with ``ok`` flag, schema version, and row counts.
        Mirrors the contract implemented by the Postgres backends so the
        ``/ready`` endpoint behaves consistently across storage drivers.
        """
        try:
            from app.job_store import _CURRENT_SCHEMA_VERSION, get_storage_health

            return get_storage_health()
        except (OSError, RuntimeError, ImportError, ValueError, AttributeError, TypeError) as exc:
            return {
                "ok": False,
                "backend": "sqlite",
                "error": str(exc),
                "schema_version": 0,
                "expected_version": _CURRENT_SCHEMA_VERSION,
                "job_count": -1,
                "recycle_bin_count": -1,
            }

    def load_jobs(self) -> dict[str, Job]:
        from app.job_store import load_state

        jobs, _, _ = load_state(recover_in_progress=False)
        return jobs

    def load_recycle_bin(self) -> dict[str, Job]:
        from app.job_store import load_state

        _, recycle, _ = load_state(recover_in_progress=False)
        return recycle

    def list_recycle_summaries(
        self,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[dict]:
        """Lightweight summary projection for ``GET /api/recycle_bin``.

        Performs a single SELECT against the small summary columns of
        the ``recycle_bin`` table and does not deserialize JSON blobs.
        The ``deleted_at`` column is included so the UI can show how
        long ago the row was soft-deleted.
        """
        from app.job_store import _DB_LOCK, _get_connection

        safe_limit = max(1, min(int(limit), 500))
        params: list[object] = []
        where = "1=1"
        if cursor:
            where += " AND created_at < ?"
            params.append(cursor)
        params.append(safe_limit)
        sql = (
            "SELECT id, name, status, mode, topic, urls, created_by, created_at, started_at, "  # nosec B608  # noqa: RUF100, S608
            "completed_at, total_records, filtered_records, progress_current, "
            "progress_total, error, deleted_at "
            "FROM recycle_bin "
            f"WHERE {where} "  # noqa: RUF100, S608
            "ORDER BY created_at DESC LIMIT ?"
        )
        with _DB_LOCK:
            conn = _get_connection()
            try:
                rows = conn.execute(sql, params).fetchall()
            finally:
                conn.close()
        summaries: list[dict] = []
        for row in rows:
            d = dict(row)
            urls_raw = d.get("urls") or "[]"
            try:
                import json as _json

                urls_val = _json.loads(urls_raw) if isinstance(urls_raw, str) else (urls_raw or [])
            except (TypeError, ValueError):
                urls_val = []
            summaries.append(
                {
                    "id": d.get("id"),
                    "name": d.get("name"),
                    "mode": d.get("mode"),
                    "urls": urls_val,
                    "created_by": d.get("created_by", "") or "",
                    "topic": d.get("topic", "") or "",
                    "status": d.get("status"),
                    "created_at": d.get("created_at"),
                    "started_at": d.get("started_at") or None,
                    "completed_at": d.get("completed_at") or None,
                    "total_records": d.get("total_records", 0) or 0,
                    "filtered_records": d.get("filtered_records", 0) or 0,
                    "progress_current": d.get("progress_current", 0) or 0,
                    "progress_total": d.get("progress_total", 0) or 0,
                    "error": d.get("error") or None,
                    "deleted_at": d.get("deleted_at") or None,
                },
            )
        return summaries

    def get_job(self, job_id: str) -> Job | None:
        """Targeted read: load a single job by primary key from SQLite.

        Avoids deserializing every row in the ``jobs`` table on hot read
        paths (single-job detail, worker-mode refresh, etc.).
        """
        from app.job_store import _DB_LOCK, _get_connection, _row_to_job

        with _DB_LOCK:
            conn = _get_connection()
            try:
                row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if not row:
                    return None
                return _row_to_job(dict(row))
            finally:
                conn.close()

    def list_job_summaries(
        self,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[dict]:
        """Lightweight summary projection for ``GET /api/jobs`` in worker mode.

        Performs a single SELECT against the small summary columns and
        does not deserialize JSON blobs (results, logs, selectors_map, …).
        """
        from app.job_store import _DB_LOCK, _get_connection

        safe_limit = max(1, min(int(limit), 500))
        params: list[object] = []
        where = "1=1"
        if cursor:
            where += " AND created_at < ?"
            params.append(cursor)
        params.append(safe_limit)
        sql = (
            "SELECT id, name, status, mode, topic, urls, created_by, created_at, started_at, "  # nosec B608  # noqa: RUF100, S608
            "completed_at, total_records, filtered_records, progress_current, "
            "progress_total, error "
            "FROM jobs "
            f"WHERE {where} "  # noqa: RUF100, S608
            "ORDER BY created_at DESC LIMIT ?"
        )
        with _DB_LOCK:
            conn = _get_connection()
            try:
                rows = conn.execute(sql, params).fetchall()
            finally:
                conn.close()
        summaries: list[dict] = []
        for row in rows:
            d = dict(row)
            # ``urls`` is stored as JSON; decode once for the API surface.
            urls_raw = d.get("urls") or "[]"
            try:
                import json as _json

                urls_val = _json.loads(urls_raw) if isinstance(urls_raw, str) else (urls_raw or [])
            except (TypeError, ValueError):
                urls_val = []
            summaries.append(
                {
                    "id": d.get("id"),
                    "name": d.get("name"),
                    "mode": d.get("mode"),
                    "urls": urls_val,
                    "created_by": d.get("created_by", "") or "",
                    "topic": d.get("topic", "") or "",
                    "status": d.get("status"),
                    "created_at": d.get("created_at"),
                    "started_at": d.get("started_at") or None,
                    "completed_at": d.get("completed_at") or None,
                    "total_records": d.get("total_records", 0) or 0,
                    "filtered_records": d.get("filtered_records", 0) or 0,
                    "progress_current": d.get("progress_current", 0) or 0,
                    "progress_total": d.get("progress_total", 0) or 0,
                    "error": d.get("error") or None,
                },
            )
        return summaries

    def load_all(self, recover_in_progress: bool = True) -> tuple[dict[str, Job], dict[str, Job], dict | None]:
        from app.job_store import load_state

        return load_state(recover_in_progress=recover_in_progress)

    def save_all(self, jobs: dict[str, Job], recycle_bin: dict[str, Job], prune_missing: bool = False) -> None:
        from app.job_store import save_state

        save_state(jobs, recycle_bin, prune_missing=prune_missing)

    def read_events(
        self,
        job_id: str,
        limit: int = 200,
        offset: int = 0,
        level_prefix: str | None = None,
    ) -> list[dict]:
        """Read events from the ``job_events`` companion table.

        Returns an empty list when the table is empty (e.g. before
        v4 dual-write has populated it) so the caller can fall back
        to the in-memory ``Job.logs`` list.
        """
        from app.job_store import read_job_events

        return read_job_events(
            job_id,
            limit=limit,
            offset=offset,
            level_prefix=level_prefix,
        )

    def is_cancel_requested(self, job_id: str) -> bool:
        """Check from SQLite whether a job has a pending cancellation request.

        The SQLite ``jobs`` table does not carry a ``deleted_at`` column —
        soft-delete is modelled by moving the row into ``recycle_bin``. So a
        ``SELECT`` on ``jobs`` alone is sufficient (and safe).
        """
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                row = conn.execute(
                    "SELECT cancel_requested FROM jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()
                if row:
                    return bool(row[0])
                return False
            finally:
                conn.close()

    def read_results(
        self,
        job_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Read a job's results from the companion table.

        Delegates to ``app.job_store.read_job_results_paginated`` which reads
        from the ``job_results`` table with pagination.
        """
        from app.job_store import read_job_results_paginated as _read_paginated

        return _read_paginated(job_id, limit=limit, offset=offset)

    def lookup_idempotency_key(self, idem_key: str) -> str | None:
        """Lookup an idempotency key in SQLite."""
        from app.job_store import lookup_idempotency_key as _lookup

        return _lookup(idem_key)

    def lookup_idempotency_fingerprint(self, idem_key: str) -> str | None:
        """Lookup an idempotency key's request fingerprint in SQLite."""
        from app.job_store import lookup_idempotency_fingerprint as _lookup_fingerprint

        return _lookup_fingerprint(idem_key)

    def record_idempotency_key(
        self,
        idem_key: str,
        job_id: str,
        request_fingerprint: str,
    ) -> None:
        """Record an idempotency key in SQLite."""
        from app.job_store import record_idempotency_key as _record

        _record(idem_key, job_id, request_fingerprint)

    def prune_idempotency_keys(self, older_than_days: int = 7) -> int:
        """Prune old idempotency keys from SQLite."""
        from app.job_store import prune_idempotency_keys as _prune

        return _prune(older_than_days)

    def cleanup_companion_data(self, job_id: str) -> None:
        """Remove companion-table rows for a job in SQLite."""
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                conn.execute("DELETE FROM job_results WHERE job_id = ?", (job_id,))
                conn.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
                conn.commit()
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                conn.rollback()
                raise
            finally:
                conn.close()

    def save_single(self, job: Job) -> None:
        from app.job_store import persist_state_single

        persist_state_single(job)

    def save_world_state(self, payload: dict[str, Any]) -> None:
        """Save semantic world state to the SQLite world_state.json file atomically."""
        import json
        import os
        import tempfile

        from app.job_store import _get_db_path

        ws_path = _get_db_path().parent / "world_state.json"
        # Write to a temp file first, then atomic rename to prevent partial
        # writes.
        tmp_dir = ws_path.parent
        tmp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json.tmp",
            dir=str(tmp_dir),
            delete=False,
        ) as f:
            f.write(json.dumps(payload, ensure_ascii=False, indent=2))
            tmp_path = f.name
        os.replace(tmp_path, str(ws_path))

    def load_world_state(self) -> dict | None:
        """Load semantic world state from the SQLite world_state.json file."""
        import json

        from app.job_store import _get_db_path

        ws_path = _get_db_path().parent / "world_state.json"
        if ws_path.exists():
            try:
                return json.loads(ws_path.read_text())  # type: ignore[no-any-return]
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                logger.debug("Failed to parse world_state.json", exc_info=True)
                return None
        return None

    def move_to_recycle_bin(self, job_id: str) -> bool:
        """Move a job to the recycle bin atomically in SQLite."""
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                # Find the row in jobs
                cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                # Convert to dict
                col_names = [description[0] for description in cursor.description]
                row_dict = dict(zip(col_names, row, strict=False))
                # Delete from jobs
                conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                # Set deleted_at timestamp
                import datetime

                row_dict["deleted_at"] = datetime.datetime.now(datetime.UTC).isoformat()
                # Insert into recycle_bin
                columns = ", ".join(row_dict.keys())
                placeholders = ", ".join("?" for _ in row_dict)
                conn.execute(
                    f"INSERT OR REPLACE INTO recycle_bin ({columns}) VALUES ({placeholders})",  # noqa: RUF100, S608
                    list(row_dict.values()),
                )
                conn.commit()
                return True
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                conn.rollback()
                raise
            finally:
                conn.close()

    def restore_from_recycle_bin(self, job_id: str) -> bool:
        """Restore a job from the recycle bin back to active jobs atomically in SQLite."""
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                # Find row in recycle_bin
                cursor = conn.execute("SELECT * FROM recycle_bin WHERE id = ?", (job_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                col_names = [description[0] for description in cursor.description]
                row_dict = dict(zip(col_names, row, strict=False))
                # Delete from recycle_bin
                conn.execute("DELETE FROM recycle_bin WHERE id = ?", (job_id,))

                # Exclude deleted_at as it is not present in jobs table
                row_dict.pop("deleted_at", None)

                # Insert into jobs
                columns = ", ".join(row_dict.keys())
                placeholders = ", ".join("?" for _ in row_dict)
                conn.execute(
                    f"INSERT OR REPLACE INTO jobs ({columns}) VALUES ({placeholders})",  # noqa: RUF100, S608
                    list(row_dict.values()),
                )
                conn.commit()
                return True
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                conn.rollback()
                raise
            finally:
                conn.close()

    def hard_delete(self, job_id: str) -> bool:
        """Permanently delete a job atomically in SQLite.

        A job may live in either ``jobs`` (never recycled) or ``recycle_bin``
        (soft-deleted). The caller should not have to know which — this
        method removes the row from both tables and reports success if it
        affected either one.

        Companion-table rows (``job_results``, ``job_events``) are also
        explicitly deleted because the foreign key relationship does not
        use ``ON DELETE CASCADE`` — that would destroy companion data
        when a job is moved to the recycle bin rather than hard-deleted.
        """
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                jobs_cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                recycle_cursor = conn.execute("DELETE FROM recycle_bin WHERE id = ?", (job_id,))
                deleted = (jobs_cursor.rowcount or 0) + (recycle_cursor.rowcount or 0)
                # Explicitly clean up companion tables (no ON DELETE CASCADE)
                conn.execute("DELETE FROM job_results WHERE job_id = ?", (job_id,))
                conn.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
                conn.commit()
                return deleted > 0
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                conn.rollback()
                raise
            finally:
                conn.close()

    def clear_terminal_jobs(self, older_than: str | None = None) -> int:
        """Remove terminal-status jobs atomically in SQLite and move them to recycle_bin.

        Companion-table rows (``job_results``, ``job_events``) are also
        explicitly deleted because the foreign key relationship does not
        use ``ON DELETE CASCADE`` — that would destroy companion data
        when a job is moved to the recycle bin rather than hard-deleted.
        """
        from app.job_store import _DB_LOCK, _get_connection

        terminal_statuses = ("completed", "failed", "canceled", "degraded", "empty_result")
        with _DB_LOCK:
            conn = _get_connection()
            try:
                query = "SELECT * FROM jobs WHERE status IN (?, ?, ?, ?, ?)"
                params = list(terminal_statuses)
                if older_than:
                    query += " AND completed_at < ?"
                    params.append(older_than)

                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                if not rows:
                    return 0

                col_names = [description[0] for description in cursor.description]
                import datetime

                now = datetime.datetime.now(datetime.UTC).isoformat()
                for r in rows:
                    row_dict = dict(zip(col_names, r, strict=False))
                    jid = row_dict["id"]
                    # Delete from jobs
                    conn.execute("DELETE FROM jobs WHERE id = ?", (jid,))
                    # Set deleted_at timestamp
                    row_dict["deleted_at"] = now
                    # Insert into recycle_bin
                    columns = ", ".join(row_dict.keys())
                    placeholders = ", ".join("?" for _ in row_dict)
                    conn.execute(
                        f"INSERT OR REPLACE INTO recycle_bin ({columns}) VALUES ({placeholders})",  # noqa: RUF100, S608
                        list(row_dict.values()),
                    )
                    # Explicitly clean up companion tables (no ON DELETE CASCADE)
                    conn.execute("DELETE FROM job_results WHERE job_id = ?", (jid,))
                    conn.execute("DELETE FROM job_events WHERE job_id = ?", (jid,))
                conn.commit()
                return len(rows)
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                conn.rollback()
                raise
            finally:
                conn.close()


# ───────────────────────────────────────────────────────────────────────
# Repository resolver factory
# ───────────────────────────────────────────────────────────────────────


def get_job_repository() -> JobRepository:
    """Resolve the appropriate JobRepository based on configuration.

    Returns:
        PostgresJobRepository if DATAFORGE_STORAGE_BACKEND=postgres is set
        (and DATAFORGE_DATABASE_URL points to a running instance),
        otherwise SQLiteJobRepository.

    The repository is cached as a module-level singleton so that
    all callers share the same instance.

    """
    # Fast-path check: avoid acquiring the lock on every call.
    global _repository_instance
    if _repository_instance is not None:
        return _repository_instance

    with _REPOSITORY_LOCK:
        # Re-check under the lock to avoid duplicate initialisation when
        # two threads race the first call.
        if _repository_instance is not None:
            return _repository_instance

        from app.config import settings

        storage_backend = settings.STORAGE_BACKEND

        if storage_backend == "postgres":
            database_url = settings.DATABASE_URL
            if not database_url:
                msg = (
                    "DATAFORGE_STORAGE_BACKEND=postgres requires DATAFORGE_DATABASE_URL "
                    "to be set. Example: postgresql://user:pass@host:5432/dataforge"
                )
                raise RuntimeError(
                    msg,
                )
            # Phase A: driver selection via DATAFORGE_PG_DRIVER. Defaults to
            # psycopg2 in dev (preserves existing behaviour) but FAILS FAST in
            # production if not set, because the production image ships only
            # psycopg3 and psycopg2 would crash the worker on first use.
            pg_driver_env = os.environ.get("DATAFORGE_PG_DRIVER", "").strip().lower()
            if not pg_driver_env and settings.ENV.lower() == "production":
                msg = (
                    "DATAFORGE_PG_DRIVER is not set. Production requires "
                    "DATAFORGE_PG_DRIVER=psycopg3 because the production image "
                    "installs only psycopg3 (psycopg2 is intentionally excluded). "
                    "Set DATAFORGE_PG_DRIVER=psycopg3 in the dataforge and worker "
                    "service environment in docker-compose.prod.yml."
                )
                raise RuntimeError(
                    msg,
                )
            pg_driver = pg_driver_env or "psycopg2"

            if pg_driver == "psycopg3":
                try:
                    from app.psycopg3_repository import (
                        Psycopg3JobRepository,
                        verify_psycopg3_connectivity,
                    )

                    connectivity = verify_psycopg3_connectivity()
                    if not connectivity.get("ok"):
                        msg = (
                            f"Postgres (psycopg3) connectivity check failed: "
                            f"{connectivity.get('error', 'unknown error')}. "
                            "Cannot use Postgres backend. Check DATAFORGE_DATABASE_URL "
                            "and ensure the database is running."
                        )
                        raise RuntimeError(msg)
                    repo: JobRepository = Psycopg3JobRepository()
                    _repository_instance = repo
                    logger.info("Using Psycopg3JobRepository (STORAGE_BACKEND=postgres, PG_DRIVER=psycopg3)")
                    return repo
                except RuntimeError:
                    raise
                except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, ImportError) as e:
                    msg = (
                        f"Failed to create Psycopg3JobRepository: {e}. "
                        "Install psycopg 3 with: pip install 'psycopg[binary,pool]>=3.2'"
                    )
                    raise RuntimeError(msg) from e

            try:
                from app.postgres_repository import (
                    PostgresJobRepository,
                    verify_postgres_connectivity,
                )

                connectivity = verify_postgres_connectivity()
                if not connectivity.get("ok"):
                    msg = (
                        f"Postgres connectivity check failed: {connectivity.get('error', 'unknown error')}. "
                        "Cannot use Postgres backend. Check DATAFORGE_DATABASE_URL and ensure "
                        "the database is running."
                    )
                    raise RuntimeError(
                        msg,
                    )
                repo = PostgresJobRepository()
                _repository_instance = repo
                logger.info("Using PostgresJobRepository (explicit STORAGE_BACKEND=postgres)")
                return repo
            except RuntimeError:
                raise
            except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, ImportError) as e:
                msg = f"Failed to create PostgresJobRepository: {e}. Install psycopg2-binary: pip install psycopg2-binary"
                raise RuntimeError(
                    msg,
                ) from e

        repo_sqlite: JobRepository = SQLiteJobRepository()
        _repository_instance = repo_sqlite
        return repo_sqlite


_repository_instance: JobRepository | None = None


def reset_repository() -> None:
    """Reset the cached repository instance (for testing).

    If a PostgresJobRepository (psycopg2) was cached, also closes the
    psycopg2 connection pool. If a Psycopg3JobRepository was cached,
    closes the psycopg 3 connection pool. Prevents connection leaks
    across test runs.
    """
    global _repository_instance
    if _repository_instance is not None:
        cls_name = type(_repository_instance).__name__
        if "PostgresJobRepository" in cls_name:
            try:
                from app.postgres_repository import shutdown_postgres

                shutdown_postgres()
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                logger.warning("Failed to shut down Postgres repository", exc_info=True)
        elif "Psycopg3JobRepository" in cls_name:
            try:
                from app.psycopg3_repository import shutdown_psycopg3

                shutdown_psycopg3()
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                logger.warning("Failed to shut down Psycopg3 repository", exc_info=True)
    _repository_instance = None
