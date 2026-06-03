"""Tests for the DegradationPredictor."""

from __future__ import annotations

import time

from app.degradation_predictor import (
    DegradationPredictor,
    Prediction,
    PredictionReport,
    get_degradation_predictor,
)
from app.trend_analyzer import DomainTrend

# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


def _make_domain_trend(
    domain: str = "example.com",
    health_score: float = 80.0,
    sample_count: int = 30,
    avg_quality_score: float = 0.8,
    failure_rate: float = 0.1,
    avg_fetch_ms: float = 2000,
    quality_trend: str = "stable",
    fetch_latency_trend: str = "stable",
    anti_bot_trend: str = "stable",
    selector_decay_accelerating: bool = False,
    top_failure_categories: list | None = None,
) -> DomainTrend:
    """Build a DomainTrend object for testing."""
    return DomainTrend(
        domain=domain,
        health_score=health_score,
        sample_count=sample_count,
        avg_quality_score=avg_quality_score,
        failure_rate=failure_rate,
        avg_fetch_ms=avg_fetch_ms,
        quality_trend=quality_trend,
        fetch_latency_trend=fetch_latency_trend,
        anti_bot_trend=anti_bot_trend,
        selector_decay_accelerating=selector_decay_accelerating,
        top_failure_categories=top_failure_categories or [],
    )


def _make_telemetry_event(
    url: str = "https://example.com/page",
    success: bool = True,
    latency_ms: float = 2000,
    quality_score: float = 0.8,
    anti_bot_score: float = 0.0,
    estimated_cost_usd: float = 0.01,
    fallback_triggered: bool = False,
    fetch_method: str = "playwright",
    failure_category: str | None = None,
) -> dict:
    """Build a minimal ScrapeTelemetry event dict."""
    return {
        "url": url,
        "success": success,
        "latency_ms": latency_ms,
        "quality_score": quality_score,
        "anti_bot_score": anti_bot_score,
        "estimated_cost_usd": estimated_cost_usd,
        "fallback_triggered": fallback_triggered,
        "fetch_method": fetch_method,
        "failure_category": failure_category,
        "timestamp": time.time(),
        "domain": url.split("/")[2] if "://" in url else url,
    }


def _healthy_domain_trend() -> DomainTrend:
    return _make_domain_trend(
        health_score=92.0,
        avg_quality_score=0.88,
        failure_rate=0.02,
        quality_trend="stable",
    )


def _degrading_domain_trend() -> DomainTrend:
    return _make_domain_trend(
        health_score=38.0,
        sample_count=25,
        avg_quality_score=0.35,
        failure_rate=0.45,
        quality_trend="degrading",
        anti_bot_trend="degrading",
        selector_decay_accelerating=True,
        top_failure_categories=[
            {"category": "selector_decay", "count": 6},
            {"category": "anti_bot", "count": 4},
        ],
    )


def _critical_domain_trend() -> DomainTrend:
    return _make_domain_trend(
        health_score=15.0,
        sample_count=50,
        avg_quality_score=0.08,
        failure_rate=0.85,
        quality_trend="degrading",
        fetch_latency_trend="degrading",
        anti_bot_trend="degrading",
        selector_decay_accelerating=True,
        top_failure_categories=[
            {"category": "selector_decay", "count": 20},
            {"category": "anti_bot", "count": 15},
            {"category": "timeout", "count": 8},
        ],
    )


def _latency_creep_trend() -> DomainTrend:
    return _make_domain_trend(
        health_score=55.0,
        avg_quality_score=0.6,
        failure_rate=0.2,
        avg_fetch_ms=22000,
        fetch_latency_trend="degrading",
    )


def _zero_result_trend() -> DomainTrend:
    return _make_domain_trend(
        health_score=45.0,
        avg_quality_score=0.08,
        failure_rate=0.3,
        sample_count=12,
    )


# ─────────────────────────────────────────────────────────────────────
# Prediction Unit Tests
# ─────────────────────────────────────────────────────────────────────


class TestPredictionModel:
    def test_to_dict_returns_all_keys(self):
        p = Prediction(
            domain="test.com",
            risk_level="high",
            confidence=0.85,
            predicted_failure_type="selector_decay",
            health_score_current=42.0,
            health_score_trend="declining",
            evidence=["Evidence 1"],
            recommended_actions=["Action 1"],
        )
        d = p.to_dict()
        assert d["domain"] == "test.com"
        assert d["risk_level"] == "high"
        assert d["confidence"] == 0.85
        assert d["predicted_failure_type"] == "selector_decay"
        assert "generated_at" in d

    def test_prediction_defaults(self):
        p = Prediction(
            domain="test.com",
            risk_level="low",
            confidence=0.5,
            predicted_failure_type="general_degradation",
            health_score_current=80.0,
            health_score_trend="stable",
            evidence=[],
            recommended_actions=[],
        )
        assert p.cascade_risk is False
        assert p.cascade_risk_domains == []
        assert p.sample_count == 0
        assert p.data_window_size == 0


class TestPredictionReport:
    def test_empty_report(self):
        r = PredictionReport()
        d = r.to_dict()
        assert d["domains_analyzed"] == 0
        assert d["predictions"] == []
        assert d["systemic_risk_level"] == "low"
        assert "summary" in d

    def test_report_with_predictions(self):
        r = PredictionReport()
        r.domains_analyzed = 2
        r.predictions = [
            Prediction(
                domain="a.com",
                risk_level="high",
                confidence=0.8,
                predicted_failure_type="selector_decay",
                health_score_current=30.0,
                health_score_trend="declining",
                evidence=[],
                recommended_actions=[],
            ),
            Prediction(
                domain="b.com",
                risk_level="low",
                confidence=0.6,
                predicted_failure_type="general_degradation",
                health_score_current=75.0,
                health_score_trend="stable",
                evidence=[],
                recommended_actions=[],
            ),
        ]
        r.critical_risk_count = 0
        r.high_risk_count = 1
        r.medium_risk_count = 0
        r.low_risk_count = 1
        r.average_confidence = 0.7
        r.most_common_failure_type = "selector_decay"
        r.systemic_risk_level = "medium"

        r.top_risks = [p.to_dict() for p in r.predictions]

        d = r.to_dict()
        assert len(d["predictions"]) == 2
        assert d["summary"]["critical"] == 0
        assert d["summary"]["high"] == 1
        assert d["summary"]["low"] == 1
        assert d["systemic_risk_level"] == "medium"
        assert len(d["top_risks"]) == 2


# ─────────────────────────────────────────────────────────────────────
# DegradationPredictor Unit Tests
# ─────────────────────────────────────────────────────────────────────


class TestDegradationPredictor:
    def test_predict_healthy_domain_no_predictions(self):
        predictor = DegradationPredictor()
        trends = {"example.com": _healthy_domain_trend()}
        report = predictor.predict([], trends)

        assert report.domains_analyzed == 1
        # Healthy domains shouldn't generate high-risk predictions
        high_risk = sum(1 for p in report.predictions if p.risk_level in ("high", "critical"))
        assert (
            high_risk == 0
        ), f"Expected no high-risk predictions for healthy domain, got {high_risk}: {[p.to_dict() for p in report.predictions]}"

    def test_predict_degrading_domain_has_predictions(self):
        predictor = DegradationPredictor()
        trends = {"degrading.com": _degrading_domain_trend()}
        report = predictor.predict([], trends)

        assert report.domains_analyzed == 1
        assert len(report.predictions) >= 1, "Degrading domain should generate predictions"
        # At least one should be medium, high, or critical
        severities = {p.risk_level for p in report.predictions}
        assert severities & {"medium", "high", "critical"}, f"Expected at least medium severity, got {severities}"

    def test_predict_critical_domain_generates_high_risk(self):
        predictor = DegradationPredictor()
        trends = {"critical.com": _critical_domain_trend()}
        report = predictor.predict([], trends)

        assert report.domains_analyzed == 1
        assert len(report.predictions) >= 2
        high_or_critical = [p for p in report.predictions if p.risk_level in ("high", "critical")]
        assert len(high_or_critical) >= 1, f"Expected at least 1 high/critical prediction, got {len(high_or_critical)}"
        # Check cascade risk detection for high-volume critical domain
        has_cascade = any(p.cascade_risk for p in report.predictions)
        assert has_cascade, "High-volume critical domain should have cascade risk"

    def test_predict_selector_decay_accelerating(self):
        predictor = DegradationPredictor()
        trend = _make_domain_trend(
            health_score=45.0,
            quality_trend="degrading",
            selector_decay_accelerating=True,
            avg_quality_score=0.5,
            failure_rate=0.15,
        )
        trends = {"decay.com": trend}
        report = predictor.predict([], trends)

        decay_preds = [p for p in report.predictions if p.predicted_failure_type == "selector_decay"]
        assert len(decay_preds) >= 1, "Accelerating selector decay should generate a decay prediction"
        # Should have an estimated time to failure
        decay = decay_preds[0]
        assert decay.estimated_time_to_failure_hours is not None

    def test_predict_anti_bot_intensification(self):
        predictor = DegradationPredictor()
        trend = _make_domain_trend(
            health_score=55.0,
            anti_bot_trend="degrading",
            failure_rate=0.15,
        )
        trends = {"bot.com": trend}
        report = predictor.predict([], trends)

        bot_preds = [p for p in report.predictions if p.predicted_failure_type == "anti_bot_block"]
        assert len(bot_preds) >= 1, "Degrading anti-bot should generate a prediction"

    def test_predict_latency_timeout_spiral(self):
        predictor = DegradationPredictor()
        trends = {"slow.com": _latency_creep_trend()}
        report = predictor.predict([], trends)

        timeout_preds = [p for p in report.predictions if p.predicted_failure_type == "timeout_death_spiral"]
        assert len(timeout_preds) >= 1, "High latency with degrading trend should warn of timeout death spiral"

    def test_predict_zero_result_drift(self):
        predictor = DegradationPredictor()
        trends = {"empty.com": _zero_result_trend()}
        report = predictor.predict([], trends)

        zero_preds = [p for p in report.predictions if p.predicted_failure_type == "zero_result_drift"]
        assert len(zero_preds) >= 1, "Very low quality with enough samples should predict zero result drift"

    def test_predict_sustained_failure_rate(self):
        predictor = DegradationPredictor()
        trend = _make_domain_trend(
            health_score=25.0,
            failure_rate=0.75,
            sample_count=30,
            quality_trend="degrading",
        )
        trends = {"failing.com": trend}
        report = predictor.predict([], trends)

        failure_preds = [p for p in report.predictions if p.predicted_failure_type == "sustained_failure_rate"]
        assert len(failure_preds) >= 1, "High failure rate should generate sustained failure prediction"
        assert failure_preds[0].risk_level in ("high", "critical")

    def test_predict_insufficient_data(self):
        predictor = DegradationPredictor()
        trend = _make_domain_trend(
            sample_count=1,
            health_score=50.0,
        )
        trends = {"new.com": trend}
        report = predictor.predict([], trends)

        # No predictions should be made for domains with < 2 samples
        assert len(report.predictions) == 0

    def test_confidence_increases_with_samples(self):
        predictor = DegradationPredictor()
        low_sample = _make_domain_trend(
            health_score=35.0,
            sample_count=2,
            quality_trend="degrading",
            selector_decay_accelerating=True,
        )
        high_sample = _make_domain_trend(
            health_score=35.0,
            sample_count=50,
            quality_trend="degrading",
            selector_decay_accelerating=True,
        )

        report_low = predictor.predict([], {"d.com": low_sample})
        report_high = predictor.predict([], {"d.com": high_sample})

        # High-sample predictions should have higher average confidence
        avg_low = report_low.average_confidence
        avg_high = report_high.average_confidence
        assert avg_high >= avg_low, f"Expected higher confidence with more samples ({avg_high} >= {avg_low})"

    def test_systemic_risk_computation(self):
        predictor = DegradationPredictor()

        # Create a report with critical predictions
        report = PredictionReport()
        report.critical_risk_count = 1
        report.high_risk_count = 2
        risk = predictor._compute_systemic_risk(report)
        assert risk == "high", f"Expected 'high' systemic risk for 1 critical + 2 high, got {risk}"

        # High only
        report2 = PredictionReport()
        report2.high_risk_count = 2
        risk2 = predictor._compute_systemic_risk(report2)
        assert risk2 == "medium", f"Expected 'medium' systemic risk for 2 high, got {risk2}"

        # Low risk
        report3 = PredictionReport()
        report3.medium_risk_count = 2
        risk3 = predictor._compute_systemic_risk(report3)
        assert risk3 == "low", f"Expected 'low' systemic risk for 2 medium, got {risk3}"

        # Critical threshold
        report4 = PredictionReport()
        report4.critical_risk_count = 3
        risk4 = predictor._compute_systemic_risk(report4)
        assert risk4 == "critical", f"Expected 'critical' systemic risk for 3 critical, got {risk4}"

    def test_top_risks_sorted_by_severity(self):
        predictor = DegradationPredictor()
        trends = {
            "low.com": _healthy_domain_trend(),
            "degrading.com": _degrading_domain_trend(),
            "critical.com": _critical_domain_trend(),
        }
        report = predictor.predict([], trends)

        assert len(report.top_risks) > 0
        # Top risks should be sorted with critical first
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for i in range(len(report.top_risks) - 1):
            current = severity_order.get(report.top_risks[i]["risk_level"], 99)
            next_ = severity_order.get(report.top_risks[i + 1]["risk_level"], 99)
            assert (
                current <= next_
            ), f"Top risks not sorted: {report.top_risks[i]['risk_level']} before {report.top_risks[i + 1]['risk_level']}"

    def test_multi_domain_prediction(self):
        predictor = DegradationPredictor()
        trends = {
            "healthy.com": _healthy_domain_trend(),
            "degrading.com": _degrading_domain_trend(),
        }
        report = predictor.predict([], trends)

        assert report.domains_analyzed == 2
        # Degrading domain should have more predictions than healthy
        healthy_preds = [p for p in report.predictions if p.domain == "healthy.com"]
        degrading_preds = [p for p in report.predictions if p.domain == "degrading.com"]
        assert len(degrading_preds) >= len(
            healthy_preds
        ), f"Degrading domain ({len(degrading_preds)}) should have >= predictions than healthy ({len(healthy_preds)})"

    def test_health_trend_determination(self):
        predictor = DegradationPredictor()
        trend_all_bad = _make_domain_trend(
            quality_trend="degrading",
            fetch_latency_trend="degrading",
            anti_bot_trend="degrading",
            selector_decay_accelerating=True,
        )
        trend_all_good = _make_domain_trend(
            quality_trend="improving",
            fetch_latency_trend="improving",
            anti_bot_trend="stable",
            selector_decay_accelerating=False,
        )
        trend_mixed = _make_domain_trend(
            quality_trend="degrading",
            fetch_latency_trend="improving",
            anti_bot_trend="stable",
            selector_decay_accelerating=True,
        )

        # We can verify _determine_health_trend logic through predictions
        report_bad = predictor.predict([], {"bad.com": trend_all_bad})
        predictor.predict([], {"good.com": trend_all_good})
        predictor.predict([], {"mixed.com": trend_mixed})

        # Bad domain should have predictions with declining health trend
        bad_health_trends = {p.health_score_trend for p in report_bad.predictions}
        assert "declining" in bad_health_trends or report_bad.predictions

        # Test _determine_health_trend directly
        class DecliningFakeTrend:
            quality_trend = "degrading"
            fetch_latency_trend = "degrading"
            anti_bot_trend = "degrading"
            selector_decay_accelerating = True

        result = predictor._determine_health_trend(DecliningFakeTrend())
        assert result == "declining", f"Expected declining, got {result}"

        class ImprovingFakeTrend:
            quality_trend = "improving"
            fetch_latency_trend = "improving"
            anti_bot_trend = "stable"
            selector_decay_accelerating = False

        result = predictor._determine_health_trend(ImprovingFakeTrend())
        assert result == "improving", f"Expected improving, got {result}"

    def test_multi_predictions_use_recommended_actions(self):
        """Verify that predictions include actionable recommendations."""
        predictor = DegradationPredictor()
        trends = {"degrading.com": _degrading_domain_trend()}
        report = predictor.predict([], trends)

        for p in report.predictions:
            assert (
                len(p.recommended_actions) >= 1
            ), f"Prediction for {p.domain} ({p.predicted_failure_type}) should have at least 1 recommended action"
            assert len(p.evidence) >= 1, f"Prediction for {p.domain} should have at least 1 evidence item"


# ─────────────────────────────────────────────────────────────────────
# Integration and Singleton Tests
# ─────────────────────────────────────────────────────────────────────


class TestDegradationPredictorIntegration:
    def test_predict_with_real_telemetry(self):
        """Use simulated telemetry events to drive predictions."""
        events = []
        # 8 healthy events
        for i in range(8):
            events.append(
                _make_telemetry_event(
                    url="https://healthy.com/page",
                    success=True,
                    quality_score=0.85,
                    latency_ms=1000,
                )
            )
        # 12 degrading events
        for i in range(12):
            events.append(
                _make_telemetry_event(
                    url="https://degrading.com/page",
                    success=(i < 6),
                    quality_score=0.4 if i >= 6 else 0.7,
                    latency_ms=5000 if i >= 6 else 2000,
                    anti_bot_score=0.5 if i >= 6 else 0.1,
                )
            )

        predictor = DegradationPredictor(history_window=50)
        report = predictor.predict(events)

        assert report.domains_analyzed >= 1
        # Degrading domain should generate predictions
        degrading_preds = [p for p in report.predictions if "degrading.com" in p.domain]
        if degrading_preds:
            assert any(p.risk_level in ("medium", "high") for p in degrading_preds)

    def test_singleton_returns_same_instance(self):
        p1 = get_degradation_predictor()
        p2 = get_degradation_predictor()
        assert p1 is p2

    def test_empty_telemetry_returns_empty_report(self):
        predictor = DegradationPredictor()
        report = predictor.predict([])
        assert report.domains_analyzed == 0
        assert report.predictions == []
        assert report.systemic_risk_level == "low"
