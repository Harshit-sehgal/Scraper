"""API tests for custom headers/cookies PATCH endpoint (Feat 1)."""

from __future__ import annotations

import app.main as main_mod
from fastapi.testclient import TestClient


def _create_job(client: TestClient, name: str = "headers-api-test") -> str:
    payload = {
        "name": name,
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    return resp.json()["job_id"]


def test_update_headers_full(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.patch(
        f"/api/jobs/{job_id}/headers",
        json={"headers": {"X-Custom": "val1", "Accept-Language": "en-US"}, "cookies": {"session": "abc"}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    job = main_mod.jobs_store[job_id]
    assert job.headers == {"X-Custom": "val1", "Accept-Language": "en-US"}
    assert job.cookies == {"session": "abc"}


def test_update_headers_empty_clears(client: TestClient) -> None:
    job_id = _create_job(client)
    client.patch(f"/api/jobs/{job_id}/headers", json={"headers": {"X-Foo": "bar"}, "cookies": {"c": "d"}})
    resp = client.patch(f"/api/jobs/{job_id}/headers", json={"headers": {}, "cookies": {}})
    assert resp.status_code == 200
    job = main_mod.jobs_store[job_id]
    assert job.headers == {}
    assert job.cookies == {}


def test_update_headers_idempotent(client: TestClient) -> None:
    job_id = _create_job(client)
    payload = {"headers": {"X-Idempotent": "yes"}, "cookies": {"t": "1"}}
    resp1 = client.patch(f"/api/jobs/{job_id}/headers", json=payload)
    resp2 = client.patch(f"/api/jobs/{job_id}/headers", json=payload)
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()


def test_update_headers_rejects_oversized_value(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.patch(
        f"/api/jobs/{job_id}/headers",
        json={"headers": {"X-Big": "x" * 2001}, "cookies": {}},
    )
    assert resp.status_code == 422


def test_update_headers_rejects_oversized_cookie(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.patch(
        f"/api/jobs/{job_id}/headers",
        json={"headers": {}, "cookies": {"big": "x" * 4097}},
    )
    assert resp.status_code == 422


def test_update_headers_rejects_too_many_keys(client: TestClient) -> None:
    job_id = _create_job(client)
    many_headers = {f"X-Key-{i}": f"val{i}" for i in range(51)}
    resp = client.patch(f"/api/jobs/{job_id}/headers", json={"headers": many_headers, "cookies": {}})
    assert resp.status_code == 422


def test_update_headers_not_found(client: TestClient) -> None:
    resp = client.patch("/api/jobs/non-existent/headers", json={"headers": {}, "cookies": {}})
    assert resp.status_code == 404


def test_update_headers_only_headers(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.patch(f"/api/jobs/{job_id}/headers", json={"headers": {"Referer": "https://ref.com"}, "cookies": {}})
    assert resp.status_code == 200
    job = main_mod.jobs_store[job_id]
    assert job.headers == {"Referer": "https://ref.com"}
    assert job.cookies == {}


def test_update_headers_only_cookies(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.patch(f"/api/jobs/{job_id}/headers", json={"headers": {}, "cookies": {"auth": "token123"}})
    assert resp.status_code == 200
    job = main_mod.jobs_store[job_id]
    assert job.headers == {}
    assert job.cookies == {"auth": "token123"}


def test_update_headers_persists_empty_header_key(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.patch(
        f"/api/jobs/{job_id}/headers",
        json={"headers": {"": ""}, "cookies": {}},
    )
    assert resp.status_code == 200
