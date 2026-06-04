import asyncio
import io
import json
import zipfile
from typing import Any, cast

import app.main as main_mod
import pytest
from app.browser_pool import BrowserPool
from app.config import settings
from app.domain_evolution_model import get_domain_evolution_model
from app.models import FieldType, Job, JobStatus, SchemaField
from app.utils.job_results_store import get_job_results_path, save_job_results_to_disk


def test_job_results_disk_offload_and_retrieval(client, monkeypatch) -> None:
    """Test Component 1: Bound Job Results Memory Footprint offloading and dynamic loading."""
    # 1. Setup a job with 1005 mock records
    job_id = "test-large-job-123"
    results = [{"id": i, "email": f"user{i}@example.com", "name": f"User {i}"} for i in range(1005)]

    job = Job(
        id=job_id,
        name="Large Scrape Job",
        status=JobStatus.COMPLETED,
        schema_fields=[SchemaField(name="name", field_type=FieldType.STRING, description="", required=True)],
        results=results,
        total_records=1005,
    )
    main_mod.jobs_store[job_id] = job

    # Verify save_job_results_to_disk persists results to disk
    path_str = save_job_results_to_disk(job_id, results)
    path = get_job_results_path(job_id)
    assert path.exists()

    # Update job object memory status to simulate post-processing behavior
    job.results_on_disk = True
    job.results_file_path = path_str
    job.results = []  # Clear in-memory results

    # 2. Test GET /api/jobs/{job_id} loads results dynamically from disk
    r = client.get(f"/api/jobs/{job_id}?include_results=true")
    assert r.status_code == 200
    data = r.json()
    assert len(data["results"]) == 1005
    assert data["results_on_disk"] is True

    # 3. Test GET /api/jobs/{job_id}/export/json loads from disk
    export_r = client.get(f"/api/jobs/{job_id}/export/json")
    assert export_r.status_code == 200
    export_data = export_r.json()
    assert len(export_data) == 1005

    # 4. Test Reclean job reads from disk and writes back
    # Mock ai_clean_and_align_records to return a subset
    async def fake_ai_clean_and_align(rows, *args, **kwargs):
        return rows[:1002], {}

    monkeypatch.setattr("app.routers.jobs.ai_clean_and_align_records", fake_ai_clean_and_align)

    reclean_r = client.post(f"/api/jobs/{job_id}/reclean")
    assert reclean_r.status_code == 200
    assert reclean_r.json()["after_records"] == 1002
    # Verify it was offloaded again because 1002 > 1000
    updated_job = main_mod.jobs_store[job_id]
    assert updated_job.results_on_disk is True
    assert len(updated_job.results) == 0

    # 5. Delete job moves to recycle bin, hard delete removes results from disk
    del_r = client.delete(f"/api/jobs/{job_id}")
    assert del_r.status_code == 200
    assert path.exists()  # should still exist in recycle bin

    hard_del_r = client.delete(f"/api/recycle_bin/{job_id}")
    assert hard_del_r.status_code == 200
    assert not path.exists()  # now it's gone


@pytest.mark.asyncio
async def test_browser_pool_hard_recycling(monkeypatch) -> None:
    """Test Component 2: Playwright Hard Process Recycling conditions."""
    pool = BrowserPool()

    # Pin settings to known values to stay immune to state pollution from other tests
    monkeypatch.setattr(settings, "BROWSER_MAX_CUMULATIVE_FETCHES", 200)
    monkeypatch.setattr(settings, "BROWSER_MAX_RSS_MEMORY_MB", 1024)

    # Mock _get_rss_memory to return a safe baseline so process-level memory
    # does not cause spurious recycling signals during unrelated assertions.
    monkeypatch.setattr(pool, "_get_rss_memory", lambda: 500 * 1024 * 1024)  # 500MB (< 1GB threshold)

    # 1. Test cumulative page fetches limit triggers recycling at BROWSER_MAX_CUMULATIVE_FETCHES (=200)
    pool._cumulative_fetches = 199
    assert pool._should_recycle() is False

    pool._cumulative_fetches = 200
    assert pool._should_recycle() is True

    # Reset fetches
    pool._cumulative_fetches = 50

    # 2. Test resident set size (RSS) memory boundary > 1GB
    monkeypatch.setattr(pool, "_get_rss_memory", lambda: 500 * 1024 * 1024)  # 500MB
    assert pool._should_recycle() is False

    monkeypatch.setattr(pool, "_get_rss_memory", lambda: 1025 * 1024 * 1024)  # 1.001GB
    assert pool._should_recycle() is True

    # 3. Test recycling process blocks & drains active fetches
    pool._cumulative_fetches = 250
    pool._active_fetches = 1

    # Simulate a background method that decreases active fetches after a delay
    async def simulate_active_fetches_drain() -> None:
        await asyncio.sleep(0.1)
        pool._active_fetches = 0

    # Mock hard_recycle to avoid launching/interacting with real Playwright in unit tests
    recycle_called = False

    async def fake_hard_recycle() -> None:
        nonlocal recycle_called
        recycle_called = True

    monkeypatch.setattr(pool, "_hard_recycle", fake_hard_recycle)

    drain_task = asyncio.create_task(simulate_active_fetches_drain())
    await pool._check_and_trigger_recycle()
    await drain_task

    assert recycle_called is True
    assert pool._recycling is False


def test_diagnostics_exporter_endpoint(client, monkeypatch) -> None:
    """Test Component 3: GET /api/system/diagnostics/export and PII sanitization."""
    # Seed job store with PII data to verify sanitization
    pii_job_id = "pii-job-999"
    job = Job(
        id=pii_job_id,
        name="Sensitive Customer Scraping",
        status=JobStatus.COMPLETED,
        urls=["https://example.com"],
        results=[
            {"email": "harshit.sehgal@gmail.com", "phone": "+91 98765 43210", "auth_header": "Bearer secret_jwt_token_12345"},
        ],
    )
    main_mod.jobs_store[pii_job_id] = job

    # Setup selector memory mock
    class FakeSelectorMemory:
        _memory = {
            "example.com": {
                "selectors": {"title": "h1"},
                "success_count": 10,
                "failure_count": 1,
                "first_seen": 1780000000.0,
                "last_success": 1780000005.0,
            },
        }

        def _compute_confidence(self, entry):
            class FakeConfidence:
                raw_confidence = 0.9
                age_factor = 1.0
                freshness_factor = 1.0
                final_score = 0.9
                reason = "Excellent"

            return FakeConfidence()

    monkeypatch.setattr("app.selector_memory.get_selector_memory", FakeSelectorMemory)

    # Setup world state/observability telemetry mock
    class FakeObservability:
        telemetry = [
            {
                "type": "scrape",
                "timestamp": 1780000000.0,
                "details": {"url": "https://example.com/user/harshit.sehgal@gmail.com"},
            },
        ]

    class FakeWorldState:
        _observability = FakeObservability()

    monkeypatch.setattr("app.semantic_world_state.get_world_state", FakeWorldState)

    # Set config settings values (use ADMIN_API_KEY since endpoint requires ADMIN role)
    monkeypatch.setattr(settings, "API_KEY", "super_secret_api_key_123")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "super_secret_admin_key_456")
    monkeypatch.setattr(settings, "ALERT_WEBHOOK_URL", "http://alert.webhook/endpoint")

    # Retrieve diagnostics zip
    r = client.get("/api/system/diagnostics/export", headers={"X-API-Key": "super_secret_admin_key_456"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    # Parse Zip content in memory
    zip_data = io.BytesIO(r.content)
    with zipfile.ZipFile(zip_data) as zf:
        file_list = zf.namelist()
        assert "anonymized_state.json" in file_list
        assert "active_settings.json" in file_list
        assert "selector_decay_snapshots.json" in file_list
        assert "telemetry_snapshots.json" in file_list

        # Verify anonymized_state.json PII masking
        anonymized_state = json.loads(zf.read("anonymized_state.json"))
        job_data = anonymized_state["jobs"][pii_job_id]
        record = cast("dict[str, Any]", job_data["results"][0])
        assert record["email"] == "<redacted_email>"
        assert record["phone"] == "<redacted_phone>"
        assert "Bearer" not in record["auth_header"]

        # Verify active_settings.json masking
        active_settings: dict = json.loads(zf.read("active_settings.json"))
        assert active_settings["API_KEY"] == "********"
        assert active_settings["ALERT_WEBHOOK_URL"] == "********"

        # Verify selector decay snapshot
        selector_decay: dict = json.loads(zf.read("selector_decay_snapshots.json"))
        assert "example.com" in selector_decay
        assert selector_decay["example.com"]["confidence"]["final_score"] == 0.9

        # Verify telemetry snapshot sanitization
        telemetry: list = json.loads(zf.read("telemetry_snapshots.json"))
        assert len(telemetry) == 1
        assert "<redacted_email>" in telemetry[0]["details"]["url"]


@pytest.mark.asyncio
async def test_domain_escalation_webhook(monkeypatch) -> None:
    """Test Component 4: Outgoing anti-bot escalation webhook alerts."""
    webhook_triggered = False
    webhook_url = "http://test-webhook.local/alert"
    webhook_payload = None

    # 1. Mock the HTTP post call
    async def mock_post(url, json, **kwargs):
        nonlocal webhook_triggered, webhook_payload
        if url == webhook_url:
            webhook_triggered = True
            webhook_payload = json

        class FakeResponse:
            status_code = 200

        return FakeResponse()

    # We monkeypatch the _trigger_webhook inside app.domain_evolution_model
    monkeypatch.setattr("app.domain_evolution_model._trigger_webhook", mock_post)
    monkeypatch.setattr(settings, "ALERT_WEBHOOK_URL", webhook_url)

    # Get the singleton evolution model
    model = get_domain_evolution_model()

    # Seed model domains with initial state
    domain = "volatile-site.com"
    metrics = model._get_or_create(domain)
    metrics.current_anti_bot_level = "basic"

    # 2. Trigger escalation change (anti-bot score 0.85 -> "aggressive")
    model.record_anti_bot_escalation(domain, 0.85)

    # Let async loop tasks run (since loop.create_task is asynchronous)
    await asyncio.sleep(0.1)

    # Verify the webhook POST was correctly generated and contains expected fields
    assert webhook_triggered is True
    assert webhook_payload is not None
    assert webhook_payload["event"] == "anti_bot_escalation"
    assert webhook_payload["domain"] == domain
    assert webhook_payload["old_level"] == "basic"
    assert webhook_payload["new_level"] == "aggressive"
    assert webhook_payload["score"] == 0.85
    assert "timestamp" in webhook_payload
