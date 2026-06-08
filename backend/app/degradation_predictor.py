"""Degradation Predictor — predicts what's about to fail in the extraction system.

Uses telemetry trend data from TrendAnalyzer to:
  - Identify domains heading toward failure based on slope analysis
  - Assign risk scores and estimated time-to-failure
  - Generate predictive alerts with confidence levels
  - Detect systemic degradation patterns (cascade risks)

LAW: Prediction without confidence is noise. Every prediction carries
a confidence score and a clear rationale.

LAW: Preventive action is cheaper than recovery. Predictions include
recommended actions to prevent the predicted failure.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.trend_analyzer import DomainTrend

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class Prediction:
    """A single prediction about an upcoming failure."""

    domain: str
    risk_level: str  # 'low' | 'medium' | 'high' | 'critical'
    confidence: float  # 0.0 to 1.0
    predicted_failure_type: str
    """What kind of failure is predicted (e.g., 'selector_decay', 'anti_bot_block',
    'timeout_death_spiral', 'zero_result_drift', 'latency_collapse')."""

    estimated_time_to_failure_hours: float | None = None
    """How many hours until the predicted failure is expected to occur."""

    health_score_current: float = 100.0
    health_score_trend: str = "stable"
    """Direction of health score change: 'improving' | 'stable' | 'declining'."""

    evidence: list[str] = field(default_factory=list)
    """Specific evidence supporting this prediction."""

    recommended_actions: list[str] = field(default_factory=list)
    """What the operator should do to prevent this failure."""

    # Cascade risk
    cascade_risk: bool = False
    """Whether this failure could cascade to other domains."""
    cascade_risk_domains: list[str] = field(default_factory=list)
    """Domains that would be affected by a cascade."""

    # Timing
    generated_at: float = field(default_factory=time.time)
    data_window_size: int = 0
    sample_count: int = 0

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "risk_level": self.risk_level,
            "confidence": round(self.confidence, 3),
            "predicted_failure_type": self.predicted_failure_type,
            "estimated_time_to_failure_hours": self.estimated_time_to_failure_hours,
            "health_score_current": round(self.health_score_current, 1),
            "health_score_trend": self.health_score_trend,
            "evidence": self.evidence,
            "recommended_actions": self.recommended_actions,
            "cascade_risk": self.cascade_risk,
            "cascade_risk_domains": self.cascade_risk_domains,
            "generated_at": self.generated_at,
            "data_window_size": self.data_window_size,
            "sample_count": self.sample_count,
        }


@dataclass
class PredictionReport:
    """Complete degradation prediction report for the system."""

    generated_at: float = field(default_factory=time.time)
    predictions: list[Prediction] = field(default_factory=list)

    # Summary
    domains_analyzed: int = 0
    high_risk_count: int = 0
    medium_risk_count: int = 0
    low_risk_count: int = 0
    critical_risk_count: int = 0

    # Systemic risk
    systemic_risk_level: str = "low"
    """Overall system risk: 'low' | 'medium' | 'high' | 'critical'."""
    cascade_risk_count: int = 0
    most_common_failure_type: str = "none"
    average_confidence: float = 0.0

    # Top risks
    top_risks: list[dict] = field(default_factory=list)
    """Sorted by risk level and confidence, limited to top 10."""

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "domains_analyzed": self.domains_analyzed,
            "predictions": [p.to_dict() for p in self.predictions],
            "summary": {
                "critical": self.critical_risk_count,
                "high": self.high_risk_count,
                "medium": self.medium_risk_count,
                "low": self.low_risk_count,
                "cascade_risks": self.cascade_risk_count,
                "most_common_failure_type": self.most_common_failure_type,
                "average_confidence": round(self.average_confidence, 3),
            },
            "systemic_risk_level": self.systemic_risk_level,
            "top_risks": self.top_risks[:10],
        }


# ═══════════════════════════════════════════════════════════════════════
# Degradation Pattern Detectors
# ═══════════════════════════════════════════════════════════════════════


class DegradationPredictor:
    """Predicts what's about to fail by analyzing telemetry trends.

    Uses the output of TrendAnalyzer and applies predictive models:
      - Extrapolates current trends forward
      - Identifies inflection points
      - Detects cascade risk patterns
      - Generates actionable predictions
    """

    # Risk thresholds
    CRITICAL_HEALTH_THRESHOLD = 25
    HIGH_HEALTH_THRESHOLD = 45
    MEDIUM_HEALTH_THRESHOLD = 65

    def __init__(self, history_window: int = 200) -> None:
        self._history_window = history_window

    def predict(self, telemetry_history: list[dict], domain_trends: dict | None = None) -> PredictionReport:
        """Run full degradation prediction on telemetry data.

        Args:
            telemetry_history: List of ScrapeTelemetry dicts.
            domain_trends: Optional pre-computed domain trends from TrendAnalyzer.
                           If not provided, they'll be computed.

        Returns:
            A PredictionReport with per-domain predictions and system risk.

        """
        from app.trend_analyzer import TrendAnalyzer

        analyzer = TrendAnalyzer(history_window=self._history_window)

        # Compute trends if not provided
        if domain_trends is None:
            trend_report = analyzer.analyze(telemetry_history)
            domain_trends = trend_report.domain_trends

        result = PredictionReport()
        result.domains_analyzed = len(domain_trends)

        # Collect all predictions
        all_predictions: list[Prediction] = []
        failure_type_counts: dict[str, int] = defaultdict(int)

        for domain, trend in domain_trends.items():
            predictions = self._predict_domain(domain, trend)
            all_predictions.extend(predictions)
            for p in predictions:
                failure_type_counts[p.predicted_failure_type] += 1

        result.predictions = all_predictions

        # Count by risk level
        for p in all_predictions:
            if p.risk_level == "critical":
                result.critical_risk_count += 1
            elif p.risk_level == "high":
                result.high_risk_count += 1
            elif p.risk_level == "medium":
                result.medium_risk_count += 1
            else:
                result.low_risk_count += 1

            if p.cascade_risk:
                result.cascade_risk_count += 1

        # Most common failure type
        if failure_type_counts:
            result.most_common_failure_type = max(failure_type_counts, key=lambda k: failure_type_counts[k])

        # Average confidence
        if all_predictions:
            result.average_confidence = sum(p.confidence for p in all_predictions) / len(all_predictions)

        # Systemic risk level
        result.systemic_risk_level = self._compute_systemic_risk(result)

        # Top risks sorted by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_predictions = sorted(
            all_predictions,
            key=lambda p: (
                severity_order.get(p.risk_level, 99),
                -p.confidence,
            ),
        )
        result.top_risks = [p.to_dict() for p in sorted_predictions[:10]]

        return result

    # ── Per-Domain Prediction ───────────────────────────────────────

    def _predict_domain(self, domain: str, trend: DomainTrend) -> list[Prediction]:
        """Generate all predictions for a single domain."""
        predictions: list[Prediction] = []

        if trend.sample_count < 2:
            return predictions  # Not enough data

        # 1. General health-based risk assessment
        health_pred = self._predict_health_failure(domain, trend)
        if health_pred:
            predictions.append(health_pred)

        # 2. Check for selector decay acceleration
        if trend.selector_decay_accelerating:
            pred = self._build_prediction(
                domain=domain,
                risk_level="high" if trend.health_score < 50 else "medium",
                failure_type="selector_decay",
                confidence=self._estimate_confidence(trend, base=0.75),
                health_score_current=trend.health_score,
                health_score_trend=trend.quality_trend,
                evidence=[
                    "Selector decay rate is accelerating",
                    f"Quality trend: {trend.quality_trend}",
                    f"Health score: {trend.health_score:.0f}/100",
                ],
                recommended_actions=[
                    "Force selector rediscovery",
                    "Increase fallback selector pool size",
                    "Run diagnostic scrape on this domain",
                ],
                trend=trend,
            )
            if pred.risk_level in ("high", "critical"):
                pred.estimated_time_to_failure_hours = self._estimate_selector_decay_timer(trend)
            predictions.append(pred)

        # 3. Check for anti-bot intensification
        if trend.anti_bot_trend == "degrading":
            pred = self._build_prediction(
                domain=domain,
                risk_level="medium" if trend.health_score > 50 else "high",
                failure_type="anti_bot_block",
                confidence=self._estimate_confidence(trend, base=0.7),
                health_score_current=trend.health_score,
                health_score_trend=trend.anti_bot_trend,
                evidence=[
                    "Anti-bot pressure is increasing",
                    f"Current health score: {trend.health_score:.0f}/100",
                    f"Failure rate: {trend.failure_rate:.0%}",
                ],
                recommended_actions=[
                    "Rotate proxy pool",
                    "Reduce request frequency for this domain",
                    "Increase page settle delay",
                    "Consider forensic mode for debugging",
                ],
                trend=trend,
            )
            predictions.append(pred)

        # 4. Check for latency creep (timeout death spiral)
        if trend.fetch_latency_trend == "degrading" and trend.avg_fetch_ms > 15000:
            pred = self._build_prediction(
                domain=domain,
                risk_level="medium",
                failure_type="timeout_death_spiral",
                confidence=self._estimate_confidence(trend, base=0.65),
                health_score_current=trend.health_score,
                health_score_trend=trend.fetch_latency_trend,
                evidence=[
                    f"Fetch latency increasing (avg: {trend.avg_fetch_ms:.0f}ms)",
                    f"Latency trend: {trend.fetch_latency_trend}",
                ],
                recommended_actions=[
                    "Increase timeout for this domain",
                    "Switch to lighter fetch strategy",
                    "Check if anti-bot is causing slowdown",
                ],
                trend=trend,
            )
            predictions.append(pred)

        # 5. Check for zero-result drift (empty pages)
        if trend.avg_quality_score < 0.15 and trend.sample_count >= 5:
            pred = self._build_prediction(
                domain=domain,
                risk_level="high" if trend.health_score < 40 else "medium",
                failure_type="zero_result_drift",
                confidence=self._estimate_confidence(trend, base=0.7),
                health_score_current=trend.health_score,
                health_score_trend=trend.quality_trend,
                evidence=[
                    f"Very low quality score: {trend.avg_quality_score:.2f}",
                    f"Failure rate: {trend.failure_rate:.0%}",
                    "Pages may be returning empty results",
                ],
                recommended_actions=[
                    "Re-analyze page structure",
                    "Check for anti-bot redirects",
                    "Verify page layout hasn't changed",
                    "Run diagnostic scrape",
                ],
                trend=trend,
            )
            predictions.append(pred)

        # 6. High failure rate with poor health
        if trend.failure_rate > 0.5 and trend.health_score < 40:
            # Check cascade risk: if this is a major domain, failures could
            # cascade
            cascade = trend.sample_count >= 20
            pred = self._build_prediction(
                domain=domain,
                risk_level="critical" if trend.failure_rate > 0.8 else "high",
                failure_type="sustained_failure_rate",
                confidence=self._estimate_confidence(trend, base=0.85),
                health_score_current=trend.health_score,
                health_score_trend="declining",
                evidence=[
                    f"Sustained failure rate: {trend.failure_rate:.0%}",
                    f"Health score: {trend.health_score:.0f}/100",
                    f"Top failure categories: {[c['category'] for c in trend.top_failure_categories[:3]]}",
                ],
                recommended_actions=[
                    "Pause scraping on this domain",
                    "Investigate root cause of failures",
                    "Check if domain structure has changed",
                    "Run forensic diagnostics",
                ],
                trend=trend,
                cascade_risk=cascade,
                cascade_risk_domains=[domain] if cascade else [],
            )
            if cascade:
                pred.evidence.append("High-volume domain — failure could cascade to dependent systems")
                pred.recommended_actions.append("Reduce concurrency for all domains sharing this proxy pool")
            predictions.append(pred)

        return predictions

    def _predict_health_failure(self, domain: str, trend: DomainTrend) -> Prediction | None:
        """Generate a general health-based prediction if health is poor or declining."""
        if trend.health_score >= self.MEDIUM_HEALTH_THRESHOLD:
            return None  # Healthy enough

        if trend.health_score < self.CRITICAL_HEALTH_THRESHOLD:
            risk_level = "critical"
        elif trend.health_score < self.HIGH_HEALTH_THRESHOLD:
            risk_level = "high"
        else:
            risk_level = "medium"

        evidence = [
            f"Health score: {trend.health_score:.0f}/100",
            f"Failure rate: {trend.failure_rate:.0%}",
            f"Sample count: {trend.sample_count}",
        ]
        if trend.quality_trend == "degrading":
            evidence.append("Quality metrics are declining")

        rec_actions = [
            "Increase monitoring frequency",
            "Review recent changes to extraction configuration",
        ]
        if trend.selector_decay_accelerating:
            rec_actions.append("Force selector rediscovery")
        if trend.anti_bot_trend == "degrading":
            rec_actions.append("Rotate proxies and reduce frequency")

        return self._build_prediction(
            domain=domain,
            risk_level=risk_level,
            failure_type="general_degradation",
            confidence=self._estimate_confidence(trend, base=0.6),
            health_score_current=trend.health_score,
            health_score_trend=self._determine_health_trend(trend),
            evidence=evidence,
            recommended_actions=rec_actions,
            trend=trend,
        )

    # ── Helpers ─────────────────────────────────────────────────────

    def _build_prediction(
        self,
        domain: str,
        risk_level: str,
        failure_type: str,
        confidence: float,
        health_score_current: float,
        health_score_trend: str,
        evidence: list[str],
        recommended_actions: list[str],
        trend: DomainTrend,
        cascade_risk: bool = False,
        cascade_risk_domains: list[str] | None = None,
    ) -> Prediction:
        return Prediction(
            domain=domain,
            risk_level=risk_level,
            confidence=confidence,
            predicted_failure_type=failure_type,
            health_score_current=health_score_current,
            health_score_trend=health_score_trend,
            evidence=evidence,
            recommended_actions=recommended_actions,
            cascade_risk=cascade_risk,
            cascade_risk_domains=cascade_risk_domains or [],
            sample_count=trend.sample_count,
            data_window_size=self._history_window,
        )

    def _estimate_confidence(self, trend: DomainTrend, base: float) -> float:
        """Adjust base confidence based on data quality."""
        # More samples = more confident
        sample_factor = min(1.0, trend.sample_count / 30)
        # Adjust for data recency and volume
        adjusted = base * (0.5 + 0.5 * sample_factor)
        return max(0.1, min(1.0, adjusted))

    def _estimate_selector_decay_timer(self, trend: DomainTrend) -> float | None:
        """Estimate hours until selector decay causes significant extraction loss."""
        if trend.sample_count < 5:
            return None

        # Use recent quality trend to estimate decay rate
        if trend.quality_trend == "degrading":
            # Assume linear decay: estimate time until quality < 0.1
            quality_gap = max(0, trend.avg_quality_score - 0.1)
            if quality_gap <= 0:
                return 0  # Already critically low

            # Rough estimate: at current decay rate, how many hours?
            # Use 0.05 per 100 scrapes as baseline decay rate
            decay_per_scrape = 0.05 / 100
            scrapes_to_critical = quality_gap / decay_per_scrape
            # Assume ~2 scrapes per hour for this domain
            hours = scrapes_to_critical / 2
            return max(1, min(168, hours))  # Between 1 hour and 1 week

        return None

    def _determine_health_trend(self, trend: DomainTrend) -> str:
        """Determine if health is improving, stable, or declining."""
        declining_signals = 0
        if trend.quality_trend == "degrading":
            declining_signals += 1
        if trend.fetch_latency_trend == "degrading":
            declining_signals += 1
        if trend.anti_bot_trend == "degrading":
            declining_signals += 1
        if trend.selector_decay_accelerating:
            declining_signals += 1

        improving_signals = 0
        if trend.quality_trend == "improving":
            improving_signals += 1
        if trend.fetch_latency_trend == "improving":
            improving_signals += 1

        if declining_signals >= 2:
            return "declining"
        if improving_signals >= 2:
            return "improving"
        return "stable"

    def _compute_systemic_risk(self, report: PredictionReport) -> str:
        """Compute overall systemic risk level."""
        if report.critical_risk_count >= 3 or report.high_risk_count >= 5:
            return "critical"
        if report.critical_risk_count >= 1 or report.high_risk_count >= 3:
            return "high"
        if report.high_risk_count >= 1 or report.medium_risk_count >= 5:
            return "medium"
        return "low"


# ═══════════════════════════════════════════════════════════════════════
# Prediction Engine Singleton
# ═══════════════════════════════════════════════════════════════════════

_predictor: DegradationPredictor | None = None
_predictor_lock = threading.Lock()


def get_degradation_predictor() -> DegradationPredictor:
    """Get the global degradation predictor singleton."""
    global _predictor
    if _predictor is None:
        with _predictor_lock:
            if _predictor is None:
                _predictor = DegradationPredictor()
    return _predictor
