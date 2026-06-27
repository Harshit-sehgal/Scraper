"""Tests for cross-tenant query guardian."""

from __future__ import annotations

from typing import Any

from app.utils.cross_tenant_guard import (
    get_cross_tenant_alert_count,
    guard_cross_tenant,
    reset_cross_tenant_alert_count,
)


def test_single_org_no_alert():
    reset_cross_tenant_alert_count()
    rows = [{"org_id": "org-1"}, {"org_id": "org-1"}]
    result = guard_cross_tenant(rows)
    assert result == {"org-1"}
    assert get_cross_tenant_alert_count() == 0


def test_multi_org_fires_alert():
    reset_cross_tenant_alert_count()
    rows = [{"org_id": "org-1"}, {"org_id": "org-2"}]
    result = guard_cross_tenant(rows)
    assert result == {"org-1", "org-2"}
    assert get_cross_tenant_alert_count() == 1


def test_empty_rows_no_alert():
    reset_cross_tenant_alert_count()
    result = guard_cross_tenant([])
    assert result == set()
    assert get_cross_tenant_alert_count() == 0


def test_rows_without_org_id():
    reset_cross_tenant_alert_count()
    rows = [{"id": "1"}, {"id": "2"}]
    result = guard_cross_tenant(rows)
    assert result == set()
    assert get_cross_tenant_alert_count() == 0


def test_mixed_org_and_none():
    reset_cross_tenant_alert_count()
    rows: list[dict[str, Any]] = [{"org_id": "org-1"}, {"org_id": None}, {"id": "3"}]
    result = guard_cross_tenant(rows)
    assert result == {"org-1"}
    assert get_cross_tenant_alert_count() == 0


def test_context_label():
    reset_cross_tenant_alert_count()
    rows = [{"org_id": "a"}, {"org_id": "b"}]
    guard_cross_tenant(rows, context="list_jobs_endpoint")
    assert get_cross_tenant_alert_count() == 1


def test_alert_counter_increments():
    reset_cross_tenant_alert_count()
    rows = [{"org_id": "a"}, {"org_id": "b"}]
    guard_cross_tenant(rows)
    guard_cross_tenant(rows)
    guard_cross_tenant(rows)
    assert get_cross_tenant_alert_count() == 3


def test_reset_clears_counter():
    reset_cross_tenant_alert_count()
    rows = [{"org_id": "a"}, {"org_id": "b"}]
    guard_cross_tenant(rows)
    assert get_cross_tenant_alert_count() == 1
    reset_cross_tenant_alert_count()
    assert get_cross_tenant_alert_count() == 0
