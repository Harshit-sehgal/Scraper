"""Default end-to-end job lifecycle test (not gated behind postgres).

Exercises: POST /api/jobs -> job in PENDING state -> status checks ->
recycle -> restore -> verify lifecycle transitions.

This test does NOT require Postgres, Playwright, or a running worker.
The ``client`` fixture (conftest.py) patches out real job execution.
"""

from __future__ import annotations

from app.models import JobStatus


class TestJobLifecycleDefaultE2E:
    """End-to-end job lifecycle test using the default test client."""

    MINIMAL_JOB = {
        "name": "lifecycle-e2e-test",
        "mode": "manual",
        "urls": ["https://example.com/data"],
        "schema_fields": [
            {"name": "title", "field_type": "string", "required": True},
            {"name": "price", "field_type": "currency", "required": False},
        ],
    }

    def test_create_job_returns_201(self, client):
        resp = client.post("/api/jobs", json=self.MINIMAL_JOB)
        assert resp.status_code == 201
        body = resp.json()
        assert "job_id" in body
        assert body["status"] == "pending"

    def test_created_job_state_machine_transitions(self, client):
        import app.main as main_mod

        resp = client.post("/api/jobs", json=self.MINIMAL_JOB)
        job_id = resp.json()["job_id"]

        job = main_mod.jobs_store[job_id]
        assert job.status == JobStatus.PENDING

        job.status = JobStatus.RUNNING
        job.status = JobStatus.COMPLETED
        job.total_records = 5
        job.results = [{"title": "Test", "price": "$10"}]

        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

    def test_delete_and_restore_lifecycle(self, client):
        import app.main as main_mod

        resp = client.post("/api/jobs", json=self.MINIMAL_JOB)
        job_id = resp.json()["job_id"]

        main_mod.jobs_store[job_id].status = JobStatus.COMPLETED

        resp = client.delete(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        assert job_id in main_mod.recycle_bin_store
        assert job_id not in main_mod.jobs_store

        resp = client.post(f"/api/recycle_bin/{job_id}/restore")
        assert resp.status_code == 200
        assert job_id in main_mod.jobs_store
        assert job_id not in main_mod.recycle_bin_store

    def test_create_job_with_url_validation(self, client):
        resp = client.post(
            "/api/jobs",
            json={
                "name": "ssrf-blocked",
                "mode": "manual",
                "urls": ["http://169.254.169.254/latest/meta-data/"],
            },
        )
        assert resp.status_code in {400, 422}

        resp = client.post(
            "/api/jobs",
            json={
                "name": "valid-url",
                "mode": "manual",
                "urls": ["https://example.com/valid"],
                "schema_fields": [{"name": "x", "field_type": "string"}],
            },
        )
        assert resp.status_code == 201

    def test_cancel_job(self, client):
        resp = client.post("/api/jobs", json=self.MINIMAL_JOB)
        job_id = resp.json()["job_id"]

        resp = client.post(f"/api/jobs/{job_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["cancel_requested"] is True

    def test_cancel_missing_job_returns_404(self, client):
        resp = client.post("/api/jobs/nonexistent-id/cancel")
        assert resp.status_code == 404

    def test_bulk_cleanup_terminal_jobs(self, client):
        import app.main as main_mod

        ids = []
        for i in range(3):
            resp = client.post(
                "/api/jobs",
                json={
                    "name": f"cleanup-{i}",
                    "mode": "manual",
                    "urls": ["https://example.com/data"],
                },
            )
            ids.append(resp.json()["job_id"])

        main_mod.jobs_store[ids[0]].status = JobStatus.COMPLETED
        main_mod.jobs_store[ids[1]].status = JobStatus.FAILED
        main_mod.jobs_store[ids[2]].status = JobStatus.RUNNING

        resp = client.delete("/api/jobs/cleanup/terminal?keep_recent=1")
        assert resp.status_code == 200
        remaining = set(main_mod.jobs_store.keys())
        assert ids[2] in remaining

    def test_idempotent_job_creation(self, client):
        first = client.post(
            "/api/jobs",
            json=self.MINIMAL_JOB,
            headers={"Idempotency-Key": "lifecycle-e2e-idem"},
        )
        assert first.status_code == 201
        assert first.json()["idempotent_replay"] is False

        second = client.post(
            "/api/jobs",
            json=self.MINIMAL_JOB,
            headers={"Idempotency-Key": "lifecycle-e2e-idem"},
        )
        assert second.status_code == 201
        assert second.json()["idempotent_replay"] is True
        assert second.json()["job_id"] == first.json()["job_id"]
