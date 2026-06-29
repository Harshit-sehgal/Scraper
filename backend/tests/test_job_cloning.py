"""Tests for job cloning (Feat 21)."""

from __future__ import annotations

import app.main as main_mod
from fastapi.testclient import TestClient


def _create_job(client: TestClient, name: str = "source-job") -> str:
    payload = {
        "name": name,
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
        "headers": {"X-Source": "original"},
        "cookies": {"session": "abc"},
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    return resp.json()["job_id"]


def test_clone_job_basic(client: TestClient) -> None:
    src_id = _create_job(client, "basic-clone")
    resp = client.post(f"/api/jobs/{src_id}/clone", json={})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source_job_id"] == src_id
    assert body["status"] == "pending"
    assert "(clone)" in body["name"]


def test_clone_job_custom_name(client: TestClient) -> None:
    src_id = _create_job(client, "custom-name")
    resp = client.post(f"/api/jobs/{src_id}/clone", json={"name": "my-custom-clone"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "my-custom-clone"


def test_clone_job_custom_urls(client: TestClient) -> None:
    src_id = _create_job(client, "custom-urls")
    new_urls = ["https://other.com/page1", "https://other.com/page2"]
    resp = client.post(f"/api/jobs/{src_id}/clone", json={"urls": new_urls})
    assert resp.status_code == 201

    cloned_id = resp.json()["job_id"]
    cloned = main_mod.jobs_store[cloned_id]
    assert cloned.urls == new_urls


def test_clone_job_not_found(client: TestClient) -> None:
    resp = client.post("/api/jobs/non-existent/clone", json={})
    assert resp.status_code == 404


def test_clone_job_preserves_schema(client: TestClient) -> None:
    src_id = _create_job(client, "preserve-schema")
    resp = client.post(f"/api/jobs/{src_id}/clone", json={})
    cloned_id = resp.json()["job_id"]
    cloned = main_mod.jobs_store[cloned_id]
    assert len(cloned.schema_fields) == 1
    assert cloned.schema_fields[0].name == "title"


def test_clone_job_preserves_headers(client: TestClient) -> None:
    src_id = _create_job(client, "preserve-headers")
    resp = client.post(f"/api/jobs/{src_id}/clone", json={})
    cloned_id = resp.json()["job_id"]
    cloned = main_mod.jobs_store[cloned_id]
    assert cloned.headers.get("X-Source") == "original"


def test_clone_job_return_structure(client: TestClient) -> None:
    src_id = _create_job(client, "return-struct")
    resp = client.post(f"/api/jobs/{src_id}/clone", json={})
    assert resp.status_code == 201
    body = resp.json()
    assert "job_id" in body
    assert "source_job_id" in body
    assert "status" in body
    assert "name" in body


def test_clone_job_and_verify_independent(client: TestClient) -> None:
    src_id = _create_job(client, "independent")
    resp = client.post(f"/api/jobs/{src_id}/clone", json={"name": "clone-independent"})
    cloned_id = resp.json()["job_id"]
    assert cloned_id != src_id

    src = main_mod.jobs_store[src_id]
    cloned = main_mod.jobs_store[cloned_id]
    assert src.id != cloned.id
    assert src.name != cloned.name
