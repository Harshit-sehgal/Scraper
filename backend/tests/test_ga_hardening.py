import asyncio

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

    # ARCH-001 refactoring moved reclean logic from jobs_write.py into
    # JobRecleanerService (app.services.job_mutation_service.py), which
    # imports ai_clean_and_align_records lazily from app.scraper inside
    # the method body.  Patching the source module (app.scraper) ensures
    # the lazy import resolves to the mock regardless of the caller.
    monkeypatch.setattr("app.scraper.ai_clean_and_align_records", fake_ai_clean_and_align)

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
    """Diagnostics export endpoint has been removed. Verify the route returns 404."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "super_secret_admin_key_456")

    r = client.get("/api/system/diagnostics/export", headers={"X-API-Key": "super_secret_admin_key_456"})
    assert r.status_code == 404


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
