"""
Self-Tuning Extraction — Automatically adjusts extraction parameters based on runtime telemetry.

Provides:
  - Dynamic timeout adjustment based on observed fetch times
  - Adaptive pacing (delay between requests) based on rate-limit signals
  - Retry policy optimization based on failure patterns
  - Confidence threshold tuning based on extraction quality
  - Resource budget management (browser, LLM, bandwidth)

Architecture:
  - Reads per-domain telemetry from scrape_telemetry
  - Adjusts parameters using a heuristic controller (PID-like)
  - Parameters are stored in a runtime-overridable config
  - Changes are logged and reported for observability

LAW: Optimal extraction parameters are domain-specific and time-varying.
The system must self-tune without human intervention.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TuningParameters:
    """Current tuning parameters for a domain."""

    domain: str
    fetch_timeout_s: float = 30.0  # Dynamic fetch timeout
    delay_between_requests_s: float = 1.0  # Adaptive pacing delay
    max_retries: int = 2  # Optimal retry count
    min_confidence_threshold: float = 0.35  # Dynamic quality gate

    # Internal state
    last_adjusted: float = 0.0
    adjustment_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TuningTelemetry:
    """Observed metrics used for tuning decisions."""

    avg_fetch_time_ms: float = 0.0
    success_rate: float = 1.0
    rate_limit_hits: int = 0
    anti_bot_score: float = 0.0
    avg_quality_score: float = 0.5
    sample_count: int = 0


class SelfTuningController:
    """Heuristic controller that adjusts extraction parameters.

    Uses a simple PID-like approach:
      - **Proportional**: Direct response to current error (deviation from target)
      - **Integral**: Accumulated error over time (persistent issues)
      - **Derivative**: Rate of change (rapidly worsening conditions)

    Instead of actual PID math, we use domain-specific heuristics that
    are easier to tune and more interpretable.
    """

    def __init__(self) -> None:
        self._parameters: Dict[str, TuningParameters] = {}
        self._telemetry: Dict[str, List[TuningTelemetry]] = {}

        # Tuning bounds
        self._min_timeout = 10.0
        self._max_timeout = 90.0
        self._min_delay = 0.5
        self._max_delay = 10.0
        self._min_retries = 0
        self._max_retries = 5
        self._min_confidence = 0.1
        self._max_confidence = 0.8

    def _get_or_create_params(self, domain: str) -> TuningParameters:
        if domain not in self._parameters:
            self._parameters[domain] = TuningParameters(
                domain=domain,
                fetch_timeout_s=settings.PLAYWRIGHT_TIMEOUT / 1000.0,
                delay_between_requests_s=settings.CRAWL_DEFAULT_DELAY_SECONDS,
                max_retries=settings.MAX_RETRIES,
                min_confidence_threshold=settings.DEFAULT_MIN_RECORD_SCORE,
            )
        return self._parameters[domain]

    def record_telemetry(self, domain: str, telemetry: dict) -> None:
        """Record a telemetry snapshot for tuning.

        Args:
            domain: The domain the telemetry is for
            telemetry: ScrapeTelemetry dict
        """
        if domain not in self._telemetry:
            self._telemetry[domain] = []

        t = TuningTelemetry(
            avg_fetch_time_ms=telemetry.get("fetch_ms", 0.0),
            success_rate=1.0 if not telemetry.get("error") else 0.0,
            rate_limit_hits=1 if telemetry.get("failure_category") == "rate_limited" else 0,
            anti_bot_score=telemetry.get("anti_bot_score", 0.0),
            avg_quality_score=telemetry.get("confidence_map", {}).get("overall_avg", 0.5),
        )

        self._telemetry[domain].append(t)
        # Keep last 50 observations
        if len(self._telemetry[domain]) > 50:
            self._telemetry[domain] = self._telemetry[domain][-50:]

        # Re-tune after every observation
        self._tune(domain)

    def _tune(self, domain: str) -> None:
        """Adjust tuning parameters based on recent telemetry.

        Adjusts:
          1. **Fetch timeout**: Based on observed fetch times + margin
          2. **Delay between requests**: Based on rate-limit hits and anti-bot score
          3. **Max retries**: Based on success rate
          4. **Confidence threshold**: Based on extraction quality distribution
        """
        params = self._get_or_create_params(domain)
        history = self._telemetry.get(domain, [])

        if len(history) < 3:
            return  # Need minimum samples

        recent = history[-10:]  # Last 10 observations

        # ── 1. Fetch timeout tuning ────────────────────────────────────
        fetch_times = [t.avg_fetch_time_ms for t in recent if t.avg_fetch_time_ms > 0]
        if fetch_times:
            avg_fetch = mean(fetch_times)
            # Timeout = 2x average fetch time + 5s safety margin
            new_timeout = min(self._max_timeout, max(self._min_timeout, (avg_fetch / 1000.0) * 2.0 + 5.0))
            params.fetch_timeout_s = round(new_timeout, 1)

        # ── 2. Adaptive pacing ─────────────────────────────────────────
        rate_limit_hits = sum(t.rate_limit_hits for t in recent)
        avg_anti_bot = mean(t.anti_bot_score for t in recent)

        # Increase delay if rate limited or anti-bot detected
        base_delay = settings.CRAWL_DEFAULT_DELAY_SECONDS
        delay_multiplier = 1.0

        if rate_limit_hits > 0:
            delay_multiplier += rate_limit_hits * 0.5  # +0.5s per hit
        if avg_anti_bot > 0.5:
            delay_multiplier += (avg_anti_bot - 0.5) * 2.0  # +1s per 0.5 above 0.5
        if avg_anti_bot > 0.8:
            delay_multiplier += 2.0  # Heavy anti-bot = extra delay

        new_delay = min(self._max_delay, max(self._min_delay, base_delay * delay_multiplier))
        params.delay_between_requests_s = round(new_delay, 1)

        # ── 3. Retry optimization ──────────────────────────────────────
        recent_successes = sum(1 for t in recent if t.success_rate > 0)
        recent_total = len(recent)
        success_rate = recent_successes / max(1, recent_total)

        if success_rate < 0.3:
            params.max_retries = min(self._max_retries, params.max_retries + 1)
        elif success_rate > 0.8 and params.max_retries > self._min_retries:
            params.max_retries = max(self._min_retries, params.max_retries - 1)

        # ── 4. Confidence threshold tuning ─────────────────────────────
        quality_scores = [t.avg_quality_score for t in recent if t.avg_quality_score > 0]
        if quality_scores and len(quality_scores) >= 3:
            avg_quality = mean(quality_scores)
            # If quality is consistently high, raise the bar; if low, lower it
            if avg_quality > 0.7:
                params.min_confidence_threshold = min(self._max_confidence, params.min_confidence_threshold + 0.02)
            elif avg_quality < 0.3:
                params.min_confidence_threshold = max(self._min_confidence, params.min_confidence_threshold - 0.02)

        params.last_adjusted = time.time()
        params.adjustment_count += 1

        logger.debug(
            "Tuned parameters for %s: timeout=%.1fs delay=%.1fs retries=%d threshold=%.2f",
            domain,
            params.fetch_timeout_s,
            params.delay_between_requests_s,
            params.max_retries,
            params.min_confidence_threshold,
        )

    def get_parameters(self, domain: str) -> TuningParameters:
        """Get current tuning parameters for a domain."""
        return self._get_or_create_params(domain)

    def get_tuning_report(self) -> dict:
        """Get comprehensive tuning report for all domains."""
        domains = list(self._parameters.keys())

        return {
            "total_domains_tuned": len(domains),
            "total_adjustments": sum(p.adjustment_count for p in self._parameters.values()),
            "domains": [p.to_dict() for p in self._parameters.values()],
            "averages": {
                "avg_timeout_s": (
                    round(mean(p.fetch_timeout_s for p in self._parameters.values()), 1) if self._parameters else 0.0
                ),
                "avg_delay_s": (
                    round(mean(p.delay_between_requests_s for p in self._parameters.values()), 1)
                    if self._parameters
                    else 0.0
                ),
                "avg_retries": (
                    round(mean(p.max_retries for p in self._parameters.values()), 1) if self._parameters else 0.0
                ),
                "avg_confidence_threshold": (
                    round(mean(p.min_confidence_threshold for p in self._parameters.values()), 3)
                    if self._parameters
                    else 0.0
                ),
            },
        }

    def get_domain_report(self, domain: str) -> Optional[dict]:
        """Get tuning report for a specific domain."""
        params = self._parameters.get(domain)
        if not params:
            return None
        return params.to_dict()


# Global singleton
_tuning_controller: SelfTuningController | None = None


def get_self_tuning_controller() -> SelfTuningController:
    """Get the global self-tuning controller."""
    global _tuning_controller
    if _tuning_controller is None:
        _tuning_controller = SelfTuningController()
    return _tuning_controller
