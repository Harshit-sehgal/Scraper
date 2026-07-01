from __future__ import annotations

import httpx
import pytest
from app.routers.health import router as health_router
from fastapi import FastAPI


@pytest.fixture
def health_app():
    app = FastAPI()
    app.include_router(health_router)
    return app


@pytest.mark.asyncio
async def test_health_returns_ok(health_app):
    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_root_returns_api_info(health_app):
    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "DataForge" in data["message"]


@pytest.mark.asyncio
async def test_root_includes_experimental_flag(health_app):
    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/")
    data = resp.json()
    assert "experimental_enabled" in data
    assert "aup_version" in data


@pytest.mark.asyncio
async def test_ready_returns_readiness_info(health_app):
    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ready")
    assert resp.status_code in (200, 503)
    assert "status" in resp.json()


@pytest.mark.asyncio
async def test_ready_returns_503_when_repo_fails(monkeypatch, health_app):
    from app.storage_interface import get_job_repository

    def failing_health():
        msg = "DB unavailable"
        raise RuntimeError(msg)

    repo = get_job_repository()
    monkeypatch.setattr(repo, "health_check", failing_health)

    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"


@pytest.mark.asyncio
async def test_root_includes_aup_version(health_app):
    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/")
    assert isinstance(resp.json()["aup_version"], (int, str))


@pytest.mark.asyncio
async def test_ready_includes_backend_info_on_success(health_app):
    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ready")
    assert resp.status_code == 200, f"Ready endpoint returned {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "storage" in data
    assert data["storage"] == "ok"


@pytest.mark.asyncio
async def test_root_includes_docs_in_dev(health_app):
    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/")
    assert "docs" in resp.json()


# ── Health sub-endpoints: /health/worker, /health/db, /health/browser ────


@pytest.mark.asyncio
async def test_health_worker_returns_queue_status(monkeypatch, health_app):
    """Worker health returns queue status with expected keys."""
    from app.worker_queue import get_worker_queue

    mock_status = {
        "pending": 5,
        "running": 2,
        "max_concurrency": 4,
        "retrying": 1,
        "dead_letter": 0,
    }
    monkeypatch.setattr(get_worker_queue(), "get_status", lambda: mock_status)

    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health/worker")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["pending"] == 5
    assert data["running"] == 2
    assert data["idle_capacity"] == 2
    assert data["max_concurrency"] == 4


@pytest.mark.asyncio
async def test_health_worker_returns_503_when_saturated(monkeypatch, health_app):
    """Worker health returns 503 when queue is saturated (pending > 0, no idle capacity)."""
    from app.worker_queue import get_worker_queue

    mock_status = {
        "pending": 10,
        "running": 4,
        "max_concurrency": 4,
        "retrying": 0,
        "dead_letter": 0,
    }
    monkeypatch.setattr(get_worker_queue(), "get_status", lambda: mock_status)

    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health/worker")
    assert resp.status_code == 503
    assert resp.json()["status"] == "saturated"
    assert resp.json()["idle_capacity"] == 0


@pytest.mark.asyncio
async def test_health_worker_handles_error(monkeypatch, health_app):
    """Worker health returns 503 when queue inspection fails."""
    from app.worker_queue import get_worker_queue

    def raise_error():
        _msg = "Queue unavailable"
        raise RuntimeError(_msg)

    monkeypatch.setattr(get_worker_queue(), "get_status", raise_error)

    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health/worker")
    assert resp.status_code == 503
    assert resp.json()["status"] == "error"


@pytest.mark.asyncio
async def test_health_db_returns_db_status(health_app):
    """DB health returns database status with expected keys."""
    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health/db")
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data
    assert "backend" in data
    if resp.status_code == 200:
        assert data["status"] == "ok"
        assert "schema_version" in data
    else:
        assert data["status"] == "error"


@pytest.mark.asyncio
async def test_health_db_returns_503_when_unhealthy(monkeypatch, health_app):
    """DB health returns 503 when the repo reports unhealthy."""
    from app.storage_interface import get_job_repository

    repo = get_job_repository()
    monkeypatch.setattr(repo, "health_check", lambda: {"ok": False, "error": "DB is down", "schema_version": 0})

    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health/db")
    assert resp.status_code == 503
    assert resp.json()["status"] == "error"


@pytest.mark.asyncio
async def test_health_browser_returns_pool_status(monkeypatch, health_app):
    """Browser health returns pool status when circuit breaker is closed."""
    import app.browser_pool as bp_module

    mock_health = {
        "circuit_breaker": {"state": "closed", "failure_count": 0, "success_count": 5},
        "pool": {
            "connected": True,
            "active_contexts": 2,
            "reusable_contexts": 1,
            "isolated_contexts": 1,
            "active_acquires": 0,
            "crash_count": 0,
            "context_reuse_rate": 0.75,
        },
        "healthy": True,
    }
    monkeypatch.setattr(bp_module, "get_browser_pool_health", lambda: mock_health)

    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health/browser")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["connected"] is True
    assert data["active_contexts"] == 2


@pytest.mark.asyncio
async def test_health_browser_returns_503_when_circuit_open(monkeypatch, health_app):
    """Browser health returns 503 when circuit breaker is open."""
    import app.browser_pool as bp_module

    mock_health = {
        "circuit_breaker": {"state": "open", "failure_count": 5, "success_count": 0},
        "pool": {
            "connected": False,
            "active_contexts": 0,
            "reusable_contexts": 0,
            "isolated_contexts": 0,
            "active_acquires": 0,
            "crash_count": 3,
            "context_reuse_rate": 0.0,
        },
        "healthy": False,
    }
    monkeypatch.setattr(bp_module, "get_browser_pool_health", lambda: mock_health)

    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health/browser")
    assert resp.status_code == 503
    assert resp.json()["status"] == "unhealthy"
    assert resp.json()["circuit_breaker"] == "open"


@pytest.mark.asyncio
async def test_health_browser_handles_error(monkeypatch, health_app):
    """Browser health returns 503 when pool inspection fails."""
    import app.browser_pool as bp_module

    def raise_error():
        _msg = "Browser pool unavailable"
        raise RuntimeError(_msg)

    monkeypatch.setattr(bp_module, "get_browser_pool_health", raise_error)

    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health/browser")
    assert resp.status_code == 503
    assert resp.json()["status"] == "error"
