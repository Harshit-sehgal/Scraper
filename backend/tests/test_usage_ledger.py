"""Unit tests for the usage ledger and quota system.

Covers record_usage, idempotency, check_quota, set_quota, get_quota,
reset_quotas, get_usage, get_usage_summary, and error paths — all
in-memory (no SQLite persistence dependency).
"""

from __future__ import annotations

import datetime

import pytest
from app.utils.usage_ledger import (
    Quota,
    QuotaPeriod,
    UsageLedger,
    UsageRecord,
    UsageType,
)


@pytest.fixture
def ledger() -> UsageLedger:
    """Return a fresh in-memory ledger (no file persistence)."""
    return UsageLedger(storage_path=None)


# ─── record_usage ──────────────────────────────────────────────────────────


class TestRecordUsage:
    def test_records_usage(self, ledger: UsageLedger) -> None:
        record = ledger.record_usage("user-1", UsageType.API_REQUEST)
        assert isinstance(record, UsageRecord)
        assert record.user_id == "user-1"
        assert record.usage_type == UsageType.API_REQUEST
        assert record.quantity == 1

    def test_records_with_custom_quantity(self, ledger: UsageLedger) -> None:
        record = ledger.record_usage("user-1", UsageType.PAGE_FETCHED, quantity=5)
        assert record.quantity == 5

    def test_records_with_metadata(self, ledger: UsageLedger) -> None:
        record = ledger.record_usage("user-1", UsageType.JOB_CREATED, metadata={"job_id": "job-123"})
        assert record.metadata == {"job_id": "job-123"}

    def test_records_with_org_and_project(self, ledger: UsageLedger) -> None:
        record = ledger.record_usage("user-1", UsageType.EXPORT_GENERATED, org_id="org-1", project_id="project-1")
        assert record.org_id == "org-1"
        assert record.project_id == "project-1"

    def test_negative_quantity_raises(self, ledger: UsageLedger) -> None:
        with pytest.raises(ValueError, match="usage quantity must be non-negative"):
            ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=-1)

    def test_zero_quantity_allowed(self, ledger: UsageLedger) -> None:
        record = ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=0)
        assert record.quantity == 0

    def test_multiple_recordings_accumulate(self, ledger: UsageLedger) -> None:
        ledger.record_usage("user-1", UsageType.API_REQUEST)
        ledger.record_usage("user-1", UsageType.API_REQUEST)
        records = ledger.get_usage("user-1", UsageType.API_REQUEST)
        assert len(records) == 2

    def test_records_have_unique_ids(self, ledger: UsageLedger) -> None:
        r1 = ledger.record_usage("user-1", UsageType.API_REQUEST)
        r2 = ledger.record_usage("user-1", UsageType.API_REQUEST)
        assert r1.id != r2.id


# ─── idempotency ───────────────────────────────────────────────────────────


class TestIdempotency:
    def test_idempotent_key_returns_same_record(self, ledger: UsageLedger) -> None:
        r1 = ledger.record_usage("user-1", UsageType.API_REQUEST, idempotency_key="key-1")
        r2 = ledger.record_usage("user-1", UsageType.API_REQUEST, idempotency_key="key-1")
        assert r1.id == r2.id

    def test_different_keys_different_records(self, ledger: UsageLedger) -> None:
        r1 = ledger.record_usage("user-1", UsageType.API_REQUEST, idempotency_key="key-1")
        r2 = ledger.record_usage("user-1", UsageType.API_REQUEST, idempotency_key="key-2")
        assert r1.id != r2.id

    def test_idempotent_different_users_same_key(self, ledger: UsageLedger) -> None:
        r1 = ledger.record_usage("user-1", UsageType.API_REQUEST, idempotency_key="same-key")
        r2 = ledger.record_usage("user-2", UsageType.API_REQUEST, idempotency_key="same-key")
        # Different users: different idempotency scope
        assert r1.id != r2.id

    def test_idempotent_different_types_same_key(self, ledger: UsageLedger) -> None:
        r1 = ledger.record_usage("user-1", UsageType.API_REQUEST, idempotency_key="key-1")
        r2 = ledger.record_usage("user-1", UsageType.JOB_CREATED, idempotency_key="key-1")
        assert r1.id != r2.id


# ─── check_quota ───────────────────────────────────────────────────────────


class TestCheckQuota:
    def test_no_quota_set_allows(self, ledger: UsageLedger) -> None:
        ok, quota = ledger.check_quota("user-1", UsageType.API_REQUEST)
        assert ok is True
        assert quota is None

    def test_within_quota_allows(self, ledger: UsageLedger) -> None:
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=10)
        ok, quota = ledger.check_quota("user-1", UsageType.API_REQUEST, amount=5)
        assert ok is True
        assert quota is not None

    def test_exact_quota_allows(self, ledger: UsageLedger) -> None:
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=10)
        ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=10)
        ok, _ = ledger.check_quota("user-1", UsageType.API_REQUEST, amount=0)
        assert ok is True

    def test_over_quota_denies(self, ledger: UsageLedger) -> None:
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=10)
        ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=10)
        ok, _ = ledger.check_quota("user-1", UsageType.API_REQUEST, amount=1)
        assert ok is False

    def test_check_quota_without_recording(self, ledger: UsageLedger) -> None:
        """check_quota shouldn't consume quota, just peek."""
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=10)
        ok, _ = ledger.check_quota("user-1", UsageType.API_REQUEST, amount=10)
        assert ok is True
        # Still have 0 usage since we didn't record anything
        _, quota = ledger.check_quota("user-1", UsageType.API_REQUEST)
        assert quota is not None
        assert quota.current_usage == 0


# ─── set_quota and get_quota ───────────────────────────────────────────────


class TestQuotaManagement:
    def test_set_and_get_quota(self, ledger: UsageLedger) -> None:
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=100, period=QuotaPeriod.DAILY)
        quota = ledger.get_quota("user-1", UsageType.API_REQUEST)
        assert quota is not None
        assert quota.limit == 100
        assert quota.period == QuotaPeriod.DAILY

    def test_get_nonexistent_quota_returns_none(self, ledger: UsageLedger) -> None:
        quota = ledger.get_quota("user-unknown", UsageType.API_REQUEST)
        assert quota is None

    def test_set_quota_overwrites(self, ledger: UsageLedger) -> None:
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=10)
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=50)
        quota = ledger.get_quota("user-1", UsageType.API_REQUEST)
        assert quota is not None
        assert quota.limit == 50

    def test_negative_limit_raises(self, ledger: UsageLedger) -> None:
        with pytest.raises(ValueError, match="quota limit must be non-negative"):
            ledger.set_quota("user-1", UsageType.API_REQUEST, limit=-1)

    def test_zero_limit_allowed(self, ledger: UsageLedger) -> None:
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=0)
        quota = ledger.get_quota("user-1", UsageType.API_REQUEST)
        assert quota is not None
        assert quota.limit == 0

    def test_different_types_have_independent_quotas(self, ledger: UsageLedger) -> None:
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=10)
        ledger.set_quota("user-1", UsageType.JOB_CREATED, limit=5)
        api_quota = ledger.get_quota("user-1", UsageType.API_REQUEST)
        job_quota = ledger.get_quota("user-1", UsageType.JOB_CREATED)
        assert api_quota is not None and api_quota.limit == 10
        assert job_quota is not None and job_quota.limit == 5


# ─── quota enforcement during recording ────────────────────────────────────


class TestQuotaEnforcement:
    def test_recording_honors_quota(self, ledger: UsageLedger) -> None:
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=5)
        ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=5)
        with pytest.raises(ValueError, match="quota exceeded"):
            ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=1)

    def test_recording_updates_quota_usage(self, ledger: UsageLedger) -> None:
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=10)
        ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=3)
        ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=2)
        quota = ledger.get_quota("user-1", UsageType.API_REQUEST)
        assert quota is not None
        assert quota.current_usage == 5

    def test_recording_different_types_independent(self, ledger: UsageLedger) -> None:
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=5)
        ledger.set_quota("user-1", UsageType.JOB_CREATED, limit=3)
        ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=5)
        ledger.record_usage("user-1", UsageType.JOB_CREATED, quantity=3)
        api_quota = ledger.get_quota("user-1", UsageType.API_REQUEST)
        job_quota = ledger.get_quota("user-1", UsageType.JOB_CREATED)
        assert api_quota is not None and api_quota.current_usage == 5
        assert job_quota is not None and job_quota.current_usage == 3

    def test_record_without_quota_not_blocked(self, ledger: UsageLedger) -> None:
        """Recording usage without setting a quota should always work."""
        ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=10000)
        assert True  # No exception


# ─── reset_quotas ──────────────────────────────────────────────────────────


class TestResetQuotas:
    def test_reset_all_quotas(self, ledger: UsageLedger) -> None:
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=10)
        ledger.set_quota("user-2", UsageType.API_REQUEST, limit=10)
        ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=5)
        ledger.record_usage("user-2", UsageType.API_REQUEST, quantity=3)

        count = ledger.reset_quotas()
        assert count == 2

        q1 = ledger.get_quota("user-1", UsageType.API_REQUEST)
        q2 = ledger.get_quota("user-2", UsageType.API_REQUEST)
        assert q1 is not None and q1.current_usage == 0
        assert q2 is not None and q2.current_usage == 0

    def test_reset_single_user(self, ledger: UsageLedger) -> None:
        ledger.set_quota("user-1", UsageType.API_REQUEST, limit=10)
        ledger.set_quota("user-2", UsageType.API_REQUEST, limit=10)
        ledger.record_usage("user-1", UsageType.API_REQUEST, quantity=5)
        ledger.record_usage("user-2", UsageType.API_REQUEST, quantity=3)

        count = ledger.reset_quotas(user_id="user-1")
        assert count == 1

        q1 = ledger.get_quota("user-1", UsageType.API_REQUEST)
        q2 = ledger.get_quota("user-2", UsageType.API_REQUEST)
        assert q1 is not None and q1.current_usage == 0
        assert q2 is not None and q2.current_usage == 3

    def test_reset_no_quotas_returns_zero(self, ledger: UsageLedger) -> None:
        count = ledger.reset_quotas()
        assert count == 0


# ─── get_usage ─────────────────────────────────────────────────────────────


class TestGetUsage:
    def test_get_all_usage_for_user(self, ledger: UsageLedger) -> None:
        ledger.record_usage("user-1", UsageType.API_REQUEST)
        ledger.record_usage("user-1", UsageType.JOB_CREATED)
        records = ledger.get_usage("user-1")
        assert len(records) == 2

    def test_filter_by_type(self, ledger: UsageLedger) -> None:
        ledger.record_usage("user-1", UsageType.API_REQUEST)
        ledger.record_usage("user-1", UsageType.JOB_CREATED)
        records = ledger.get_usage("user-1", usage_type=UsageType.API_REQUEST)
        assert len(records) == 1
        assert records[0].usage_type == UsageType.API_REQUEST

    def test_filter_by_date_range(self, ledger: UsageLedger) -> None:
        ledger.record_usage("user-1", UsageType.API_REQUEST)
        end = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
        start = end - datetime.timedelta(hours=2)
        records = ledger.get_usage("user-1", start_date=start, end_date=end)
        assert len(records) == 1

    def test_empty_usage_returns_empty_list(self, ledger: UsageLedger) -> None:
        records = ledger.get_usage("nonexistent-user")
        assert records == []

    def test_different_users_isolated(self, ledger: UsageLedger) -> None:
        ledger.record_usage("user-1", UsageType.API_REQUEST)
        ledger.record_usage("user-2", UsageType.JOB_CREATED)
        records = ledger.get_usage("user-1")
        assert len(records) == 1
        assert records[0].user_id == "user-1"

    def test_org_id_lookup(self, ledger: UsageLedger) -> None:
        ledger.record_usage("user-1", UsageType.API_REQUEST, org_id="org-1")
        records = ledger.get_usage("org-1")
        assert len(records) == 1


# ─── get_usage_summary ─────────────────────────────────────────────────────


class TestGetUsageSummary:
    def test_summary_contains_all_types(self, ledger: UsageLedger) -> None:
        ledger.record_usage("user-1", UsageType.API_REQUEST)
        ledger.record_usage("user-1", UsageType.JOB_CREATED, quantity=3)
        summary = ledger.get_usage_summary("user-1")
        assert summary["user_id"] == "user-1"
        assert summary["usage"]["api_request"]["count"] == 1
        assert summary["usage"]["api_request"]["total_quantity"] == 1
        assert summary["usage"]["job_created"]["count"] == 1
        assert summary["usage"]["job_created"]["total_quantity"] == 3

    def test_summary_zero_counts_for_unused_types(self, ledger: UsageLedger) -> None:
        summary = ledger.get_usage_summary("user-1")
        for usage_type in UsageType:
            assert usage_type.value in summary["usage"]
            assert summary["usage"][usage_type.value]["count"] == 0
            assert summary["usage"][usage_type.value]["total_quantity"] == 0

    def test_summary_with_date_range(self, ledger: UsageLedger) -> None:
        start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
        end = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
        ledger.record_usage("user-1", UsageType.API_REQUEST)
        summary = ledger.get_usage_summary("user-1", start_date=start, end_date=end)
        assert summary["period"]["start"] is not None
        assert "api_request" in summary["usage"]


# ─── Quota data class edge cases ───────────────────────────────────────────


class TestQuotaDataClass:
    def test_default_quota_values(self) -> None:
        q = Quota()
        assert q.limit == 1000
        assert q.period == QuotaPeriod.MONTHLY
        assert q.current_usage == 0
        assert q.usage_type == UsageType.API_REQUEST

    def test_custom_quota_values(self) -> None:
        q = Quota(user_id="user-1", usage_type=UsageType.JOB_CREATED, limit=50, period=QuotaPeriod.DAILY)
        assert q.user_id == "user-1"
        assert q.usage_type == UsageType.JOB_CREATED
        assert q.limit == 50
        assert q.period == QuotaPeriod.DAILY


class TestUsageRecordDataClass:
    def test_default_usage_record_values(self) -> None:
        r = UsageRecord()
        assert r.quantity == 1
        assert r.usage_type == UsageType.API_REQUEST
        assert r.user_id == ""

    def test_custom_usage_record(self) -> None:
        r = UsageRecord(
            user_id="user-1",
            usage_type=UsageType.BROWSER_MINUTE,
            quantity=10,
            metadata={"page": "test"},
        )
        assert r.user_id == "user-1"
        assert r.usage_type == UsageType.BROWSER_MINUTE
        assert r.quantity == 10
        assert r.metadata == {"page": "test"}
