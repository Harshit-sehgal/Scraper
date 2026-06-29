"""Tests for email delivery of results (Feat 35)."""

from __future__ import annotations

import app.main as main_mod
from fastapi.testclient import TestClient


def _create_job_with_results(client: TestClient) -> str:
    payload = {
        "name": "email-test-job",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]
    main_mod.jobs_store[job_id].results = [{"title": "Test Result"}]
    return job_id


def test_email_results_csv(client: TestClient) -> None:
    job_id = _create_job_with_results(client)
    resp = client.post(
        f"/api/jobs/{job_id}/email",
        json={"recipients": ["user@example.com"], "format": "csv"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["format"] == "csv"


def test_email_results_json(client: TestClient) -> None:
    job_id = _create_job_with_results(client)
    resp = client.post(
        f"/api/jobs/{job_id}/email",
        json={"recipients": ["user@example.com"], "format": "json"},
    )
    assert resp.status_code == 200
    assert resp.json()["format"] == "json"


def test_email_results_multiple_recipients(client: TestClient) -> None:
    job_id = _create_job_with_results(client)
    recipients = ["a@example.com", "b@example.com"]
    resp = client.post(
        f"/api/jobs/{job_id}/email",
        json={"recipients": recipients, "format": "csv"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["recipients"]) == 2


def test_email_results_no_recipients_returns_422(client: TestClient) -> None:
    job_id = _create_job_with_results(client)
    resp = client.post(
        f"/api/jobs/{job_id}/email",
        json={"recipients": [], "format": "csv"},
    )
    assert resp.status_code == 422


def test_email_results_invalid_format(client: TestClient) -> None:
    job_id = _create_job_with_results(client)
    resp = client.post(
        f"/api/jobs/{job_id}/email",
        json={"recipients": ["user@example.com"], "format": "pdf"},
    )
    assert resp.status_code == 422


def test_email_job_not_found(client: TestClient) -> None:
    resp = client.post(
        "/api/jobs/non-existent/email",
        json={"recipients": ["user@example.com"], "format": "csv"},
    )
    assert resp.status_code == 404
