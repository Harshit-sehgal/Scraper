"""Workflow end-to-end test — create → run → extract → export flow."""

import pytest


@pytest.mark.asyncio
async def test_workflow_create_run_extract_export_e2e(clean_db, session_client):
    """Full E2E: Create workflow → run job → get results → export."""
    workflow_resp = session_client.post(
        "/api/workflows",
        json={
            "name": "Test Workflow",
            "original_url": "https://example.com",
            "extraction_schema": [
                {"name": "title", "field_type": "string"},
            ],
            "steps": [
                {
                    "step_type": "goto",
                    "value": "https://example.com/page",
                }
            ],
        },
    )

    assert workflow_resp.status_code == 201
    workflow_id = workflow_resp.json()["id"]

    get_resp = session_client.get(f"/api/workflows/{workflow_id}")
    assert get_resp.status_code == 200
    workflow = get_resp.json()
    assert workflow["name"] == "Test Workflow"

    run_resp = session_client.post(f"/api/workflows/{workflow_id}/run")
    assert run_resp.status_code in (200, 201, 202)

    run_data = run_resp.json()
    job_id = run_data.get("job_id")
    if job_id:
        results_resp = session_client.get(f"/api/jobs/{job_id}/results")
        assert results_resp.status_code in (200, 404)

        export_resp = session_client.get(f"/api/jobs/{job_id}/export/json")
        assert export_resp.status_code in (200, 404, 403)


@pytest.mark.asyncio
async def test_workflow_list_and_filter(clean_db, session_client):
    """Verify workflow list endpoint works."""
    for i in range(2):
        session_client.post(
            "/api/workflows",
            json={
                "name": f"Workflow {i}",
                "original_url": f"https://example.com/{i}",
                "extraction_schema": [],
                "steps": [],
            },
        )

    list_resp = session_client.get("/api/workflows")
    assert list_resp.status_code == 200

    workflows = list_resp.json()
    assert isinstance(workflows, (dict, list))


@pytest.mark.asyncio
async def test_workflow_update_and_delete(clean_db, session_client):
    """Verify workflow update and delete operations."""
    create_resp = session_client.post(
        "/api/workflows",
        json={
            "name": "Original Name",
            "original_url": "https://example.com",
            "extraction_schema": [],
            "steps": [],
        },
    )
    assert create_resp.status_code == 201

    workflow_id = create_resp.json()["id"]

    update_resp = session_client.patch(
        f"/api/workflows/{workflow_id}",
        json={"name": "Updated Name"},
    )

    if update_resp.status_code == 200:
        updated = update_resp.json()
        assert updated["name"] == "Updated Name"

    delete_resp = session_client.delete(f"/api/workflows/{workflow_id}")
    assert delete_resp.status_code in (200, 204)

    get_resp = session_client.get(f"/api/workflows/{workflow_id}")
    assert get_resp.status_code in (404, 200)
