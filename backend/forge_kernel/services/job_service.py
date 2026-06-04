"""
Job service — orchestrates job lifecycle and extraction orchestration.

Responsible for:
- Creating and validating jobs
- Running extraction for all URLs in a job
- Aggregating results and building quality reports
- Persisting job state
"""

from __future__ import annotations

import asyncio
import datetime
import logging

from forge_kernel.config import settings
from forge_kernel.contracts.job import Job, JobStatus
from forge_kernel.contracts.result import ResultRecord
from forge_kernel.persistence import get_job_repository
from forge_kernel.services.extraction_service import ExtractionService

logger = logging.getLogger(__name__)


class JobService:
    """Service for managing the job lifecycle."""

    def __init__(self, jobs_store: dict[str, Job], recycle_bin_store: dict[str, Job]):
        self._jobs = jobs_store
        self._recycle_bin = recycle_bin_store
        self._extraction = ExtractionService()

    # ─── Queries ────────────────────────────────────────────────────────

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_all(self) -> list[Job]:
        return list(self._jobs.values())

    def get_recycle(self, job_id: str) -> Job | None:
        return self._recycle_bin.get(job_id)

    def list_recycle(self) -> list[Job]:
        return list(self._recycle_bin.values())

    # ─── Mutations ──────────────────────────────────────────────────────

    def create(self, job: Job) -> Job:
        self._jobs[job.id] = job
        self._persist()
        return job

    def cancel(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if not job:
            return None
        job.cancel_requested = True
        if job.status in (JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING):
            job.status = JobStatus.CANCELED
            job.completed_at = datetime.datetime.now().isoformat()
        self._persist()
        return job

    def delete(self, job_id: str) -> bool:
        job = self._jobs.pop(job_id, None)
        if job:
            self._recycle_bin[job_id] = job
            self._persist()
            return True
        return False

    def hard_delete(self, job_id: str) -> bool:
        repo = get_job_repository()
        self._jobs.pop(job_id, None)
        self._recycle_bin.pop(job_id, None)
        return repo.hard_delete(job_id)

    def restore(self, job_id: str) -> Job | None:
        job = self._recycle_bin.pop(job_id, None)
        if job:
            self._jobs[job_id] = job
            self._persist()
            return job
        return None

    # ─── Running ────────────────────────────────────────────────────────

    async def run(self, job_id: str) -> None:
        """Run a job — extract records from all URLs."""
        job = self._jobs.get(job_id)
        if not job:
            return

        if job.cancel_requested:
            job.status = JobStatus.CANCELED
            job.completed_at = datetime.datetime.now().isoformat()
            self._persist()
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.datetime.now().isoformat()
        job.progress_total = len(job.urls) + 2
        job.progress_current = 0
        self._persist()

        all_records: list[ResultRecord] = []
        schema_dicts = [sf.model_dump() for sf in job.schema_fields]

        for idx, url in enumerate(job.urls):
            if job.cancel_requested:
                job.status = JobStatus.CANCELED
                job.completed_at = datetime.datetime.now().isoformat()
                self._persist()
                return

            job.progress_current = idx + 1
            self._persist()

            try:
                records = await asyncio.wait_for(
                    self._extraction.extract_url(
                        url=url,
                        schema_fields=schema_dicts,
                        min_record_score=job.min_record_score,
                        selectors_map=job.selectors_map if job.selectors_map else None,
                    ),
                    timeout=settings.extraction.PER_URL_TIMEOUT_SECONDS,
                )
                all_records.extend(records)
            except asyncio.TimeoutError:
                logger.warning("Timeout extracting %s, continuing", url)
                job.warnings.append(f"Timeout extracting {url}")
            except Exception as e:
                logger.exception("Failed to extract %s: %s", url, e)
                job.warnings.append(f"Failed to extract {url}: {e}")

        # Finalize
        from forge_kernel.extraction.quality import build_quality_report

        job.quality_report = build_quality_report(
            [r.data for r in all_records],
            schema_dicts,
            warnings=job.warnings,
        )

        # Convert to dicts for storage
        job.results = [r.data for r in all_records]
        job.total_records = len(all_records)
        job.filtered_records = len(all_records)

        if not all_records:
            job.status = JobStatus.EMPTY_RESULT
            job.error = "No records extracted from any URL"
        elif job.warnings:
            job.status = JobStatus.DEGRADED
            job.error = "Extraction completed with warnings"
        else:
            job.status = JobStatus.COMPLETED

        job.completed_at = datetime.datetime.now().isoformat()
        job.progress_current = job.progress_total
        self._persist()

    # ─── Persistence ────────────────────────────────────────────────────

    def _persist(self):
        try:
            repo = get_job_repository()
            repo.save_all(jobs=self._jobs, recycle_bin=self._recycle_bin)
        except Exception as e:
            logger.error("Failed to persist state: %s", e)

    def load_all(self):
        """Load all state from the persistent store."""
        try:
            repo = get_job_repository()
            jobs, recycle, ws = repo.load_all()
            self._jobs.clear()
            self._jobs.update(jobs)
            self._recycle_bin.clear()
            self._recycle_bin.update(recycle)
            return ws
        except Exception as e:
            logger.error("Failed to load state: %s", e)
            return None
