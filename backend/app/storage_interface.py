import logging
import os
from abc import ABC, abstractmethod

from app.models import Job

logger = logging.getLogger(__name__)


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
    def save_single(self, job: Job) -> None:
        """Atomically upsert or save a single job's status, progress, or logs."""

    def health_check(self) -> dict:
        """Check repository health. Returns a dict with 'ok' key and backend info."""
        return {"ok": True, "backend": self.__class__.__name__}

    # ─── Individual repository operations (avoid full-state rewrites) ────

    def is_cancel_requested(self, job_id: str) -> bool:
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

    # ─── World state persistence ────────────────────────────────────────

    def load_world_state(self) -> dict | None:
        """Load semantic world state from the persistent store."""
        return None

    def save_world_state(self, payload: dict) -> None:
        """Save semantic world state to the persistent store."""


class SQLiteJobRepository(JobRepository):
    """SQLite-backed implementation of the JobRepository interface.

    Delegates to the optimized app.job_store functions.
    """

    backend = "sqlite"

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
            "SELECT id, name, status, mode, topic, urls, created_at, started_at, "  # nosec B608
            "completed_at, total_records, filtered_records, progress_current, "
            "progress_total, error, deleted_at "
            "FROM recycle_bin "
            f"WHERE {where} "  # nosec B608
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
            "SELECT id, name, status, mode, topic, urls, created_at, started_at, "  # nosec B608
            "completed_at, total_records, filtered_records, progress_current, "
            "progress_total, error "
            "FROM jobs "
            f"WHERE {where} "  # nosec B608
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

    def save_single(self, job: Job) -> None:
        from app.job_store import persist_state_single

        persist_state_single(job)

    def save_world_state(self, payload: dict) -> None:
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
        os.replace(tmp_path, str(ws_path))  # noqa: PTH105

    def load_world_state(self) -> dict | None:
        """Load semantic world state from the SQLite world_state.json file."""
        import json

        from app.job_store import _get_db_path

        ws_path = _get_db_path().parent / "world_state.json"
        if ws_path.exists():
            try:
                return json.loads(ws_path.read_text())  # type: ignore[no-any-return]
            except Exception:
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

                row_dict["deleted_at"] = datetime.datetime.now().isoformat()
                # Insert into recycle_bin
                columns = ", ".join(row_dict.keys())
                placeholders = ", ".join("?" for _ in row_dict)
                conn.execute(
                    f"INSERT OR REPLACE INTO recycle_bin ({columns}) VALUES ({placeholders})",
                    list(row_dict.values()),
                )
                conn.commit()
                return True
            except Exception:
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
                    f"INSERT OR REPLACE INTO jobs ({columns}) VALUES ({placeholders})",
                    list(row_dict.values()),
                )
                conn.commit()
                return True
            except Exception:
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
        """
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                jobs_cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                recycle_cursor = conn.execute("DELETE FROM recycle_bin WHERE id = ?", (job_id,))
                deleted = (jobs_cursor.rowcount or 0) + (recycle_cursor.rowcount or 0)
                conn.commit()
                return deleted > 0
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def clear_terminal_jobs(self, older_than: str | None = None) -> int:
        """Remove terminal-status jobs atomically in SQLite and move them to recycle_bin."""
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

                now = datetime.datetime.now().isoformat()
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
                        f"INSERT OR REPLACE INTO recycle_bin ({columns}) VALUES ({placeholders})",
                        list(row_dict.values()),
                    )
                conn.commit()
                return len(rows)
            except Exception:
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
    global _repository_instance
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
        # psycopg2 (preserves existing behaviour). Set
        # DATAFORGE_PG_DRIVER=psycopg3 to opt in to the new driver.
        pg_driver = (os.environ.get("DATAFORGE_PG_DRIVER") or "psycopg2").strip().lower()

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
            except Exception as e:
                msg = (
                    f"Failed to create Psycopg3JobRepository: {e}. "
                    "Install psycopg 3 with: pip install 'psycopg[binary,pool]>=3.2'"
                )
                raise RuntimeError(msg) from e

        try:
            from app.postgres_repository import PostgresJobRepository, verify_postgres_connectivity

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
        except Exception as e:
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

    If a PostgresJobRepository was cached, also closes the psycopg2 pool
    to prevent connection leaks.
    """
    global _repository_instance
    if _repository_instance is not None:
        if hasattr(_repository_instance, "__class__") and "PostgresJobRepository" in type(_repository_instance).__name__:
            try:
                from app.postgres_repository import shutdown_postgres

                shutdown_postgres()
            except Exception:  # nosec B110
                pass  # nosec B110
    _repository_instance = None
