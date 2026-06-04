from app.globals import jobs_store
from app.models import Job, JobStatus


def test_list_jobs_returns_summary_only(client, monkeypatch) -> None:
    # 1. Add a job with results and logs and results_file_path to jobs_store
    job_id = "test-summary-job-123"
    job = Job(
        id=job_id,
        name="Contract Summary Test Job",
        urls=["https://example.com"],
        results=[{"title": "Test Title", "price": "$100"}],
        results_file_path="/tmp/leak.gz",
        results_on_disk=False,
        logs=[{"timestamp": "2026-06-04T00:00:00", "message": "Scraped something", "level": "info"}],
        status=JobStatus.COMPLETED,
    )
    jobs_store[job_id] = job

    try:
        # Configure local development bypass
        from app.config import settings

        monkeypatch.setattr(settings, "API_KEY", "")
        monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
        monkeypatch.setattr(settings, "OPERATOR_API_KEY", "")
        monkeypatch.setattr(settings, "ALLOW_INSECURE_DEV_AUTH", True)
        monkeypatch.setattr(settings, "ENV", "development")

        # 2. Get list of jobs
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        payload = resp.json()["jobs"]

        # Find our job
        matched = next((j for j in payload if j["id"] == job_id), None)
        assert matched is not None

        # 3. Assert summary fields are present, but bulky/unsafe ones are absent
        assert "id" in matched
        assert "name" in matched
        assert "mode" in matched
        assert "urls" in matched
        assert "status" in matched
        assert "created_at" in matched

        assert "results" not in matched
        assert "logs" not in matched
        assert "results_file_path" not in matched
        assert "selectors_map" not in matched

        # 4. Get job detail and assert results_file_path is not returned
        resp_detail = client.get(f"/api/jobs/{job_id}")
        assert resp_detail.status_code == 200
        detail = resp_detail.json()

        assert "results" in detail
        assert "results_file_path" not in detail
    finally:
        # Clean up jobs_store
        jobs_store.pop(job_id, None)
