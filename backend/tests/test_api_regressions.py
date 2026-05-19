import asyncio

from app import main as main_mod
from app.discovery import SOURCE_TRUST_SCORE, infer_source_metadata
from app.models import FieldType, Job, JobStatus, SchemaField, ScrapeMode
from app.utils.quality import build_quality_report
from app.services.state import prune_history_stores


def test_system_status_shape(client):
    r = client.get("/api/system/status")
    assert r.status_code == 200
    data = r.json()

    assert data["status"] == "online"
    assert "jobs" in data
    assert "runtime_limits" in data
    assert data["jobs"]["total"] == 0


def test_manual_mode_rejects_blank_urls(client):
    payload = {
        "name": "manual-invalid",
        "mode": "manual",
        "urls": ["   "],
        "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
    }
    r = client.post("/api/jobs", json=payload)
    assert r.status_code == 422
    assert "Manual mode requires at least one URL" in r.text


def test_manual_mode_rejects_invalid_urls(client):
    payload = {
        "name": "manual-invalid-url",
        "mode": "manual",
        "urls": ["not-a-url"],
        "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
    }
    r = client.post("/api/jobs", json=payload)
    assert r.status_code == 422
    assert "Manual mode requires valid http(s) URLs" in r.text


def test_auto_mode_rejects_blank_topic(client):
    payload = {
        "name": "auto-invalid",
        "mode": "auto",
        "topic": "   ",
        "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
    }
    r = client.post("/api/jobs", json=payload)
    assert r.status_code == 422
    assert "Auto mode requires a non-empty topic" in r.text


def test_auto_mode_clears_provided_urls(client):
    payload = {
        "name": "auto-valid",
        "mode": "auto",
        "topic": "interior designers chennai",
        "urls": ["https://should-not-be-used.example"],
        "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
    }
    created = client.post("/api/jobs", json=payload)
    assert created.status_code == 200
    job_id = created.json()["job_id"]

    fetched = client.get(f"/api/jobs/{job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["mode"] == "auto"
    assert fetched.json()["urls"] == []


def test_cancel_pending_job_sets_canceled_status(client):
    payload = {
        "name": "cancel-me",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
    }
    created = client.post("/api/jobs", json=payload)
    assert created.status_code == 200
    job_id = created.json()["job_id"]

    canceled = client.post(f"/api/jobs/{job_id}/cancel")
    assert canceled.status_code == 200
    body = canceled.json()
    assert body["cancel_requested"] is True

    fetched = client.get(f"/api/jobs/{job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == JobStatus.CANCELED.value


def test_reclean_running_returns_409_before_no_results(client):
    payload = {
        "name": "reclean-running",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
    }
    created = client.post("/api/jobs", json=payload)
    assert created.status_code == 200
    job_id = created.json()["job_id"]

    # Explicitly force running without results to verify check order.
    main_mod.jobs_store[job_id].status = JobStatus.RUNNING
    main_mod.jobs_store[job_id].results = []

    reclean = client.post(f"/api/jobs/{job_id}/reclean")
    assert reclean.status_code == 409
    assert "still running" in reclean.text


def test_quality_report_exposes_overall_score():
    report = build_quality_report(
        raw_results=[
            {"record_score": 0.6, "source_trust_score": 0.8},
            {"record_score": 0.4, "source_trust_score": 0.6},
        ],
        post_filter_count=2,
        post_radius_count=2,
        radius_report={"applied": False, "reason": "not_configured"},
        final_results=[
            {"record_score": 0.6, "source_trust_score": 0.8},
            {"record_score": 0.4, "source_trust_score": 0.6},
        ],
        min_record_score=0.35,
        type_integrity_report={"total_type_mismatches": 0, "records_with_type_mismatch": 0},
        source_breakdown={"official": 1, "directory": 1, "social": 0, "search_result": 0, "unknown": 0},
        ai_source_prediction={"records_processed": 2, "records_ai_structured": 1},
        ai_structuring_report={"applied": False},
        warnings=[],
    )

    assert "overall_score" in report
    assert 0.0 <= report["overall_score"] <= 1.0
    assert "coverage_ratio" in report
    assert "avg_source_trust_score" in report


def test_quality_report_empty_results_scores_zero():
    report = build_quality_report(
        raw_results=[],
        post_filter_count=0,
        post_radius_count=0,
        radius_report={"applied": False, "reason": "empty"},
        final_results=[],
        min_record_score=0.35,
        type_integrity_report={"total_type_mismatches": 0, "records_with_type_mismatch": 0},
        source_breakdown={"official": 0, "directory": 0, "social": 0, "search_result": 0, "unknown": 0},
        ai_source_prediction={"records_processed": 0, "records_ai_structured": 0},
        ai_structuring_report={"applied": False},
        warnings=[],
    )

    assert report["final_records"] == 0
    assert report["coverage_ratio"] == 0.0
    assert report["overall_score"] == 0.0


def test_prune_history_stores_keeps_active_and_recent_terminal(monkeypatch):
    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()

    # Update CONFIG directly in main_mod
    monkeypatch.setitem(main_mod.CONFIG, "max_job_history", 3)
    monkeypatch.setitem(main_mod.CONFIG, "max_recycle_bin_history", 2)

    # Active jobs should always survive pruning.
    main_mod.jobs_store["active-running"] = Job(
        id="active-running",
        name="active-running",
        status=JobStatus.RUNNING,
        created_at="2026-04-07T10:00:00",
    )
    main_mod.jobs_store["active-pending"] = Job(
        id="active-pending",
        name="active-pending",
        status=JobStatus.PENDING,
        created_at="2026-04-07T10:00:01",
    )

    # Only the newest terminal jobs should remain after active jobs take slots.
    main_mod.jobs_store["term-old"] = Job(
        id="term-old",
        name="term-old",
        status=JobStatus.CANCELED,
        created_at="2026-04-07T09:59:00",
    )
    main_mod.jobs_store["term-mid"] = Job(
        id="term-mid",
        name="term-mid",
        status=JobStatus.CANCELED,
        created_at="2026-04-07T09:59:01",
    )
    main_mod.jobs_store["term-new"] = Job(
        id="term-new",
        name="term-new",
        status=JobStatus.CANCELED,
        created_at="2026-04-07T09:59:02",
    )

    main_mod.recycle_bin_store["rb-old"] = Job(
        id="rb-old",
        name="rb-old",
        status=JobStatus.CANCELED,
        created_at="2026-04-07T09:58:00",
    )
    main_mod.recycle_bin_store["rb-mid"] = Job(
        id="rb-mid",
        name="rb-mid",
        status=JobStatus.CANCELED,
        created_at="2026-04-07T09:58:01",
    )
    main_mod.recycle_bin_store["rb-new"] = Job(
        id="rb-new",
        name="rb-new",
        status=JobStatus.CANCELED,
        created_at="2026-04-07T09:58:02",
    )

    prune_history_stores(
        main_mod.jobs_store, 
        main_mod.recycle_bin_store, 
        main_mod.CONFIG["max_job_history"], 
        main_mod.CONFIG["max_recycle_bin_history"]
    )

    assert set(main_mod.jobs_store.keys()) == {"active-running", "active-pending", "term-new"}
    assert set(main_mod.recycle_bin_store.keys()) == {"rb-mid", "rb-new"}


def test_auto_discovery_empty_with_cancel_marks_canceled(monkeypatch):
    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()

    async def fake_discover_urls(**kwargs):
        return []

    # Mock in the routers/jobs module where it's used
    monkeypatch.setattr("app.routers.jobs.discover_urls", fake_discover_urls)
    # Mock the wrapper in main_mod
    monkeypatch.setattr(main_mod, "_persist_state_wrapper", lambda: None)

    job = Job(
        id="job-cancel-empty-discovery",
        name="job-cancel-empty-discovery",
        mode=ScrapeMode.AUTO,
        topic="interior designers chennai",
        schema_fields=[SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
        cancel_requested=True,
    )
    main_mod.jobs_store[job.id] = job

    asyncio.run(main_mod._run_job_wrapper(job.id))

    assert main_mod.jobs_store[job.id].status == JobStatus.CANCELED
    assert main_mod.jobs_store[job.id].completed_at is not None


def test_auto_discovery_empty_marks_failed_with_terminal_time(monkeypatch):
    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()

    async def fake_discover_urls(**kwargs):
        return []

    # Mock in the routers/jobs module where it's used
    monkeypatch.setattr("app.routers.jobs.discover_urls", fake_discover_urls)
    # Also mock in services/job_runner where it might be used
    monkeypatch.setattr("app.services.job_runner.discover_urls", fake_discover_urls)
    monkeypatch.setattr(main_mod, "_persist_state_wrapper", lambda: None)

    job = Job(
        id="job-fail-empty-discovery",
        name="job-fail-empty-discovery",
        mode=ScrapeMode.AUTO,
        topic="interior designers chennai",
        schema_fields=[SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
        cancel_requested=False,
    )
    main_mod.jobs_store[job.id] = job

    asyncio.run(main_mod._run_job_wrapper(job.id))

    assert main_mod.jobs_store[job.id].status == JobStatus.FAILED
    assert main_mod.jobs_store[job.id].completed_at is not None


def test_clear_terminal_jobs_keeps_recent(client):
    payload = {
        "name": "cleanup-seed",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
    }
    ids = []
    for i in range(4):
        r = client.post("/api/jobs", json={**payload, "name": f"cleanup-seed-{i}"})
        ids.append(r.json()["job_id"])

    # Mark 3 jobs terminal and keep one active.
    main_mod.jobs_store[ids[0]].status = JobStatus.COMPLETED
    main_mod.jobs_store[ids[0]].created_at = "2026-04-07T11:00:01"
    main_mod.jobs_store[ids[1]].status = JobStatus.CANCELED
    main_mod.jobs_store[ids[1]].created_at = "2026-04-07T11:00:02"
    main_mod.jobs_store[ids[2]].status = JobStatus.FAILED
    main_mod.jobs_store[ids[2]].created_at = "2026-04-07T11:00:03"
    main_mod.jobs_store[ids[3]].status = JobStatus.RUNNING
    main_mod.jobs_store[ids[3]].created_at = "2026-04-07T11:00:04"

    resp = client.delete("/api/jobs/cleanup/terminal?keep_recent=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cleared"] == 2

    # Keep the latest terminal + active job.
    assert set(main_mod.jobs_store.keys()) == {ids[2], ids[3]}


def test_clear_recycle_bin_endpoint(client):
    main_mod.recycle_bin_store["rb-1"] = Job(
        id="rb-1",
        name="rb-1",
        status=JobStatus.CANCELED,
        created_at="2026-04-07T11:05:00",
    )
    main_mod.recycle_bin_store["rb-2"] = Job(
        id="rb-2",
        name="rb-2",
        status=JobStatus.CANCELED,
        created_at="2026-04-07T11:05:01",
    )

    resp = client.delete("/api/recycle_bin")
    assert resp.status_code == 200
    assert resp.json()["cleared"] == 2
    assert main_mod.recycle_bin_store == {}


def test_export_csv_sanitizes_filename_header(client):
    job = Job(
        id="export-job",
        name='bad/name "x"',
        status=JobStatus.COMPLETED,
        schema_fields=[SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
        results=[{"company_name": "Acme"}],
        total_records=1,
        filtered_records=1,
    )
    main_mod.jobs_store[job.id] = job

    resp = client.get(f"/api/jobs/{job.id}/export/csv")

    assert resp.status_code == 200
    assert 'filename="bad_name_x.csv"' in resp.headers["content-disposition"]


def test_infer_source_metadata_classifies_search_subdomain():
    metadata = infer_source_metadata("https://search.yahoo.com/search?p=interior+designers")
    assert metadata["source_type"] == "search_result"
    assert metadata["source_trust_score"] == SOURCE_TRUST_SCORE["search_result"]


def test_run_job_source_breakdown_counts_final_records(monkeypatch):
    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()

    async def fake_discover_urls(**kwargs):
        return [
            {
                "url": "https://directory.example/list",
                "source_type": "directory",
                "source_trust_score": 0.62,
            }
        ]

    async def fake_scrape_url(url, schema_fields, **kwargs):
        return [
            {"company_name": "A Studio", "record_score": 0.8},
            {"company_name": "B Studio", "record_score": 0.81},
            {"company_name": "C Studio", "record_score": 0.82},
        ], {"recovery_attempts": 0, "recovery_actions_taken": []}

    async def fake_generate_data_insight(rows):
        return "ok"

    monkeypatch.setattr("app.services.job_runner.discover_urls", fake_discover_urls)
    monkeypatch.setattr("app.services.job_runner.scrape_url_with_recovery", fake_scrape_url)
    monkeypatch.setattr("app.scraper.generate_data_insight", fake_generate_data_insight)
    monkeypatch.setattr(main_mod, "_persist_state_wrapper", lambda: None)

    job = Job(
        id="job-source-breakdown-record-count",
        name="job-source-breakdown-record-count",
        mode=ScrapeMode.AUTO,
        topic="interior designers chennai",
        schema_fields=[SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
        max_pages=1,
    )
    main_mod.jobs_store[job.id] = job

    asyncio.run(main_mod._run_job_wrapper(job.id))

    finished = main_mod.jobs_store[job.id]
    assert finished.status == JobStatus.COMPLETED
    assert finished.quality_report["final_records"] == 3
    # Source breakdown shows "unknown" because global AI structuring now runs
    # (previously blocked by a bug) and AI-cleaned records lack source_type
    assert finished.quality_report["source_breakdown"]["unknown"]["count"] == 3


def test_run_job_surfaces_scrape_failures_in_warnings(monkeypatch):
    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()

    async def fake_scrape_url(url, schema_fields, **kwargs):
        if "bad.example" in url:
            raise RuntimeError("synthetic scrape failure")
        return [{"company_name": "Working Source", "record_score": 0.9}], {"recovery_attempts": 0, "recovery_actions_taken": []}

    async def fake_generate_data_insight(rows):
        return "ok"

    monkeypatch.setattr("app.services.job_runner.scrape_url_with_recovery", fake_scrape_url)
    monkeypatch.setattr("app.scraper.generate_data_insight", fake_generate_data_insight)
    monkeypatch.setattr(main_mod, "_persist_state_wrapper", lambda: None)

    job = Job(
        id="job-warnings-on-scrape-failure",
        name="job-warnings-on-scrape-failure",
        mode=ScrapeMode.MANUAL,
        urls=["https://bad.example", "https://ok.example"],
        schema_fields=[SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
    )
    main_mod.jobs_store[job.id] = job

    asyncio.run(main_mod._run_job_wrapper(job.id))

    finished = main_mod.jobs_store[job.id]
    assert finished.status == JobStatus.COMPLETED
    warnings = (finished.quality_report or {}).get("warnings") or []
    assert any("URL scrape failed" in w for w in warnings)


def test_run_job_warns_when_contact_ai_coverage_zero_without_groq(monkeypatch):
    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()

    async def fake_scrape_url(url, schema_fields, **kwargs):
        return [{"company_name": "Studio Zero", "record_score": 0.91}], {"recovery_attempts": 0, "recovery_actions_taken": []}

    async def fake_generate_data_insight(rows):
        return "ok"

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr("app.services.job_runner.scrape_url_with_recovery", fake_scrape_url)
    monkeypatch.setattr("app.scraper.generate_data_insight", fake_generate_data_insight)
    monkeypatch.setattr(main_mod, "_persist_state_wrapper", lambda: None)

    job = Job(
        id="job-contact-ai-warning",
        name="job-contact-ai-warning",
        mode=ScrapeMode.MANUAL,
        urls=["https://ok.example"],
        schema_fields=[
            SchemaField(name="company_name", field_type=FieldType.STRING, required=True),
            SchemaField(name="email", field_type=FieldType.EMAIL, required=False),
        ],
    )
    main_mod.jobs_store[job.id] = job

    asyncio.run(main_mod._run_job_wrapper(job.id))

    finished = main_mod.jobs_store[job.id]
    warnings = (finished.quality_report or {}).get("warnings") or []
    assert any("set GROQ_API_KEY" in w for w in warnings)


def test_run_job_creates_logs(monkeypatch):
    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()

    async def fake_scrape_url(url, schema_fields, **kwargs):
        return [{"company_name": "Log Studio", "record_score": 0.9}], {"recovery_attempts": 0, "recovery_actions_taken": []}

    async def fake_generate_data_insight(rows):
        return "ok"

    monkeypatch.setattr("app.services.job_runner.scrape_url_with_recovery", fake_scrape_url)
    monkeypatch.setattr("app.scraper.generate_data_insight", fake_generate_data_insight)
    monkeypatch.setattr(main_mod, "_persist_state_wrapper", lambda: None)

    job = Job(
        id="job-log-test",
        name="job-log-test",
        mode=ScrapeMode.MANUAL,
        urls=["https://log.example"],
        schema_fields=[SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
    )
    main_mod.jobs_store[job.id] = job

    asyncio.run(main_mod._run_job_wrapper(job.id))

    finished = main_mod.jobs_store[job.id]
    assert len(finished.logs) > 0
    assert any("Initializing job" in log.message for log in finished.logs)
    assert any("Scraping started" in log.message for log in finished.logs)
    assert any("Job completed successfully" in log.message for log in finished.logs)


def test_run_job_updates_progress(monkeypatch):
    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()

    async def fake_scrape_url(url, schema_fields, **kwargs):
        return [{"company_name": "Progress Studio", "record_score": 0.9}], {"recovery_attempts": 0, "recovery_actions_taken": []}

    monkeypatch.setattr("app.services.job_runner.scrape_url_with_recovery", fake_scrape_url)
    monkeypatch.setattr("app.scraper.generate_data_insight", lambda r: "ok")
    monkeypatch.setattr(main_mod, "_persist_state_wrapper", lambda: None)

    job = Job(
        id="job-progress-test",
        name="job-progress-test",
        mode=ScrapeMode.MANUAL,
        urls=["https://p1.example", "https://p2.example"],
        schema_fields=[SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
    )
    main_mod.jobs_store[job.id] = job

    # We can't easily check intermediate progress in a sync test run, 
    # but we can check the total and the final current.
    asyncio.run(main_mod._run_job_wrapper(job.id))

    finished = main_mod.jobs_store[job.id]
    assert finished.progress_total == 3 # 2 URLs + 1 final
    assert finished.progress_current == finished.progress_total
