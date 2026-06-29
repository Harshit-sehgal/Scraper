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
        raise RuntimeError("DB unavailable")

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
    if resp.status_code == 200:
        data = resp.json()
        assert "storage" in data
        assert data["storage"] == "ok"


@pytest.mark.asyncio
async def test_root_includes_docs_in_dev(health_app):
    transport = httpx.ASGITransport(app=health_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/")
    assert "docs" in resp.json()
