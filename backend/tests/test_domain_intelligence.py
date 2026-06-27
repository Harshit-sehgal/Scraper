"""Tests for Domain Behavior Intelligence — Phase 79 Verification and coverage extension."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from app.domain_intelligence import (
    DomainIntelligence,
    DomainIntelligenceRegistry,
    get_domain_intelligence,
)


@pytest.fixture
def registry() -> DomainIntelligenceRegistry:
    reg = DomainIntelligenceRegistry(storage_path="backend/data/test_domain_intel.json")
    # Clear any existing test data
    reg._registry = {}
    return reg


@pytest.fixture(autouse=True)
def _cleanup_test_file():
    """Remove the test domain intel JSON after each test."""
    yield
    for fn in ["backend/data/test_domain_intel.json"]:
        with contextlib.suppress(OSError):
            Path(fn).unlink(missing_ok=True)


import contextlib


class TestMovingAverageHydration:
    """Smoothed hydration delay computation."""

    def test_single_ema_step(self, registry: DomainIntelligenceRegistry) -> None:
        url = "https://moving-avg.com/page1"
        registry.update_from_telemetry(
            {"url": url, "js_render_delay_ms": 2000.0, "anti_bot_score": 0.0, "fallback_usage": "none"}
        )
        intel = registry.get_intelligence(url)
        assert intel.hydration_delay_ms == 600.0  # 0.3 * 2000

    def test_two_ema_steps_converge(self, registry: DomainIntelligenceRegistry) -> None:
        url = "https://moving-avg.com/page2"
        registry.update_from_telemetry(
            {"url": url, "js_render_delay_ms": 2000.0, "anti_bot_score": 0.0, "fallback_usage": "none"}
        )
        registry.update_from_telemetry(
            {"url": url, "js_render_delay_ms": 1000.0, "anti_bot_score": 0.0, "fallback_usage": "none"}
        )
        intel = registry.get_intelligence(url)
        # 600 * 0.7 + 1000 * 0.3 = 720
        assert intel.hydration_delay_ms == 720.0

    def test_zero_delay_does_not_shift_average(self, registry: DomainIntelligenceRegistry) -> None:
        url = "https://no-render.com"
        registry.update_from_telemetry({"url": url, "js_render_delay_ms": 500.0, "anti_bot_score": 0.0, "fallback_usage": "none"})
        registry.update_from_telemetry({"url": url, "js_render_delay_ms": 0.0, "anti_bot_score": 0.0, "fallback_usage": "none"})
        intel = registry.get_intelligence(url)
        # delay=0 is guarded by `if delay > 0` in the code — hydration stays at 150.0
        assert intel.hydration_delay_ms == 150.0


class TestAntiBotRisk:
    """Anti-bot risk smoothed computation."""

    def test_risk_smoothing(self, registry: DomainIntelligenceRegistry) -> None:
        url = "https://botty.com"
        registry.update_from_telemetry({"url": url, "anti_bot_score": 0.9, "fallback_usage": "none"})
        intel = registry.get_intelligence(url)
        assert intel.anti_bot_risk == pytest.approx(0.3 * 0.9)

    def test_error_event_counts_as_fetch(self, registry: DomainIntelligenceRegistry) -> None:
        url = "https://error.com"
        registry.update_from_telemetry({"url": url, "error": "Blocked", "anti_bot_score": 0.95})
        intel = registry.get_intelligence(url)
        assert intel.total_fetches == 1
        assert intel.success_count == 0  # Errored fetch — not counted as success


class TestStrategyPreference:
    """Strategy selection and persistence."""

    def test_successful_strategy_recorded(self, registry: DomainIntelligenceRegistry) -> None:
        url = "https://strategy.com"
        registry.update_from_telemetry(
            {"url": url, "js_render_delay_ms": 100.0, "anti_bot_score": 0.1, "fallback_usage": "regex", "error": None},
        )
        intel = registry.get_intelligence(url)
        assert intel.preferred_strategy == "regex"

    def test_errored_fetch_does_not_update_strategy(self, registry: DomainIntelligenceRegistry) -> None:
        """Strategy must only change on successful fetches."""
        url = "https://error-strat.com"
        registry.update_from_telemetry(
            {"url": url, "fallback_usage": "regex", "error": "Timeout"},
        )
        intel = registry.get_intelligence(url)
        assert intel.preferred_strategy == "none"

    def test_unknown_strategy_not_recorded(self, registry: DomainIntelligenceRegistry) -> None:
        """Unrecognised strategy strings must not overwrite preferred_strategy."""
        url = "https://unknown-strat.com"
        registry.update_from_telemetry(
            {"url": url, "fallback_usage": "bogus", "error": None},
        )
        intel = registry.get_intelligence(url)
        assert intel.preferred_strategy == "none"


class TestCountsAndStats:
    """Total fetches and success counts."""

    def test_total_fetches_increment(self, registry: DomainIntelligenceRegistry) -> None:
        url = "https://count.com"
        registry.update_from_telemetry({"url": url})
        registry.update_from_telemetry({"url": url})
        registry.update_from_telemetry({"url": url})
        intel = registry.get_intelligence(url)
        assert intel.total_fetches == 3

    def test_success_count_increment(self, registry: DomainIntelligenceRegistry) -> None:
        url = "https://success.com"
        registry.update_from_telemetry({"url": url, "error": None})
        registry.update_from_telemetry({"url": url, "error": None})
        registry.update_from_telemetry({"url": url, "error": "Blocked"})
        intel = registry.get_intelligence(url)
        assert intel.success_count == 2
        assert intel.total_fetches == 3


class TestSelectorDecayRate:
    """Selector decay tracking."""

    def test_decay_triggered(self, registry: DomainIntelligenceRegistry) -> None:
        url = "https://decay.com"
        registry.update_from_telemetry({"url": url, "fallback_triggered": True})
        intel = registry.get_intelligence(url)
        assert intel.selector_decay_rate == pytest.approx(0.3)

    def test_decay_converges_downward(self, registry: DomainIntelligenceRegistry) -> None:
        url = "https://decay-down.com"
        registry.update_from_telemetry({"url": url, "fallback_triggered": True})
        registry.update_from_telemetry({"url": url, "fallback_triggered": False})
        intel = registry.get_intelligence(url)
        # First: 0.3, Second: 0.3*0.7 + 0*0.3 = 0.21
        assert intel.selector_decay_rate == pytest.approx(0.21)


class TestPersistence:
    """Disk persistence round-trip."""

    def test_round_trip(self, registry: DomainIntelligenceRegistry) -> None:
        url = "https://persist.com"
        registry.update_from_telemetry({"url": url, "js_render_delay_ms": 500.0})

        reg2 = DomainIntelligenceRegistry(storage_path="backend/data/test_domain_intel.json")
        intel2 = reg2.get_intelligence(url)
        assert intel2.hydration_delay_ms > 0
        assert intel2.total_fetches == 1

    def test_multiple_domains_persisted(self, registry: DomainIntelligenceRegistry) -> None:
        for url in ("https://a.com", "https://b.com", "https://c.com"):
            registry.update_from_telemetry({"url": url})

        reg2 = DomainIntelligenceRegistry(storage_path="backend/data/test_domain_intel.json")
        assert len(reg2._registry) == 3

    def test_corrupt_file_does_not_crash(self) -> None:
        """A corrupt JSON file must load as empty registry without raising."""
        corrupt = Path("backend/data/test_corrupt_intel.json")
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt.write_text("{not valid json")
        try:
            reg = DomainIntelligenceRegistry(storage_path=str(corrupt))
            assert len(reg._registry) == 0
        finally:
            corrupt.unlink(missing_ok=True)


class TestExtractDomain:
    """URL → domain extraction."""

    def test_standard_url(self) -> None:
        assert DomainIntelligenceRegistry._extract_domain("https://example.com/foo") == "example.com"

    def test_url_with_port(self) -> None:
        assert DomainIntelligenceRegistry._extract_domain("https://example.com:8080/path") == "example.com:8080"

    def test_no_scheme(self) -> None:
        """Without scheme, urlparse treats the first segment as path, not netloc."""
        result = DomainIntelligenceRegistry._extract_domain("example.com/path")
        # urlparse("example.com/path") sees path="example.com/path", netloc=""
        # so the method returns "unknown"
        assert result == "unknown"

    def test_invalid_url_falls_back(self) -> None:
        assert DomainIntelligenceRegistry._extract_domain("") == "unknown"


class TestDomainIntelligenceToDict:
    """Serialization of individual domain entries."""

    def test_to_dict_round_trips(self) -> None:
        di = DomainIntelligence("test.com")
        di.total_fetches = 5
        di.success_count = 3
        di.anti_bot_risk = 0.45
        d = di.to_dict()
        assert d["domain"] == "test.com"
        assert d["total_fetches"] == 5
        assert d["success_count"] == 3
        assert d["anti_bot_risk"] == 0.45

    def test_defaults(self) -> None:
        di = DomainIntelligence("fresh.com")
        d = di.to_dict()
        assert d["hydration_delay_ms"] == 0.0
        assert d["preferred_strategy"] == "none"


class TestGlobalSingleton:
    """get_domain_intelligence singleton behaviour."""

    def test_returns_same_instance(self) -> None:
        reg1 = get_domain_intelligence()
        reg2 = get_domain_intelligence()
        assert reg1 is reg2

    def test_config_path_takes_precedence(self) -> None:
        """When DOMAIN_INTELLIGENCE_PATH is set, the registry must use it."""
        with patch("app.domain_intelligence.settings") as mock_settings:
            mock_settings.DOMAIN_INTELLIGENCE_PATH = "data/custom_intel.json"
            reg = DomainIntelligenceRegistry()
            assert "custom_intel.json" in str(reg.path)


class TestUpdateEdgeCases:
    """Edge cases for update_from_telemetry."""

    def test_empty_url_creates_unknown_entry(self, registry: DomainIntelligenceRegistry) -> None:
        """An empty URL yields 'unknown' domain — the registry still creates an entry."""
        registry.update_from_telemetry({})
        assert "unknown" in registry._registry

    def test_unknown_domain_extraction_creates_entry(self, registry: DomainIntelligenceRegistry) -> None:
        """A URL that yields 'unknown' from extraction creates an 'unknown' entry."""
        registry.update_from_telemetry({"url": ""})
        assert "unknown" in registry._registry

    def test_missing_keys_default_to_zero(self, registry: DomainIntelligenceRegistry) -> None:
        """Missing telemetry keys must not crash."""
        registry.update_from_telemetry({"url": "https://minimal.com"})
        intel = registry.get_intelligence("https://minimal.com")
        assert intel.hydration_delay_ms == 0.0
        assert intel.anti_bot_risk == 0.0
