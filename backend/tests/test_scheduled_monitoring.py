"""Tests for the Scheduled Monitoring router."""

import logging
from datetime import UTC
from unittest.mock import patch

from app.models import ScheduledJob, ScheduledJobFrequency
from fastapi.testclient import TestClient


class TestScheduledJobModel:
    """Tests for ScheduledJob model."""

    def test_create_job(self):
        job = ScheduledJob(name="Daily Scrape", job_name="Daily Scrape Run", frequency=ScheduledJobFrequency.DAILY)
        assert job.name == "Daily Scrape"
        assert job.frequency == ScheduledJobFrequency.DAILY
        assert job.enabled is True


class TestCronExpressionLoopGuard:
    """The cron-expression handler must reject malformed expressions to
    prevent runaway re-execution loops. See F-SCHEDULER-001, F-SCHEDULER-002.
    """

    def setup_method(self) -> None:
        # Reset the per-process fallback counters between tests.
        from app.routers import scheduled_monitoring

        scheduled_monitoring._cron_fallback_counts.clear()

    def test_malformed_cron_returns_blank_next_run(self) -> None:
        """“not-a-cron-expression” must return "" to halt re-execution."""
        from app.routers import scheduled_monitoring

        record = {
            "id": "sched-1",
            "cron_expression": "not-a-cron-expression",
            "frequency": "daily",
        }
        with patch("app.utils.cron_parser.is_valid", return_value=False):
            nxt = scheduled_monitoring._compute_next_from_record(record)
        assert nxt == ""

    def test_valid_cron_returns_future_timestamp(self) -> None:
        """A real cron expression must produce a future ISO timestamp."""
        from datetime import datetime, timedelta

        from app.routers import scheduled_monitoring

        record = {
            "id": "sched-1",
            "cron_expression": "*/5 * * * *",  # every 5 minutes
            "frequency": "hourly",
        }
        with patch("app.utils.cron_parser.is_valid", return_value=True):
            nxt = scheduled_monitoring._compute_next_from_record(record)
        # Should be a non-empty ISO timestamp in the near future
        assert nxt
        assert isinstance(nxt, str)
        parsed = datetime.fromisoformat(nxt)
        assert parsed > datetime.now(UTC) - timedelta(minutes=1)

    def test_record_cron_fallback_increments_per_job(self) -> None:
        """Each call increments only the targeted job counter."""
        from app.routers import scheduled_monitoring

        scheduled_monitoring._record_cron_fallback(job_id="sched-A")
        scheduled_monitoring._record_cron_fallback(job_id="sched-A")
        scheduled_monitoring._record_cron_fallback(job_id="sched-B")
        assert scheduled_monitoring._cron_fallback_counts["sched-A"] == 2
        assert scheduled_monitoring._cron_fallback_counts["sched-B"] == 1

    def test_threshold_triggers_critical_log_and_audit(self, caplog) -> None:
        """Hitting the loop threshold emits CRITICAL + audit event."""
        from app.routers import scheduled_monitoring

        with patch("app.audit_logger.log_admin_action") as mock_audit:
            with caplog.at_level(logging.CRITICAL, logger="app.routers.scheduled_monitoring"):
                # Hit the threshold (CRON_LOOP_THRESHOLD == 5)
                for _ in range(scheduled_monitoring._CRON_LOOP_THRESHOLD):
                    scheduled_monitoring._record_cron_fallback(job_id="sched-loop")
        # The audit event fires once at the threshold
        assert mock_audit.called
        # The CRITICAL log message mentions the cron-loop detection
        critical_logs = [r for r in caplog.records if r.levelno == logging.CRITICAL]
        assert any("cron_loop" in r.getMessage() or "cron fallback" in r.getMessage() for r in critical_logs)


class TestURLListBound:
    """The scheduler endpoints must reject oversized URL lists (DoS via DNS)."""

    def test_max_urls_constant_is_bounded(self) -> None:
        """A hard cap must exist and be small enough to prevent DoS."""
        from app.routers import scheduled_monitoring

        assert hasattr(scheduled_monitoring, "_MAX_URLS_PER_SCHEDULE")
        assert scheduled_monitoring._MAX_URLS_PER_SCHEDULE <= 1000

    def test_validate_urls_rejects_oversized_input(self) -> None:
        """Validate that oversized URL input raises HTTPException before DNS resolution."""
        from app.routers import scheduled_monitoring
        from app.url_safety import set_dns_resolver
        from fastapi import HTTPException

        # Inject a fake DNS resolver so the test never blocks on real DNS.
        # The cap is checked *before* per-URL validation so the resolver
        # is never actually called, but we set it defensively.
        set_dns_resolver(lambda _host: ["93.184.216.34"])
        try:
            urls = [f"https://example.com/path{i}" for i in range(scheduled_monitoring._MAX_URLS_PER_SCHEDULE + 1)]
            try:
                scheduled_monitoring._validate_urls(urls)
            except HTTPException as exc:
                assert exc.status_code == 400
                assert "Too many URLs" in exc.detail or "max" in exc.detail.lower()
                return
            msg = f"Expected HTTPException for {len(urls)} URLs"
            raise AssertionError(msg)
        finally:
            set_dns_resolver(None)

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

    # ---- SSRF guard tests (LAW 8) ------------------------------------

    def test_create_rejects_loopback_url(self, client: TestClient):
        """Creating a scheduled job with a localhost URL must 400."""
        resp = client.post(
            "/api/scheduled?name=Bad&job_name=Bad&urls=http://localhost:8080/",
        )
        assert resp.status_code == 400
        assert "security check" in resp.json()["detail"].lower()

    def test_create_rejects_metadata_endpoint(self, client: TestClient):
        """Creating a scheduled job with the AWS metadata IP must 400."""
        resp = client.post(
            "/api/scheduled?name=Bad&job_name=Bad&urls=http://169.254.169.254/latest/meta-data/",
        )
        assert resp.status_code == 400

    def test_create_accepts_public_url(self, client: TestClient):
        """Creating a scheduled job with a public URL must 201."""
        resp = client.post(
            "/api/scheduled?name=Good&job_name=Good&urls=https://example.com/",
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "https://example.com/" in body["urls"]

    def test_create_deduplicates_urls(self, client: TestClient):
        """Duplicate URLs must be deduplicated on the way in."""
        resp = client.post(
            "/api/scheduled?name=Dup&job_name=Dup&urls=https://example.com/&urls=https://example.com/",
        )
        assert resp.status_code == 201
        assert resp.json()["urls"] == ["https://example.com/"]

    def test_update_rejects_loopback_url(self, client: TestClient):
        """Updating a scheduled job with a loopback URL must 400."""
        create = client.post("/api/scheduled?name=Update&job_name=Update")
        assert create.status_code == 201
        job_id = create.json()["id"]
        update = client.put(
            f"/api/scheduled/{job_id}?urls=http://127.0.0.1:9000/",
        )
        assert update.status_code == 400

    def test_update_accepts_valid_urls(self, client: TestClient):
        """Updating with a valid URL list must succeed."""
        create = client.post("/api/scheduled?name=UpdateOK&job_name=UpdateOK")
        assert create.status_code == 201
        job_id = create.json()["id"]
        update = client.put(
            f"/api/scheduled/{job_id}?urls=https://example.com/&urls=https://other.com/",
        )
        assert update.status_code == 200
        assert len(update.json()["urls"]) == 2
