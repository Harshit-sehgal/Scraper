"""P0 billing date math and usage quota regression tests."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.config import settings
from app.models import Job, JobStatus
from app.utils import billing as billing_mod
from app.utils import usage_ledger as usage_mod
from app.utils.billing import InvoiceGenerator, InvoiceItem
from app.utils.rbac import _fingerprint_key
from app.utils.usage_ledger import QuotaPeriod, UsageLedger, UsageType


def _freeze_billing_now(monkeypatch: pytest.MonkeyPatch, fixed: datetime) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed.replace(tzinfo=None)
            return fixed.astimezone(tz)

    monkeypatch.setattr(billing_mod, "datetime", FixedDateTime)


@pytest.mark.parametrize(
    ("now", "due_days", "expected"),
    [
        (datetime(2026, 1, 31, 12, 0, tzinfo=UTC), 30, datetime(2026, 3, 2, 12, 0, tzinfo=UTC)),
        (datetime(2024, 2, 28, 8, 15, tzinfo=UTC), 1, datetime(2024, 2, 29, 8, 15, tzinfo=UTC)),
        (datetime(2026, 6, 11, 9, 30, tzinfo=UTC), 30, datetime(2026, 7, 11, 9, 30, tzinfo=UTC)),
        (datetime(2026, 6, 11, 9, 30, tzinfo=UTC), 0, datetime(2026, 6, 11, 9, 30, tzinfo=UTC)),
    ],
)
def test_generate_invoice_due_date_uses_timedelta(monkeypatch, now: datetime, due_days: int, expected: datetime) -> None:
    _freeze_billing_now(monkeypatch, now)
    generator = InvoiceGenerator()

    invoice = generator.generate_invoice(
        "user-1",
        [InvoiceItem(description="usage", quantity=1, unit_price=10, total=10)],
        due_days=due_days,
    )

    assert invoice.due_date == expected
    assert invoice.due_date is not None
    assert invoice.due_date.tzinfo == UTC


def test_generate_invoice_rejects_negative_due_days(monkeypatch) -> None:
    _freeze_billing_now(monkeypatch, datetime(2026, 6, 11, 9, 30, tzinfo=UTC))
    generator = InvoiceGenerator()

    with pytest.raises(ValueError, match="due_days"):
        generator.generate_invoice("user-1", [], due_days=-1)


def test_record_usage_increments_quota_and_checks_amount() -> None:
    ledger = UsageLedger()
    ledger.set_quota("user-1", UsageType.API_REQUEST, limit=2, period=QuotaPeriod.MONTHLY)

    ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=1)

    quota = ledger.get_quota("user-1", UsageType.API_REQUEST)
    assert quota is not None
    assert quota.current_usage == 1
    assert ledger.check_quota("user-1", UsageType.API_REQUEST, amount=1)[0] is True
    assert ledger.check_quota("user-1", UsageType.API_REQUEST, amount=2)[0] is False


def test_record_usage_rejects_usage_above_quota() -> None:
    ledger = UsageLedger()
    ledger.set_quota("user-1", UsageType.API_REQUEST, limit=1, period=QuotaPeriod.MONTHLY)

    with pytest.raises(ValueError, match="quota"):
        ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=2)

    quota = ledger.get_quota("user-1", UsageType.API_REQUEST)
    assert quota is not None
    assert quota.current_usage == 0
    assert ledger.get_usage("user-1", UsageType.API_REQUEST) == []


def test_usage_idempotency_key_does_not_double_charge() -> None:
    ledger = UsageLedger()
    ledger.set_quota("user-1", UsageType.EXPORT_GENERATED, limit=1, period=QuotaPeriod.MONTHLY)

    first = ledger.record_usage(
        "user-1",
        UsageType.EXPORT_GENERATED,
        quantity=1,
        idempotency_key="export-123",
    )
    second = ledger.record_usage(
        "user-1",
        UsageType.EXPORT_GENERATED,
        quantity=1,
        idempotency_key="export-123",
    )

    quota = ledger.get_quota("user-1", UsageType.EXPORT_GENERATED)
    assert quota is not None
    assert first.id == second.id
    assert quota.current_usage == 1
    assert len(ledger.get_usage("user-1", UsageType.EXPORT_GENERATED)) == 1


def test_usage_ledger_persists_events_and_quota_state(tmp_path) -> None:
    db_path = tmp_path / "usage.db"
    ledger = UsageLedger(storage_path=db_path)
    ledger.set_quota("user-1", UsageType.JOB_CREATED, limit=5, period=QuotaPeriod.MONTHLY)
    ledger.record_usage("user-1", UsageType.JOB_CREATED, quantity=2, metadata={"job_id": "job-1"})

    reloaded = UsageLedger(storage_path=db_path)

    quota = reloaded.get_quota("user-1", UsageType.JOB_CREATED)
    records = reloaded.get_usage("user-1", UsageType.JOB_CREATED)
    assert quota is not None
    assert quota.current_usage == 2
    assert quota.limit == 5
    assert len(records) == 1
    assert records[0].metadata == {"job_id": "job-1"}


def test_concurrent_usage_cannot_exceed_quota() -> None:
    ledger = UsageLedger()
    ledger.set_quota("user-1", UsageType.PAGE_FETCHED, limit=5, period=QuotaPeriod.MONTHLY)
    barrier = threading.Barrier(10)
    successes: list[str] = []
    failures: list[str] = []

    def worker(idx: int) -> None:
        barrier.wait(timeout=5)
        try:
            ledger.record_usage("user-1", UsageType.PAGE_FETCHED, quantity=1, idempotency_key=f"fetch-{idx}")
            successes.append(str(idx))
        except ValueError:
            failures.append(str(idx))

    threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    quota = ledger.get_quota("user-1", UsageType.PAGE_FETCHED)
    assert quota is not None
    assert len(successes) == 5
    assert len(failures) == 5
    assert quota.current_usage == 5
    assert len(ledger.get_usage("user-1", UsageType.PAGE_FETCHED)) == 5


def _configure_request_metering_keys(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "API_KEY", "user-key")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "operator-key")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "admin-key")
    monkeypatch.setattr(settings, "ENV", "test")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_DEV_AUTH", False)
    return _fingerprint_key("user-key")


def test_api_request_middleware_records_protected_requests(client, monkeypatch) -> None:
    user_id = _configure_request_metering_keys(monkeypatch)
    ledger = UsageLedger()
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    response = client.get("/api/jobs", headers={"X-API-Key": "user-key"})

    assert response.status_code == 200
    records = ledger.get_usage(user_id, UsageType.API_REQUEST)
    assert len(records) == 1
    assert records[0].metadata["path"] == "/api/jobs"
    assert records[0].metadata["method"] == "GET"


def test_api_request_quota_is_enforced_by_middleware(client, monkeypatch) -> None:
    import app.middlewares as middlewares_mod

    user_id = _configure_request_metering_keys(monkeypatch)
    ledger = UsageLedger()
    ledger.set_quota(user_id, UsageType.API_REQUEST, limit=1, period=QuotaPeriod.MONTHLY)
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    # Capture audit events before making requests
    audit_events: list[dict] = []

    def _capture_audit(actor, action, resource, role, outcome, details=None):
        audit_events.append({
            "actor": actor,
            "action": action,
            "resource": resource,
            "role": role,
            "outcome": outcome,
            "details": details or {},
        })

    monkeypatch.setattr(middlewares_mod, "log_rbac_event", _capture_audit, raising=False)

    first = client.get("/api/jobs", headers={"X-API-Key": "user-key"})
    second = client.get("/api/jobs", headers={"X-API-Key": "user-key"})

    assert first.status_code == 200
    assert second.status_code == 429
    quota = ledger.get_quota(user_id, UsageType.API_REQUEST)
    assert quota is not None
    assert quota.current_usage == 1
    assert len(ledger.get_usage(user_id, UsageType.API_REQUEST)) == 1

    # Verify audit event was emitted for the quota denial
    assert any(
        e.get("action") == "quota_exceeded:api_request"
        and e.get("outcome") == "denied"
        and e.get("details", {}).get("error", "").startswith("quota exceeded")
        for e in audit_events
    ), f"Expected quota_exceeded audit event not found in {audit_events}"


def test_public_session_me_is_not_metered(client, monkeypatch) -> None:
    _configure_request_metering_keys(monkeypatch)
    ledger = UsageLedger()
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    response = client.get("/api/session/me")

    assert response.status_code == 200
    assert ledger.get_usage(_fingerprint_key("user-key"), UsageType.API_REQUEST) == []


def _seed_export_job(job_id: str = "export-meter-job") -> Job:
    import app.main as main_mod

    job = Job(
        id=job_id,
        name="Export Meter Job",
        urls=["https://example.com/data"],
        status=JobStatus.COMPLETED,
        results=[{"name": "Acme", "value": "42"}],
    )
    main_mod.jobs_store[job.id] = job
    return job


def test_export_quota_is_enforced(client, monkeypatch) -> None:
    _configure_request_metering_keys(monkeypatch)
    operator_id = _fingerprint_key("operator-key")
    job = _seed_export_job()
    ledger = UsageLedger()
    ledger.set_quota(operator_id, UsageType.EXPORT_GENERATED, limit=1, period=QuotaPeriod.MONTHLY)
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    first = client.get(f"/api/jobs/{job.id}/export/csv", headers={"X-API-Key": "operator-key"})
    second = client.get(f"/api/jobs/{job.id}/export/csv", headers={"X-API-Key": "operator-key"})

    assert first.status_code == 200
    assert second.status_code == 429
    quota = ledger.get_quota(operator_id, UsageType.EXPORT_GENERATED)
    assert quota is not None
    assert quota.current_usage == 1
    records = ledger.get_usage(operator_id, UsageType.EXPORT_GENERATED)
    assert len(records) == 1
    assert records[0].metadata["job_id"] == job.id
    assert records[0].metadata["format"] == "csv"


def test_export_idempotency_key_does_not_double_charge(client, monkeypatch) -> None:
    _configure_request_metering_keys(monkeypatch)
    operator_id = _fingerprint_key("operator-key")
    job = _seed_export_job("export-idempotent-job")
    ledger = UsageLedger()
    ledger.set_quota(operator_id, UsageType.EXPORT_GENERATED, limit=1, period=QuotaPeriod.MONTHLY)
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)
    headers = {"X-API-Key": "operator-key", "Idempotency-Key": "export-retry-1"}

    first = client.get(f"/api/jobs/{job.id}/export/json", headers=headers)
    second = client.get(f"/api/jobs/{job.id}/export/json", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    quota = ledger.get_quota(operator_id, UsageType.EXPORT_GENERATED)
    assert quota is not None
    assert quota.current_usage == 1
    assert len(ledger.get_usage(operator_id, UsageType.EXPORT_GENERATED)) == 1


def test_failed_export_is_not_charged(client, monkeypatch) -> None:
    _configure_request_metering_keys(monkeypatch)
    operator_id = _fingerprint_key("operator-key")
    ledger = UsageLedger()
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    response = client.get("/api/jobs/missing-export-job/export/csv", headers={"X-API-Key": "operator-key"})

    assert response.status_code == 404
    assert ledger.get_usage(operator_id, UsageType.EXPORT_GENERATED) == []


def test_record_page_fetch_records_page_fetched_usage(monkeypatch) -> None:
    from app.services.scraping import _record_page_fetch

    ledger = UsageLedger()
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    job = Job(
        id="fetch-test-job",
        name="fetch-test",
        created_by="user-page",
        urls=["https://example.com"],
        status=JobStatus.RUNNING,
    )
    _record_page_fetch(job, "https://example.com/page")

    records = ledger.get_usage("user-page", UsageType.PAGE_FETCHED)
    assert len(records) == 1
    assert records[0].quantity == 1
    assert records[0].metadata["url"] == "https://example.com/page"
    assert records[0].metadata["job_id"] == "fetch-test-job"


def test_record_page_fetch_skips_when_created_by_missing(monkeypatch) -> None:
    from app.services.scraping import _record_page_fetch

    ledger = UsageLedger()
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    job = Job(id="anon-fetch", name="anon-test", urls=["https://example.com"], status=JobStatus.RUNNING)
    assert _record_page_fetch(job, "https://example.com/page") is True

    assert ledger.get_usage("", UsageType.PAGE_FETCHED) == []


def test_record_page_fetch_quota_exceeded_logs_warning(monkeypatch) -> None:
    from app.services.scraping import _record_page_fetch

    ledger = UsageLedger()
    ledger.set_quota("user-quota", UsageType.PAGE_FETCHED, limit=0, period=QuotaPeriod.MONTHLY)
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    job = Job(id="quota-job", name="quota-test", created_by="user-quota", urls=["https://example.com"], status=JobStatus.RUNNING)
    assert _record_page_fetch(job, "https://example.com/page") is False

    records = ledger.get_usage("user-quota", UsageType.PAGE_FETCHED)
    assert len(records) == 0


def test_worker_queue_enqueue_records_scheduled_job_usage(tmp_path, monkeypatch) -> None:
    from app.worker_queue import WorkerQueue

    ledger = UsageLedger()
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)
    queue = WorkerQueue(db_path=tmp_path / "worker_queue.db")

    task_id = asyncio.run(
        queue.enqueue(
            "scrape_job",
            {"job_id": "scheduled-job-1"},
            task_id="scheduled-job-1",
            usage_context={
                "user_id": "user-scheduled",
                "org_id": "org-scheduled",
                "project_id": "project-scheduled",
                "job_id": "scheduled-job-1",
            },
        ),
    )

    assert task_id == "scheduled-job-1"
    assert queue.get_status()["pending"] == 1
    records = ledger.get_usage("user-scheduled", UsageType.SCHEDULED_JOB)
    assert len(records) == 1
    assert records[0].quantity == 1
    assert records[0].org_id == "org-scheduled"
    assert records[0].project_id == "project-scheduled"
    assert records[0].metadata["task_id"] == "scheduled-job-1"
    assert records[0].metadata["task_type"] == "scrape_job"


def test_worker_queue_enqueue_enforces_scheduled_job_quota(tmp_path, monkeypatch) -> None:
    from app.worker_queue import WorkerQueue

    ledger = UsageLedger()
    ledger.set_quota("user-scheduled", UsageType.SCHEDULED_JOB, limit=0, period=QuotaPeriod.MONTHLY)
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)
    queue = WorkerQueue(db_path=tmp_path / "worker_queue.db")

    with pytest.raises(ValueError, match="scheduled_job"):
        asyncio.run(
            queue.enqueue(
                "scrape_job",
                {"job_id": "blocked-scheduled-job"},
                task_id="blocked-scheduled-job",
                usage_context={"user_id": "user-scheduled", "job_id": "blocked-scheduled-job"},
            ),
        )

    assert queue.get_status()["pending"] == 0
    assert ledger.get_usage("user-scheduled", UsageType.SCHEDULED_JOB) == []


def test_create_job_enforces_scheduled_job_quota_in_worker_mode(client, tmp_path, monkeypatch) -> None:
    from app.main import jobs_store
    from app.worker_queue import get_worker_queue, reset_worker_queue

    reset_worker_queue()
    monkeypatch.setenv("DATAFORGE_WORKER_QUEUE", "true")
    queue = get_worker_queue(db_path=tmp_path / "worker_queue.db")

    ledger = UsageLedger()
    ledger.set_quota("dev-admin", UsageType.SCHEDULED_JOB, limit=0, period=QuotaPeriod.MONTHLY)
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    response = client.post(
        "/api/jobs",
        json={
            "name": "quota-blocked-worker-job",
            "mode": "manual",
            "urls": ["https://example.com"],
        },
    )

    assert response.status_code == 429
    assert "scheduled_job" in response.json()["detail"]
    assert queue.get_status()["pending"] == 0
    assert jobs_store == {}
    assert ledger.get_usage("dev-admin", UsageType.SCHEDULED_JOB) == []
    monkeypatch.setenv("DATAFORGE_WORKER_QUEUE", "false")
    reset_worker_queue()


def test_browser_minute_metering_records_tenant_context(monkeypatch) -> None:
    from app.html_utils import _record_browser_minutes

    ledger = UsageLedger()
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    allowed = _record_browser_minutes(
        usage_context={
            "user_id": "user-browser",
            "org_id": "org-browser",
            "project_id": "project-browser",
            "job_id": "browser-job",
        },
        url="https://example.com/page",
        method="playwright_full",
        quantity=2,
        phase="additional",
        duration_ms=121_000.4,
    )

    assert allowed is True
    records = ledger.get_usage("user-browser", UsageType.BROWSER_MINUTE)
    assert len(records) == 1
    assert records[0].quantity == 2
    assert records[0].org_id == "org-browser"
    assert records[0].project_id == "project-browser"
    assert records[0].metadata["job_id"] == "browser-job"
    assert records[0].metadata["method"] == "playwright_full"
    assert records[0].metadata["phase"] == "additional"
    assert records[0].metadata["duration_ms"] == 121000.4


def test_browser_minute_metering_enforces_quota(monkeypatch) -> None:
    from app.html_utils import _record_browser_minutes

    ledger = UsageLedger()
    ledger.set_quota("user-browser", UsageType.BROWSER_MINUTE, limit=0, period=QuotaPeriod.MONTHLY)
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    allowed = _record_browser_minutes(
        usage_context={"user_id": "user-browser", "job_id": "browser-job"},
        url="https://example.com/page",
        method="playwright_full",
        quantity=1,
        phase="initial",
    )

    assert allowed is False
    assert ledger.get_usage("user-browser", UsageType.BROWSER_MINUTE) == []


@pytest.mark.asyncio
async def test_page_fetch_quota_blocks_scrape_before_network_call(monkeypatch) -> None:
    from app.services.scraping import run_scraping_phase

    ledger = UsageLedger()
    ledger.set_quota("user-quota", UsageType.PAGE_FETCHED, limit=0, period=QuotaPeriod.MONTHLY)
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    mock_policy = MagicMock()
    mock_policy.can_fetch.return_value = True
    mock_policy.get_or_create.return_value = MagicMock(max_parallel=1)
    monkeypatch.setattr("app.domain_runtime_policy.get_domain_runtime_policy", lambda: mock_policy)

    scrape_url = AsyncMock(return_value=([{"name": "should-not-run"}], {"recovery_attempts": 0}))
    monkeypatch.setattr("app.services.job_runner.scrape_url_with_recovery", scrape_url)

    async def no_cancel() -> bool:
        return False

    job = Job(
        id="quota-block-job",
        name="quota-block-test",
        created_by="user-quota",
        urls=["https://example.com"],
        status=JobStatus.RUNNING,
    )

    all_raw, urls_with_records, warnings, scraped = await run_scraping_phase(
        job,
        max_job_runtime_seconds=60,
        per_url_scrape_timeout_seconds=10,
        persist_fn=lambda: None,
        cancel_check=no_cancel,
    )

    scrape_url.assert_not_awaited()
    assert all_raw == []
    assert urls_with_records == 0
    assert warnings == ["URL skipped due to page-fetch quota (1/1): https://example.com"]
    assert scraped == [(1, [], False, {"attempted": False, "quota_exceeded": True})]
    assert job.progress_current == 1
    assert ledger.get_usage("user-quota", UsageType.PAGE_FETCHED) == []


@pytest.mark.asyncio
async def test_scraping_phase_passes_usage_context_to_recovery(monkeypatch) -> None:
    from app.services.scraping import run_scraping_phase

    ledger = UsageLedger()
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    mock_policy = MagicMock()
    mock_policy.can_fetch.return_value = True
    mock_policy.get_or_create.return_value = MagicMock(max_parallel=1)
    monkeypatch.setattr("app.domain_runtime_policy.get_domain_runtime_policy", lambda: mock_policy)

    scrape_url = AsyncMock(return_value=([], {"recovery_attempts": 0}))
    monkeypatch.setattr("app.services.job_runner.scrape_url_with_recovery", scrape_url)

    mock_ws = MagicMock()
    mock_ws.transaction.return_value.__enter__ = MagicMock()
    mock_ws.transaction.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr("app.semantic_world_state.get_world_state", lambda: mock_ws)

    async def no_cancel() -> bool:
        return False

    job = Job(
        id="usage-context-job",
        name="usage-context-test",
        created_by="user-context",
        org_id="org-context",
        project_id="project-context",
        urls=["https://example.com"],
        status=JobStatus.RUNNING,
    )

    await run_scraping_phase(
        job,
        max_job_runtime_seconds=60,
        per_url_scrape_timeout_seconds=10,
        persist_fn=lambda: None,
        cancel_check=no_cancel,
    )

    assert scrape_url.await_args is not None
    assert scrape_url.await_args.kwargs["usage_context"] == {
        "user_id": "user-context",
        "org_id": "org-context",
        "project_id": "project-context",
        "job_id": "usage-context-job",
    }


@pytest.mark.asyncio
async def test_finalization_records_job_completed_usage(monkeypatch) -> None:
    from app.services.finalization import run_finalization

    ledger = UsageLedger()
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)
    monkeypatch.setattr("app.services.job_runner.save_semantic_state", lambda: None)

    job = Job(
        id="complete-meter-job",
        name="complete-meter-test",
        created_by="user-complete",
        urls=["https://example.com"],
        status=JobStatus.RUNNING,
        results=[{"name": "Acme"}],
    )
    job.progress_total = 1
    job.total_records = 1
    job.filtered_records = 1

    await run_finalization(
        job,
        all_raw_results=[{"name": "Acme"}],
        urls_with_records=1,
        persist_fn=lambda: None,
    )
    await run_finalization(
        job,
        all_raw_results=[{"name": "Acme"}],
        urls_with_records=1,
        persist_fn=lambda: None,
    )

    records = ledger.get_usage("user-complete", UsageType.JOB_COMPLETED)
    assert len(records) == 1
    assert records[0].quantity == 1
    assert records[0].metadata["job_id"] == "complete-meter-job"
    assert records[0].metadata["status"] == JobStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_ai_structuring_records_usage_when_phase_runs(monkeypatch) -> None:
    from app.services.ai_structuring import apply_global_ai_structuring

    ledger = UsageLedger()
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    ai_clean = AsyncMock(
        return_value=(
            [{"company": "Acme"}],
            {
                "applied": True,
                "input_records": 1,
                "output_records": 1,
                "model_fallback_mode": False,
            },
        ),
    )
    monkeypatch.setattr("app.scraper.ai_clean_and_align_records", ai_clean)
    monkeypatch.setattr("app.semantic_pipeline.run_pipeline", lambda records, _fields: records)

    mock_ws = MagicMock()
    mock_ws.transaction.return_value.__enter__ = MagicMock()
    mock_ws.transaction.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr("app.semantic_world_state.get_world_state", lambda: mock_ws)

    llm_counts: list[int] = []
    structured, report, warnings = await apply_global_ai_structuring(
        all_raw_results=[{"company": "Acme", "_extraction_method": "regex"}],
        schema_fields=[SimpleNamespace(name="company")],
        ai_source_prediction={"sources_with_ai_structuring": 0},
        ai_structuring_timeout_seconds=10,
        add_job_log=lambda *_args, **_kwargs: None,
        on_llm_call=llm_counts.append,
        usage_context={
            "user_id": "user-ai",
            "org_id": "org-ai",
            "project_id": "project-ai",
            "job_id": "ai-meter-job",
        },
    )

    assert structured == [{"company": "Acme"}]
    assert report["applied"] is True
    assert warnings == []
    records = ledger.get_usage("user-ai", UsageType.AI_STRUCTURING)
    assert len(records) == 1
    assert records[0].quantity == 1
    assert records[0].metadata["job_id"] == "ai-meter-job"
    assert records[0].metadata["input_records"] == 1
    assert records[0].org_id == "org-ai"
    assert records[0].project_id == "project-ai"
