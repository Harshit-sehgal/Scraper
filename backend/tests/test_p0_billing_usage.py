"""P0 billing date math and usage quota regression tests."""

from __future__ import annotations

import threading
from datetime import UTC, datetime

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
    user_id = _configure_request_metering_keys(monkeypatch)
    ledger = UsageLedger()
    ledger.set_quota(user_id, UsageType.API_REQUEST, limit=1, period=QuotaPeriod.MONTHLY)
    monkeypatch.setattr(usage_mod, "usage_ledger", ledger)

    first = client.get("/api/jobs", headers={"X-API-Key": "user-key"})
    second = client.get("/api/jobs", headers={"X-API-Key": "user-key"})

    assert first.status_code == 200
    assert second.status_code == 429
    quota = ledger.get_quota(user_id, UsageType.API_REQUEST)
    assert quota is not None
    assert quota.current_usage == 1
    assert len(ledger.get_usage(user_id, UsageType.API_REQUEST)) == 1


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
