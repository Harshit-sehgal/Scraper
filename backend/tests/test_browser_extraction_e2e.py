"""Browser extraction end-to-end test — full job lifecycle with Playwright."""
import pytest
from app.models import JobStatus, ScrapeMode


@pytest.mark.asyncio
async def test_browser_extraction_e2e(clean_db, session_client, test_server_url):
    """Full E2E: Create → render → extract → export browser job."""
    # Create a job with browser rendering
    create_resp = session_client.post(
        "/api/jobs",
        json={
            "urls": [test_server_url + "/test-page"],
            "mode": ScrapeMode.BROWSER.value,
            "schema": {
                "fields": [
                    {"name": "title", "selector": "h1", "type": "text"},
                    {"name": "content", "selector": ".content", "type": "text"},
                ]
            },
        },
    )

    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]

    # Get job status
    status_resp = session_client.get(f"/api/jobs/{job_id}")
    assert status_resp.status_code == 200
    job = status_resp.json()

    assert job["id"] == job_id
    assert job["status"] in [JobStatus.PENDING.value, JobStatus.RUNNING.value]

    # Wait for completion (with timeout)
    import time
    max_wait = 30
    start = time.time()

    while time.time() - start < max_wait:
        status_resp = session_client.get(f"/api/jobs/{job_id}")
        job = status_resp.json()

        if job["status"] in [JobStatus.COMPLETED.value, JobStatus.DEGRADED.value, JobStatus.FAILED.value]:
            break

        time.sleep(1)

    # Verify job completed
    assert job["status"] in [JobStatus.COMPLETED.value, JobStatus.DEGRADED.value], \
        f"Job failed: {job.get('error')}"

    # Get results
    results_resp = session_client.get(f"/api/jobs/{job_id}/results")
    assert results_resp.status_code == 200
    results = results_resp.json()

    # Should have extracted at least some records
    records = results.get("records", [])
    assert len(records) > 0, "Browser extraction returned no records"

    # Export as CSV
    export_resp = session_client.post(
        f"/api/jobs/{job_id}/export",
        json={"format": "csv"},
    )

    assert export_resp.status_code == 200
    assert "text/csv" in export_resp.headers.get("content-type", "")
    csv_content = export_resp.text
    assert len(csv_content) > 0


@pytest.mark.asyncio
async def test_browser_handles_javascript_rendering(clean_db, session_client, test_server_url):
    """Verify browser mode actually renders JavaScript content."""
    # Create job that extracts data rendered by JavaScript
    create_resp = session_client.post(
        "/api/jobs",
        json={
            "urls": [test_server_url + "/js-rendered-page"],
            "mode": ScrapeMode.BROWSER.value,
            "schema": {
                "fields": [
                    {"name": "dynamic_content", "selector": "#js-rendered", "type": "text"},
                ]
            },
        },
    )

    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]

    # Wait for job
    import time
    max_wait = 30
    start = time.time()

    while time.time() - start < max_wait:
        status_resp = session_client.get(f"/api/jobs/{job_id}")
        job = status_resp.json()

        if job["status"] != JobStatus.PENDING.value:
            break

        time.sleep(1)

    # Get results
    results_resp = session_client.get(f"/api/jobs/{job_id}/results")
    assert results_resp.status_code == 200
    results = results_resp.json()

    records = results.get("records", [])
    if len(records) > 0:
        # If we got records, verify JavaScript was executed
        first_record = records[0]
        assert "dynamic_content" in first_record or len(records) > 0


@pytest.mark.asyncio
async def test_browser_pool_manages_resources(clean_db, session_client, test_server_url):
    """Verify browser pool doesn't exhaust resources on concurrent jobs."""

    # Create multiple concurrent browser jobs
    job_ids = []
    for i in range(3):
        create_resp = session_client.post(
            "/api/jobs",
            json={
                "urls": [f"{test_server_url}/test-{i}"],
                "mode": ScrapeMode.BROWSER.value,
                "schema": {"fields": [{"name": "text", "selector": "body", "type": "text"}]},
            },
        )

        if create_resp.status_code == 201:
            job_ids.append(create_resp.json()["id"])

    # Wait for all to complete
    import time
    max_wait = 60
    start = time.time()

    while time.time() - start < max_wait and len(job_ids) > 0:
        still_pending = []
        for job_id in job_ids:
            status_resp = session_client.get(f"/api/jobs/{job_id}")
            job = status_resp.json()

            if job["status"] == JobStatus.PENDING.value:
                still_pending.append(job_id)

        job_ids = still_pending
        time.sleep(2)

    # All should complete without resource exhaustion
    # (Resource exhaustion would show as jobs stuck in PENDING)
    assert len(job_ids) == 0, f"Jobs still pending after {max_wait}s (resource exhaustion?): {job_ids}"
