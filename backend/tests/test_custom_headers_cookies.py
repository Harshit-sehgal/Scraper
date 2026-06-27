"""Unit and integration tests for custom request headers and cookies configuration per job."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from app.models import JobStatus
import app.main as main_mod


def test_job_create_with_headers_cookies(client: TestClient) -> None:
    """POST a fresh job with custom headers and cookies, checking storage mapping."""
    payload = {
        "name": "headers-cookies-create-test",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
        "headers": {"X-Custom-Header": "value123"},
        "cookies": {"session_id": "sess987"},
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    job = main_mod.jobs_store[job_id]
    assert job.headers == {"X-Custom-Header": "value123"}
    assert job.cookies == {"session_id": "sess987"}


def test_patch_job_headers_cookies(client: TestClient) -> None:
    """PATCH job headers and cookies endpoint."""
    # 1. Create a job
    payload = {
        "name": "headers-cookies-patch-test",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    # 2. PATCH headers and cookies
    patch_payload = {
        "headers": {"Accept-Language": "fr-FR", "Referer": "https://google.com"},
        "cookies": {"auth_token": "token456"},
    }
    resp_patch = client.patch(f"/api/jobs/{job_id}/headers", json=patch_payload)
    assert resp_patch.status_code == 200
    assert resp_patch.json()["status"] == "success"

    # 3. Verify in memory
    job = main_mod.jobs_store[job_id]
    assert job.headers == {"Accept-Language": "fr-FR", "Referer": "https://google.com"}
    assert job.cookies == {"auth_token": "token456"}


def test_patch_job_headers_cookies_not_found(client: TestClient) -> None:
    """PATCH headers/cookies on non-existent job returns 404."""
    resp = client.patch(
        "/api/jobs/non-existent-id/headers",
        json={"headers": {"X-Header": "val"}, "cookies": {}},
    )
    assert resp.status_code == 404


def test_job_headers_validation_limits(client: TestClient) -> None:
    """Ensure size limits are enforced on custom headers/cookies."""
    # Oversized header value
    payload_bad_headers = {
        "name": "headers-limit-test",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
        "headers": {"X-Big-Header": "A" * 2001},
    }
    resp1 = client.post("/api/jobs", json=payload_bad_headers)
    assert resp1.status_code == 422

    # Oversized cookie value
    payload_bad_cookies = {
        "name": "cookies-limit-test",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
        "cookies": {"auth_token": "A" * 4097},
    }
    resp2 = client.post("/api/jobs", json=payload_bad_cookies)
    assert resp2.status_code == 422


@pytest.mark.anyio
async def test_custom_headers_cookies_propagation(monkeypatch) -> None:
    """Verify that job-level headers and cookies are correctly propagated to fetch_page_content."""
    from app.services.scraping import run_scraping_phase
    from app.models import Job, SchemaField, FieldType

    job = Job(
        id="test-propagate-job",
        name="propagate-test",
        urls=["https://example.com"],
        schema_fields=[SchemaField(name="title", field_type=FieldType.STRING, description="")],
        headers={"X-Test-Header": "foo"},
        cookies={"foo_cookie": "bar"},
    )

    mock_scrape = AsyncMock(return_value=([], {}))
    monkeypatch.setattr("app.services.job_runner.scrape_url_with_recovery", mock_scrape)

    mock_save = AsyncMock()
    await run_scraping_phase(
        job,
        max_job_runtime_seconds=60,
        per_url_scrape_timeout_seconds=30,
        persist_fn=mock_save,
        cancel_check=AsyncMock(return_value=False),
    )

    # Check that scrape_url_with_recovery was called with headers and cookies
    mock_scrape.assert_called_once()
    kwargs = mock_scrape.call_args[1]
    assert kwargs["headers"] == {"X-Test-Header": "foo"}
    assert kwargs["cookies"] == {"foo_cookie": "bar"}
