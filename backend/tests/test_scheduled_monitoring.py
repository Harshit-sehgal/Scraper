"""Tests for the Scheduled Monitoring router."""

from app.models import ScheduledJob, ScheduledJobFrequency
from fastapi.testclient import TestClient


class TestScheduledJobModel:
    """Tests for ScheduledJob model."""

    def test_create_job(self):
        job = ScheduledJob(name="Daily Scrape", job_name="Daily Scrape Run", frequency=ScheduledJobFrequency.DAILY)
        assert job.name == "Daily Scrape"
        assert job.frequency == ScheduledJobFrequency.DAILY
        assert job.enabled is True

    def test_job_id_generated(self):
        job = ScheduledJob(name="Auto ID", job_name="Auto ID Run")
        assert len(job.id) == 36

    def test_frequency_options(self):
        assert ScheduledJobFrequency.HOURLY.value == "hourly"
        assert ScheduledJobFrequency.DAILY.value == "daily"
        assert ScheduledJobFrequency.WEEKLY.value == "weekly"
        assert ScheduledJobFrequency.MONTHLY.value == "monthly"


class TestScheduledMonitoringEndpoints:
    """Integration tests for scheduled monitoring endpoints."""

    def test_create_and_get(self, client: TestClient):
        resp = client.post(
            "/api/scheduled?name=Test+Schedule&job_name=Test+Run&frequency=daily",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Schedule"
        assert data["job_name"] == "Test Run"
        job_id = data["id"]

        get_resp = client.get(f"/api/scheduled/{job_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Test Schedule"

    def test_list_scheduled(self, client: TestClient):
        resp = client.get("/api/scheduled")
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_update_schedule(self, client: TestClient):
        create_resp = client.post("/api/scheduled?name=Before+Update&job_name=Before+Run")
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        update_resp = client.put(f"/api/scheduled/{job_id}?name=After+Update")
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "After Update"

    def test_delete_schedule(self, client: TestClient):
        create_resp = client.post("/api/scheduled?name=Delete+Me&job_name=Delete+Run")
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        del_resp = client.delete(f"/api/scheduled/{job_id}")
        assert del_resp.status_code == 204

        get_resp = client.get(f"/api/scheduled/{job_id}")
        assert get_resp.status_code == 404

    def test_change_detection(self, client: TestClient):
        create_resp = client.post("/api/scheduled?name=Change+Test&job_name=Change+Run")
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        resp = client.get(f"/api/scheduled/{job_id}/changes")
        assert resp.status_code == 200
        assert resp.json()["job_id"] == job_id

    def test_change_detection_with_no_summaries(self, client: TestClient):
        """A brand-new job with no runs has nothing to diff against."""
        create = client.post("/api/scheduled?name=Fresh&job_name=Fresh&target_url=https://example.com")
        assert create.status_code == 201
        job_id = create.json()["id"]
        resp = client.get(f"/api/scheduled/{job_id}/changes")
        body = resp.json()
        assert body["changes_detected"] is False
        assert body["last_records_count"] == 0
        assert body["previous_records_count"] == 0
        assert body["record_count_delta"] == 0
        assert body["summary_count"] == 0
        assert "first run" in body["message"].lower()

    def test_change_detection_diffs_two_runs(self, client: TestClient, tmp_path, monkeypatch):
        """Two runs in recent_run_summaries yield a real diff."""

        from app.utils.json_file_store import JSONFileStore

        jobs_file = tmp_path / "scheduled_jobs.json"
        monkeypatch.setattr(
            "app.routers.scheduled_monitoring._scheduled_jobs",
            JSONFileStore(path=jobs_file),
        )

        # Seed a job with two run summaries directly through the store.
        job = {
            "id": "sched-diff-1",
            "name": "Diff Job",
            "job_name": "Diff",
            "target_url": "https://example.com",
            "frequency": "daily",
            "user_id": "tester",
            "org_id": "org-x",
            "project_id": "proj-x",
            "enabled": True,
            "recent_run_summaries": [
                {
                    "ran_at": "2026-06-15T00:00:00+00:00",
                    "status": "succeeded",
                    "records_count": 50,
                },
                {
                    "ran_at": "2026-06-16T00:00:00+00:00",
                    "status": "succeeded",
                    "records_count": 75,
                },
            ],
        }
        from app.routers import scheduled_monitoring as sm_router

        sm_router._scheduled_jobs.upsert("sched-diff-1", job)

        resp = client.get("/api/scheduled/sched-diff-1/changes")
        body = resp.json()
        assert resp.status_code == 200
        assert body["changes_detected"] is True
        assert body["last_records_count"] == 75
        assert body["previous_records_count"] == 50
        assert body["record_count_delta"] == 25
        assert body["status_changed"] is False
        # 86400s = 24h, gap is exactly 24h so frequency_met is True.
        assert body["frequency_met"] is True

    def test_change_detection_flags_status_flip(self, client: TestClient, tmp_path, monkeypatch):
        from app.utils.json_file_store import JSONFileStore

        jobs_file = tmp_path / "scheduled_jobs.json"
        monkeypatch.setattr(
            "app.routers.scheduled_monitoring._scheduled_jobs",
            JSONFileStore(path=jobs_file),
        )
        from app.routers import scheduled_monitoring as sm_router

        sm_router._scheduled_jobs.upsert(
            "sched-flip",
            {
                "id": "sched-flip",
                "name": "Flip",
                "job_name": "Flip",
                "target_url": "https://example.com",
                "frequency": "hourly",
                "user_id": "tester",
                "org_id": "org-x",
                "project_id": "proj-x",
                "enabled": True,
                "recent_run_summaries": [
                    {
                        "ran_at": "2026-06-16T00:00:00+00:00",
                        "status": "succeeded",
                        "records_count": 10,
                    },
                    {
                        "ran_at": "2026-06-16T01:00:00+00:00",
                        "status": "failed",
                        "records_count": 0,
                    },
                ],
            },
        )
        resp = client.get("/api/scheduled/sched-flip/changes")
        body = resp.json()
        assert body["status_changed"] is True
        assert body["record_count_delta"] == -10
        assert body["changes_detected"] is True

    def test_404_on_missing(self, client: TestClient):
        resp = client.get("/api/scheduled/nonexistent-id")
        assert resp.status_code == 404
