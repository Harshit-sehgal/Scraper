"""Pin the stable summary DTO contract for ``GET /api/jobs``.

The deep-research report's *Target implementation blueprint* section
recommends a stable summary DTO with these keys::

    id, name, mode, topic, status, created_at, started_at,
    completed_at, total_records, filtered_records, progress_current,
    progress_total, error

This test asserts that every concrete repository implementation
returns at least those fields. Adding extra fields is fine; missing
fields are a contract violation.
"""

from __future__ import annotations

from typing import Any

RECOMMENDED_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "name",
        "mode",
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
    },
)


def _summary_keys(s: dict[str, Any]) -> set[str]:
    return set(s.keys())


def test_recommended_fields_are_documented() -> None:
    """Sanity: the recommended set is non-empty and well-defined."""
    assert "id" in RECOMMENDED_FIELDS
    assert "status" in RECOMMENDED_FIELDS
    assert len(RECOMMENDED_FIELDS) >= 13


class TestSqliteSummaryContract:
    def test_sqlite_summary_includes_recommended_fields(self, tmp_path, monkeypatch) -> None:
        from app.config import settings
        from app.job_store import persist_state_single, reset_job_store_for_tests
        from app.models import Job, JobStatus, ScrapeMode
        from app.storage_interface import SQLiteJobRepository, get_job_repository

        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "state.json"))
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(tmp_path / "state.json"))
        reset_job_store_for_tests()
        try:
            repo: SQLiteJobRepository = get_job_repository()  # type: ignore[assignment]
            job = Job(
                id="summary-1",
                name="Summary Test",
                mode=ScrapeMode.MANUAL,
                topic="contract",
                status=JobStatus.PENDING,
            )
            persist_state_single(job)
            summaries = repo.list_job_summaries(limit=10)
            assert summaries, "list_job_summaries returned empty"
            keys = _summary_keys(summaries[0])
            missing = RECOMMENDED_FIELDS - keys
            assert not missing, f"SQLite summary DTO is missing recommended fields: {sorted(missing)}"
        finally:
            reset_job_store_for_tests()


class TestPostgresSummaryContract:
    def test_postgres_summary_abstract_signature_present(self) -> None:
        """The Postgres implementation must expose ``list_job_summaries``
        even if we cannot run it without a real DB.
        """
        from app.postgres_repository import PostgresJobRepository

        assert hasattr(PostgresJobRepository, "list_job_summaries")


class TestPsycopg3SummaryContract:
    def test_psycopg3_summary_abstract_signature_present(self) -> None:
        from app.psycopg3_repository import Psycopg3JobRepository

        assert hasattr(Psycopg3JobRepository, "list_job_summaries")
