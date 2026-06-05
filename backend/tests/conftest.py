import asyncio
import os

os.environ["DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES"] = "true"
import contextlib
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest


def pytest_addoption(parser) -> None:
    """Register optional external-service test flags."""
    with contextlib.suppress(ValueError):
        parser.addoption(
            "--run-postgres",
            action="store_true",
            default=False,
            help="Run tests marked with @pytest.mark.postgres (requires Docker + testcontainers).",
        )
    with contextlib.suppress(ValueError):
        parser.addoption(
            "--run-golden-dataset",
            action="store_true",
            default=False,
            help="Run golden dataset tests against real websites (requires network).",
        )
    with contextlib.suppress(ValueError):
        parser.addoption(
            "--run-browser",
            action="store_true",
            default=False,
            help="Run tests marked with @pytest.mark.browser (requires Playwright and local socket binding).",
        )


def pytest_configure(config) -> None:
    """Register custom markers to avoid PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers",
        "postgres: tests that require a running Postgres instance (via testcontainers). Skipped by default.",
    )
    config.addinivalue_line(
        "markers",
        "golden_dataset: tests that hit real websites for extraction validation. Skipped by default (use --run-golden-dataset).",
    )
    config.addinivalue_line(
        "markers",
        "browser: tests that require Playwright/browser runtime and local HTTP server binding. Skipped by default.",
    )
    try:
        from testcontainers.postgres import PostgresContainer

        def patched_get_connection_url(self, host=None):
            username = getattr(self, "username", getattr(self, "POSTGRES_USER", "testuser"))
            password = getattr(self, "password", getattr(self, "POSTGRES_PASSWORD", "testpassword"))
            dbname = getattr(self, "dbname", getattr(self, "POSTGRES_DB", "testdb"))
            port = getattr(self, "port", getattr(self, "port_to_expose", 5432))
            driver = getattr(self, "driver", "") or ""
            if driver and not driver.startswith("+"):
                driver = f"+{driver}"
            return self._create_connection_url(
                dialect=f"postgresql{driver}",
                username=username,
                password=password,
                dbname=dbname,
                host="127.0.0.1",
                port=port,
            )

        PostgresContainer.get_connection_url = patched_get_connection_url
    except Exception:
        pass


def pytest_collection_modifyitems(config, items) -> None:
    skip_postgres = pytest.mark.skip(reason="need --run-postgres to run (Postgres integration tests)")
    skip_golden = pytest.mark.skip(reason="need --run-golden-dataset to run (network-dependent golden dataset validation)")
    skip_browser = pytest.mark.skip(reason="need --run-browser to run (requires Playwright and local socket binding)")
    for item in items:
        if "postgres" in item.keywords and not config.getoption("--run-postgres", default=False):
            item.add_marker(skip_postgres)
        if "golden_dataset" in item.keywords and not config.getoption("--run-golden-dataset", default=False):
            item.add_marker(skip_golden)
        if "browser" in item.keywords and not config.getoption("--run-browser", default=False):
            item.add_marker(skip_browser)


def pytest_sessionfinish(session, exitstatus) -> None:
    """Drain background state writes so pytest exits cleanly after direct module tests."""
    try:
        from app.state_store import flush_state_writes

        flush_state_writes()
    except Exception:
        pass

    # Clean up test-generated sqlite files, logs, and locks to avoid workspace pollution
    try:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        backend_data = root / "backend" / "data"
        global_data = root / "data"
        logs_dir = root / "logs"

        # List of directories to clean safely
        for p in [backend_data, global_data, logs_dir]:
            if p.exists():
                for item in list(p.glob("**/*")):
                    if (
                        item.is_file()
                        and item.name != ".gitkeep"
                        and any(
                            item.suffix == sfx or str(item.name).endswith(sfx)
                            for sfx in [".db", ".db-journal", ".db-wal", ".db-shm", ".lock", ".log", ".json"]
                        )
                    ):
                        # Ensure we do not delete golden dataset files
                        if "golden_dataset" not in str(item.resolve()):
                            with contextlib.suppress(OSError):
                                item.unlink()
    except Exception:
        pass


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Keep test state isolated from developer runtime state.
os.environ.setdefault("DATAFORGE_STATE_FILE", str(ROOT / "backend" / "data" / "jobs_state_test.json"))

# Set development environment and disable API key validation for tests
os.environ["DATAFORGE_ENV"] = "development"
os.environ["DATAFORGE_ALLOW_INSECURE_DEV_AUTH"] = "true"
os.environ["DATAFORGE_API_KEY"] = ""
os.environ["DATAFORGE_ADMIN_API_KEY"] = ""
os.environ["DATAFORGE_OPERATOR_API_KEY"] = ""
# Force SQLite for tests to avoid Postgres env bleed from .env
os.environ["DATAFORGE_STORAGE_BACKEND"] = "sqlite"
os.environ.pop("DATAFORGE_DATABASE_URL", None)

main_mod: ModuleType | None = None
try:
    import app.main

    main_mod = app.main
except ImportError as e:
    import warnings

    warnings.warn(f"Could not import app.main (tests requiring the client fixture will fail): {e}", stacklevel=2)


# Pre-import ``app.services.state`` so the conftest's monkeypatch.setattr
# string path ``app.services.state.persist_state`` resolves deterministically.
# ``app.services`` is a namespace package (no ``__init__.py``) and
# ``app.main`` does not transitively import ``app.services.state``; without
# this pre-import, the ``client`` fixture below can fail with
# ``AttributeError: module 'app.services' has no attribute 'state'`` in
# full-suite collection order (PR review, 2026-06).
try:
    import app.services.state  # noqa: F401  (preload for client fixture)
except ImportError:
    pass


@pytest.fixture(autouse=True)
def reset_semantic_world_state():
    try:
        from app.semantic_world_state import reset_world_state

        reset_world_state()
    except ImportError:
        pass
    yield
    try:
        from app.semantic_world_state import reset_world_state

        reset_world_state()
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def reset_failure_injection():
    from app.failure_injector import set_injection_probability

    set_injection_probability(0.0)
    yield
    set_injection_probability(0.0)


@pytest.fixture(autouse=True)
def reset_queue():
    try:
        from app.worker_queue import reset_worker_queue

        reset_worker_queue()
    except ImportError:
        pass
    yield
    try:
        from app.worker_queue import reset_worker_queue

        reset_worker_queue()
    except ImportError:
        pass


from app.models import FieldType, SchemaField


def make_schema_field_list(names: list[str], field_type: FieldType = FieldType.STRING) -> list[SchemaField]:
    """Helper to create SchemaField lists from field names. Shared across test files."""
    return [SchemaField(name=n, field_type=field_type, required=False, description="") for n in names]


class LocalASGIClient:
    """Small sync wrapper around httpx ASGITransport that avoids TestClient threads.

    Uses a single persistent event loop rather than calling ``asyncio.run()``
    per request, which avoids ResourceWarnings from sockets that outlive a
    short-lived loop.
    """

    def __init__(self, app) -> None:
        self.app = app
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

    def close(self) -> None:
        """Shut down the persistent event loop and release resources.

        Note: ``asyncio.all_tasks()`` is deliberately not called here because
        its ``loop`` parameter was removed in Python 3.12 and the httpx
        ``AsyncClient`` context manager in ``_request()`` already handles
        proper socket cleanup.
        """
        try:
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
        finally:
            self._loop.close()
            asyncio.set_event_loop(None)

    async def _request(self, method: str, url: str, **kwargs):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, **kwargs)

    def request(self, method: str, url: str, **kwargs):
        return self._loop.run_until_complete(self._request(method, url, **kwargs))

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)


@pytest.fixture
def client(monkeypatch):
    async def fake_run_job(job_id: str, **kwargs) -> None:
        # Keep jobs in pending state unless a test explicitly changes them.
        await asyncio.sleep(0.01)

    def fake_schedule_background_task(coro):
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                return loop.create_task(coro)
        except RuntimeError:
            pass
        return None

    # Avoid writing persistence files in API unit tests. We resolve the
    # module through a direct import (cached at conftest load) rather than
    # a string path, so the patch is robust to ``app.services.state`` not
    # being in ``sys.modules`` at fixture time.
    from app.services import state as _app_services_state_mod

    monkeypatch.setattr(_app_services_state_mod, "persist_state", lambda **kwargs: None)
    monkeypatch.setattr(main_mod, "run_job", fake_run_job)
    # Also patch lifespan.run_job because run_job_wrapper imports run_job at
    # module level from app.services.job_runner, not from app.main. Without
    # this patch, running the coroutine would trigger real job execution.
    monkeypatch.setattr("app.lifespan.run_job", fake_run_job)
    monkeypatch.setattr(main_mod, "_schedule_background_task", fake_schedule_background_task)

    assert main_mod is not None
    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()

    # Reset rate limiter counters so rapid test requests don't trigger 429s
    if hasattr(main_mod, "rate_limiter"):
        main_mod.rate_limiter.reset()

    # Clear idempotency keys so tests don't see stale records from previous runs
    try:
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                conn.execute("DELETE FROM idempotency_keys")
                conn.commit()
            finally:
                conn.close()
    except Exception:
        pass

    client = LocalASGIClient(main_mod.app)
    yield client

    client.close()
    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()
    try:
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                conn.execute("DELETE FROM idempotency_keys")
                conn.commit()
            finally:
                conn.close()
    except Exception:
        pass
