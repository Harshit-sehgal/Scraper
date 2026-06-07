"""Postgres persistence adapter — wraps the existing app.postgres_repository
in the clean JobRepository contract.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from forge_kernel.persistence import JobRepository

if TYPE_CHECKING:
    from forge_kernel.contracts.job import Job

logger = logging.getLogger(__name__)

_postgres_repo = None


def _get_pg_repo():
    global _postgres_repo
    if _postgres_repo is None:
        try:
            from app.postgres_repository import PostgresJobRepository as _PG

            _postgres_repo = _PG()
        except ImportError as e:
            msg = f"Cannot import app.postgres_repository: {e}. Install psycopg2-binary."
            raise RuntimeError(msg) from e
    return _postgres_repo


class PostgresJobRepository(JobRepository):
    """Postgres-backed repository adapter using the existing postgres_repository module."""

    backend = "postgres"

    def load_all(self) -> tuple[dict[str, Job], dict[str, Job], dict | None]:
        repo = _get_pg_repo()
        return repo.load_all(recover_in_progress=False)

    def save_all(self, jobs: dict[str, Job], recycle_bin: dict[str, Job]) -> None:
        repo = _get_pg_repo()
        repo.save_all(jobs=jobs, recycle_bin=recycle_bin)

    def save_single(self, job: Job) -> None:
        repo = _get_pg_repo()
        repo.save_single(job)

    def is_cancel_requested(self, job_id: str) -> bool:
        repo = _get_pg_repo()
        return repo.is_cancel_requested(job_id)

    def move_to_recycle_bin(self, job_id: str) -> bool:
        repo = _get_pg_repo()
        return repo.move_to_recycle_bin(job_id)

    def restore_from_recycle_bin(self, job_id: str) -> bool:
        repo = _get_pg_repo()
        return repo.restore_from_recycle_bin(job_id)

    def hard_delete(self, job_id: str) -> bool:
        repo = _get_pg_repo()
        return repo.hard_delete(job_id)
