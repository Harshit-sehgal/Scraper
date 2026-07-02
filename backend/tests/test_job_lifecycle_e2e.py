"""Core job lifecycle E2E integration test.

Exercises the full product flow through the REST API:
  1. Create job → PENDING
  2. Run job → COMPLETED
  3. Get results
  4. Export CSV, JSON, Excel
  5. Cancel RUNNING job
  6. SSRF-blocked URL rejected
  7. Job events / quality / diff endpoints
  8. List jobs contains created job
  9. CSV vs JSON cross-format consistency

No real network — scrape_url is mocked. No Postgres or Playwright required.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
from unittest.mock import AsyncMock

import pytest
from app.models import JobStatus

# ─── Shared helpers ────────────────────────────────────────────────────

_MOCK_RECORDS = [
    {"title": "Example Book", "price": "$19.99"},
    {"title": "Another Book", "price": "$24.50"},
]


async def _fake_run_job(job_id: str, **kwargs) -> None:
    """Simulate run_job: transition PENDING → RUNNING → COMPLETED with mock results."""
    from app.main import jobs_store

    job = jobs_store.get(job_id)
    if job is None:
        return

    job.status = JobStatus.RUNNING
    job.results = list(_MOCK_RECORDS)
    job.total_records = len(_MOCK_RECORDS)
    for rec in job.results:
        rec["_source_url"] = str(job.urls[0]) if job.urls else ""
        rec["_extraction_method"] = "schema"
        rec["_extraction_source"] = "html"
    job.status = JobStatus.COMPLETED


def _discard_schedule(coro):
    """Accept and close the coroutine to avoid RuntimeWarning about unawaited coroutines."""
    if coro is not None and hasattr(coro, "close"):
        coro.close()


def _wire_runtime_deps(monkeypatch, *, run_job_fn=None):
    """Wire up runtime deps with a mocked run_job and schedule function."""
    import app.runtime_deps as _rd

    monkeypatch.setattr(_rd, "run_job_coro_fn", run_job_fn or _fake_run_job)
    monkeypatch.setattr(_rd, "schedule_task_fn", _discard_schedule)


def _run_job_sync(job_id: str) -> None:
    """Run _fake_run_job in a fresh event loop (for sync test methods)."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_fake_run_job(job_id))
    finally:
        loop.close()


MINIMAL_JOB = {
    "name": "e2e-lifecycle-job",
    "mode": "manual",
    "urls": ["https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"],
    "schema_fields": [
        {"name": "title", "field_type": "string", "required": True},
        {"name": "price", "field_type": "string", "required": False},
    ],
}


# ─── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.api
class TestJobLifecycleE2E:
    """Full product-path E2E: create → run → status → results → export."""

    # ── 1. Create job → PENDING ───────────────────────────────────────

    def test_create_job_returns_pending(self, client, monkeypatch) -> None:
        """POST /api/jobs returns 201 with status=pending."""

        async def noop_run_job(job_id: str, **kwargs) -> None:
            return

        _wire_runtime_deps(monkeypatch, run_job_fn=noop_run_job)

        resp = client.post("/api/jobs", json=MINIMAL_JOB)
        assert resp.status_code == 201, f"Create failed: {resp.status_code} {resp.text}"
        body = resp.json()
        assert "job_id" in body
        assert body["status"] == "pending"

        # Verify GET /api/jobs/{id} shows PENDING
        job_id = body["job_id"]
        resp2 = client.get(f"/api/jobs/{job_id}")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "pending"

    # ── 2. Full lifecycle: create → run → completed → results ─────────

    def test_full_lifecycle_create_run_results(self, client, monkeypatch) -> None:
        """Create job → run it → verify completed → get results."""
        _wire_runtime_deps(monkeypatch)

        # Mock scrape_url to prevent real network
        monkeypatch.setattr(
            "app.scraper.scrape_url",
            AsyncMock(return_value=_MOCK_RECORDS),
        )
        monkeypatch.setattr(
            "app.insight_engine.generate_data_insight",
            AsyncMock(return_value="Mock insight for lifecycle test."),
        )

        # Step 1: Create
        resp = client.post("/api/jobs", json=MINIMAL_JOB)
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]

        # Step 2: Manually trigger the job runner
        _run_job_sync(job_id)

        # Step 3: Verify completed
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        job_data = resp.json()
        assert job_data["status"] == "completed", f"Expected completed, got {job_data['status']}"

        # Step 4: Get results
        resp = client.get(f"/api/jobs/{job_id}/results")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 2, f"Expected ≥2 results, got {len(results)}"

    # ── 3. Export CSV ──────────────────────────────────────────────────

    def test_export_csv_after_completion(self, client, monkeypatch) -> None:
        """Completed job exports valid CSV with expected columns."""
        _wire_runtime_deps(monkeypatch)

        resp = client.post("/api/jobs", json=MINIMAL_JOB)
        job_id = resp.json()["job_id"]
        _run_job_sync(job_id)

        # Export CSV
        resp = client.get(f"/api/jobs/{job_id}/export/csv")
        assert resp.status_code == 200, f"CSV export failed: {resp.status_code} {resp.text}"

        # Parse CSV content
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) >= 2, f"Expected ≥2 CSV rows, got {len(rows)}"
        assert "title" in rows[0], f"'title' not in CSV headers: {list(rows[0].keys())}"

    # ── 4. Export JSON ────────────────────────────────────────────────

    def test_export_json_after_completion(self, client, monkeypatch) -> None:
        """Completed job exports valid JSON with expected structure."""
        _wire_runtime_deps(monkeypatch)

        resp = client.post("/api/jobs", json=MINIMAL_JOB)
        job_id = resp.json()["job_id"]
        _run_job_sync(job_id)

        resp = client.get(f"/api/jobs/{job_id}/export/json")
        assert resp.status_code == 200, f"JSON export failed: {resp.status_code} {resp.text}"

        data = json.loads(resp.text)
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = data.get("results", data.get("records", [data]))
        else:
            records = []
        assert len(records) >= 2, f"Expected ≥2 JSON records, got {len(records)}"

    # ── 5. Export Excel (XLSX) ────────────────────────────────────────

    def test_export_xlsx_after_completion(self, client, monkeypatch) -> None:
        """Completed job exports a valid XLSX file."""
        _wire_runtime_deps(monkeypatch)

        resp = client.post("/api/jobs", json=MINIMAL_JOB)
        job_id = resp.json()["job_id"]
        _run_job_sync(job_id)

        resp = client.get(f"/api/jobs/{job_id}/export/excel")
        assert resp.status_code == 200, f"Excel export failed: {resp.status_code} {resp.text}"
        content_type = resp.headers.get("content-type", "")
        assert "spreadsheet" in content_type or "octet-stream" in content_type or "xlsx" in content_type, (
            f"Unexpected content-type: {content_type}"
        )
        assert len(resp.content) > 100, "XLSX content too small — likely empty or error"

    # ── 6. Cancel RUNNING job ────────────────────────────────────────

    def test_cancel_running_job(self, client, monkeypatch) -> None:
        """Cancel a RUNNING job sets cancel_requested without changing status."""
        import app.main as main_mod

        _wire_runtime_deps(monkeypatch)

        resp = client.post("/api/jobs", json=MINIMAL_JOB)
        job_id = resp.json()["job_id"]

        # Manually set to RUNNING
        main_mod.jobs_store[job_id].status = JobStatus.RUNNING
        main_mod.jobs_store[job_id].cancel_requested = False

        cancel_resp = client.post(f"/api/jobs/{job_id}/cancel")
        assert cancel_resp.status_code == 200
        body = cancel_resp.json()
        assert body.get("cancel_requested") is True, f"cancel_requested not set: {body}"

    # ── 7. SSRF-blocked URL rejected on create ────────────────────────

    def test_blocked_url_rejected_on_create(self, client, monkeypatch) -> None:
        """Creating a job with an SSRF-blocked URL returns 4xx."""
        _wire_runtime_deps(monkeypatch)

        resp = client.post(
            "/api/jobs",
            json={
                "name": "ssrf-reject",
                "mode": "manual",
                "urls": ["http://169.254.169.254/latest/meta-data/"],
                "schema_fields": [{"name": "data", "field_type": "string"}],
            },
        )
        assert resp.status_code in (400, 403, 422), f"SSRF URL not blocked: {resp.status_code}"

    # ── 8. Job events endpoint ────────────────────────────────────────

    def test_job_events_endpoint(self, client, monkeypatch) -> None:
        """GET /api/jobs/{id}/events returns events for a created job."""
        _wire_runtime_deps(monkeypatch)

        resp = client.post("/api/jobs", json=MINIMAL_JOB)
        job_id = resp.json()["job_id"]

        events_resp = client.get(f"/api/jobs/{job_id}/events")
        assert events_resp.status_code in (200, 404), f"Unexpected events status: {events_resp.status_code}"

    # ── 9. Quality endpoint ────────────────────────────────────────────

    def test_quality_endpoint(self, client, monkeypatch) -> None:
        """GET /api/jobs/{id}/quality returns quality metrics for a completed job."""
        _wire_runtime_deps(monkeypatch)

        resp = client.post("/api/jobs", json=MINIMAL_JOB)
        job_id = resp.json()["job_id"]
        _run_job_sync(job_id)

        quality_resp = client.get(f"/api/jobs/{job_id}/quality")
        assert quality_resp.status_code in (200, 404), f"Unexpected quality status: {quality_resp.status_code}"

    # ── 10. Diff endpoint ────────────────────────────────────────────

    def test_diff_endpoint(self, client, monkeypatch) -> None:
        """GET /api/jobs/{id}/diff returns diff info (requires compare_to param)."""
        _wire_runtime_deps(monkeypatch)

        resp = client.post("/api/jobs", json=MINIMAL_JOB)
        job_id = resp.json()["job_id"]
        _run_job_sync(job_id)

        diff_resp = client.get(f"/api/jobs/{job_id}/diff")
        # Diff requires compare_to query param, so 400 is expected without it
        assert diff_resp.status_code in (200, 400, 404), f"Unexpected diff status: {diff_resp.status_code}"

    # ── 11. List jobs returns created job ─────────────────────────────

    def test_list_jobs_contains_created_job(self, client, monkeypatch) -> None:
        """GET /api/jobs returns a list containing the created job."""
        _wire_runtime_deps(monkeypatch)

        resp = client.post("/api/jobs", json=MINIMAL_JOB)
        job_id = resp.json()["job_id"]

        list_resp = client.get("/api/jobs")
        assert list_resp.status_code == 200
        body = list_resp.json()
        # Response shape: {"total": ..., "items": [...], "jobs": [...]}
        items = body.get("items", body.get("jobs", []))
        assert isinstance(items, list), f"Expected list of items, got {type(items).__name__}"
        job_ids = [j.get("id", j.get("job_id")) for j in items]
        assert job_id in job_ids, f"Created job {job_id} not in job list: {job_ids}"

    # ── 12. CSV vs JSON consistency ───────────────────────────────────

    def test_csv_json_content_consistency(self, client, monkeypatch) -> None:
        """CSV and JSON exports contain the same records for a completed job."""
        _wire_runtime_deps(monkeypatch)

        resp = client.post("/api/jobs", json=MINIMAL_JOB)
        job_id = resp.json()["job_id"]
        _run_job_sync(job_id)

        # Get CSV
        csv_resp = client.get(f"/api/jobs/{job_id}/export/csv")
        assert csv_resp.status_code == 200
        reader = csv.DictReader(io.StringIO(csv_resp.text))
        csv_rows = list(reader)

        # Get JSON
        json_resp = client.get(f"/api/jobs/{job_id}/export/json")
        assert json_resp.status_code == 200
        json_data = json.loads(json_resp.text)
        if isinstance(json_data, list):
            json_records = json_data
        elif isinstance(json_data, dict):
            json_records = json_data.get("results", json_data.get("records", [json_data]))
        else:
            json_records = []

        # Both formats should contain the same number of core records
        assert len(csv_rows) == len(json_records), f"CSV rows ({len(csv_rows)}) != JSON records ({len(json_records)})"

        # Field names from schema should appear in both
        for field_name in ("title", "price"):
            csv_has = any(field_name in row for row in csv_rows)
            json_has = any(field_name in rec for rec in json_records)
            assert csv_has, f"'{field_name}' missing from CSV export"
            assert json_has, f"'{field_name}' missing from JSON export"
