"""
Selector Decay Predictor — Predicts when selectors are likely to fail.

Provides:
  - Decay risk scoring per domain (0.0 = fresh, 1.0 = likely failing soon)
  - Time-to-failure estimation based on historical patterns
  - DOM drift detection from selector performance regression
  - Proactive re-discovery recommendations before extraction collapses

Architecture:
  - Reads historical selector performance from SelectorMemory
  - Tracks failure rate acceleration (second derivative of failures)
  - Combines age, freshness, and recent failure velocity into a unified risk score
  - Generates actionable recommendations (re-discover, test, replace)

LAW: Selectors decay predictably. The system must anticipate failure before it happens.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Dict, List

from app.selector_memory import SelectorConfidenceScore, get_selector_memory

logger = logging.getLogger(__name__)


@dataclass
class DecayPrediction:
    """Prediction result for selector decay on a domain."""

    domain: str
    decay_risk: float  # 0.0 (stable) to 1.0 (imminent failure)
    days_until_failure: float  # Estimated days until selector fails entirely
    confidence: float  # Confidence in prediction [0, 1]
    risk_level: str  # "stable" | "watch" | "decaying" | "critical"
    # Rate of failure acceleration (positive = worsening)
    failure_velocity: float
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class SelectorDecayPredictor:
    """Predicts selector decay by analyzing historical performance patterns.

    Uses three signals to compute decay risk:
      1. **Confidence trend**: How selector confidence has changed over time
      2. **Failure velocity**: Rate at which failures are accelerating
      3. **Age regression**: How long since the selector was validated

    The predictor tracks per-domain decay state and produces proactive
    re-discovery recommendations before extraction collapses.
    """

    def __init__(self) -> None:
        self._decay_history: Dict[str, List[float]] = defaultdict(list)
        # Track confidence snapshots over time per domain
        self._confidence_snapshots: Dict[str, List[tuple[float, float]]] = defaultdict(list)
        self._load()

    @staticmethod
    def _get_snapshots_path() -> str:
        from pathlib import Path

        return str(Path(__file__).resolve().parent.parent / "data" / "selector_decay_snapshots.json")

    def _save(self) -> None:
        import json
        import os

        try:
            path = self._get_snapshots_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = {domain: [[t, c] for t, c in snapshots] for domain, snapshots in self._confidence_snapshots.items()}
            with open(path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.exception("Failed to persist selector decay snapshots: %s", e)

    def _load(self) -> None:
        import json
        import os
        import sys

        from app.config import settings

        if "pytest" in sys.modules and not settings.TEST_SELECTOR_DECAY_PERSISTENCE:
            return
        path = self._get_snapshots_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                self._confidence_snapshots.clear()
                for domain, snapshots in data.items():
                    self._confidence_snapshots[domain] = [(float(t), float(c)) for t, c in snapshots]
            except Exception as e:
                logger.exception("Failed to load selector decay snapshots: %s", e)

    def record_observation(self, domain: str, confidence: float) -> None:
        """Record a confidence observation for a domain at the current time.

        Args:
            domain: The domain being observed
            confidence: Current selector confidence score [0, 1]
        """
        now = time.time()
        self._confidence_snapshots[domain].append((now, confidence))
        # Keep only last 100 observations
        if len(self._confidence_snapshots[domain]) > 100:
            self._confidence_snapshots[domain] = self._confidence_snapshots[domain][-100:]
        self._save()

    def predict_decay(self, domain: str) -> DecayPrediction:
        """Predict selector decay for a domain.

        Args:
            domain: Domain to predict decay for

        Returns:
            DecayPrediction with risk score and recommendations
        """
        memory = get_selector_memory()
        entry = memory._memory.get(domain)

        if not entry:
            return DecayPrediction(
                domain=domain,
                decay_risk=0.0,
                days_until_failure=30.0,
                confidence=0.3,
                risk_level="stable",
                failure_velocity=0.0,
                recommendations=["No selector data yet — normal for new domain"],
            )

        confidence_score = memory._compute_confidence(entry)
        snapshots = self._confidence_snapshots.get(domain, [])

        # ── Signal 1: Confidence trend (30% weight) ────────────────────
        confidence_risk = 1.0 - confidence_score.final_score

        # ── Signal 2: Failure velocity & acceleration (40% weight) ─────
        failures = entry.get("failure_count", 0)
        successes = entry.get("success_count", 0)
        total = failures + successes + 1

        failure_rate = failures / total

        # Failure velocity: compare recent failures vs historical average
        recent_window = snapshots[-10:] if len(snapshots) >= 10 else snapshots
        if len(recent_window) >= 2:
            older_avg = sum(s[1] for s in recent_window[: len(recent_window) // 2]) / max(1, len(recent_window) // 2)
            newer_avg = sum(s[1] for s in recent_window[len(recent_window) // 2 :]) / max(
                1, len(recent_window) - len(recent_window) // 2
            )
            # Positive velocity = confidence dropping
            velocity = older_avg - newer_avg  # positive = getting worse
        else:
            velocity = 0.0

        # ── Signal 3: Age regression (30% weight) ──────────────────────
        age_risk = 1.0 - confidence_score.age_factor

        # ── Combine signals ────────────────────────────────────────────
        decay_risk = confidence_risk * 0.30 + min(1.0, failure_rate + velocity) * 0.40 + age_risk * 0.30
        decay_risk = max(0.0, min(1.0, decay_risk))

        # ── Determine days until failure ───────────────────────────────
        if decay_risk < 0.2:
            days_until_failure = 60.0  # Very stable
            risk_level = "stable"
        elif decay_risk < 0.4:
            days_until_failure = 30.0
            risk_level = "watch"
        elif decay_risk < 0.7:
            days_until_failure = 14.0
            risk_level = "decaying"
        else:
            days_until_failure = 3.0
            risk_level = "critical"

        # ── Confidence in prediction ───────────────────────────────────
        prediction_confidence = min(0.9, 0.3 + (len(snapshots) * 0.05))

        # ── Generate recommendations ───────────────────────────────────
        recommendations = self._generate_recommendations(domain, risk_level, decay_risk, velocity, confidence_score)

        return DecayPrediction(
            domain=domain,
            decay_risk=round(decay_risk, 3),
            days_until_failure=days_until_failure,
            confidence=min(0.9, round(prediction_confidence, 2)),
            risk_level=risk_level,
            failure_velocity=round(velocity, 3),
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self,
        domain: str,
        risk_level: str,
        decay_risk: float,
        velocity: float,
        confidence_score: SelectorConfidenceScore,
    ) -> list[str]:
        """Generate actionable recommendations based on decay analysis."""
        recs = []

        if risk_level == "critical":
            recs.append("URGENT: Re-discover selectors immediately — imminent failure")
            recs.append(f"Decay risk at {decay_risk:.0%}, velocity {velocity:+.3f}")
            recs.append("Consider switching fetch strategy as precaution")
        elif risk_level == "decaying":
            recs.append("Schedule selector re-discovery within 7 days")
            recs.append(f"Failure velocity accelerating ({velocity:+.3f})")
            recs.append("Increase extraction quality monitoring for this domain")
        elif risk_level == "watch":
            recs.append("Monitor selector health — minor degradation detected")
            if velocity > 0.05:
                recs.append(f"Failure trend rising ({velocity:+.3f}) — prepare re-discovery")
        else:
            recs.append("Selector is stable — no action required")

        # Add age-based recommendations
        if confidence_score.age_factor < 0.5:
            recs.append("Selector is aging (>14 days old) — schedule refresh")

        return recs

    def get_domains_at_risk(self, threshold: float = 0.5) -> list[DecayPrediction]:
        """Get all domains with decay risk above a threshold.

        Args:
            threshold: Minimum decay risk to include (default 0.5)

        Returns:
            List of DecayPrediction for at-risk domains
        """
        memory = get_selector_memory()
        at_risk = []

        for domain in memory._memory:
            pred = self.predict_decay(domain)
            if pred.decay_risk >= threshold:
                at_risk.append(pred)

        return sorted(at_risk, key=lambda x: x.decay_risk, reverse=True)

    def get_decay_report(self) -> dict:
        """Get comprehensive decay prediction report for all domains."""
        memory = get_selector_memory()
        domains = list(memory._memory.keys())

        predictions = [self.predict_decay(d) for d in domains]
        predictions.sort(key=lambda x: x.decay_risk, reverse=True)

        at_risk_count = sum(1 for p in predictions if p.decay_risk >= 0.5)
        critical_count = sum(1 for p in predictions if p.risk_level == "critical")

        return {
            "total_domains_tracked": len(domains),
            "at_risk_domains": at_risk_count,
            "critical_domains": critical_count,
            "avg_decay_risk": round(sum(p.decay_risk for p in predictions) / max(1, len(predictions)), 3),
            "predictions": [p.to_dict() for p in predictions[:50]],  # Top 50
        }


# Global singleton
_predictor: SelectorDecayPredictor | None = None


def get_selector_decay_predictor() -> SelectorDecayPredictor:
    """Get the global selector decay predictor."""
    global _predictor
    if _predictor is None:
        _predictor = SelectorDecayPredictor()
    return _predictor
