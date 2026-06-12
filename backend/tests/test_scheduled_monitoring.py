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

    def test_404_on_missing(self, client: TestClient):
        resp = client.get("/api/scheduled/nonexistent-id")
        assert resp.status_code == 404
