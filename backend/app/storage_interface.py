from abc import ABC, abstractmethod
from typing import Optional
from app.models import Job

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

