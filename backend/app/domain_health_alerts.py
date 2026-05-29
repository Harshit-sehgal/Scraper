"""
Domain Health Degradation Alerts — Predictive alerts for domain failure patterns.

Provides:
  - Health scoring for each domain based on recent failure patterns
  - Trend analysis to detect degradation before critical failure
  - Alert generation when health drops below thresholds
  - Recommendation engine for preventive actions

Health Scoring:
  - Success Rate (0-1): percentage of successful scrapes
  - Consistency (0-1): variance in failures (high variance = unpredictable)
  - Recency Bias: Recent failures weighted more than old ones
  - Degradation Trend: Slope of failure rate (positive = worsening)

Alerts:
  - YELLOW: Health dropped below 0.7, trend is negative
  - RED: Health below 0.5, multiple recent failures
  - CRITICAL: Domain blacklisted (>90% failure rate)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Optional
from collections import deque
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DomainHealthLevel(str, Enum):
    """Domain health alert levels."""
    HEALTHY = "healthy"  # score >= 0.8
    DEGRADING = "degrading"  # 0.7 <= score < 0.8, negative trend
    UNHEALTHY = "unhealthy"  # 0.5 <= score < 0.7
    CRITICAL = "critical"  # score < 0.5, multiple recent failures
    BLACKLISTED = "blacklisted"  # > 90% failure rate over time window


@dataclass
class DomainHealthAlert:
    """Alert for domain health status change."""

    domain: str
    level: DomainHealthLevel
    score: float  # 0.0 (worst) to 1.0 (best)
    failure_count: int  # Recent failures
    success_count: int  # Recent successes
    degradation_trend: float  # Slope of failure rate (-1 to +1)
    avg_failure_rate: float  # Average failure rate over time window
    recommendations: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["level"] = self.level.value
        return result


@dataclass
class DomainHealthMetrics:
    """Metrics for domain health calculation."""

    domain: str
    success_count: int = 0
    failure_count: int = 0
    last_success_time: float = 0.0
    last_failure_time: float = 0.0
    last_failure_category: Optional[str] = None

    # Time-series data for trend analysis
    recent_attempts: deque = field(default_factory=lambda: deque(maxlen=50))  # Last 50 attempts
    hourly_stats: dict[int, dict] = field(default_factory=dict)  # Per-hour failure rates

    def get_success_rate(self) -> float:
        """Get recent success rate."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0  # New domain, assume healthy
        return self.success_count / total

    def get_consistency_score(self) -> float:
        """Get consistency score (low variance = high score).

        Analyzes recent attempts to detect if failures are clustered
        or spread out over time.
        """
        if len(self.recent_attempts) < 3:
            return 1.0  # Not enough data

        # Convert to binary (1=success, 0=failure)
        values = [1.0 if a["success"] else 0.0 for a in self.recent_attempts]

        # Calculate variance (high variance = failures clustered)
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)

        # Convert variance to consistency score (inverse relationship)
        # Max variance is 0.25 (50% success rate with equal distribution)
        consistency = 1.0 - min(1.0, variance / 0.25)
        return consistency

    def get_degradation_trend(self) -> float:
        """Get trend slope (-1 to +1).

        Negative = improving, Positive = degrading.
        """
        if len(self.recent_attempts) < 5:
            return 0.0  # Not enough data

        # Simple linear regression on failure rate
        attempts_list = list(self.recent_attempts)
        failures = [0.0 if a["success"] else 1.0 for a in attempts_list]

        # Calculate trend using simple slope
        n = len(failures)
        x_mean = (n - 1) / 2  # Indices 0 to n-1
        y_mean = sum(failures) / n

        numerator = sum((i - x_mean) * (f - y_mean) for i, f in enumerate(failures))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        slope = numerator / denominator
        return max(-1.0, min(1.0, slope))  # Clamp to [-1, 1]


class DomainHealthMonitor:
    """Monitor and alert on domain health degradation."""

    def __init__(self, alert_callback=None):
        """Initialize health monitor.

        Args:
            alert_callback: Optional async callable to handle alerts
        """
        self._domains: dict[str, DomainHealthMetrics] = {}
        self._last_alert_time: dict[str, float] = {}  # Avoid alert spam
        self._alert_cooldown_seconds = 300  # Min 5 minutes between alerts per domain
        self.alert_callback = alert_callback

    def record_attempt(self, url: str, success: bool, failure_category: Optional[str] = None):
        """Record a scrape attempt for a domain.

        Args:
            url: The URL that was scraped
            success: Whether the attempt succeeded
            failure_category: Category of failure (if success=False)
        """
        domain = self._extract_domain(url)
        if not domain:
            return

        now = time.time()
        metrics = self._domains.setdefault(domain, DomainHealthMetrics(domain=domain))

        # Update counts
        if success:
            metrics.success_count += 1
            metrics.last_success_time = now
        else:
            metrics.failure_count += 1
            metrics.last_failure_time = now
            metrics.last_failure_category = failure_category

        # Record in time series
        metrics.recent_attempts.append({
            "timestamp": now,
            "success": success,
            "category": failure_category,
        })

        # Update hourly stats
        hour_key = int(now) // 3600
        if hour_key not in metrics.hourly_stats:
            metrics.hourly_stats[hour_key] = {"success": 0, "failure": 0}

        if success:
            metrics.hourly_stats[hour_key]["success"] += 1
        else:
            metrics.hourly_stats[hour_key]["failure"] += 1

        # Check if we should alert
        self._check_and_alert(domain, metrics)

    def _check_and_alert(self, domain: str, metrics: DomainHealthMetrics):
        """Check if health alert should be triggered."""
        now = time.time()

        # Avoid alert spam
        last_alert = self._last_alert_time.get(domain, 0)
        if (now - last_alert) < self._alert_cooldown_seconds:
            return

        # Calculate health score
        score = self._calculate_health_score(metrics)
        level = self._determine_health_level(score, metrics)

        # Only alert if status changed or is critical
        # For now, always generate alert (caller can decide what to do)
        recommendations = self._generate_recommendations(level, metrics, score)

        alert = DomainHealthAlert(
            domain=domain,
            level=level,
            score=score,
            failure_count=metrics.failure_count,
            success_count=metrics.success_count,
            degradation_trend=metrics.get_degradation_trend(),
            avg_failure_rate=1.0 - metrics.get_success_rate(),
            recommendations=recommendations,
        )

        logger.info(
            "Domain health alert for %s: %s (score=%.2f, trend=%.2f)",
            domain, level.value, score, metrics.get_degradation_trend()
        )

        # Call alert callback if registered
        if self.alert_callback:
            import asyncio
            try:
                asyncio.create_task(self.alert_callback(alert))
            except Exception as e:
                logger.error("Alert callback failed: %s", e)

        self._last_alert_time[domain] = now

    def _calculate_health_score(self, metrics: DomainHealthMetrics) -> float:
        """Calculate overall domain health score [0, 1].

        Factors:
          - Success rate (50% weight)
          - Consistency (30% weight)
          - Recency (20% weight)
        """
        success_rate = metrics.get_success_rate()
        consistency = metrics.get_consistency_score()

        # Recency factor: penalize if many recent failures
        recent_window = list(metrics.recent_attempts)[-10:] if metrics.recent_attempts else []
        if recent_window:
            recent_failures = sum(1 for a in recent_window if not a["success"])
            recency_factor = 1.0 - (recent_failures / len(recent_window))
        else:
            recency_factor = 1.0

        # Weighted average
        health_score = (
            success_rate * 0.5 +
            consistency * 0.3 +
            recency_factor * 0.2
        )

        return health_score

    def _determine_health_level(self, score: float, metrics: DomainHealthMetrics) -> DomainHealthLevel:
        """Determine health level based on score and metrics."""
        success_rate = metrics.get_success_rate()

        # Critical: extreme failure rate
        if success_rate < 0.1:  # >90% failure rate
            return DomainHealthLevel.BLACKLISTED

        # Unhealthy/Critical: very low score with recent failures
        if score < 0.5:
            recent_failures = sum(1 for a in list(metrics.recent_attempts)[-10:] if not a["success"])
            if recent_failures >= 7:  # 7+ failures in last 10 attempts
                return DomainHealthLevel.CRITICAL
            return DomainHealthLevel.UNHEALTHY

        # Degrading: score dropping with negative trend
        if 0.7 <= score < 0.8:
            trend = metrics.get_degradation_trend()
            if trend > 0.1:  # Significant negative trend
                return DomainHealthLevel.DEGRADING

        # Healthy
        return DomainHealthLevel.HEALTHY

    def _generate_recommendations(
        self,
        level: DomainHealthLevel,
        metrics: DomainHealthMetrics,
        score: float,
    ) -> list[str]:
        """Generate actionable recommendations based on health status."""
        recommendations = []

        if level == DomainHealthLevel.BLACKLISTED:
            recommendations.append("Consider blacklisting this domain temporarily")
            recommendations.append("Investigate root cause of sustained failures")
            return recommendations

        if level == DomainHealthLevel.CRITICAL:
            recommendations.append("Increase backoff delays for this domain")
            recommendations.append("Rotate proxy pools more frequently")
            recommendations.append("Consider reducing concurrency")
            if metrics.last_failure_category == "anti_bot_block":
                recommendations.append("Anti-bot detected; use proxy rotation urgently")
            return recommendations

        if level == DomainHealthLevel.UNHEALTHY:
            recommendations.append("Monitor domain closely")
            recommendations.append("Increase timeout values")
            recommendations.append("Enable verbose logging for debugging")
            return recommendations

        if level == DomainHealthLevel.DEGRADING:
            trend = metrics.get_degradation_trend()
            recommendations.append(f"Failure rate trending negative (slope={trend:.2f})")
            recommendations.append("Proactively increase delays before critical failures")
            recommendations.append("Re-validate selectors for this domain")
            return recommendations

        return recommendations

    def get_domain_health(self, url: str) -> Optional[dict]:
        """Get current health status for a domain.

        Returns:
            Dictionary with health metrics or None if domain not found
        """
        domain = self._extract_domain(url)
        if not domain:
            return None

        metrics = self._domains.get(domain)
        if not metrics:
            return None

        score = self._calculate_health_score(metrics)
        level = self._determine_health_level(score, metrics)

        return {
            "domain": domain,
            "health_level": level.value,
            "health_score": score,
            "success_rate": metrics.get_success_rate(),
            "consistency_score": metrics.get_consistency_score(),
            "degradation_trend": metrics.get_degradation_trend(),
            "total_attempts": metrics.success_count + metrics.failure_count,
            "recent_failure_category": metrics.last_failure_category,
        }

    def get_all_domains_health(self) -> list[dict]:
        """Get health status for all monitored domains."""
        health_statuses = []
        for domain in self._domains:
            health = {
                "domain": domain,
                "health_level": self._determine_health_level(
                    self._calculate_health_score(self._domains[domain]),
                    self._domains[domain]
                ).value,
                "health_score": self._calculate_health_score(self._domains[domain]),
            }
            health_statuses.append(health)
        return sorted(health_statuses, key=lambda x: x["health_score"])

    @staticmethod
    def _extract_domain(url: str) -> Optional[str]:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() or None
        except Exception:
            return None


# Global singleton
_monitor: DomainHealthMonitor | None = None


def get_domain_health_monitor() -> DomainHealthMonitor:
    """Get the global domain health monitor."""
    global _monitor
    if _monitor is None:
        _monitor = DomainHealthMonitor()
    return _monitor
