from __future__ import annotations

import pytest
from app.plan_enforcer import check_usage_limit
from app.utils.usage_ledger import UsageType, get_usage_ledger, reset_usage_ledger


@pytest.fixture(autouse=True)
def _reset():
    reset_usage_ledger()
    yield


class TestTenantQuotas:
    def test_check_usage_limit_allows_within_budget(self) -> None:
        allowed, details = check_usage_limit("test_tenant", UsageType.API_REQUEST, 1)
        assert allowed is True
        assert details["limit"] > 0

    def test_usage_ledger_records_and_counts(self) -> None:
        ledger = get_usage_ledger()
        ledger.record_usage("user1", UsageType.API_REQUEST, quantity=1)
        summary = ledger.get_usage_summary("user1")
        assert summary["user_id"] == "user1"

    def test_usage_ledger_tracks_multiple_tenants(self) -> None:
        ledger = get_usage_ledger()
        ledger.record_usage("tenant_a", UsageType.API_REQUEST, quantity=5)
        ledger.record_usage("tenant_b", UsageType.API_REQUEST, quantity=3)
        a_summary = ledger.get_usage_summary("tenant_a")
        b_summary = ledger.get_usage_summary("tenant_b")
        assert a_summary is not None
        assert b_summary is not None

    def test_reset_usage_ledger_function_exists(self) -> None:
        result = reset_usage_ledger(user_id="test_user_for_reset")
        assert isinstance(result, int)

    def test_check_usage_limit_with_project_context(self) -> None:
        allowed, details = check_usage_limit(
            "proj_1",
            UsageType.API_REQUEST,
            1,
            org_id="org_1",
            project_id="proj_1",
        )
        assert allowed is True
        assert "limit" in details
