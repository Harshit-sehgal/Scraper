"""Persistence contracts — repository ABC and serialization helpers.

Defines the JobRepository interface and shared serializers for both backends.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge_kernel.contracts.job import Job

logger = logging.getLogger(__name__)


class JobRepository(ABC):
    """Abstract repository interface for job state persistence."""

    @abstractmethod
    def load_all(self) -> tuple[dict[str, Job], dict[str, Job], dict | None]:
        """Load active jobs, recycled jobs, and world state."""

    @abstractmethod
    def save_all(self, jobs: dict[str, Job], recycle_bin: dict[str, Job]) -> None:
        """Atomically persist all state."""

    @abstractmethod
    def save_single(self, job: Job) -> None:
        """Upsert a single job's state."""

    @abstractmethod
    def is_cancel_requested(self, job_id: str) -> bool:
        """Check if a cancellation has been requested for this job."""

    @abstractmethod
    def move_to_recycle_bin(self, job_id: str) -> bool:
        """Move a job to the recycle bin."""

    @abstractmethod
    def restore_from_recycle_bin(self, job_id: str) -> bool:
        """Restore a job from the recycle bin."""

    @abstractmethod
    def hard_delete(self, job_id: str) -> bool:
        """Permanently delete a job."""


# Lazy import of repository resolver to avoid circular imports
_repository_instance: JobRepository | None = None


def get_job_repository() -> JobRepository:
    """Resolve the appropriate JobRepository based on configuration."""
    global _repository_instance
    if _repository_instance is not None:
        return _repository_instance

    from forge_kernel.config import settings

    backend = settings.storage.STORAGE_BACKEND
    if backend == "postgres":
        database_url = settings.storage.DATABASE_URL
        if not database_url:
            msg = "Postgres backend requires DATAFORGE_DATABASE_URL"
            raise RuntimeError(msg)
        try:
            from forge_kernel.persistence.postgres import PostgresJobRepository

            _repository_instance = PostgresJobRepository()
        except Exception as e:
            msg = f"Failed to create PostgresJobRepository: {e}"
            raise RuntimeError(msg) from e
        else:
            return _repository_instance

    from forge_kernel.persistence.sqlite import SQLiteJobRepository

    _repository_instance = SQLiteJobRepository()
    return _repository_instance


def reset_repository() -> None:
    """Reset the cached repository instance (for testing)."""
    global _repository_instance
    _repository_instance = None


def job_to_row(job: Job) -> dict[str, Any]:
    """Serialize a Job to a flat dict row."""
    d = job.model_dump()
    d["status"] = job.status.value if hasattr(job.status, "value") else str(job.status)
    d["mode"] = job.mode.value if hasattr(job.mode, "value") else str(job.mode)
    d["source_policy"] = job.source_policy.value if hasattr(job.source_policy, "value") else str(job.source_policy)
    d["acquisition_mode"] = job.acquisition_mode
    d["schema_fields"] = json.dumps([sf.model_dump() for sf in job.schema_fields])
    d["filters"] = json.dumps([fr.model_dump() for fr in job.filters])
    d["results"] = json.dumps(job.results)
    d["logs"] = json.dumps([log.model_dump() for log in job.logs])
    d["quality_report"] = json.dumps(job.quality_report)
    discovered = job.discovered_urls if hasattr(job, "discovered_urls") else []
    d["discovered_urls"] = json.dumps(discovered)
    d["selectors_map"] = json.dumps(job.selectors_map) if job.selectors_map else "{}"
    d["search_params"] = json.dumps(job.search_params) if job.search_params else "{}"
    d["warnings"] = json.dumps(job.warnings) if job.warnings else "[]"
    for field in ("results_on_disk", "results_file_path", "analysis"):
        if field in d and field not in job.model_fields:
            d.pop(field, None)
    return d
