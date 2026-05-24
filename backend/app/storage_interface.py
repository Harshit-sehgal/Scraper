from abc import ABC, abstractmethod
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
    def save_all(self, jobs: dict[str, Job], recycle_bin: dict[str, Job]) -> None:
        """Atomically persist the entire state to the persistent store."""
        pass
        
    @abstractmethod
    def save_single(self, job: Job) -> None:
        """Atomically upsert or save a single job's status, progress, or logs."""
        pass
