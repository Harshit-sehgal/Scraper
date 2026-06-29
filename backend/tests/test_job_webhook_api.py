"""API tests for job webhook endpoints (Feat 2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import app.main as main_mod
from fastapi.testclient import TestClient


def _create_job(client: TestClient, name: str = "webhook-api-test") -> str:
    payload = {
        "name": name,
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    return resp.json()["job_id"]


def test_set_webhook(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.patch(
        f"/api/jobs/{job_id}/webhook",
        json={"webhook_url": "https://hooks.example.com/callback", "webhook_secret": "sec-123"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    job = main_mod.jobs_store[job_id]
    assert job.webhook_url == "https://hooks.example.com/callback"
    assert job.webhook_secret == "sec-123"


def test_update_webhook_overwrites(client: TestClient) -> None:
    job_id = _create_job(client)
    client.patch(
        f"/api/jobs/{job_id}/webhook",
        json={"webhook_url": "https://hooks.example.com/old", "webhook_secret": "old-sec"},
    )
    resp = client.patch(
        f"/api/jobs/{job_id}/webhook",
        json={"webhook_url": "https://hooks.example.com/new", "webhook_secret": "new-sec"},
    )
    assert resp.status_code == 200
    job = main_mod.jobs_store[job_id]
    assert job.webhook_url == "https://hooks.example.com/new"
    assert job.webhook_secret == "new-sec"


def test_remove_webhook(client: TestClient) -> None:
    job_id = _create_job(client)
    client.patch(
        f"/api/jobs/{job_id}/webhook",
        json={"webhook_url": "https://hooks.example.com/cb", "webhook_secret": "sec"},
    )
    resp = client.patch(f"/api/jobs/{job_id}/webhook", json={"webhook_url": None, "webhook_secret": None})
    assert resp.status_code == 200
    job = main_mod.jobs_store[job_id]
    assert job.webhook_url is None
    assert job.webhook_secret is None


def test_set_webhook_not_found(client: TestClient) -> None:
    resp = client.patch(
        "/api/jobs/non-existent/webhook",
        json={"webhook_url": "https://example.com/hook"},
    )
    assert resp.status_code == 404


def test_set_webhook_rejects_private_ip(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.patch(
        f"/api/jobs/{job_id}/webhook",
        json={"webhook_url": "http://192.168.1.1/hook"},
    )
    assert resp.status_code == 422


def test_set_webhook_rejects_loopback(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.patch(
        f"/api/jobs/{job_id}/webhook",
        json={"webhook_url": "http://127.0.0.1:8080/hook"},
    )
    assert resp.status_code == 422


def test_redeliver_webhook(client: TestClient) -> None:
    job_id = _create_job(client)
    client.patch(
        f"/api/jobs/{job_id}/webhook",
        json={"webhook_url": "https://example.com/hook", "webhook_secret": "sec"},
    )
    with patch("app.services.webhook_delivery.deliver_webhook", new_callable=AsyncMock) as mock_deliver:
        mock_deliver.return_value = True
        resp = client.post(f"/api/jobs/{job_id}/webhook/redeliver")
        assert resp.status_code == 200
        assert resp.json()["delivered"] is True


def test_redeliver_webhook_no_url_returns_400(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.post(f"/api/jobs/{job_id}/webhook/redeliver")
    assert resp.status_code == 400


def test_redeliver_webhook_not_found(client: TestClient) -> None:
    resp = client.post("/api/jobs/non-existent/webhook/redeliver")
    assert resp.status_code == 404


def test_set_webhook_with_secret_too_long(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.patch(
        f"/api/jobs/{job_id}/webhook",
        json={"webhook_url": "https://example.com/hook", "webhook_secret": "x" * 200},
    )
    assert resp.status_code == 422


def test_webhook_secret_set_flag(client: TestClient) -> None:
    job_id = _create_job(client)
    resp1 = client.patch(
        f"/api/jobs/{job_id}/webhook",
        json={"webhook_url": "https://example.com/hook", "webhook_secret": None},
    )
    assert resp1.json()["webhook_secret_set"] is False
    resp2 = client.patch(
        f"/api/jobs/{job_id}/webhook",
        json={"webhook_url": "https://example.com/hook", "webhook_secret": "s3cr3t"},
    )
    assert resp2.json()["webhook_secret_set"] is True
