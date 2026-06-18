# backend_full_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T19:11:07.219580+00:00
- end_time: 2026-06-16T19:15:15.870367+00:00
- duration_seconds: 248.65
- exit_code: 1
- timeout_seconds: 600
- required: true
- redaction_applied: false

## stdout

```text
........................................................................ [  1%]
........................................................................ [  3%]
....................................F................................... [  5%]
........................................................................ [  7%]
........................................................................ [  9%]
........................................................................ [ 11%]
........................................................................ [ 13%]
........................................................................ [ 15%]
........................................................................ [ 17%]
..............................s......................................... [ 19%]
........................................................................ [ 21%]
........................................................................ [ 23%]
........................................................................ [ 25%]
........................................................................ [ 27%]
........................................................................ [ 29%]
........................................................................ [ 31%]
.....ssssssss........................................................... [ 33%]
......................................................................s. [ 35%]
................s....................................................... [ 37%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 48%]
...............................ssssssssssssssssssssss...F............... [ 50%]
.......sss.............................................................. [ 52%]
...........ss..................................F.FF..................... [ 54%]
........................................................................ [ 56%]
........................................................................ [ 58%]
..........................sssssssssssss................................. [ 60%]
..s..................................................................... [ 62%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 82%]
....sssssss............................................................. [ 83%]
........................................................................ [ 85%]
..........................................F............................. [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
.......................................................................s [ 95%]
...................ss..sssssssssssssssssss.............................. [ 97%]
........................................................................ [ 99%]
...............                                                          [100%]
=================================== FAILURES ===================================
______________________________ test_no_stale_pyc _______________________________

    def test_no_stale_pyc() -> None:
        """No .pyc files without corresponding .py source."""
        app_dir = _app_path("app")
        pyc_files = []
        for root, _dirs, files in os.walk(app_dir):
            for f in files:
                if f.endswith(".pyc"):
                    # Convert __pycache__/file.cpython-312.pyc -> file.py
                    py_name = f.split(".")[0] + ".py"
                    # The source file could be in the parent directory or a sibling
                    parent = os.path.dirname(root)  # app if root is app/__pycache__
                    py_path = os.path.join(parent, py_name)
                    if not os.path.exists(py_path):
                        pyc_files.append(os.path.join(root, f))

>       assert not pyc_files, f"Stale .pyc files: {pyc_files}. These will be loaded instead of current source."
E       AssertionError: Stale .pyc files: ['backend/app/utils/__pycache__/workflow_store.cpython-312.pyc']. These will be loaded instead of current source.
E       assert not ['backend/app/utils/__pycache__/workflow_store.cpython-312.pyc']

backend/tests/test_architecture_invariants.py:224: AssertionError
______ TestJobRepositoryFactory.test_fallback_on_postgres_import_failure _______

self = <tests.test_postgres_repository.TestJobRepositoryFactory object at 0x791608f50ce0>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7916031d1d00>

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
>           repo = gjr()
                   ^^^^^

backend/tests/test_postgres_repository.py:103:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    def get_job_repository() -> JobRepository:
        """Resolve the appropriate JobRepository based on configuration.

        Returns:
            PostgresJobRepository if DATAFORGE_STORAGE_BACKEND=postgres is set
            (and DATAFORGE_DATABASE_URL points to a running instance),
            otherwise SQLiteJobRepository.

        The repository is cached as a module-level singleton so that
        all callers share the same instance.

        """
        # Fast-path check: avoid acquiring the lock on every call.
        global _repository_instance
        if _repository_instance is not None:
            return _repository_instance

        with _REPOSITORY_LOCK:
            # Re-check under the lock to avoid duplicate initialisation when
            # two threads race the first call.
            if _repository_instance is not None:
                return _repository_instance

            from app.config import settings

            storage_backend = settings.STORAGE_BACKEND

            if storage_backend == "postgres":
                database_url = settings.DATABASE_URL
                if not database_url:
                    msg = (
                        "DATAFORGE_STORAGE_BACKEND=postgres requires DATAFORGE_DATABASE_URL "
                        "to be set. Example: postgresql://user:pass@host:5432/dataforge"
                    )
                    raise RuntimeError(
                        msg,
                    )
                # Phase A: driver selection via DATAFORGE_PG_DRIVER. Defaults to
                # psycopg2 in dev (preserves existing behaviour) but FAILS FAST in
                # production if not set, because the production image ships only
                # psycopg3 and psycopg2 would crash the worker on first use.
                pg_driver_env = os.environ.get("DATAFORGE_PG_DRIVER", "").strip().lower()
                if not pg_driver_env and settings.ENV.lower() == "production":
                    msg = (
                        "DATAFORGE_PG_DRIVER is not set. Production requires "
                        "DATAFORGE_PG_DRIVER=psycopg3 because the production image "
                        "installs only psycopg3 (psycopg2 is intentionally excluded). "
                        "Set DATAFORGE_PG_DRIVER=psycopg3 in the dataforge and worker "
                        "service environment in docker-compose.prod.yml."
                    )
                    raise RuntimeError(
                        msg,
                    )
                pg_driver = pg_driver_env or "psycopg2"

                if pg_driver == "psycopg3":
                    try:
                        from app.psycopg3_repository import (
                            Psycopg3JobRepository,
                            verify_psycopg3_connectivity,
                        )

                        connectivity = verify_psycopg3_connectivity()
                        if not connectivity.get("ok"):
                            msg = (
                                f"Postgres (psycopg3) connectivity check failed: "
                                f"{connectivity.get('error', 'unknown error')}. "
                                "Cannot use Postgres backend. Check DATAFORGE_DATABASE_URL "
                                "and ensure the database is running."
                            )
                            raise RuntimeError(msg)
                        repo: JobRepository = Psycopg3JobRepository()
                        _repository_instance = repo
                        logger.info("Using Psycopg3JobRepository (STORAGE_BACKEND=postgres, PG_DRIVER=psycopg3)")
                        return repo
                    except RuntimeError:
                        raise
                    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as e:
                        msg = (
                            f"Failed to create Psycopg3JobRepository: {e}. "
                            "Install psycopg 3 with: pip install 'psycopg[binary,pool]>=3.2'"
                        )
                        raise RuntimeError(msg) from e

                try:
>                   from app.postgres_repository import (
                        PostgresJobRepository,
                        verify_postgres_connectivity,
                    )
E                   ImportError: cannot import name 'PostgresJobRepository' from 'postgres_repository' (unknown location)

backend/app/storage_interface.py:989: ImportError
______ TestPsycopg3RepositoryContract.test_schema_columns_match_psycopg2 _______

self = <tests.test_psycopg3_repository.TestPsycopg3RepositoryContract object at 0x791608e71040>

    def test_schema_columns_match_psycopg2(self) -> None:
        """The CREATE TABLE column list is reused from psycopg2 — verify."""
>       from app.postgres_repository import PostgresJobRepository
E       ImportError: cannot import name 'PostgresJobRepository' from 'postgres_repository' (unknown location)

backend/tests/test_psycopg3_repository.py:121: ImportError
_ TestFactorySelectsPsycopg3.test_factory_errors_cleanly_when_psycopg3_missing _

self = <tests.test_psycopg3_repository.TestFactorySelectsPsycopg3 object at 0x791608e719d0>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x791601950740>

    def test_factory_errors_cleanly_when_psycopg3_missing(
        self,
        monkeypatch,
    ) -> None:
        """If the operator requested psycopg3 but it isn't installed,
        the error message must be actionable (point at the install
        command).
        """
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
>                   get_job_repository()

backend/tests/test_psycopg3_repository.py:187:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    def get_job_repository() -> JobRepository:
        """Resolve the appropriate JobRepository based on configuration.

        Returns:
            PostgresJobRepository if DATAFORGE_STORAGE_BACKEND=postgres is set
            (and DATAFORGE_DATABASE_URL points to a running instance),
            otherwise SQLiteJobRepository.

        The repository is cached as a module-level singleton so that
        all callers share the same instance.

        """
        # Fast-path check: avoid acquiring the lock on every call.
        global _repository_instance
        if _repository_instance is not None:
            return _repository_instance

        with _REPOSITORY_LOCK:
            # Re-check under the lock to avoid duplicate initialisation when
            # two threads race the first call.
            if _repository_instance is not None:
                return _repository_instance

            from app.config import settings

            storage_backend = settings.STORAGE_BACKEND

            if storage_backend == "postgres":
                database_url = settings.DATABASE_URL
                if not database_url:
                    msg = (
                        "DATAFORGE_STORAGE_BACKEND=postgres requires DATAFORGE_DATABASE_URL "
                        "to be set. Example: postgresql://user:pass@host:5432/dataforge"
                    )
                    raise RuntimeError(
                        msg,
                    )
                # Phase A: driver selection via DATAFORGE_PG_DRIVER. Defaults to
                # psycopg2 in dev (preserves existing behaviour) but FAILS FAST in
                # production if not set, because the production image ships only
                # psycopg3 and psycopg2 would crash the worker on first use.
                pg_driver_env = os.environ.get("DATAFORGE_PG_DRIVER", "").strip().lower()
                if not pg_driver_env and settings.ENV.lower() == "production":
                    msg = (
                        "DATAFORGE_PG_DRIVER is not set. Production requires "
                        "DATAFORGE_PG_DRIVER=psycopg3 because the production image "
                        "installs only psycopg3 (psycopg2 is intentionally excluded). "
                        "Set DATAFORGE_PG_DRIVER=psycopg3 in the dataforge and worker "
                        "service environment in docker-compose.prod.yml."
                    )
                    raise RuntimeError(
                        msg,
                    )
                pg_driver = pg_driver_env or "psycopg2"

                if pg_driver == "psycopg3":
                    try:
>                       from app.psycopg3_repository import (
                            Psycopg3JobRepository,
                            verify_psycopg3_connectivity,
                        )
E                       ModuleNotFoundError: import of app.psycopg3_repository halted; None in sys.modules

backend/app/storage_interface.py:961: ModuleNotFoundError
__________ TestFactorySelectsPsycopg3.test_default_driver_is_psycopg2 __________

self = <tests.test_psycopg3_repository.TestFactorySelectsPsycopg3 object at 0x791608e71e50>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x791603fe74d0>

    def test_default_driver_is_psycopg2(self, monkeypatch) -> None:
        """When no driver is specified, the factory should keep using
        psycopg2 (preserves existing behaviour).
        """
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
>               get_job_repository()

backend/tests/test_psycopg3_repository.py:207:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    def get_job_repository() -> JobRepository:
        """Resolve the appropriate JobRepository based on configuration.

        Returns:
            PostgresJobRepository if DATAFORGE_STORAGE_BACKEND=postgres is set
            (and DATAFORGE_DATABASE_URL points to a running instance),
            otherwise SQLiteJobRepository.

        The repository is cached as a module-level singleton so that
        all callers share the same instance.

        """
        # Fast-path check: avoid acquiring the lock on every call.
        global _repository_instance
        if _repository_instance is not None:
            return _repository_instance

        with _REPOSITORY_LOCK:
            # Re-check under the lock to avoid duplicate initialisation when
            # two threads race the first call.
            if _repository_instance is not None:
                return _repository_instance

            from app.config import settings

            storage_backend = settings.STORAGE_BACKEND

            if storage_backend == "postgres":
                database_url = settings.DATABASE_URL
                if not database_url:
                    msg = (
                        "DATAFORGE_STORAGE_BACKEND=postgres requires DATAFORGE_DATABASE_URL "
                        "to be set. Example: postgresql://user:pass@host:5432/dataforge"
                    )
                    raise RuntimeError(
                        msg,
                    )
                # Phase A: driver selection via DATAFORGE_PG_DRIVER. Defaults to
                # psycopg2 in dev (preserves existing behaviour) but FAILS FAST in
                # production if not set, because the production image ships only
                # psycopg3 and psycopg2 would crash the worker on first use.
                pg_driver_env = os.environ.get("DATAFORGE_PG_DRIVER", "").strip().lower()
                if not pg_driver_env and settings.ENV.lower() == "production":
                    msg = (
                        "DATAFORGE_PG_DRIVER is not set. Production requires "
                        "DATAFORGE_PG_DRIVER=psycopg3 because the production image "
                        "installs only psycopg3 (psycopg2 is intentionally excluded). "
                        "Set DATAFORGE_PG_DRIVER=psycopg3 in the dataforge and worker "
                        "service environment in docker-compose.prod.yml."
                    )
                    raise RuntimeError(
                        msg,
                    )
                pg_driver = pg_driver_env or "psycopg2"

                if pg_driver == "psycopg3":
                    try:
                        from app.psycopg3_repository import (
                            Psycopg3JobRepository,
                            verify_psycopg3_connectivity,
                        )

                        connectivity = verify_psycopg3_connectivity()
                        if not connectivity.get("ok"):
                            msg = (
                                f"Postgres (psycopg3) connectivity check failed: "
                                f"{connectivity.get('error', 'unknown error')}. "
                                "Cannot use Postgres backend. Check DATAFORGE_DATABASE_URL "
                                "and ensure the database is running."
                            )
                            raise RuntimeError(msg)
                        repo: JobRepository = Psycopg3JobRepository()
                        _repository_instance = repo
                        logger.info("Using Psycopg3JobRepository (STORAGE_BACKEND=postgres, PG_DRIVER=psycopg3)")
                        return repo
                    except RuntimeError:
                        raise
                    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as e:
                        msg = (
                            f"Failed to create Psycopg3JobRepository: {e}. "
                            "Install psycopg 3 with: pip install 'psycopg[binary,pool]>=3.2'"
                        )
                        raise RuntimeError(msg) from e

                try:
>                   from app.postgres_repository import (
                        PostgresJobRepository,
                        verify_postgres_connectivity,
                    )
E                   ImportError: cannot import name 'PostgresJobRepository' from 'postgres_repository' (unknown location)

backend/app/storage_interface.py:989: ImportError
_ TestPostgresSummaryContract.test_postgres_summary_abstract_signature_present _

self = <tests.test_summary_dto_contract.TestPostgresSummaryContract object at 0x7916087263f0>

    def test_postgres_summary_abstract_signature_present(self) -> None:
        """The Postgres implementation must expose ``list_job_summaries``
        even if we cannot run it without a real DB.
        """
>       from app.postgres_repository import PostgresJobRepository
E       ImportError: cannot import name 'PostgresJobRepository' from 'postgres_repository' (unknown location)

backend/tests/test_summary_dto_contract.py:83: ImportError
=========================== short test summary info ============================
FAILED backend/tests/test_architecture_invariants.py::test_no_stale_pyc - Ass...
FAILED backend/tests/test_postgres_repository.py::TestJobRepositoryFactory::test_fallback_on_postgres_import_failure
FAILED backend/tests/test_psycopg3_repository.py::TestPsycopg3RepositoryContract::test_schema_columns_match_psycopg2
FAILED backend/tests/test_psycopg3_repository.py::TestFactorySelectsPsycopg3::test_factory_errors_cleanly_when_psycopg3_missing
FAILED backend/tests/test_psycopg3_repository.py::TestFactorySelectsPsycopg3::test_default_driver_is_psycopg2
FAILED backend/tests/test_summary_dto_contract.py::TestPostgresSummaryContract::test_postgres_summary_abstract_signature_present

```

## stderr

```text

```
