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

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


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


# ----------------------------------------------------------------------
# Factory tests
# ----------------------------------------------------------------------


class TestJobRepositoryFactory:
    """Tests for the get_job_repository() factory resolver."""

    def test_default_returns_sqlite(self) -> None:
        """Without DATAFORGE_DATABASE_URL, the factory returns SQLiteJobRepository."""
        reset_repository()
        if "DATAFORGE_DATABASE_URL" in os.environ:
            del os.environ["DATAFORGE_DATABASE_URL"]

        repo = get_job_repository()
        assert isinstance(repo, SQLiteJobRepository)
        reset_repository()

    def test_factory_caches_instance(self) -> None:
        """The factory caches and returns the same instance on repeated calls."""
        reset_repository()
        if "DATAFORGE_DATABASE_URL" in os.environ:
            del os.environ["DATAFORGE_DATABASE_URL"]

        repo1 = get_job_repository()
        repo2 = get_job_repository()
        assert repo1 is repo2  # Same instance
        reset_repository()

    def test_reset_repository_clears_cache(self) -> None:
        """reset_repository() clears the cached instance."""
        reset_repository()
        if "DATAFORGE_DATABASE_URL" in os.environ:
            del os.environ["DATAFORGE_DATABASE_URL"]

        repo1 = get_job_repository()
        reset_repository()
        repo2 = get_job_repository()
        assert repo1 is not repo2  # Different instance after reset
        reset_repository()

    def test_fallback_on_postgres_import_failure(self, monkeypatch) -> None:
        """If Postgres import fails, the factory falls back to SQLite."""
        reset_repository()
        monkeypatch.setenv("DATAFORGE_DATABASE_URL", "postgresql://localhost:5432/test")
        monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "postgres")

        import sys
        import types

        class _FakeModule(types.ModuleType):
            pass

        fake_mod = _FakeModule("postgres_repository")
        sys.modules["app.postgres_repository"] = fake_mod

        from app.storage_interface import get_job_repository as gjr

        reset_repository()

        try:
            repo = gjr()
            assert isinstance(repo, SQLiteJobRepository)
        except RuntimeError:
            pass  # Expected: Postgres backend requested but not available

        sys.modules.pop("app.postgres_repository", None)
        reset_repository()


# ----------------------------------------------------------------------
# SQLite repository tests
# ----------------------------------------------------------------------


class TestSQLiteJobRepository:
    """Verify that SQLiteJobRepository delegates correctly."""

    def test_is_job_repository(self) -> None:
        """SQLiteJobRepository implements the JobRepository ABC."""
        repo = SQLiteJobRepository()
        assert isinstance(repo, JobRepository)

    def test_save_and_load_round_trip(self, isolated_db) -> None:
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
        assert len(loaded_recycle) == 0
        reset_job_store_for_tests()

    def test_recycle_bin_round_trip(self, isolated_db) -> None:
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

    def test_save_single_updates_job(self, isolated_db) -> None:
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

        job.status = JobStatus.COMPLETED
        repo.save_single(job)

        loaded = repo.load_jobs()
        assert loaded[job.id].status == JobStatus.COMPLETED
        reset_job_store_for_tests()

    def test_load_all_returns_three_tuple(self, isolated_db) -> None:
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


# ----------------------------------------------------------------------
# Postgres serialization tests (no DB connection required)
# ----------------------------------------------------------------------


class TestPostgresSerialization:
    """Test the job_to_row / row_to_job serialization functions."""

    def _import_postgres_module(self):
        try:
            # The serialization helpers were moved to app.postgres_repository_base
            # during Phase C deduplication and renamed (no leading underscore)
            # to signal they are part of the module's public surface.
            from app.postgres_repository_base import job_to_row, row_to_job

            return job_to_row, row_to_job
        except ImportError:
            pytest.skip("psycopg2 not installed")
            return None, None

    def test_job_to_row_basic_fields(self) -> None:
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

    def test_job_to_row_optional_fields(self) -> None:
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

    def test_job_to_row_preserves_created_by(self) -> None:
        _job_to_row, _ = self._import_postgres_module()
        if _job_to_row is None:
            return

        job = Job(
            id="test-owner",
            name="Owned Job",
            urls=["https://example.com"],
            created_by="owner-fingerprint",
        )

        row = _job_to_row(job)

        assert row["created_by"] == "owner-fingerprint"

    def test_job_to_row_bool_fields(self) -> None:
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

    def test_row_to_job_round_trip(self) -> None:
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
            results_file_path="/tmp/results.gz",  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
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

    def test_row_to_job_preserves_org_id_and_project_id(self) -> None:
        """P0-SAAS-001: tenant ownership columns round-trip through the row mapping."""
        from app.postgres_repository_base import row_to_job

        row: dict[str, object] = {
            "id": "saas-test-job",
            "name": "SaaS tenant job",
            "status": "completed",
            "mode": "manual",
            "topic": "",
            "intent": "",
            "urls": "[]",
            "schema_fields": "[]",
            "filters": "[]",
            "results": "[]",
            "logs": "[]",
            "total_records": 0,
            "filtered_records": 0,
            "total_llm_calls": 0,
            "error": "",
            "warnings": "[]",
            "quality_report": "{}",
            "analysis": "",
            "discovered_urls": "[]",
            "selectors_map": "{}",
            "search_params": "{}",
            "max_pages": 0,
            "progress_current": 0,
            "progress_total": 0,
            "estimated_cost_usd": 0,
            "cancel_requested": False,
            "created_by": "user-uuid-abc",
            "org_id": "org-uuid-123",
            "project_id": "project-uuid-456",
            "created_at": "2026-06-11T10:00:00+00:00",
            "completed_at": "",
            "min_record_score": 0.35,
            "acquisition_mode": "standard",
            "location": "",
            "preferred_domain": "",
            "source_policy": "all_sources",
            "max_per_domain": 4,
            "origin_location": "",
            "max_distance_km": None,
            "pagination": False,
            "deduplicate": True,
            "deduplicate_field": "",
            "started_at": "",
            "results_on_disk": False,
            "results_file_path": "",
            "updated_at": "",
            "deleted_at": None,
        }
        restored = row_to_job(row)
        assert restored is not None
        assert restored.org_id == "org-uuid-123"
        assert restored.project_id == "project-uuid-456"
        assert restored.created_by == "user-uuid-abc"

    def test_job_to_row_includes_org_id_and_project_id(self) -> None:
        """P0-SAAS-001: job_to_row must include the new tenant columns."""
        from app.models import Job, JobStatus, ScrapeMode
        from app.postgres_repository_base import job_to_row

        job = Job(
            id="saas-write-job",
            name="SaaS write job",
            mode=ScrapeMode.MANUAL,
            urls=["https://example.com/data"],
            status=JobStatus.COMPLETED,
            created_by="user-uuid-xyz",
            org_id="org-uuid-789",
            project_id="project-uuid-012",
        )
        row = job_to_row(job)
        assert row["org_id"] == "org-uuid-789"
        assert row["project_id"] == "project-uuid-012"
        assert row["created_by"] == "user-uuid-xyz"

    def test_row_to_job_preserves_created_by(self) -> None:
        _job_to_row, _row_to_job = self._import_postgres_module()
        if _job_to_row is None:
            return

        row = _job_to_row(
            Job(
                id="rt-owner",
                name="Owner Round Trip",
                urls=["https://example.com"],
            ),
        )
        row["created_by"] = "owner-fingerprint"

        restored = _row_to_job(row)

        assert restored is not None
        assert restored.created_by == "owner-fingerprint"

    def test_row_to_job_invalid_row_returns_none(self) -> None:
        _, _row_to_job = self._import_postgres_module()
        if _row_to_job is None:
            return

        result = _row_to_job({})
        assert result is None

    # Note: ``deleted_at`` is NOT in the shared mapper output (ARCH-004).
    # It is stamped by the Postgres save methods (save_all,
    # move_to_recycle_bin, clear_terminal_jobs) after calling job_to_row.
    # See postgres_repository_base for the inline stamping.


class TestPostgresSchemaRepair:
    """Tests for Postgres schema repair logic (no DB connection required)."""

    def _import(self):
        try:
            # These helpers were moved to app.postgres_repository_base during
            # Phase C deduplication and renamed (no leading underscore) to
            # signal they are part of the module's public surface.
            from app.postgres_repository_base import (
                build_create_jobs_sql,
                build_create_recycle_bin_sql,
                ensure_required_tables,
            )

            return ensure_required_tables, build_create_jobs_sql, build_create_recycle_bin_sql
        except ImportError:
            pytest.skip("psycopg2 not installed")
            return None, None, None

    def test_build_create_jobs_includes_status_column(self) -> None:
        _, build_jobs, _ = self._import()
        if build_jobs is None:
            return
        sql = build_jobs()
        assert "CREATE TABLE IF NOT EXISTS jobs" in sql
        assert "id TEXT PRIMARY KEY" in sql
        assert "name TEXT NOT NULL" in sql
        assert "mode TEXT DEFAULT 'manual'" in sql
        assert "cancel_requested" in sql
        assert "source_policy" in sql

    def test_shared_jobs_schema_includes_created_by(self) -> None:
        from app.storage_interface import _JOBS_COLUMNS_SQL

        assert any(col.startswith("created_by TEXT") for col in _JOBS_COLUMNS_SQL)

    def test_build_create_jobs_includes_created_by_column(self) -> None:
        _, build_jobs, build_recycle = self._import()
        if build_jobs is None or build_recycle is None:
            return

        assert "created_by TEXT" in build_jobs()
        assert "created_by TEXT" in build_recycle()

    def test_ensure_required_tables_creates_created_by_index(self, monkeypatch) -> None:
        import app.postgres_repository_base as pg_base

        statements: list[str] = []

        def capture_execute(_conn, sql: str, _params=None):
            statements.append(sql)

        monkeypatch.setattr(pg_base, "execute", capture_execute)

        pg_base.ensure_required_tables(object())

        assert any("idx_jobs_created_by" in statement for statement in statements)

    def test_build_create_recycle_includes_columns(self) -> None:
        _, _, build_recycle = self._import()
        if build_recycle is None:
            return
        sql = build_recycle()
        assert "CREATE TABLE IF NOT EXISTS recycle_bin" in sql
        assert "id TEXT PRIMARY KEY" in sql
        assert "name TEXT NOT NULL" in sql
        assert sql.count("\n        mode TEXT DEFAULT 'manual'") == 1
        assert "deleted_at" in sql

    def test_ensure_required_tables_syntax_valid(self) -> None:
        ensure, build_jobs, build_recycle = self._import()
        if ensure is None:
            return
        jobs_sql = build_jobs()
        recycle_sql = build_recycle()
        assert jobs_sql.count("CREATE TABLE") == 1
        assert recycle_sql.count("CREATE TABLE") == 1
        assert jobs_sql.count("(") == jobs_sql.count(")")
        assert recycle_sql.count("(") == recycle_sql.count(")")

    def test_current_schema_version_is_2(self) -> None:
        try:
            from app.postgres_repository_base import _CURRENT_SCHEMA_VERSION

            assert _CURRENT_SCHEMA_VERSION >= 2
        except ImportError:
            pytest.skip("psycopg2 not installed")


class TestPostgresHealthCheck:
    """Tests for health check (without Postgres connection)."""

    def test_health_check_fails_gracefully(self) -> None:
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


# ----------------------------------------------------------------------
# Postgres integration tests (require Docker + --run-postgres)
# ----------------------------------------------------------------------


@pytest.mark.postgres
class TestPostgresIntegration:
    """Real Postgres integration tests using testcontainers.

    These tests require Docker and are skipped by default.
    Run with: pytest --run-postgres -m postgres -v
    """

    @pytest.fixture(autouse=True)
    def postgres_container(self):
        """Start a Postgres testcontainer or reuse a running one."""
        import socket

        from app.postgres_repository import _close_pool
        from app.storage_interface import reset_repository

        _close_pool()
        reset_repository()

        use_running = False
        dsn = os.environ.get("DATAFORGE_DATABASE_URL")
        if dsn:
            use_running = True
        else:
            try:
                with socket.create_connection(("127.0.0.1", 5432), timeout=1):
                    use_running = True
                    os.environ["DATAFORGE_STORAGE_BACKEND"] = "postgres"
                    os.environ["DATAFORGE_DATABASE_URL"] = "postgresql://testuser:testpassword@127.0.0.1:5432/testdb"
                    os.environ["PGPASSWORD"] = "testpassword"
            except (TimeoutError, ConnectionRefusedError):
                pass

        if use_running:
            try:
                yield
            finally:
                _close_pool()
                reset_repository()
                if not dsn:
                    os.environ.pop("DATAFORGE_STORAGE_BACKEND", None)
                    os.environ.pop("DATAFORGE_DATABASE_URL", None)
                    os.environ.pop("PGPASSWORD", None)
        else:
            from testcontainers.postgres import PostgresContainer

            with PostgresContainer("postgres:16-alpine") as pg:
                os.environ["DATAFORGE_STORAGE_BACKEND"] = "postgres"
                os.environ["DATAFORGE_DATABASE_URL"] = pg.get_connection_url().replace("+psycopg2", "")
                os.environ["PGPASSWORD"] = pg.password
                try:
                    yield
                finally:
                    _close_pool()
                    reset_repository()
                    os.environ.pop("DATAFORGE_STORAGE_BACKEND", None)
                    os.environ.pop("DATAFORGE_DATABASE_URL", None)
                    os.environ.pop("PGPASSWORD", None)

    def _setup_v1_schema(self, conn) -> None:
        """Create a minimal v1 schema (jobs table but no recycle_bin)."""
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
            cur.execute("DELETE FROM schema_version")
            cur.execute("INSERT INTO schema_version (version) VALUES (1)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    mode TEXT NOT NULL DEFAULT 'manual',
                    urls TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT DEFAULT ''
                )
            """)
        conn.commit()

    def test_postgres_repairs_missing_recycle_bin_when_schema_version_is_current(self) -> None:
        """When schema_version=1 and recycle_bin is missing, _ensure_schema() creates it."""
        import psycopg2

        dsn = os.environ["DATAFORGE_DATABASE_URL"]
        if dsn.startswith("postgresql+psycopg2://"):
            dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
        conn = psycopg2.connect(dsn)
        try:
            self._setup_v1_schema(conn)
        finally:
            conn.close()

        # Reset the module-level pool so the repo uses our container
        from app.postgres_repository import _close_pool

        _close_pool()
        from app.storage_interface import reset_repository

        reset_repository()

        from app.postgres_repository import PostgresJobRepository

        repo = PostgresJobRepository()

        # Trigger schema ensure + health check
        health = repo.health_check()
        assert health["ok"] is True, f"Health check failed: {health}"
        from app.postgres_repository_base import _CURRENT_SCHEMA_VERSION

        assert health["schema_version"] == _CURRENT_SCHEMA_VERSION, (
            f"Expected schema_version={_CURRENT_SCHEMA_VERSION}, got {health['schema_version']}"
        )

        # Verify recycle_bin table exists
        health2 = repo.health_check()
        assert "recycle_bin_count" in health2

        # Verify we can insert into recycle_bin
        from app.models import Job, JobStatus

        recycled = Job(
            id="recycled-after-repair",
            name="Repair Test",
            urls=["https://example.com"],
            status=JobStatus.COMPLETED,
        )
        repo.save_all({}, {recycled.id: recycled})
        _, loaded_recycle, _ = repo.load_all()
        assert recycled.id in loaded_recycle, "Recycle bin should accept entries after repair"

        _close_pool()
        reset_repository()

    def test_postgres_save_single_restores_soft_deleted_job_id(self) -> None:
        """Saving an active job over a soft-deleted ID should restore visibility."""
        import psycopg2

        dsn = os.environ["DATAFORGE_DATABASE_URL"]
        if dsn.startswith("postgresql+psycopg2://"):
            dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
        conn = psycopg2.connect(dsn)
        try:
            self._setup_v1_schema(conn)
        finally:
            conn.close()

        from app.postgres_repository import _close_pool

        _close_pool()
        from app.storage_interface import reset_repository

        reset_repository()

        from app.postgres_repository import PostgresJobRepository

        repo = PostgresJobRepository()

        # Insert a job, then soft-delete it
        from app.models import Job, JobStatus

        job = Job(
            id="soft-delete-test",
            name="Will Be Deleted",
            urls=["https://example.com"],
            status=JobStatus.COMPLETED,
        )
        repo.save_all({job.id: job}, {})

        # Move to recycle bin (simulates soft delete)
        repo.save_all({}, {job.id: job})

        # Verify it's gone from active jobs
        active_jobs, _, _ = repo.load_all()
        assert job.id not in active_jobs, "Job should be hidden after soft delete"

        # Now save an active job with the same ID (simulating restore)
        restored_job = Job(
            id="soft-delete-test",
            name="Restored Job",
            urls=["https://example.com"],
            status=JobStatus.PENDING,
        )
        repo.save_single(restored_job)

        # Verify it's visible again
        loaded, _, _ = repo.load_all()
        assert restored_job.id in loaded, "Job should be visible after save_single over soft-deleted ID"
        assert loaded[restored_job.id].name == "Restored Job"

        _close_pool()
        reset_repository()
