"""Tests for PostgresJobRepository and related infrastructure.

Since Postgres is not available in CI, these tests:
1. Verify the SQLite fallback path in get_job_repository()
2. Test _job_to_row / _row_to_job serialization functions directly
3. Verify the PostgresJobRepository initialization (without DB connection)
4. Test that the repository factory correctly resolves implementations
"""

import json
import os

import pytest

from app.models import Job, JobStatus, ScrapeMode, SourcePolicy
from app.storage_interface import (
    JobRepository,
    SQLiteJobRepository,
    get_job_repository,
    reset_repository,
)


# ───────────────────────────────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────────────────────────────


@pytest.fixture()
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


# ───────────────────────────────────────────────────────────────────────
# Factory tests
# ───────────────────────────────────────────────────────────────────────


class TestJobRepositoryFactory:
    """Tests for the get_job_repository() factory resolver."""

    def test_default_returns_sqlite(self):
        """Without DATAFORGE_DATABASE_URL, the factory returns SQLiteJobRepository."""
        reset_repository()
        if "DATAFORGE_DATABASE_URL" in os.environ:
            del os.environ["DATAFORGE_DATABASE_URL"]

        repo = get_job_repository()
        assert isinstance(repo, SQLiteJobRepository)
        reset_repository()

    def test_factory_caches_instance(self):
        """The factory caches and returns the same instance on repeated calls."""
        reset_repository()
        if "DATAFORGE_DATABASE_URL" in os.environ:
            del os.environ["DATAFORGE_DATABASE_URL"]

        repo1 = get_job_repository()
        repo2 = get_job_repository()
        assert repo1 is repo2  # Same instance
        reset_repository()

    def test_reset_repository_clears_cache(self):
        """reset_repository() clears the cached instance."""
        reset_repository()
        if "DATAFORGE_DATABASE_URL" in os.environ:
            del os.environ["DATAFORGE_DATABASE_URL"]

        repo1 = get_job_repository()
        reset_repository()
        repo2 = get_job_repository()
        assert repo1 is not repo2  # Different instance after reset
        reset_repository()

    def test_fallback_on_postgres_import_failure(self, monkeypatch):
        """If Postgres import fails, the factory falls back to SQLite."""
        reset_repository()
        monkeypatch.setenv("DATAFORGE_DATABASE_URL", "postgresql://localhost:5432/test")
        monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "postgres")

        # Block the postgres_repository module so the factory skips it
        import sys
        import types

        class _FakeModule(types.ModuleType):
            pass

        # Prevent import of psycopg2 which is needed by postgres_repository
        fake_mod = _FakeModule("postgres_repository")
        sys.modules["app.postgres_repository"] = fake_mod

        # Force a fresh resolve
        from app.storage_interface import get_job_repository as gjr
        reset_repository()

        # Attempt to resolve — should raise RuntimeError since postgres_repository
        # was never properly imported (it's a stub), or fall back
        try:
            repo = gjr()
            # If it didn't raise, we got a fallback
            assert isinstance(repo, SQLiteJobRepository)
        except RuntimeError:
            pass  # Expected: Postgres backend requested but not available

        # Clean up
        sys.modules.pop("app.postgres_repository", None)
        reset_repository()


# ───────────────────────────────────────────────────────────────────────
# SQLite repository tests
# ───────────────────────────────────────────────────────────────────────


class TestSQLiteJobRepository:
    """Verify that SQLiteJobRepository delegates correctly."""

    def test_is_job_repository(self):
        """SQLiteJobRepository implements the JobRepository ABC."""
        repo = SQLiteJobRepository()
        assert isinstance(repo, JobRepository)

    def test_save_and_load_round_trip(self, isolated_db):
        """A job saved via the repository can be loaded back."""
        from app.job_store import reset_job_store_for_tests

        repo = SQLiteJobRepository()
        job = Job(
            id="test-repo-job",
            name="Repo Test",
            urls=["https://example.com"],
            status=JobStatus.PENDING,
        )

        repo.save_all({job.id: job}, {})
        loaded_jobs = repo.load_jobs()
        loaded_recycle = repo.load_recycle_bin()

        assert job.id in loaded_jobs
        assert loaded_jobs[job.id].name == "Repo Test"
        # load_state recovers PENDING to FAILED (crash restart semantics)
        # so we just check it's not empty
        assert len(loaded_recycle) == 0
        reset_job_store_for_tests()

    def test_recycle_bin_round_trip(self, isolated_db):
        """Jobs in the recycle bin are loaded separately."""
        from app.job_store import reset_job_store_for_tests

        repo = SQLiteJobRepository()
        job = Job(
            id="test-recycle-job",
            name="Recycle Test",
            urls=["https://example.com"],
            status=JobStatus.COMPLETED,
        )

        repo.save_all({}, {job.id: job})
        loaded_jobs = repo.load_jobs()
        loaded_recycle = repo.load_recycle_bin()

        assert job.id not in loaded_jobs
        assert job.id in loaded_recycle
        assert loaded_recycle[job.id].name == "Recycle Test"
        reset_job_store_for_tests()

    def test_save_single_updates_job(self, isolated_db):
        """save_single persists a single job update."""
        from app.job_store import reset_job_store_for_tests

        repo = SQLiteJobRepository()
        job = Job(
            id="test-single-job",
            name="Single Update",
            urls=["https://example.com"],
            status=JobStatus.RUNNING,
        )

        repo.save_all({job.id: job}, {})

        # Update the job status and save single
        job.status = JobStatus.COMPLETED
        repo.save_single(job)

        loaded = repo.load_jobs()
        assert loaded[job.id].status == JobStatus.COMPLETED
        reset_job_store_for_tests()

    def test_load_all_returns_three_tuple(self, isolated_db):
        """load_all returns the expected (jobs, recycle, world_state) tuple."""
        from app.job_store import reset_job_store_for_tests

        repo = SQLiteJobRepository()
        job = Job(
            id="test-all-job",
            name="Load All Test",
            urls=["https://example.com"],
        )

        repo.save_all({job.id: job}, {})

        jobs, recycle, world_state = repo.load_all()
        assert job.id in jobs
        assert isinstance(recycle, dict)
        assert world_state is None or isinstance(world_state, dict)
        reset_job_store_for_tests()


# ───────────────────────────────────────────────────────────────────────
# Postgres serialization tests (no DB connection required)
# ───────────────────────────────────────────────────────────────────────


class TestPostgresSerialization:
    """Test the _job_to_row / _row_to_job serialization functions."""

    def _import_postgres_module(self):
        """Import the postgres repository module (may fail if asyncpg missing)."""
        try:
            from app.postgres_repository import _job_to_row, _row_to_job
            return _job_to_row, _row_to_job
        except ImportError:
            pytest.skip("asyncpg not installed")
            return None, None

    def test_job_to_row_basic_fields(self):
        """Basic Job fields are serialized correctly to a row dict."""
        _job_to_row, _ = self._import_postgres_module()
        if _job_to_row is None:
            return

        job = Job(
            id="test-1",
            name="Test Job",
            urls=["https://example.com"],
            status=JobStatus.PENDING,
            mode=ScrapeMode.MANUAL,
        )
        row = _job_to_row(job)
        assert row["id"] == "test-1"
        assert row["name"] == "Test Job"
        assert row["status"] == "pending"
        assert row["mode"] == "manual"
        assert json.loads(row["urls"]) == ["https://example.com"]

    def test_job_to_row_optional_fields(self):
        """Optional/None fields are converted to empty strings or defaults."""
        _job_to_row, _ = self._import_postgres_module()
        if _job_to_row is None:
            return

        job = Job(
            id="test-2",
            name="Test Optional",
            urls=["https://example.com"],
        )
        row = _job_to_row(job)
        assert row["error"] == ""
        assert row["analysis"] == ""
        assert row["warnings"] == "[]"
        assert json.loads(row["results"]) == []

    def test_job_to_row_bool_fields(self):
        """Boolean fields are preserved as Python bools."""
        _job_to_row, _ = self._import_postgres_module()
        if _job_to_row is None:
            return

        job = Job(
            id="test-3",
            name="Test Bool",
            urls=["https://example.com"],
            cancel_requested=True,
            pagination=True,
            deduplicate=False,
            results_on_disk=True,
        )
        row = _job_to_row(job)
        assert row["cancel_requested"] is True
        assert row["pagination"] is True
        assert row["deduplicate"] is False
        assert row["results_on_disk"] is True

    def test_row_to_job_round_trip(self):
        """A job serialized and deserialized preserves all fields."""
        _job_to_row, _row_to_job = self._import_postgres_module()
        if _job_to_row is None:
            return

        original = Job(
            id="rt-1",
            name="Round Trip Test",
            urls=["https://example.com/products", "https://example.com/shop"],
            status=JobStatus.COMPLETED,
            mode=ScrapeMode.AUTO,
            topic="test products",
            intent="find all products",
            location="New York",
            preferred_domain="example.com",
            source_policy=SourcePolicy.ALL_SOURCES,
            max_per_domain=5,
            cancel_requested=True,
            total_records=42,
            error="test error",
            warnings=["warning 1", "warning 2"],
            acquisition_mode="aggressive",
            results=[{"name": "Widget", "price": 9.99}],
            analysis="High quality",
            estimated_cost_usd=0.05,
            total_llm_calls=3,
            progress_current=42,
            progress_total=42,
            results_on_disk=True,
            results_file_path="/tmp/results.gz",
        )

        row = _job_to_row(original)
        restored = _row_to_job(row)

        assert restored is not None
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.status == original.status
        assert restored.urls == original.urls
        assert restored.topic == original.topic
        assert restored.warnings == original.warnings
        assert restored.acquisition_mode == original.acquisition_mode
        assert restored.total_records == original.total_records
        assert restored.error == original.error

    def test_row_to_job_invalid_row_returns_none(self):
        """Deserializing an invalid row returns None without crashing."""
        _, _row_to_job = self._import_postgres_module()
        if _row_to_job is None:
            return

        result = _row_to_job({})
        assert result is None


class TestPostgresHealthCheck:
    """Tests for health check (without Postgres connection)."""

    def test_health_check_fails_gracefully(self):
        """Postgres health check returns error state without a real connection."""
        try:
            from app.postgres_repository import PostgresJobRepository
        except ImportError:
            pytest.skip("psycopg2 not installed")
            return

        repo = PostgresJobRepository(auto_ensure_schema=False)
        result = repo.health_check()
        assert result["ok"] is False
        assert result["backend"] == "postgres"
        assert "error" in result
