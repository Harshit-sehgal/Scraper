"""Tests for Trend Analyzer — telemetry intelligence and economic tracking.

Tests cover:
  - TrendAnalyzer: empty history, domain grouping, trend detection, health scoring, alerts
  - Trend detection: improving, stable, degrading trajectories
  - EconomicTracker: cost analysis, efficiency ratings, domain breakdowns
  - Alert generation: degrading domains, selector decay, anti-bot intensification
"""

from __future__ import annotations

import time

import pytest
from app.trend_analyzer import (
    EconomicReport,
    EconomicTracker,
    TrendAnalyzer,
    TrendReport,
)

# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


def _make_telemetry(**overrides) -> dict:
    """Create a telemetry dict with sensible defaults."""
    base = {
        "url": "https://example.com/page",
        "fetch_method": "playwright",
        "fetch_ms": 2500.0,
        "dom_nodes": 500,
        "selector_success": True,
        "selector_hit_rate": 0.85,
        "fallback_triggered": False,
        "records_final": 10,
        "anti_bot_score": 0.0,
        "retry_count": 0,
        "estimated_cost_usd": 0.05,
        "llm_calls_count": 3,
        "failure_category": None,
        "error": None,
        "timestamp": time.time(),
    }
    base.update(overrides)
    return base


def _healthy_history(count: int = 10) -> list[dict]:
    """Generate a history of healthy scrape events."""
    return [
        _make_telemetry(
            url="https://example.com/page",
            selector_hit_rate=0.9,
            fetch_ms=1000.0,
            records_final=15,
            anti_bot_score=0.05,
        )
        for _ in range(count)
    ]


def _degrading_history(count: int = 10) -> list[dict]:
    """Generate a history where quality degrades over time."""
    events = []
    for i in range(count):
        # Each event gets progressively worse
        ratio = i / count
        events.append(
            _make_telemetry(
                url="https://bad.example.com/page",
                selector_hit_rate=max(0.1, 0.9 - ratio * 0.8),
                fetch_ms=1000.0 + ratio * 4000.0,
                records_final=max(0, 10 - int(ratio * 12)),
                anti_bot_score=min(1.0, ratio * 0.8),
                fallback_triggered=ratio > 0.5,
                estimated_cost_usd=0.05 + ratio * 0.15,
            ),
        )
    return events


def _multi_domain_history() -> list[dict]:
    """Generate telemetry across multiple domains."""
    events = []
    # Healthy domain (10 events)
    for _ in range(10):
        events.append(
            _make_telemetry(
                url="https://good.example.com/page",
                selector_hit_rate=0.95,
                fetch_ms=800.0,
                records_final=20,
            ),
        )
    # Mediocre domain (6 events with some failures)
    for i in range(6):
        events.append(
            _make_telemetry(
                url="https://ok.example.com/page",
                selector_hit_rate=0.6 if i < 3 else 0.3,
                fetch_ms=2000.0,
                records_final=5 if i < 3 else 0,
                fallback_triggered=i >= 3,
                error="partial extraction" if i >= 3 else None,
                failure_category="partial_extraction" if i >= 3 else None,
            ),
        )
    # Bad domain (8 events, all failing with zero quality)
    for i in range(8):
        events.append(
            _make_telemetry(
                url="https://bad.example.com/page",
                selector_hit_rate=0.0,
                fetch_ms=5000.0,
                records_final=0,
                fallback_triggered=True,
                error="timeout",
                anti_bot_score=0.9,
                estimated_cost_usd=0.15,
            ),
        )
    return events


# ═══════════════════════════════════════════════════════════════════════
# TrendAnalyzer Tests
# ═══════════════════════════════════════════════════════════════════════


class TestTrendAnalyzerEmpty:
    """Tests with empty or minimal telemetry."""

    def test_empty_history(self) -> None:
        analyzer = TrendAnalyzer()
        report = analyzer.analyze([])
        assert isinstance(report, TrendReport)
        assert report.domain_count == 0
        assert report.total_scrapes == 0
        assert report.alerts == []

    def test_single_event(self) -> None:
        analyzer = TrendAnalyzer()
        history = [_make_telemetry(url="https://example.com/page")]
        report = analyzer.analyze(history)
        assert report.domain_count == 1
        assert report.total_scrapes == 1
        assert "example.com" in report.domain_trends
        trend = report.domain_trends["example.com"]
        assert trend.sample_count == 1
        assert trend.health_score < 100  # Low sample penalty


class TestTrendAnalyzerDomainGrouping:
    """Tests that domains are correctly grouped and analyzed."""

    def test_single_domain(self) -> None:
        analyzer = TrendAnalyzer()
        history = _healthy_history(10)
        report = analyzer.analyze(history)
        assert report.domain_count == 1
        assert "example.com" in report.domain_trends

    def test_multi_domain(self) -> None:
        analyzer = TrendAnalyzer()
        history = _multi_domain_history()
        report = analyzer.analyze(history)
        assert report.domain_count == 3
        assert "good.example.com" in report.domain_trends
        assert "ok.example.com" in report.domain_trends
        assert "bad.example.com" in report.domain_trends

    def test_domain_extraction(self) -> None:
        assert TrendAnalyzer.extract_domain("https://www.example.com/path") == "www.example.com"
        assert TrendAnalyzer.extract_domain("http://sub.domain.co.uk/page?q=1") == "sub.domain.co.uk"
        assert TrendAnalyzer.extract_domain("") == "unknown"


class TestTrendAnalyzerHealthScores:
    """Tests for health score computation."""

    def test_healthy_domain_high_score(self) -> None:
        analyzer = TrendAnalyzer()
        history = _healthy_history(10)
        report = analyzer.analyze(history)
        trend = report.domain_trends["example.com"]
        assert trend.health_score >= 80

    def test_degrading_domain_low_score(self) -> None:
        analyzer = TrendAnalyzer()
        history = _degrading_history(10)
        report = analyzer.analyze(history)
        trend = report.domain_trends["bad.example.com"]
        assert trend.health_score < 60

    def test_failing_domain_very_low_score(self) -> None:
        """100% failure rate domain should have very low health."""
        analyzer = TrendAnalyzer()
        history = [
            _make_telemetry(
                url="https://dead.example.com/page",
                records_final=0,
                error="timeout",
                selector_hit_rate=0.0,
            )
            for _ in range(10)
        ]
        report = analyzer.analyze(history)
        trend = report.domain_trends["dead.example.com"]
        assert trend.failure_rate == 1.0
        assert trend.health_score < 40

    def test_health_score_with_mixed_signals(self) -> None:
        """Domain with mixed performance should get intermediate score."""
        analyzer = TrendAnalyzer()
        # 5 good events then 5 bad events
        history = [  # Good first half
            _make_telemetry(
                url="https://mixed.example.com/page",
                selector_hit_rate=0.9,
                records_final=15,
                fetch_ms=1000,
            )
            for _ in range(5)
        ] + [  # Bad second half
            _make_telemetry(
                url="https://mixed.example.com/page",
                selector_hit_rate=0.2,
                records_final=0,
                fetch_ms=5000,
                error="timeout",
                failure_category="timeout",
            )
            for _ in range(5)
        ]
        report = analyzer.analyze(history)
        trend = report.domain_trends["mixed.example.com"]
        # 50% failure rate + degrading trend = medium-low score
        assert 20 <= trend.health_score <= 80


class TestTrendAnalyzerTrendDetection:
    """Tests for trend direction detection."""

    def test_improving_latency(self) -> None:
        """Latencies that decrease over time should be 'improving'."""
        analyzer = TrendAnalyzer()
        # Each event gets faster (improving)
        events = [
            _make_telemetry(
                url="https://improving.example.com/page",
                fetch_ms=5000.0 - i * 400.0,
                selector_hit_rate=0.8,
            )
            for i in range(10)
        ]
        report = analyzer.analyze(events)
        trend = report.domain_trends["improving.example.com"]
        assert trend.fetch_latency_trend == "improving"

    def test_degrading_quality(self) -> None:
        """Quality scores that decrease over time should be 'degrading'."""
        analyzer = TrendAnalyzer()
        events = [
            _make_telemetry(
                url="https://degrading-quality.example.com/page",
                selector_hit_rate=max(0.1, 0.95 - i * 0.09),
            )
            for i in range(10)
        ]
        report = analyzer.analyze(events)
        trend = report.domain_trends["degrading-quality.example.com"]
        assert trend.quality_trend == "degrading"

    def test_stable_domain(self) -> None:
        """Stable metrics should produce 'stable' trends."""
        analyzer = TrendAnalyzer()
        events = [
            _make_telemetry(
                url="https://stable.example.com/page",
                selector_hit_rate=0.8,
                fetch_ms=1500.0,
            )
            for _ in range(10)
        ]
        report = analyzer.analyze(events)
        trend = report.domain_trends["stable.example.com"]
        assert trend.quality_trend == "stable"
        assert trend.fetch_latency_trend == "stable"

    def test_short_history_is_stable(self) -> None:
        """Fewer than 3 events should be classified as 'stable' (not enough data)."""
        analyzer = TrendAnalyzer()
        events = [
            _make_telemetry(url="https://short.example.com/page", fetch_ms=1000.0),
            _make_telemetry(url="https://short.example.com/page", fetch_ms=5000.0),
        ]
        report = analyzer.analyze(events)
        trend = report.domain_trends["short.example.com"]
        assert trend.fetch_latency_trend == "stable"

    def test_anti_bot_trend(self) -> None:
        """Anti-bot scores that increase should be 'degrading'."""
        analyzer = TrendAnalyzer()
        events = [
            _make_telemetry(
                url="https://bot.example.com/page",
                anti_bot_score=i * 0.1,
            )
            for i in range(10)
        ]
        report = analyzer.analyze(events)
        trend = report.domain_trends["bot.example.com"]
        assert trend.anti_bot_trend == "degrading"


class TestTrendAnalyzerMetrics:
    """Tests for specific metric computations."""

    def test_failure_rate_calculation(self) -> None:
        analyzer = TrendAnalyzer()
        events = [
            _make_telemetry(url="https://x.example.com/page", records_final=5, error=None),
            _make_telemetry(url="https://x.example.com/page", records_final=0, error="timeout"),
            _make_telemetry(url="https://x.example.com/page", records_final=3, error=None),
            _make_telemetry(url="https://x.example.com/page", records_final=0, error="fail"),
        ]
        report = analyzer.analyze(events)
        trend = report.domain_trends["x.example.com"]
        assert trend.failure_rate == 0.5  # 2 out of 4
        assert trend.total_failures == 2

    def test_latency_averaging(self) -> None:
        analyzer = TrendAnalyzer()
        events = [
            _make_telemetry(url="https://latency.example.com/page", fetch_ms=1000.0),
            _make_telemetry(url="https://latency.example.com/page", fetch_ms=2000.0),
            _make_telemetry(url="https://latency.example.com/page", fetch_ms=3000.0),
        ]
        report = analyzer.analyze(events)
        trend = report.domain_trends["latency.example.com"]
        assert trend.avg_fetch_ms == 2000.0

    def test_quality_score_averaging(self) -> None:
        analyzer = TrendAnalyzer()
        events = [
            _make_telemetry(url="https://quality.example.com/page", selector_hit_rate=0.9),
            _make_telemetry(url="https://quality.example.com/page", selector_hit_rate=0.7),
            _make_telemetry(url="https://quality.example.com/page", selector_hit_rate=0.5),
        ]
        report = analyzer.analyze(events)
        trend = report.domain_trends["quality.example.com"]
        assert trend.avg_quality_score == pytest.approx(0.7, 0.01)

    def test_cost_averaging(self) -> None:
        analyzer = TrendAnalyzer()
        events = [
            _make_telemetry(url="https://cost.example.com/page", estimated_cost_usd=0.10),
            _make_telemetry(url="https://cost.example.com/page", estimated_cost_usd=0.20),
        ]
        report = analyzer.analyze(events)
        trend = report.domain_trends["cost.example.com"]
        assert trend.avg_cost_usd == pytest.approx(0.15, 0.01)

    def test_failure_category_tracking(self) -> None:
        analyzer = TrendAnalyzer()
        events = [
            _make_telemetry(
                url="https://cats.example.com/page",
                failure_category="timeout",
                records_final=0,
                error="timeout",
            ),
            _make_telemetry(
                url="https://cats.example.com/page",
                failure_category="timeout",
                records_final=0,
                error="timeout",
            ),
            _make_telemetry(
                url="https://cats.example.com/page",
                failure_category="anti_bot_block",
                records_final=0,
                error="blocked",
            ),
            _make_telemetry(
                url="https://cats.example.com/page",
                failure_category=None,
                records_final=5,
                error=None,
            ),
        ]
        report = analyzer.analyze(events)
        trend = report.domain_trends["cats.example.com"]
        cats = {c["category"]: c["count"] for c in trend.top_failure_categories}
        assert cats.get("timeout") == 2
        assert cats.get("anti_bot_block") == 1


class TestTrendAnalyzerAlerts:
    """Tests for alert generation."""

    def test_degrading_domain_alert(self) -> None:
        analyzer = TrendAnalyzer()
        history = _degrading_history(10)
        report = analyzer.analyze(history)
        assert len(report.alerts) >= 1
        # The domain has degrading trends but health_score may be above 40
        # (so it won't be in degrading_domains). But it should still
        # trigger medium alerts (selector decay, anti-bot intensification).
        bad_alerts = [a for a in report.alerts if "bad.example.com" in a["domain"]]
        assert len(bad_alerts) >= 1

    def test_no_alerts_for_healthy(self) -> None:
        analyzer = TrendAnalyzer()
        history = _healthy_history(10)
        report = analyzer.analyze(history)
        high_alerts = [a for a in report.alerts if a["severity"] == "high"]
        assert len(high_alerts) == 0

    def test_selector_decay_alert(self) -> None:
        """Selector decay acceleration should generate medium alerts."""
        analyzer = TrendAnalyzer()
        # Events where fallback rate increases over time
        events = [
            _make_telemetry(
                url="https://decay.example.com/page",
                fallback_triggered=i > 4,
                selector_hit_rate=0.8 if i < 5 else 0.2,
                records_final=10 if i < 5 else 2,
            )
            for i in range(10)
        ]
        report = analyzer.analyze(events)
        decay_alerts = [a for a in report.alerts if "selector decay" in a["message"].lower()]
        assert len(decay_alerts) >= 1

    def test_anti_bot_alert(self) -> None:
        """Increasing anti-bot scores should generate medium alerts."""
        analyzer = TrendAnalyzer()
        events = [
            _make_telemetry(
                url="https://botty.example.com/page",
                anti_bot_score=i * 0.1 + 0.1,
            )
            for i in range(10)
        ]
        report = analyzer.analyze(events)
        bot_alerts = [a for a in report.alerts if "anti-bot" in a["message"].lower()]
        assert len(bot_alerts) >= 1


class TestTrendAnalyzerCategorization:
    """Tests for domain health categorization."""

    def test_degrading_domains_list(self) -> None:
        analyzer = TrendAnalyzer()
        history = _multi_domain_history()
        report = analyzer.analyze(history)
        assert "bad.example.com" in report.degrading_domains

    def test_stable_domains_list(self) -> None:
        analyzer = TrendAnalyzer()
        history = _multi_domain_history()
        report = analyzer.analyze(history)
        # good.example.com has 10 healthy scrapes
        assert "good.example.com" in report.improving_domains

    def test_unseen_domains(self) -> None:
        """Domains with < 2 events should be 'unseen'."""
        analyzer = TrendAnalyzer()
        history = [
            _make_telemetry(url="https://fresh.example.com/page"),
        ]
        report = analyzer.analyze(history)
        assert "fresh.example.com" in report.unseen_domains

    def test_domain_in_both_lists(self) -> None:
        """A domain should only appear in one category list."""
        analyzer = TrendAnalyzer()
        history = _multi_domain_history()
        report = analyzer.analyze(history)
        all_domains = set()
        for lst in [report.improving_domains, report.stable_domains, report.degrading_domains, report.unseen_domains]:
            for d in lst:
                assert d not in all_domains, f"{d} appears in multiple lists"
                all_domains.add(d)


# ═══════════════════════════════════════════════════════════════════════
# EconomicTracker Tests
# ═══════════════════════════════════════════════════════════════════════


class TestEconomicTrackerEmpty:
    """Tests with empty or minimal telemetry."""

    def test_empty_history(self) -> None:
        tracker = EconomicTracker()
        report = tracker.analyze([])
        assert isinstance(report, EconomicReport)
        assert report.total_cost_usd == 0.0
        assert report.total_scrapes == 0
        assert report.total_records == 0

    def test_single_event(self) -> None:
        tracker = EconomicTracker()
        history = [
            _make_telemetry(
                url="https://example.com/page",
                estimated_cost_usd=0.05,
                records_final=10,
            ),
        ]
        report = tracker.analyze(history)
        assert report.total_scrapes == 1
        assert report.total_records == 10
        assert report.total_cost_usd > 0


class TestEconomicTrackerCostAnalysis:
    """Tests for cost calculations."""

    def test_cost_from_estimated_field(self) -> None:
        tracker = EconomicTracker()
        history = [
            _make_telemetry(
                url="https://cost.example.com/page",
                estimated_cost_usd=0.05,
                records_final=10,
            ),
            _make_telemetry(
                url="https://cost.example.com/page",
                estimated_cost_usd=0.15,
                records_final=5,
            ),
        ]
        report = tracker.analyze(history)
        summary = report.cost_by_domain["cost.example.com"]
        assert summary.total_cost_usd == pytest.approx(0.20, 0.01)
        assert summary.avg_cost_per_scrape == pytest.approx(0.10, 0.01)

    def test_cost_from_components(self) -> None:
        """When estimated_cost_usd is 0, costs should be derived from components."""
        tracker = EconomicTracker()
        history = [
            _make_telemetry(
                url="https://components.example.com/page",
                estimated_cost_usd=0.0,
                llm_calls_count=5,
                fetch_ms=3000.0,
                fetch_method="playwright",
                records_final=10,
            ),
        ]
        report = tracker.analyze(history)
        summary = report.cost_by_domain["components.example.com"]
        # Expected: 5 * 0.01 (LLM) + 3 * 0.005 (browser) + 0.001 (network)  # noqa: ERA001
        expected = 5 * 0.01 + 3 * 0.005 + 0.001
        assert summary.cost_breakdown["llm"] == pytest.approx(0.05, 0.01)
        assert summary.cost_breakdown["browser"] == pytest.approx(0.015, 0.01)
        assert summary.cost_breakdown["network"] == pytest.approx(0.001, 0.01)
        assert summary.total_cost_usd == pytest.approx(expected, 0.01)

    def test_httpx_lower_cost(self) -> None:
        """Httpx (no browser) should cost less than playwright."""
        tracker = EconomicTracker()
        httpx_history = [
            _make_telemetry(
                url="https://httpx.example.com/page",
                estimated_cost_usd=0.0,
                fetch_method="httpx",
                fetch_ms=500.0,
                llm_calls_count=2,
                records_final=10,
            ),
        ]
        playwright_history = [
            _make_telemetry(
                url="https://pw.example.com/page",
                estimated_cost_usd=0.0,
                fetch_method="playwright",
                fetch_ms=3000.0,
                llm_calls_count=2,
                records_final=10,
            ),
        ]
        httpx_report = tracker.analyze(httpx_history)
        pw_report = tracker.analyze(playwright_history)
        assert httpx_report.total_cost_usd < pw_report.total_cost_usd


class TestEconomicTrackerMultiDomain:
    """Tests for multi-domain cost analysis."""

    def test_multi_domain_cost_breakdown(self) -> None:
        tracker = EconomicTracker()
        history = _multi_domain_history()
        report = tracker.analyze(history)
        assert "good.example.com" in report.cost_by_domain
        assert "ok.example.com" in report.cost_by_domain
        assert "bad.example.com" in report.cost_by_domain
        assert report.most_expensive_domains[0]["domain"] == "bad.example.com"

    def test_cost_by_category(self) -> None:
        tracker = EconomicTracker()
        history = [
            _make_telemetry(
                url="https://cat.example.com/page",
                estimated_cost_usd=0.0,
                llm_calls_count=10,
                fetch_ms=2000.0,
                fetch_method="playwright",
            ),
        ]
        report = tracker.analyze(history)
        assert "llm" in report.cost_by_category
        assert "browser" in report.cost_by_category
        assert "network" in report.cost_by_category

    def test_total_cost_aggregation(self) -> None:
        tracker = EconomicTracker()
        history = _multi_domain_history()  # 10 + 6 + 8 = 24 events
        report = tracker.analyze(history)
        assert report.total_scrapes == 24
        assert report.total_cost_usd > 0


class TestEconomicTrackerEfficiency:
    """Tests for efficiency rating calculations."""

    def test_high_efficiency(self) -> None:
        """Cost per record <= 0.01 should be 'excellent'."""
        assert EconomicTracker._rate_efficiency(0.005) == "excellent"
        assert EconomicTracker._rate_efficiency(0.01) == "excellent"

    def test_good_efficiency(self) -> None:
        assert EconomicTracker._rate_efficiency(0.02) == "good"

    def test_fair_efficiency(self) -> None:
        assert EconomicTracker._rate_efficiency(0.05) == "fair"

    def test_poor_efficiency(self) -> None:
        assert EconomicTracker._rate_efficiency(0.15) == "poor"

    def test_efficiency_in_report(self) -> None:
        """Report-level efficiency should match domain averages."""
        tracker = EconomicTracker()
        history = [
            _make_telemetry(
                url="https://cheap.example.com/page",
                estimated_cost_usd=0.02,
                records_final=20,
            ),
        ]
        report = tracker.analyze(history)
        # 0.02 / 20 = 0.001 per record = excellent
        assert report.efficiency_rating == "excellent"
        assert report.cost_by_domain["cheap.example.com"].efficiency_rating == "excellent"


class TestEconomicTrackerDomainSorting:
    """Tests for most/least expensive domain ordering."""

    def test_most_expensive_first(self) -> None:
        tracker = EconomicTracker()
        history = _multi_domain_history()
        report = tracker.analyze(history)
        assert len(report.most_expensive_domains) >= 1
        # bad.example.com should be most expensive (highest failure rate)
        assert report.most_expensive_domains[0]["domain"] == "bad.example.com"

    def test_domain_summary_fields(self) -> None:
        tracker = EconomicTracker()
        history = [
            _make_telemetry(
                url="https://summary.example.com/page",
                estimated_cost_usd=0.10,
                records_final=5,
            ),
        ]
        report = tracker.analyze(history)
        summary = report.cost_by_domain["summary.example.com"]
        assert summary.total_scrapes == 1
        assert summary.total_records == 5
        assert summary.total_cost_usd == 0.10
        assert summary.cost_breakdown is not None
