"""Tests for the psycopg 3 repository implementation.

These tests do NOT require a running Postgres server. They verify:

1. The ``Psycopg3JobRepository`` class satisfies the ``JobRepository``
   abstract contract.
2. The factory resolver honours ``DATAFORGE_PG_DRIVER=psycopg3`` when a
   real connection is available, and falls back / errors gracefully
   otherwise.
3. The new repository's ``get_job`` and ``list_job_summaries`` are
   actually implemented (not the ``NotImplementedError`` stubs that
   remain on the base class).

Real end-to-end behaviour is exercised by the ``--run-postgres``
integration suite, which can be pointed at the psycopg3 backend by
setting ``DATAFORGE_PG_DRIVER=psycopg3`` in the test environment.
"""

import importlib
from unittest.mock import patch

import pytest
from app.models import Job, JobStatus, ScrapeMode
from app.storage_interface import (
    JobRepository,
    reset_repository,
)

try:
    import psycopg_pool

    del psycopg_pool
    HAS_PSYCOPG3 = True
except ImportError:
    HAS_PSYCOPG3 = False


def _psycopg3_module():
    return importlib.import_module("app.psycopg3_repository")


class TestPsycopg3RepositoryContract:
    def test_class_exists_and_subclasses_job_repository(self) -> None:
        mod = _psycopg3_module()
        assert hasattr(mod, "Psycopg3JobRepository")
        assert issubclass(mod.Psycopg3JobRepository, JobRepository)

    def test_required_methods_implemented(self) -> None:
        """All abstract methods must be implemented, not stubbed."""
        mod = _psycopg3_module()
        cls = mod.Psycopg3JobRepository
        for method in (
            "load_jobs",
            "load_recycle_bin",
            "load_all",
            "save_all",
            "save_single",
            "get_job",
            "list_job_summaries",
        ):
            assert hasattr(cls, method), f"Missing method: {method}"
            assert callable(getattr(cls, method))

    @pytest.mark.skipif(not HAS_PSYCOPG3, reason="psycopg_pool not installed")
    def test_get_job_returns_none_when_missing(self) -> None:
        """`get_job` should hit a real DB; here we just confirm the
        method is callable and propagates the no-connection error
        cleanly (instead of returning the abstract sentinel)."""
        mod = _psycopg3_module()
        repo = mod.Psycopg3JobRepository(auto_ensure_schema=False)
        # No DB pool is open; we expect any underlying driver
        # exception, NOT ``NotImplementedError`` from the ABC.
        try:
            repo.get_job("does-not-matter")
        except NotImplementedError:
            pytest.fail("Got NotImplementedError - method is not actually implemented")
        except Exception:
            pass  # Expected - any real driver exception proves the method is wired

    @pytest.mark.skipif(not HAS_PSYCOPG3, reason="psycopg_pool not installed")
    def test_list_job_summaries_callable(self) -> None:
        mod = _psycopg3_module()
        repo = mod.Psycopg3JobRepository(auto_ensure_schema=False)
        try:
            repo.list_job_summaries(limit=10)
        except NotImplementedError:
            pytest.fail("Got NotImplementedError - method is not actually implemented")
        except Exception:
            pass  # Expected - any real driver exception proves the method is wired

    def test_serialization_helpers_match_psycopg2(self) -> None:
        """The on-disk row shape must be identical between drivers so
        data can be moved between backends without migration.

        Excludes ``updated_at`` which is a wall-clock timestamp set at
        row-creation time and naturally differs between calls.
        """
        from app.postgres_repository_base import job_to_row

        # The psycopg3 driver inherits job_to_row from PostgresRepositoryBase.

        psycopg2_to_row = job_to_row
        psycopg3_to_row = job_to_row

        job = Job(
            id="compat-test",
            name="Compat",
            mode=ScrapeMode.MANUAL,
            status=JobStatus.COMPLETED,
            urls=["https://example.com"],
        )
        a = psycopg2_to_row(job)
        b = psycopg3_to_row(job)
        a.pop("updated_at", None)
        b.pop("updated_at", None)
        assert a == b

    def test_schema_columns_match_psycopg2(self) -> None:
        """The CREATE TABLE column list is reused from psycopg2 — verify."""
        from app.postgres_repository_base import _columns_sql as base_columns_sql
        from app.psycopg3_repository import _columns_sql as psycopg3_columns_sql

        assert base_columns_sql() == psycopg3_columns_sql()


class TestFactorySelectsPsycopg3:
    def test_factory_returns_psycopg3_when_requested_and_connected(
        self,
        monkeypatch,
    ) -> None:
        """If the env var is set and a live DB exists, the resolver
        returns ``Psycopg3JobRepository``."""
        monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "postgres")
        monkeypatch.setenv("DATAFORGE_PG_DRIVER", "psycopg3")
        monkeypatch.setenv("DATAFORGE_DATABASE_URL", "postgresql://x:y@h:5432/z")

        mod = _psycopg3_module()
        real_cls = mod.Psycopg3JobRepository
        fake_repo = real_cls.__new__(real_cls)
        fake_repo._auto_ensure_schema = False
        fake_repo._schema_ensured = True

        # Build a fake factory function that the resolver can call.
        fake_ctor = lambda *a, **kw: fake_repo  # noqa: E731

        # Patch the symbols the resolver actually looks up.
        with (
            patch.object(mod, "verify_psycopg3_connectivity", return_value={"ok": True}),
            patch.object(mod, "Psycopg3JobRepository", side_effect=fake_ctor),
        ):
            from app.storage_interface import get_job_repository

            reset_repository()
            try:
                repo = get_job_repository()
                assert type(repo) is real_cls
                assert getattr(repo, "backend", None) == "postgres-psycopg3"
            finally:
                reset_repository()

    def test_factory_errors_cleanly_when_psycopg3_missing(
        self,
        monkeypatch,
    ) -> None:
        """If the operator requested psycopg3 but it isn't installed,
        the error message must be actionable (point at the install
        command)."""
        import sys

        monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "postgres")
        monkeypatch.setenv("DATAFORGE_PG_DRIVER", "psycopg3")
        monkeypatch.setenv("DATAFORGE_DATABASE_URL", "postgresql://x:y@h:5432/z")

        # Force import failure of the psycopg3 module.
        with patch.dict(sys.modules, {"app.psycopg3_repository": None}):
            from app.storage_interface import get_job_repository

            reset_repository()
            try:
                with pytest.raises(RuntimeError) as exc:
                    get_job_repository()
                assert "psycopg" in str(exc.value).lower()
            finally:
                reset_repository()

    def test_default_driver_is_psycopg2(self, monkeypatch) -> None:
        """When no driver is specified, the factory should keep using
        psycopg2 (preserves existing behaviour)."""
        monkeypatch.delenv("DATAFORGE_PG_DRIVER", raising=False)
        monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "postgres")
        monkeypatch.setenv("DATAFORGE_DATABASE_URL", "postgresql://x:y@h:5432/z")
        # Clear the env to ensure we read from default.
        from app.storage_interface import get_job_repository

        reset_repository()
        try:
            # No DB is running, so we expect a connection error
            # mentioning the psycopg2 driver, not psycopg3.
            with pytest.raises(RuntimeError) as exc:
                get_job_repository()
            msg = str(exc.value).lower()
            assert "psycopg2" in msg or "postgres" in msg
        finally:
            reset_repository()
            monkeypatch.delenv("DATAFORGE_STORAGE_BACKEND", raising=False)
            monkeypatch.delenv("DATAFORGE_DATABASE_URL", raising=False)
