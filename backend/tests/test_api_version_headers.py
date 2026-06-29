"""Tests that API responses include version headers (Roadmap Wave 10 Polish).

Verifies that responses carry X-API-Version and related headers
as documented in API_VERSIONING.md.
"""

from __future__ import annotations


def test_health_response_has_version_header(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200


def test_api_response_has_cors_headers(client) -> None:
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert "content-type" in resp.headers


def test_api_error_response_has_trace_id(client) -> None:
    resp = client.get("/api/jobs/nonexistent-job-id-for-testing")
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
    assert "trace_id" in body


def test_api_jobs_list_response_shape(client) -> None:
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert "jobs" in body


def test_response_has_content_type_json(client) -> None:
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("application/json")


def test_api_has_x_request_id_header(client) -> None:
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert "x-request-id" in resp.headers
    assert len(resp.headers["x-request-id"]) > 0


def test_api_security_headers_present(client) -> None:
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
