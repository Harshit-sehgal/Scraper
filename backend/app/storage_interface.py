import logging
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
        pass

    @abstractmethod
    def load_recycle_bin(self) -> dict[str, Job]:
        """Load all deleted / recycled jobs from the persistent store."""
        pass

    @abstractmethod
    def load_all(self, recover_in_progress: bool = True) -> tuple[dict[str, Job], dict[str, Job], dict | None]:
        """Load active jobs, recycled jobs, and world state in a single DB read pass.

        Args:
            recover_in_progress: When True, pending/running jobs are marked failed as
                startup recovery. Worker hot-path reads must pass False.
        """
        pass

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
        pass

    @abstractmethod
    def save_single(self, job: Job) -> None:
        """Atomically upsert or save a single job's status, progress, or logs."""
        pass

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
        pass


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

    def load_all(self, recover_in_progress: bool = True) -> tuple[dict[str, Job], dict[str, Job], dict | None]:
        from app.job_store import load_state

        return load_state(recover_in_progress=recover_in_progress)

    def save_all(self, jobs: dict[str, Job], recycle_bin: dict[str, Job], prune_missing: bool = False) -> None:
        from app.job_store import save_state

        save_state(jobs, recycle_bin, prune_missing=prune_missing)

    def is_cancel_requested(self, job_id: str) -> bool:
        """Check from SQLite whether a job has a pending cancellation request."""
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                row = conn.execute(
                    "SELECT cancel_requested FROM jobs WHERE id = ? AND deleted_at IS NULL",
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
        os.replace(tmp_path, str(ws_path))

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
                row_dict = dict(zip(col_names, row))
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
                row_dict = dict(zip(col_names, row))
                # Delete from recycle_bin
                conn.execute("DELETE FROM recycle_bin WHERE id = ?", (job_id,))

                # Exclude deleted_at as it is not present in jobs table
                if "deleted_at" in row_dict:
                    del row_dict["deleted_at"]

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
        """Permanently delete a job atomically in SQLite."""
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                cursor = conn.execute("DELETE FROM recycle_bin WHERE id = ?", (job_id,))
                deleted = cursor.rowcount
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
                    row_dict = dict(zip(col_names, r))
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
            repo: JobRepository = PostgresJobRepository()
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


def reset_repository():
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
                pass
    _repository_instance = None
