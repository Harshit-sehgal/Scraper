"""
Tests for Domain Behavior Intelligence — Phase 79 Verification.
"""

import pytest
from app.domain_intelligence import DomainIntelligenceRegistry


@pytest.fixture
def registry():
    reg = DomainIntelligenceRegistry(storage_path="backend/data/test_domain_intel.json")
    # Clear any existing test data
    reg._registry = {}
    return reg


def test_moving_average_hydration(registry):
    url = "https://moving-avg.com/page1"

    # First update: 2000ms
    registry.update_from_telemetry({
        "url": url,
        "js_render_delay_ms": 2000.0,
        "anti_bot_score": 0.0,
        "fallback_usage": "none"
    })

    intel = registry.get_intelligence(url)
    assert intel.hydration_delay_ms == 600.0  # 0.3 * 2000

    # Second update: 1000ms
    registry.update_from_telemetry({
        "url": url,
        "js_render_delay_ms": 1000.0,
        "anti_bot_score": 0.0,
        "fallback_usage": "none"
    })

    # 600 * 0.7 + 1000 * 0.3 = 420 + 300 = 720
    assert intel.hydration_delay_ms == 720.0


def test_strategy_preference(registry):
    url = "https://strategy.com"

    # Successful regex fallback
    registry.update_from_telemetry({
        "url": url,
        "js_render_delay_ms": 100.0,
        "anti_bot_score": 0.1,
        "fallback_usage": "regex",
        "error": None
    })

    intel = registry.get_intelligence(url)
    assert intel.preferred_strategy == "regex"

    # High anti-bot risk update
    registry.update_from_telemetry({
        "url": url,
        "js_render_delay_ms": 100.0,
        "anti_bot_score": 0.9,  # Heavy anti-bot
        "fallback_usage": "none",
        "error": "Blocked"
    })

    assert intel.anti_bot_risk == 0.3 * 0.9 + 0.7 * 0.03  # smoothed risk
    # Preferred strategy should remain regex (most recent SUCCESSFUL candidate)
    assert intel.preferred_strategy == "regex"


def test_persistence(registry):
    url = "https://persist.com"
    registry.update_from_telemetry({
        "url": url,
        "infinite_scroll_required": True,
        "js_render_delay_ms": 500.0
    })

    # Create a new registry instance pointing to same file
    reg2 = DomainIntelligenceRegistry(storage_path="backend/data/test_domain_intel.json")
    intel2 = reg2.get_intelligence(url)

    assert intel2.hydration_delay_ms > 0
    assert intel2.total_fetches == 1
