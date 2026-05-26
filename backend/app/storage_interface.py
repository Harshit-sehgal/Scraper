import logging
from abc import ABC, abstractmethod
from typing import Optional

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
        """Load all deleted/recycled jobs from the persistent store."""
        pass
        
    @abstractmethod
    def load_all(self) -> tuple[dict[str, Job], dict[str, Job], Optional[dict]]:
        """Load active jobs, recycled jobs, and world state in a single DB read pass."""
        pass
        
    @abstractmethod
    def save_all(self, jobs: dict[str, Job], recycle_bin: dict[str, Job]) -> None:
        """Atomically persist the entire state to the persistent store."""
        pass
        
    @abstractmethod
    def save_single(self, job: Job) -> None:
        """Atomically upsert or save a single job's status, progress, or logs."""
        pass

    # ─── Individual repository operations (avoid full-state rewrites) ────

    def move_to_recycle_bin(self, job_id: str) -> bool:
        """Move a job to the recycle bin. Returns True if the job was moved."""
        raise NotImplementedError

    def restore_from_recycle_bin(self, job_id: str) -> bool:
        """Restore a job from the recycle bin. Returns True if restored."""
        raise NotImplementedError

    def hard_delete(self, job_id: str) -> bool:
        """Permanently delete a job. Returns True if deleted."""
        raise NotImplementedError

    def clear_terminal_jobs(self, older_than: Optional[str] = None) -> int:
        """Remove terminal-status jobs older than the given timestamp. Returns count removed."""
        raise NotImplementedError

    # ─── World state persistence ────────────────────────────────────────

    def load_world_state(self) -> Optional[dict]:
        """Load semantic world state from the persistent store."""
        return None

    def save_world_state(self, payload: dict) -> None:
        """Save semantic world state to the persistent store."""
        pass


class SQLiteJobRepository(JobRepository):
    """SQLite-backed implementation of the JobRepository interface.
    
    Delegates to the optimized app.job_store functions.
    """
    
    def load_jobs(self) -> dict[str, Job]:
        from app.job_store import load_state
        jobs, _, _ = load_state()
        return jobs
        
    def load_recycle_bin(self) -> dict[str, Job]:
        from app.job_store import load_state
        _, recycle, _ = load_state()
        return recycle

    def load_all(self) -> tuple[dict[str, Job], dict[str, Job], Optional[dict]]:
        from app.job_store import load_state
        return load_state()
        
    def save_all(self, jobs: dict[str, Job], recycle_bin: dict[str, Job]) -> None:
        from app.job_store import save_state
        save_state(jobs, recycle_bin)
        
    def save_single(self, job: Job) -> None:
        from app.job_store import persist_state_single
        persist_state_single(job)

    def save_world_state(self, payload: dict) -> None:
        """Save semantic world state to the SQLite world_state.json file."""
        import json
        from app.job_store import _get_db_path
        ws_path = _get_db_path().parent / "world_state.json"
        ws_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    def load_world_state(self) -> Optional[dict]:
        """Load semantic world state from the SQLite world_state.json file."""
        import json
        from app.job_store import _get_db_path
        ws_path = _get_db_path().parent / "world_state.json"
        if ws_path.exists():
            try:
                return json.loads(ws_path.read_text())
            except Exception:
                return None
        return None


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
    import os

    global _repository_instance
    if _repository_instance is not None:
        return _repository_instance

    storage_backend = os.getenv("DATAFORGE_STORAGE_BACKEND", "sqlite").strip().lower()

    if storage_backend == "postgres":
        database_url = os.getenv("DATAFORGE_DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError(
                "DATAFORGE_STORAGE_BACKEND=postgres requires DATAFORGE_DATABASE_URL "
                "to be set. Example: postgresql://user:pass@host:5432/dataforge"
            )
        try:
            from app.postgres_repository import PostgresJobRepository, verify_postgres_connectivity
            connectivity = verify_postgres_connectivity()
            if not connectivity.get("ok"):
                raise RuntimeError(
                    f"Postgres connectivity check failed: {connectivity.get('error', 'unknown error')}. "
                    "Cannot use Postgres backend. Check DATAFORGE_DATABASE_URL and ensure "
                    "the database is running."
                )
            repo = PostgresJobRepository()
            _repository_instance = repo
            logger.info("Using PostgresJobRepository (explicit STORAGE_BACKEND=postgres)")
            return repo
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"Failed to create PostgresJobRepository: {e}. "
                "Install psycopg2-binary: pip install psycopg2-binary"
            ) from e

    repo = SQLiteJobRepository()
    _repository_instance = repo
    return repo


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
            except Exception:
                pass
    _repository_instance = None
