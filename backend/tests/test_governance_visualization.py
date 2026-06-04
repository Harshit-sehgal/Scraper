"""Unit Tests for Phase 90 System Governance & Visualization."""

from __future__ import annotations

import contextlib
import os

import pytest
from app.config import settings
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
    assert settings.PLAYWRIGHT_TIMEOUT == 30000

    # Switch to Stealth
    adjustments = dashboard.set_operator_mode(OperatorMode.STEALTH)
    assert settings.PLAYWRIGHT_TIMEOUT == 60000
    assert adjustments["stealth"] is True

    # Switch to Low-cost
    adjustments_lc = dashboard.set_operator_mode(OperatorMode.LOW_COST)
    assert settings.PLAYWRIGHT_TIMEOUT == 20000
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
