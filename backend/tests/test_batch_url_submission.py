"""Tests for batch URL submission (Feat 13)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _urls(n: int) -> list[str]:
    return [f"https://example.com/page{i}" for i in range(n)]


def test_batch_submit_small(client: TestClient) -> None:
    resp = client.post(
        "/api/jobs/batch",
        json={
            "urls": _urls(3),
            "name": "small-batch",
            "schema_fields": [{"name": "title", "field_type": "string"}],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_urls"] == 3
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["url_count"] == 3


def test_batch_submit_large_splits_into_multiple_jobs(client: TestClient) -> None:
    resp = client.post(
        "/api/jobs/batch",
        json={
            "urls": _urls(250),
            "name": "large-batch",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_urls"] == 250
    assert len(body["jobs"]) == 3


def test_batch_submit_empty_urls_returns_201_with_zero_jobs(client: TestClient) -> None:
    resp = client.post("/api/jobs/batch", json={"urls": [], "name": "empty"})
    assert resp.status_code == 201
    assert resp.json()["total_urls"] == 0
    assert resp.json()["jobs"] == []


def test_batch_submit_with_headers(client: TestClient) -> None:
    resp = client.post(
        "/api/jobs/batch",
        json={
            "urls": _urls(2),
            "name": "batch-headers",
            "headers": {"X-Custom": "val"},
            "cookies": {"session": "abc"},
        },
    )
    assert resp.status_code == 201
    assert resp.json()["total_urls"] == 2


def test_batch_submit_returns_batch_id(client: TestClient) -> None:
    resp = client.post(
        "/api/jobs/batch",
        json={"urls": _urls(5), "name": "batch-id"},
    )
    assert resp.status_code == 201
    assert "batch_id" in resp.json()


def test_batch_submit_response_structure(client: TestClient) -> None:
    resp = client.post(
        "/api/jobs/batch",
        json={"urls": _urls(1), "name": "struct"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "jobs" in body
    assert "total_urls" in body
    assert "batch_id" in body
    assert "message" in body
