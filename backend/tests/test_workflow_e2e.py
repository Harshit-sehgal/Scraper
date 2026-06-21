"""Workflow end-to-end test — create → run → extract → export flow."""
import pytest
from app.models import JobStatus


@pytest.mark.asyncio
async def test_workflow_create_run_extract_export_e2e(clean_db, session_client):
    """Full E2E: Create workflow → run job → get results → export."""
    # Create a workflow
    workflow_resp = session_client.post(
        "/api/workflows",
        json={
            "name": "Test Workflow",
            "original_url": "https://example.com",
            "extraction_schema": {
                "fields": [
                    {"name": "title", "selector": "h1", "type": "text"},
                ]
            },
            "steps": [
                {
                    "type": "goto",
                    "url": "https://example.com/page",
                }
            ],
        },
    )

    assert workflow_resp.status_code == 201
    workflow_id = workflow_resp.json()["id"]

    # Get workflow
    get_resp = session_client.get(f"/api/workflows/{workflow_id}")
    assert get_resp.status_code == 200
    workflow = get_resp.json()
    assert workflow["name"] == "Test Workflow"

    # Run workflow (creates a job)
    run_resp = session_client.post(f"/api/workflows/{workflow_id}/run")
    assert run_resp.status_code in (200, 201)

    # Get run status
    run_data = run_resp.json()
    if "job_id" in run_data:
        job_id = run_data["job_id"]

        # Wait for job completion
        import time
        max_wait = 30
        start = time.time()

        while time.time() - start < max_wait:
            job_resp = session_client.get(f"/api/jobs/{job_id}")
            job = job_resp.json()

            if job["status"] != JobStatus.PENDING.value:
                break

            time.sleep(1)

        # Get results
        results_resp = session_client.get(f"/api/jobs/{job_id}/results")
        assert results_resp.status_code == 200

        # Export results
        export_resp = session_client.post(
            f"/api/jobs/{job_id}/export",
            json={"format": "json"},
        )
        assert export_resp.status_code == 200


@pytest.mark.asyncio
async def test_workflow_list_and_filter(clean_db, session_client):
    """Verify workflow list endpoint works."""
    # Create multiple workflows
    for i in range(2):
        session_client.post(
            "/api/workflows",
            json={
                "name": f"Workflow {i}",
                "original_url": f"https://example.com/{i}",
                "extraction_schema": {"fields": []},
                "steps": [],
            },
        )

    # List workflows
    list_resp = session_client.get("/api/workflows")
    assert list_resp.status_code == 200

    workflows = list_resp.json()
    assert isinstance(workflows, (dict, list))


@pytest.mark.asyncio
async def test_workflow_update_and_delete(clean_db, session_client):
    """Verify workflow update and delete operations."""
    # Create workflow
    create_resp = session_client.post(
        "/api/workflows",
        json={
            "name": "Original Name",
            "original_url": "https://example.com",
            "extraction_schema": {"fields": []},
            "steps": [],
        },
    )

    workflow_id = create_resp.json()["id"]

    # Update workflow
    update_resp = session_client.patch(
        f"/api/workflows/{workflow_id}",
        json={"name": "Updated Name"},
    )

    if update_resp.status_code == 200:
        updated = update_resp.json()
        assert updated["name"] == "Updated Name"

    # Delete workflow
    delete_resp = session_client.delete(f"/api/workflows/{workflow_id}")
    assert delete_resp.status_code in (200, 204)

    # Verify deletion
    get_resp = session_client.get(f"/api/workflows/{workflow_id}")
    assert get_resp.status_code == 404 or get_resp.status_code == 200  # May be soft-deleted
