"""Tests for X-RateLimit headers in API responses (Feat 29)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_rate_limit_headers_present_on_jobs_list(client: TestClient) -> None:
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers
    assert "X-RateLimit-Reset" in resp.headers


def test_rate_limit_headers_positive_values(client: TestClient) -> None:
    resp = client.get("/api/jobs")
    limit = int(resp.headers["X-RateLimit-Limit"])
    remaining = int(resp.headers["X-RateLimit-Remaining"])
    assert limit > 0
    assert remaining >= 0
    assert remaining <= limit


def test_rate_limit_headers_on_create_job(client: TestClient) -> None:
    payload = {
        "name": "rate-limit-test",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers


def test_rate_limit_headers_on_404_response(client: TestClient) -> None:
    resp = client.get("/api/jobs/non-existent")
    assert resp.status_code == 404
    assert "X-RateLimit-Limit" in resp.headers


def test_rate_limit_headers_decrements_on_subsequent_calls(client: TestClient) -> None:
    resp1 = client.get("/api/jobs")
    remaining1 = int(resp1.headers["X-RateLimit-Remaining"])
    resp2 = client.get("/api/jobs")
    remaining2 = int(resp2.headers["X-RateLimit-Remaining"])
    assert remaining2 <= remaining1


def test_rate_limit_headers_reset_is_future_timestamp(client: TestClient) -> None:
    resp = client.get("/api/jobs")
    reset_val = int(resp.headers["X-RateLimit-Reset"])
    import time

    assert reset_val >= int(time.time()) - 10


def test_rate_limit_headers_type(client: TestClient) -> None:
    resp = client.get("/api/jobs")
    assert resp.headers["X-RateLimit-Limit"].isdigit()
    assert resp.headers["X-RateLimit-Remaining"].isdigit()
    assert resp.headers["X-RateLimit-Reset"].isdigit()
