"""Unit Tests for Phase 90 System Governance & Visualization."""

from __future__ import annotations

import contextlib
import os

import pytest
from app.visualization import MAP_PATH, OperatorMode, SystemGovernorDashboard


@pytest.fixture(autouse=True)
def clean_gov_env():
    # Remove existing files if any
    if os.path.exists(MAP_PATH):
        with contextlib.suppress(Exception):
            os.remove(MAP_PATH)
    yield
    # Cleanup files after test run
    if os.path.exists(MAP_PATH):
        with contextlib.suppress(Exception):
            os.remove(MAP_PATH)


def test_operator_mode_adjustments() -> None:
    dashboard = SystemGovernorDashboard(mode=OperatorMode.PRODUCTION)
    # _apply_mode_settings should return mode-specific values WITHOUT
    # mutating global settings (avoids race conditions in concurrent requests).
    adjustments = dashboard.set_operator_mode(OperatorMode.STEALTH)
    assert adjustments["timeout"] == 60000
    assert adjustments["settle"] == 6.0
    assert adjustments["stealth"] is True

    # Switch to Low-cost
    adjustments_lc = dashboard.set_operator_mode(OperatorMode.LOW_COST)
    assert adjustments_lc["timeout"] == 20000
    assert adjustments_lc["settle"] == 2.0
    assert adjustments_lc["stealth"] is False


def test_system_map_generation() -> None:
    dashboard = SystemGovernorDashboard(mode=OperatorMode.PRODUCTION)

    # Generate map
    dashboard.generate_system_map()
    assert os.path.exists(MAP_PATH)

    with open(MAP_PATH, encoding="utf-8") as f:
        content = f.read()

    assert "DataForge Visual System" in content
    assert "Active Operator Profile" in content
    assert "CrawlFrontier" in content


def test_governance_summary() -> None:
    dashboard = SystemGovernorDashboard(mode=OperatorMode.PRODUCTION)
    summary = dashboard.get_governance_summary()

    assert summary["active_mode"] == "production"
    assert "resources" in summary
    assert "accumulated_tokens" in summary["resources"]
