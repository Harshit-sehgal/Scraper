# backend_full_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T19:22:41.979713+00:00
- end_time: 2026-06-16T19:26:51.230655+00:00
- duration_seconds: 249.25
- exit_code: 1
- timeout_seconds: 600
- required: true
- redaction_applied: false

## stdout

```text
........................................................................ [  1%]
........................................................................ [  3%]
........................................................................ [  5%]
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
...............................ssssssssssssssssssssss................... [ 50%]
........ss.............................................................. [ 52%]
...........ss....................................F...................... [ 54%]
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
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
.......................................................................s [ 95%]
...................ss..sssssssssssssssssss.............................. [ 97%]
........................................................................ [ 99%]
...............                                                          [100%]
=================================== FAILURES ===================================
_ TestFactorySelectsPsycopg3.test_factory_errors_cleanly_when_psycopg3_missing _

self = <tests.test_psycopg3_repository.TestFactorySelectsPsycopg3 object at 0x779bdf54db20>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x779bde434200>

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
=========================== short test summary info ============================
FAILED backend/tests/test_psycopg3_repository.py::TestFactorySelectsPsycopg3::test_factory_errors_cleanly_when_psycopg3_missing

```

## stderr

```text

```
