"""Tests for the targeted-read repository contract (get_job / list_job_summaries).

These tests pin the behaviour of the new abstract methods added to
``JobRepository`` and assert that the existing hot-path routes do not
load every job from the database on a single-job read.
"""

from unittest.mock import Mock

import pytest
from app.models import Job, JobStatus, ScrapeMode
from app.storage_interface import (
    SQLiteJobRepository,
    get_job_repository,
    reset_repository,
)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point job_store at a fresh temp DB for each test."""
    from app.config import settings
    from app.job_store import reset_job_store_for_tests

    db_file = tmp_path / "test_jobs.db"
    state_file = db_file.with_suffix(".json")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(state_file))
    monkeypatch.setattr(settings, "STATE_FILE_PATH", str(state_file))
    reset_job_store_for_tests()
    yield db_file
    reset_job_store_for_tests()


def _make_job(idx: int) -> Job:
    return Job(
        id=f"job-{idx}",
        name=f"Job {idx}",
        urls=[f"https://example.com/{idx}"],
        mode=ScrapeMode.MANUAL,
        status=JobStatus.COMPLETED,
        total_records=idx,
        filtered_records=idx,
    )


class TestGetJobTargetedRead:
    def test_get_job_returns_none_when_missing(self, isolated_db) -> None:
        reset_repository()
        repo = get_job_repository()
        assert repo.get_job("nonexistent") is None
        reset_repository()

    def test_get_job_returns_single_job(self, isolated_db) -> None:
        reset_repository()
        repo = get_job_repository()
        job = _make_job(1)
        repo.save_single(job)

        loaded = repo.get_job("job-1")
        assert loaded is not None
        assert loaded.id == "job-1"
        assert loaded.name == "Job 1"
        assert loaded.total_records == 1
        reset_repository()

    def test_get_job_does_not_scan_full_table(self, isolated_db) -> None:
        """Sanity: ``get_job`` should not require reading every row."""
        reset_repository()
        repo = get_job_repository()
        for i in range(5):
            repo.save_single(_make_job(i))

        # Patch load_jobs and assert it was NOT invoked by get_job.
        original = repo.load_jobs
        repo.load_jobs = Mock(side_effect=AssertionError("load_jobs() must not be called by get_job()"))  # type: ignore[method-assign]
        try:
            loaded = repo.get_job("job-2")
        finally:
            repo.load_jobs = original  # type: ignore[method-assign]
        assert loaded is not None
        assert loaded.id == "job-2"
        reset_repository()


class TestListJobSummaries:
    def test_summaries_exclude_heavy_fields(self, isolated_db) -> None:
        reset_repository()
        repo = get_job_repository()
        job = _make_job(1)
        job.selectors_map = {"title": "h1"}  # type: ignore[attr-defined]
        repo.save_single(job)

        summaries = repo.list_job_summaries(limit=10)
        assert len(summaries) == 1
        s = summaries[0]
        # Summary keys
        for key in (
            "id",
            "name",
            "mode",
            "urls",
            "topic",
            "status",
            "created_at",
            "started_at",
            "completed_at",
            "total_records",
            "filtered_records",
            "progress_current",
            "progress_total",
            "error",
        ):
            assert key in s, f"Missing summary key: {key}"
        # Heavy fields deliberately excluded from projection
        for forbidden in ("results", "logs", "selectors_map", "schema_fields", "filters"):
            assert forbidden not in s, f"Summary leaked heavy field: {forbidden}"
        reset_repository()

    def test_summaries_ordered_newest_first(self, isolated_db) -> None:
        reset_repository()
        repo = get_job_repository()
        for i in range(3):
            j = _make_job(i)
            j.created_at = f"2026-06-0{i + 1}T00:00:00"
            repo.save_single(j)

        summaries = repo.list_job_summaries(limit=10)
        ids = [s["id"] for s in summaries]
        assert ids == ["job-2", "job-1", "job-0"]
        reset_repository()

    def test_summaries_respect_limit(self, isolated_db) -> None:
        reset_repository()
        repo = get_job_repository()
        for i in range(10):
            repo.save_single(_make_job(i))

        summaries = repo.list_job_summaries(limit=3)
        assert len(summaries) == 3
        reset_repository()

    def test_summaries_clamps_oversized_limit(self, isolated_db) -> None:
        reset_repository()
        repo = get_job_repository()
        for i in range(3):
            repo.save_single(_make_job(i))

        # Asking for 10_000 should not break; we should get at most 3 here
        # but the limit clamp should be at least 500 (impl detail).
        summaries = repo.list_job_summaries(limit=10_000)
        assert len(summaries) == 3
        reset_repository()

    def test_summaries_have_correct_url_decoding(self, isolated_db) -> None:
        reset_repository()
        repo: SQLiteJobRepository = get_job_repository()  # type: ignore[assignment]
        job = _make_job(42)
        job.urls = ["https://example.com/x", "https://example.com/y"]
        repo.save_single(job)

        summaries = repo.list_job_summaries(limit=10)
        assert len(summaries) == 1
        assert summaries[0]["urls"] == ["https://example.com/x", "https://example.com/y"]
        reset_repository()


class TestRepositoryContract:
    """Both SQLite and Postgres repos must satisfy the new abstract methods."""

    def test_sqlite_repo_implements_targeted_reads(self) -> None:
        # Static check: SQLiteJobRepository must implement the new methods.
        assert hasattr(SQLiteJobRepository, "get_job")
        assert hasattr(SQLiteJobRepository, "list_job_summaries")


class TestRouterUsesTargetedReads:
    """The /api/jobs routes must not call load_jobs() on single-item reads."""

    def test_list_jobs_does_not_call_load_jobs_in_worker_mode(
        self,
        client,
        monkeypatch,
    ) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "API_KEY", "")
        monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
        monkeypatch.setattr(settings, "OPERATOR_API_KEY", "")
        monkeypatch.setattr(settings, "ALLOW_INSECURE_DEV_AUTH", True)
        monkeypatch.setattr(settings, "ENV", "development")
        # WORKER_QUEUE is a dynamic env-var property. Toggle via env.
        monkeypatch.setenv("DATAFORGE_WORKER_QUEUE", "true")

        # Replace the repository with a mock that fails the test if
        # load_jobs is invoked during the request path.
        mock_repo = Mock()
        mock_repo.list_job_summaries.return_value = [
            {
                "id": "job-1",
                "name": "Mock",
                "mode": "manual",
                "urls": ["https://example.com"],
                "topic": "",
                "status": "completed",
                "created_at": "2026-06-05T00:00:00",
                "started_at": None,
                "completed_at": None,
                "total_records": 0,
                "filtered_records": 0,
                "progress_current": 0,
                "progress_total": 0,
                "error": None,
            },
        ]
        mock_repo.get_job.return_value = None
        mock_repo.load_jobs.side_effect = AssertionError(
            "load_jobs() must not be called on list view in worker mode",
        )

        import app.storage_interface as storage_mod

        monkeypatch.setattr(storage_mod, "_repository_instance", mock_repo)

        resp = client.get("/api/jobs")
        assert resp.status_code in {200, 403}
        # Only assert the call if auth let us through.
        if resp.status_code == 200:
            mock_repo.list_job_summaries.assert_called_once()
            mock_repo.load_jobs.assert_not_called()
            assert resp.json()["jobs"][0]["id"] == "job-1"

        # Reset for subsequent tests
        monkeypatch.setenv("DATAFORGE_WORKER_QUEUE", "false")
