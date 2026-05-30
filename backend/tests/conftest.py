import asyncio
import os
import sys
from pathlib import Path

import httpx
import pytest


def pytest_addoption(parser):
    """Register the --run-postgres CLI flag."""
    parser.addoption(
        "--run-postgres",
        action="store_true",
        default=False,
        help="Run tests marked with @pytest.mark.postgres (requires Docker + testcontainers).",
    )


def pytest_configure(config):
    """Register custom markers to avoid PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers",
        "postgres: tests that require a running Postgres instance (via testcontainers). Skipped by default.",
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
                dialect="postgresql{}".format(driver),
                username=username,
                password=password,
                dbname=dbname,
                host="127.0.0.1",
                port=port
            )
        PostgresContainer.get_connection_url = patched_get_connection_url
    except Exception:
        pass


def pytest_collection_modifyitems(config, items):
    """Skip tests marked 'postgres' unless --run-postgres is provided."""
    if config.getoption("--run-postgres", default=False):
        return  # Don't skip anything

    skip_postgres = pytest.mark.skip(reason="need --run-postgres to run (Postgres integration tests)")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip_postgres)


def pytest_sessionfinish(session, exitstatus):
    """Drain background state writes so pytest exits cleanly after direct module tests."""
    try:
        from app.state_store import flush_state_writes
        flush_state_writes()
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
os.environ["DATAFORGE_API_KEY"] = ""
os.environ["DATAFORGE_ADMIN_API_KEY"] = ""
os.environ["DATAFORGE_OPERATOR_API_KEY"] = ""

try:
    from app import main as main_mod  # noqa: E402
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import app.main (tests requiring the client fixture will fail): {e}")
    main_mod = None  # type: ignore[assignment]


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


class LocalASGIClient:
    """Small sync wrapper around httpx ASGITransport that avoids TestClient threads."""

    def __init__(self, app):
        self.app = app

    async def _request(self, method: str, url: str, **kwargs):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, **kwargs)

    def request(self, method: str, url: str, **kwargs):
        return asyncio.run(self._request(method, url, **kwargs))

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)


@pytest.fixture()
def client(monkeypatch):
    async def fake_run_job(job_id: str):
        # Keep jobs in pending state unless a test explicitly changes them.
        await asyncio.sleep(0.01)

    def fake_schedule_background_task(coro):
        return None

    # Avoid writing persistence files in API unit tests.
    monkeypatch.setattr("app.services.state.persist_state", lambda **kwargs: None)
    monkeypatch.setattr(main_mod, "run_job", fake_run_job)
    monkeypatch.setattr(main_mod, "_schedule_background_task", fake_schedule_background_task)

    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()

    yield LocalASGIClient(main_mod.app)

    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()
