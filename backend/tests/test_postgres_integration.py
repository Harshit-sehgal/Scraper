"""Real Postgres integration tests using testcontainers.

Requires Docker to be running. These tests are behind the '-m postgres' marker
and are skipped by default during CI.

Run with:
    python3 -m pytest backend/tests/test_postgres_integration.py -m postgres -v

Or to run all postgres-marked tests:
    python3 -m pytest -m postgres -v
"""

import os
import pytest

from app.models import Job, JobStatus, ScrapeMode, SourcePolicy
from app.storage_interface import get_job_repository, reset_repository


pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def postgres_container():
    """Start a Postgres container and configure the environment."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        database_url = pg.get_connection_url()
        os.environ["DATAFORGE_DATABASE_URL"] = database_url
        os.environ["DATAFORGE_STORAGE_BACKEND"] = "postgres"
        reset_repository()
        yield
        reset_repository()
        # Clean up env vars
        os.environ.pop("DATAFORGE_DATABASE_URL", None)
        os.environ.pop("DATAFORGE_STORAGE_BACKEND", None)


@pytest.fixture()
def clean_db(postgres_container):
    """Clean the Postgres database between tests."""
    from app.postgres_repository import _conn, _execute

    reset_repository()
    with _conn() as conn:
        _execute(conn, "DELETE FROM jobs")
        _execute(conn, "DELETE FROM recycle_bin")
        _execute(conn, "DELETE FROM schema_version")
    yield
    with _conn() as conn:
        _execute(conn, "DELETE FROM jobs")
        _execute(conn, "DELETE FROM recycle_bin")


# ───────────────────────────────────────────────────────────────────────
# Repository integration tests
# ───────────────────────────────────────────────────────────────────────


class TestPostgresJobRepositoryIntegration:
    """Full round-trip tests against a real Postgres instance."""

    def test_ping(self, postgres_container):
        """Smoke test: Postgres is reachable."""
        from app.postgres_repository import verify_postgres_connectivity

        result = verify_postgres_connectivity()
        assert result["ok"] is True, f"Postgres connectivity failed: {result}"

    def test_health_check_success(self, clean_db):
        """Health check returns healthy state with real Postgres."""
        repo = get_job_repository()
        health = repo.health_check()
        assert health["ok"] is True
        assert health["backend"] == "postgres"
        assert health["schema_version"] >= 1

    def test_health_check_on_fresh_empty_db(self, postgres_container):
        """health_check works on a fresh DB where no schema has been created yet."""
        from app.postgres_repository import PostgresJobRepository

        reset_repository()
        fresh_repo = PostgresJobRepository()
        # Don't call _ensure() — let health_check handle it
        health = fresh_repo.health_check()
        assert health["ok"] is True, f"Health check on fresh DB failed: {health}"
        assert health["backend"] == "postgres"
        assert health["schema_version"] >= 1
        assert health["job_count"] == 0
        assert health["recycle_bin_count"] == 0

    def test_recycle_bin_table_exists_after_schema_creation(self, postgres_container):
        """recycle_bin table is explicitly created in the Postgres schema."""
        from app.postgres_repository import PostgresJobRepository, _conn, _fetch_one

        reset_repository()
        repo = PostgresJobRepository()
        repo._ensure()

        # Verify the table exists by querying its structure
        with _conn() as conn:
            row = _fetch_one(
                conn,
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'recycle_bin'",
            )
            assert row is not None, "recycle_bin table does not exist in Postgres schema"

        # Also verify we can insert and read from it
        repo.save_all({}, {"test-id": Job(id="test-id", name="Recycle Test", urls=["https://example.com"])})
        _, recycle, _ = repo.load_all()
        assert "test-id" in recycle

    def test_factory_returns_postgres(self, postgres_container):
        """Factory returns PostgresJobRepository when configured."""
        from app.postgres_repository import PostgresJobRepository

        repo = get_job_repository()
        reset_repository()
        assert isinstance(repo, PostgresJobRepository)

    # ─── Save / Load round-trips ────────────────────────────────────────

    def test_save_single_and_load_all(self, clean_db):
        """save_single persists a job, load_all retrieves it."""
        repo = get_job_repository()
        reset_repository()

        job = Job(
            id="pg-int-test-1",
            name="Integration Test",
            urls=["https://example.com"],
            status=JobStatus.COMPLETED,
            mode=ScrapeMode.AUTO,
            topic="integration test",
            total_records=42,
            warnings=["test warning"],
            acquisition_mode="aggressive",
        )

        repo.save_single(job)
        jobs, recycle, world_state = repo.load_all()

        assert job.id in jobs
        loaded = jobs[job.id]
        assert loaded.name == "Integration Test"
        assert loaded.status == JobStatus.COMPLETED
        assert loaded.mode == ScrapeMode.AUTO
        assert loaded.topic == "integration test"
        assert loaded.total_records == 42
        assert loaded.warnings == ["test warning"]
        assert loaded.acquisition_mode == "aggressive"

    def test_save_all_load_all_full_job_parity(self, clean_db):
        """Every important Job field survives a save_all → load_all round-trip."""
        repo = get_job_repository()
        reset_repository()

        job = Job(
            id="pg-parity-1",
            name="Parity Test",
            mode=ScrapeMode.AUTO,
            intent="find all products",
            urls=["https://example.com/products", "https://example.com/shop"],
            topic="e-commerce products",
            location="New York",
            preferred_domain="example.com",
            source_policy=SourcePolicy.ALL_SOURCES,
            max_per_domain=3,
            origin_location="40.7128,-74.0060",
            max_distance_km=50.0,
            pagination=True,
            max_pages=5,
            deduplicate=False,
            deduplicate_field="url",
            min_record_score=0.7,
            cancel_requested=True,
            status=JobStatus.DEGRADED,
            created_at="2026-05-25T09:59:00",
            started_at="2026-05-25T10:00:00",
            completed_at="2026-05-25T10:05:00",
            total_records=42,
            filtered_records=38,
            error="partial scrape warning",
            results=[{"name": "Widget", "price": 9.99}],
            analysis="High quality results",
            estimated_cost_usd=0.05,
            total_llm_calls=3,
            progress_current=42,
            progress_total=42,
            results_on_disk=True,
            results_file_path="/tmp/results.gz",
            warnings=["warning1"],
            acquisition_mode="aggressive",
        )

        repo.save_all({job.id: job}, {})
        jobs, recycle, _ = repo.load_all()

        restored = jobs.get(job.id)
        assert restored is not None
        assert restored.model_dump(mode="json") == job.model_dump(mode="json")

    def test_recycle_bin_round_trip(self, clean_db):
        """Jobs in recycle bin are stored and loaded separately."""
        repo = get_job_repository()
        reset_repository()

        job = Job(
            id="pg-recycle-1",
            name="Recycle Test",
            urls=["https://example.com"],
            status=JobStatus.COMPLETED,
        )

        repo.save_all({}, {job.id: job})
        jobs, recycle, _ = repo.load_all()

        assert job.id not in jobs
        assert job.id in recycle

    def test_save_single_updates_existing(self, clean_db):
        """save_single updates an existing row."""
        repo = get_job_repository()
        reset_repository()

        job = Job(
            id="pg-update-1",
            name="Original",
            urls=["https://example.com"],
            status=JobStatus.RUNNING,
        )

        repo.save_single(job)
        job.status = JobStatus.COMPLETED
        job.total_records = 99
        repo.save_single(job)

        jobs, _, _ = repo.load_all()
        assert jobs["pg-update-1"].status == JobStatus.COMPLETED
        assert jobs["pg-update-1"].total_records == 99

    # ─── Restart recovery ──────────────────────────────────────────────

    def test_restart_recovery_persists_failed_status(self, clean_db):
        """On load_all, in-progress jobs are recovered and persisted to DB."""
        repo = get_job_repository()
        reset_repository()

        # Insert jobs in various states
        jobs_map = {
            Job(
                id="pg-rec-pending",
                name="Pending Job",
                urls=["https://example.com"],
                status=JobStatus.PENDING,
            ),
            Job(
                id="pg-rec-running",
                name="Running Job",
                urls=["https://example.com"],
                status=JobStatus.RUNNING,
            ),
            Job(
                id="pg-rec-completed",
                name="Completed Job",
                urls=["https://example.com"],
                status=JobStatus.COMPLETED,
            ),
        }
        for job in jobs_map:
            repo.save_single(job)

        # Simulate restart: create new repository
        from app.postgres_repository import PostgresJobRepository

        reset_repository()
        repo2 = PostgresJobRepository()
        jobs, _, _ = repo2.load_all()

        # PENDING and RUNNING should be FAILED
        assert jobs["pg-rec-pending"].status == JobStatus.FAILED
        assert jobs["pg-rec-running"].status == JobStatus.FAILED
        assert jobs["pg-rec-pending"].error == "Recovered after restart while still in progress."
        assert jobs["pg-rec-running"].error == "Recovered after restart while still in progress."

        # COMPLETED should remain COMPLETED
        assert jobs["pg-rec-completed"].status == JobStatus.COMPLETED

        # Verify recovery was persisted to DB
        reset_repository()
        repo3 = PostgresJobRepository()
        jobs_after_recovery, _, _ = repo3.load_all()
        assert jobs_after_recovery["pg-rec-pending"].status == JobStatus.FAILED
        assert jobs_after_recovery["pg-rec-running"].status == JobStatus.FAILED
