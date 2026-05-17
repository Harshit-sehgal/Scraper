import asyncio
import os
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Keep test state isolated from developer runtime state.
os.environ.setdefault("DATAFORGE_STATE_FILE", str(ROOT / "backend" / "data" / "jobs_state_test.json"))

try:
    from app import main as main_mod  # noqa: E402
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import app.main (tests requiring the client fixture will fail): {e}")
    main_mod = None  # type: ignore[assignment]


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
