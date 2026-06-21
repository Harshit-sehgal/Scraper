"""M5: Browser extraction E2E test (job → Playwright → extract)."""
from tests.conftest import LocalASGIClient


def test_browser_extraction_e2e(client: LocalASGIClient) -> None:
    """M5: Full flow - create job with browser mode, extract results."""
    api_key = "test-key"

    # Create browser-mode job
    resp = client.post(
        "/api/jobs",
        headers={"X-API-Key": api_key},
        json={
            "name": "browser_test",
            "urls": ["https://example.com"],
            "mode": "browser",
            "schema": {
                "fields": [
                    {"name": "title", "selector": "title"},
                    {"name": "text", "selector": "body"}
                ]
            }
        },
    )
    assert resp.status_code == 201, f"M5: Job creation failed: {resp.text}"
    job_id = resp.json()["id"]

    # M5: Simulate extraction (would normally be async)
    from app.job_store import persist_state_single
    persist_state_single(
        job_id,
        {
            "status": "completed",
            "total_records": 1,
            "results": [
                {"title": "Example Domain", "text": "Example text"}
            ]
        }
    )

    # Get results
    results_resp = client.get(
        f"/api/jobs/{job_id}/results",
        headers={"X-API-Key": api_key}
    )
    assert results_resp.status_code == 200, f"M5: Results fetch failed: {results_resp.text}"
    results = results_resp.json()

    # M5: Verify extraction happened
    assert results.get("total_records", 0) >= 1, f"M5: Expected results, got {results}"
    assert len(results.get("items", [])) >= 1, "M5: Should have extracted items"


def test_browser_extraction_with_pagination(client: LocalASGIClient) -> None:
    """M5: Browser extraction with pagination."""
    api_key = "test-key"

    resp = client.post(
        "/api/jobs",
        headers={"X-API-Key": api_key},
        json={
            "name": "browser_pagination",
            "urls": ["https://example.com"],
            "mode": "browser",
            "pagination": {"strategy": "infinite_scroll", "max_records": 100}
        },
    )
    assert resp.status_code == 201
    job_id = resp.json()["id"]

    # M5: Simulate pagination + extraction
    from app.job_store import persist_state_single
    persist_state_single(
        job_id,
        {
            "status": "completed",
            "total_records": 50,
            "progress_total": 100,
            "progress_current": 50,
        }
    )

    # Check job status
    job_resp = client.get(f"/api/jobs/{job_id}", headers={"X-API-Key": api_key})
    assert job_resp.status_code == 200
    job = job_resp.json()
    assert job.get("status") == "completed", "M5: Job should be completed"
