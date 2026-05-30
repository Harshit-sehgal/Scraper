"""
Unit Tests for Phase 89 Resource Governance.
"""

from __future__ import annotations

import pytest
from app.resource_governor import ResourceGovernor, ResourceBudgets
from app.scrape_telemetry import get_scrape_telemetry


def test_resource_budgets_initialization():
    budgets = ResourceBudgets()
    assert budgets.max_browser_memory_mb == 1024.0
    assert budgets.max_token_spend == 5.0


def test_queue_shedding():
    budgets = ResourceBudgets(max_queue_size=5)
    governor = ResourceGovernor(budgets=budgets)

    queue = ["url-1", "url-2", "url-3", "url-4", "url-5", "url-6", "url-7"]
    trimmed = governor.enforce_queue_limits(queue)

    assert len(trimmed) == 5
    assert trimmed == ["url-1", "url-2", "url-3", "url-4", "url-5"]
    assert governor.metrics["queue_sheds"] == 2


def test_telemetry_pruning():
    budgets = ResourceBudgets(max_telemetry_records=3)
    governor = ResourceGovernor(budgets=budgets)

    telemetry = get_scrape_telemetry()
    telemetry.clear()

    # Write 5 entries
    for i in range(5):
        telemetry.record(f"url-{i}", fetch_ms=200.0)

    pruned = governor.prune_telemetry()
    assert pruned == 2
    assert governor.metrics["telemetry_prunes"] == 2

    # Check that remaining entries are bounded
    recent = telemetry.get_recent(10)
    assert len(recent) == 3


def test_token_tracking_and_throttling():
    budgets = ResourceBudgets(max_token_spend=0.01)  # tiny budget: 1 cent
    governor = ResourceGovernor(budgets=budgets)

    # 5,000 tokens at $2.00 per million tokens -> 5000 * 2 / 1000000 = $0.01
    allowed = governor.track_token_spend(5000, price_per_million=2.0)
    assert allowed is True

    # Another 5,000 tokens should cross the limit and trigger throttling
    allowed2 = governor.track_token_spend(5000, price_per_million=2.0)
    assert allowed2 is False
    assert governor.metrics["throttled_cycles"] == 1

    report = governor.get_governance_report()
    assert report["accumulated_tokens"] == 10000
    assert report["token_spend_dollars"] == pytest.approx(0.02)
    assert report["token_budget_remaining"] == 0.0


@pytest.mark.asyncio
async def test_check_browser_memory_pruning(monkeypatch):
    class MockContext:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    class MockPool:
        def __init__(self):
            self._contexts = {
                "domain-1": MockContext(),
                "domain-2": MockContext(),
                "domain-3": MockContext(),
                "domain-4": MockContext(),
            }

    mock_pool = MockPool()
    monkeypatch.setattr("app.browser_pool.get_browser_pool", lambda: mock_pool)

    # 4 contexts * 150MB = 600MB. Limit to 300MB to trigger pruning of 2 contexts.
    budgets = ResourceBudgets(max_browser_memory_mb=300.0)
    governor = ResourceGovernor(budgets=budgets)

    # Record the contexts before pruning
    original_contexts = list(mock_pool._contexts.values())

    res = await governor.check_browser_memory()
    assert res["pruned"] == 2
    assert len(mock_pool._contexts) == 2

    # Assert that the pruned contexts had their close() method called
    closed_count = sum(1 for ctx in original_contexts if ctx.closed)
    assert closed_count == 2
