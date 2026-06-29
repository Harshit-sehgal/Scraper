"""API tests for the extraction diff endpoint (Feat 11).

Requires a new GET /api/jobs/{job_id}/diff endpoint that calls
app.extraction_diff.compute_extraction_diff to compare two job runs.
"""

from __future__ import annotations

import app.main as main_mod
from fastapi.testclient import TestClient


def _create_job(client: TestClient, name: str = "diff-test", results: list | None = None) -> str:
    payload = {
        "name": name,
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]
    if results is not None:
        main_mod.jobs_store[job_id].results = results
    return job_id


def test_diff_endpoint_returns_diff_structure(client: TestClient) -> None:
    job_id = _create_job(client, "diff-structure", results=[{"id": "a", "title": "Alpha"}])
    resp = client.get(f"/api/jobs/{job_id}/diff?compare_to={job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "severity" in body
    assert "record_count_delta" in body
    assert "added_records" in body
    assert "removed_records" in body


def test_diff_identical_results_stable(client: TestClient) -> None:
    job_id = _create_job(client, "diff-identical", results=[{"id": "1", "val": 10}, {"id": "2", "val": 20}])
    resp = client.get(f"/api/jobs/{job_id}/diff?compare_to={job_id}")
    assert resp.status_code == 200
    assert resp.json()["severity"] == "stable"


def test_diff_different_results_shows_severity(client: TestClient) -> None:
    job_id = _create_job(client, "diff-changed", results=[{"id": "1", "val": 10}])
    other_id = _create_job(client, "diff-changed-other", results=[{"id": "1", "val": 99}, {"id": "2", "val": 20}])
    resp = client.get(f"/api/jobs/{job_id}/diff?compare_to={other_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["severity"] in {"stable", "minor", "moderate", "major"}


def test_diff_missing_job_returns_404(client: TestClient) -> None:
    job_id = _create_job(client, "diff-missing")
    resp = client.get(f"/api/jobs/{job_id}/diff?compare_to=does-not-exist")
    assert resp.status_code == 404


def test_diff_compare_to_nonexistent_baseline(client: TestClient) -> None:
    resp = client.get("/api/jobs/does-not-exist/diff?compare_to=also-nonexistent")
    assert resp.status_code == 404


def test_diff_accepts_record_key_param(client: TestClient) -> None:
    job_id = _create_job(client, "diff-key", results=[{"sku": "S1", "price": 10}])
    other_id = _create_job(client, "diff-key-other", results=[{"sku": "S2", "price": 20}])
    resp = client.get(f"/api/jobs/{job_id}/diff?compare_to={other_id}&record_key=sku")
    assert resp.status_code == 200


def test_diff_with_field_threshold(client: TestClient) -> None:
    job_id = _create_job(client, "diff-thresh", results=[{"id": "x", "a": 1, "b": 2}])
    other_id = _create_job(client, "diff-thresh-other", results=[{"id": "x", "a": 1, "b": 2, "c": 3}])
    resp = client.get(f"/api/jobs/{job_id}/diff?compare_to={other_id}&field_threshold=0.5")
    assert resp.status_code == 200


def test_diff_to_dict_serializable(client: TestClient) -> None:
    job_id = _create_job(client, "diff-serial", results=[{"id": "a", "price": 10}, {"id": "b", "price": 20}])
    other_id = _create_job(client, "diff-serial-other", results=[{"id": "a", "price": 15}, {"id": "c", "price": 99}])
    resp = client.get(f"/api/jobs/{job_id}/diff?compare_to={other_id}")
    assert resp.status_code == 200
    import json
    json.dumps(resp.json())
