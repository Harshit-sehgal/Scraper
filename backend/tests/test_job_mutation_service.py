"""Unit tests for ``app.services.job_mutation_service``.

Tests each service class (JobCancellerService, JobBackfillService,
JobReclenerService) in isolation using mock stores and monkeypatched
dependencies so no real HTTP, AI, or disk I/O is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.models import Job, JobStatus
from app.routers.jobs_state import JobStoreManager
from app.services.job_mutation_service import JobBackfillService, JobCancellerService, JobReclenerService
from app.utils.rbac import UserRole
from fastapi import HTTPException

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_job(job_id: str = "test-job", status: JobStatus = JobStatus.PENDING, **overrides) -> Job:
    kwargs: dict[str, object] = {
        "id": job_id,
        "name": job_id,
        "status": status,
        "created_by": "user-1",
        "org_id": "org-1",
        "project_id": "project-1",
        "created_at": "2026-06-01T12:00:00",
    }
    kwargs.update(overrides)
    return Job(**kwargs)  # type: ignore[arg-type]


def _make_manager(jobs: dict[str, Job] | None = None, recycle: dict[str, Job] | None = None) -> JobStoreManager:
    return JobStoreManager(jobs or {}, recycle or {})


# ═════════════════════════════════════════════════════════════════════════════
# JobCancellerService
# ═════════════════════════════════════════════════════════════════════════════


class TestJobCancellerService:
    def test_cancel_missing_job_raises_404(self, anyio_backend) -> None:
        service = JobCancellerService(_make_manager())
        with pytest.raises(HTTPException) as exc_info:
            import anyio

            anyio.run(service.cancel_job, "unknown", UserRole.ADMIN, "u1", "o1", "p1")
        assert exc_info.value.status_code == 404

    def test_cancel_terminal_job_returns_early_message(self, anyio_backend) -> None:
        job = _make_job("j1", JobStatus.COMPLETED)
        manager = _make_manager({"j1": job})
        service = JobCancellerService(manager)
        import anyio

        result = anyio.run(service.cancel_job, "j1", UserRole.ADMIN, "u1", "o1", "p1")
        assert result["message"] == "Job already in terminal state"
        assert result["cancel_requested"] is False

    def test_cancel_pending_sets_cancel_requested(self, anyio_backend) -> None:
        job = _make_job("j1", JobStatus.PENDING)
        manager = _make_manager({"j1": job})
        service = JobCancellerService(manager)
        with patch("app.services.job_mutation_service.save_job") as mock_save:
            import anyio

            result = anyio.run(service.cancel_job, "j1", UserRole.ADMIN, "u1", "o1", "p1")
        assert result["cancel_requested"] is True
        assert job.cancel_requested is True
        mock_save.assert_awaited_once_with(job)

    def test_cancel_running_sets_cancel_requested_without_status_change(self, anyio_backend) -> None:
        job = _make_job("j1", JobStatus.RUNNING)
        manager = _make_manager({"j1": job})
        service = JobCancellerService(manager)
        with patch("app.services.job_mutation_service.save_job") as mock_save:
            import anyio

            result = anyio.run(service.cancel_job, "j1", UserRole.ADMIN, "u1", "o1", "p1")
        assert result["cancel_requested"] is True
        assert job.status == JobStatus.RUNNING
        mock_save.assert_awaited_once_with(job)

    def test_cancel_denied_for_other_org_raises_404(self, anyio_backend) -> None:
        job = _make_job("j1", JobStatus.PENDING, org_id="org-a")
        manager = _make_manager({"j1": job})
        service = JobCancellerService(manager)
        with pytest.raises(HTTPException) as exc_info:
            import anyio

            anyio.run(service.cancel_job, "j1", UserRole.USER, "u1", "org-b", "p1")
        assert exc_info.value.status_code == 404

    def test_cancel_admin_can_cancel_any_job(self, anyio_backend) -> None:
        job = _make_job("j1", JobStatus.PENDING, created_by="u2", org_id="org-a")
        manager = _make_manager({"j1": job})
        service = JobCancellerService(manager)
        with patch("app.services.job_mutation_service.save_job"):
            import anyio

            result = anyio.run(service.cancel_job, "j1", UserRole.ADMIN, "admin-u", "", "")
        assert result["cancel_requested"] is True


# ═════════════════════════════════════════════════════════════════════════════
# JobBackfillService
# ═════════════════════════════════════════════════════════════════════════════


class TestJobBackfillService:
    def test_backfill_updates_unknown_source_type(self, anyio_backend) -> None:
        job = _make_job("j1", JobStatus.COMPLETED)
        job.results = [{"source_url": "https://example.com/page", "source_type": "unknown", "source_trust_score": 0.0}]
        manager = _make_manager({"j1": job})
        service = JobBackfillService(manager)
        with (
            patch("app.services.job_mutation_service.save_job") as mock_save,
            patch(
                "app.discovery.infer_source_metadata", return_value={"source_type": "organic_search", "source_trust_score": 0.85}
            ),
        ):
            import anyio

            result = anyio.run(service.backfill_metadata, "j1", UserRole.ADMIN, "u1", "o1", "p1")
        assert result["updated"] is True
        assert job.results[0]["source_type"] == "organic_search"
        mock_save.assert_awaited_once_with(job)

    def test_backfill_skips_known_source_type(self, anyio_backend) -> None:
        job = _make_job("j1", JobStatus.COMPLETED)
        job.results = [{"source_url": "https://example.com/page", "source_type": "organic_search", "source_trust_score": 0.8}]
        manager = _make_manager({"j1": job})
        service = JobBackfillService(manager)
        with patch("app.services.job_mutation_service.save_job") as mock_save:
            import anyio

            result = anyio.run(service.backfill_metadata, "j1", UserRole.ADMIN, "u1", "o1", "p1")
        assert result["updated"] is False
        mock_save.assert_not_called()

    def test_backfill_denied_for_other_org(self, anyio_backend) -> None:
        job = _make_job("j1", JobStatus.COMPLETED, org_id="org-a")
        manager = _make_manager({"j1": job})
        service = JobBackfillService(manager)
        with pytest.raises(HTTPException):
            import anyio

            anyio.run(service.backfill_metadata, "j1", UserRole.USER, "u1", "org-b", "p1")


# ═════════════════════════════════════════════════════════════════════════════
# JobReclenerService
# ═════════════════════════════════════════════════════════════════════════════


class TestJobReclenerService:
    @staticmethod
    def _make_reclean_job() -> Job:
        job = _make_job("j1", JobStatus.COMPLETED)
        job.results = [{"source_url": "https://example.com", "title": "test"}]
        from app.models import FieldType, SchemaField

        job.schema_fields = [SchemaField(name="title", field_type=FieldType.STRING, description="", required=True)]
        return job

    def test_reclean_rejects_running_job(self, anyio_backend) -> None:
        job = _make_job("j1", JobStatus.RUNNING)
        manager = _make_manager({"j1": job})
        service = JobReclenerService(manager)
        with pytest.raises(HTTPException) as exc_info:
            import anyio

            anyio.run(service.reclean_job, "j1", UserRole.ADMIN, "u1", "o1", "p1")
        assert exc_info.value.status_code == 409

    def test_reclean_rejects_no_results(self, anyio_backend) -> None:
        job = self._make_reclean_job()
        job.results = []
        manager = _make_manager({"j1": job})
        service = JobReclenerService(manager)
        with pytest.raises(HTTPException) as exc_info:
            import anyio

            anyio.run(service.reclean_job, "j1", UserRole.ADMIN, "u1", "o1", "p1")
        assert exc_info.value.status_code == 400

    def test_reclean_rejects_no_schema_fields(self, anyio_backend) -> None:
        job = self._make_reclean_job()
        job.schema_fields = []
        manager = _make_manager({"j1": job})
        service = JobReclenerService(manager)
        with pytest.raises(HTTPException) as exc_info:
            import anyio

            anyio.run(service.reclean_job, "j1", UserRole.ADMIN, "u1", "o1", "p1")
        assert exc_info.value.status_code == 400

    def test_reclean_denied_for_other_org(self, anyio_backend) -> None:
        job = self._make_reclean_job()
        job.org_id = "org-a"
        manager = _make_manager({"j1": job})
        service = JobReclenerService(manager)
        with pytest.raises(HTTPException):
            import anyio

            anyio.run(service.reclean_job, "j1", UserRole.USER, "u1", "org-b", "p1")

    def test_reclean_success_path(self, anyio_backend) -> None:
        job = self._make_reclean_job()
        manager = _make_manager({"j1": job})
        service = JobReclenerService(manager)
        ai_report = {
            "applied": True,
            "input_records": 0,
            "output_records": 0,
            "total_chunks": 0,
            "ai_chunks": 0,
            "fallback_chunks": 0,
            "model_fallback_mode": False,
            "noise_rows_removed": 0,
            "capped_records": 0,
            "quality_filtered_after_ai": 0,
        }
        with (
            patch("app.scraper.ai_clean_and_align_records", new_callable=MagicMock) as mock_ai,
            patch("app.filters.process_results") as mock_process,
            patch("app.services.job_mutation_service.normalize_job_results", side_effect=lambda x, _: x),
            patch("app.services.job_mutation_service.save_job"),
            patch("app.discovery.infer_source_metadata", return_value={}),
            patch("app.services.job_mutation_service.compute_source_breakdown", return_value={}),
            patch("app.services.job_mutation_service.build_quality_report", return_value={}),
            patch("app.services.job_mutation_service.deduplicate_results", side_effect=lambda records, **kw: records),
        ):
            mock_ai.return_value = (job.results, ai_report)
            mock_process.return_value = (
                [{"source_url": "https://example.com", "title": "test"}],
                1,
                1,
                {},
            )
            import anyio

            result = anyio.run(service.reclean_job, "j1", UserRole.ADMIN, "u1", "o1", "p1")
        assert result["status"] == "completed"
        assert result["before_records"] == 1
        assert result["after_records"] == 1
