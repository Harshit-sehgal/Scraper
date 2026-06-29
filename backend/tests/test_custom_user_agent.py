"""API tests for custom User-Agent per job (Feat 23)."""

from __future__ import annotations

import app.main as main_mod
from fastapi.testclient import TestClient


def _create_job(client: TestClient, name: str = "ua-test") -> str:
    payload = {
        "name": name,
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    return resp.json()["job_id"]


def test_create_job_with_user_agent(client: TestClient) -> None:
    payload = {
        "name": "ua-create-test",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
        "user_agent": "Mozilla/5.0 Custom Agent",
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]
    assert main_mod.jobs_store[job_id].user_agent == "Mozilla/5.0 Custom Agent"


def test_patch_user_agent(client: TestClient) -> None:
    job_id = _create_job(client, "ua-patch")
    resp = client.patch(
        f"/api/jobs/{job_id}/user-agent",
        json={"user_agent": "MyBot/1.0"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["user_agent"] == "MyBot/1.0"
    assert main_mod.jobs_store[job_id].user_agent == "MyBot/1.0"


def test_patch_user_agent_empty_resets_to_default(client: TestClient) -> None:
    job_id = _create_job(client, "ua-reset")
    client.patch(f"/api/jobs/{job_id}/user-agent", json={"user_agent": "Custom/1.0"})
    resp = client.patch(f"/api/jobs/{job_id}/user-agent", json={"user_agent": ""})
    assert resp.status_code == 200
    assert main_mod.jobs_store[job_id].user_agent == ""


def test_patch_user_agent_not_found(client: TestClient) -> None:
    resp = client.patch(
        "/api/jobs/non-existent/user-agent",
        json={"user_agent": "Test/1.0"},
    )
    assert resp.status_code == 404


def test_patch_user_agent_too_long(client: TestClient) -> None:
    job_id = _create_job(client, "ua-long")
    long_ua = "A" * 600
    resp = client.patch(
        f"/api/jobs/{job_id}/user-agent",
        json={"user_agent": long_ua},
    )
    assert resp.status_code == 422


def test_patch_user_agent_idempotent(client: TestClient) -> None:
    job_id = _create_job(client, "ua-idempotent")
    payload = {"user_agent": "IdempotentBot/1.0"}
    r1 = client.patch(f"/api/jobs/{job_id}/user-agent", json=payload)
    r2 = client.patch(f"/api/jobs/{job_id}/user-agent", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()


def test_default_user_agent_is_empty(client: TestClient) -> None:
    job_id = _create_job(client, "ua-default")
    assert main_mod.jobs_store[job_id].user_agent == ""


def test_patch_user_agent_updates_in_memory(client: TestClient) -> None:
    job_id = _create_job(client, "ua-memory")
    client.patch(f"/api/jobs/{job_id}/user-agent", json={"user_agent": "MemoryCheck/1.0"})
    job = main_mod.jobs_store[job_id]
    assert job.user_agent == "MemoryCheck/1.0"


def test_patch_user_agent_does_not_affect_other_jobs(client: TestClient) -> None:
    j1 = _create_job(client, "ua-iso-1")
    j2 = _create_job(client, "ua-iso-2")
    client.patch(f"/api/jobs/{j1}/user-agent", json={"user_agent": "Bot1"})
    client.patch(f"/api/jobs/{j2}/user-agent", json={"user_agent": "Bot2"})
    assert main_mod.jobs_store[j1].user_agent == "Bot1"
    assert main_mod.jobs_store[j2].user_agent == "Bot2"
