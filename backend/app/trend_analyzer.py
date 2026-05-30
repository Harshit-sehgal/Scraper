"""
Trend Analyzer — Telemetry intelligence that detects degradation patterns.

Analyses accumulated scrape telemetry to identify:
  - Degrading domains (increasing failures, decreasing quality)
  - Selector decay acceleration
  - Anti-bot intensification over time
  - Latency creep (fetch time inflation)
  - Cost trends per domain
  - Overall extraction health trajectory

Provides proactive alerts so the operator knows which domains are
deteriorating before extraction actually collapses.

LAW: Telemetry without interpretation is noise. Every metric must be
trended, compared, and acted upon.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class DomainTrend:
    """Trend metrics for a single domain over a rolling window."""

    domain: str = ""
    total_scrapes: int = 0
    total_failures: int = 0
    failure_rate: float = 0.0
    """Fraction of scrapes that failed or produced zero records."""

    avg_fetch_ms: float = 0.0
    """Rolling average fetch latency."""

    fetch_latency_trend: str = "stable"
    """'improving' | 'stable' | 'degrading' based on slope over window."""

    avg_quality_score: float = 0.0
    """Rolling average of selector_hit_rate or confidence."""

    quality_trend: str = "stable"
    """'improving' | 'stable' | 'degrading'."""

    anti_bot_trend: str = "stable"
    """Whether anti-bot pressure is increasing on this domain."""

    avg_cost_usd: float = 0.0
    """Average estimated cost per scrape for this domain."""

    top_failure_categories: list[dict] = field(default_factory=list)
    """[(category, count), ...] for the most common failure types."""

    selector_decay_accelerating: bool = False
    """Whether the selector decay rate is increasing (bad sign)."""

    health_score: float = 100.0
    """0 - 100 composite health score. Lower = worse."""

    sample_count: int = 0
    """Number of telemetry events contributing to this trend."""


@dataclass
class TrendReport:
    """Overall trend report for the extraction system."""

    generated_at: float = field(default_factory=time.time)
    domain_count: int = 0
    degrading_domains: list[str] = field(default_factory=list)
    """Domains whose health is actively declining."""

    improving_domains: list[str] = field(default_factory=list)
    stable_domains: list[str] = field(default_factory=list)
    unseen_domains: list[str] = field(default_factory=list)

    global_failure_rate: float = 0.0
    global_avg_latency_ms: float = 0.0
    global_avg_cost_usd: float = 0.0
    total_cost_estimated: float = 0.0
    total_scrapes: int = 0

    alerts: list[dict] = field(default_factory=list)
    """Actionable alerts sorted by severity."""

    domain_trends: dict[str, DomainTrend] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
# Trend Analyzer
# ═══════════════════════════════════════════════════════════════════════


class TrendAnalyzer:
    """Analyzes accumulated scrape telemetry to detect meaningful patterns.

    Operates on the ScrapeTelemetryCollector's history buffer. Designed
    to be called periodically (e.g., every N scrapes or on demand via API).
    """

    def __init__(self, history_window: int = 100):
        """
        Args:
            history_window: Number of most recent telemetry events to analyze.
        """
        self._history_window = history_window

    def analyze(self, telemetry_history: list[dict]) -> TrendReport:
        """Run full trend analysis on the provided telemetry history.

        Args:
            telemetry_history: List of ScrapeTelemetry dicts, most recent last.

        Returns:
            A TrendReport with domain trends, global metrics, and alerts.
        """
        if not telemetry_history:
            return TrendReport()

        report = TrendReport()
        report.total_scrapes = len(telemetry_history)

        # Group telemetry by domain
        domain_events: dict[str, list[dict]] = defaultdict(list)
        for event in telemetry_history:
            url = event.get("url", "")
            domain = self.extract_domain(url)
            domain_events[domain].append(event)

        report.domain_count = len(domain_events)

        global_failure_count = 0
        global_latencies: list[float] = []
        global_costs: list[float] = []

        # Analyze each domain
        for domain, events in domain_events.items():
            trend = self.analyze_domain(domain, events)
            report.domain_trends[domain] = trend

            # Track global aggregates
            global_failure_count += trend.total_failures
            global_latencies.append(trend.avg_fetch_ms)
            global_costs.append(trend.avg_cost_usd)

            # Categorize domain trajectory
            if trend.health_score < 40:
                report.degrading_domains.append(domain)
            elif trend.health_score >= 80 and trend.sample_count >= 3:
                report.improving_domains.append(domain)
            elif trend.sample_count >= 2:
                report.stable_domains.append(domain)
            else:
                report.unseen_domains.append(domain)

        # Global aggregates
        n_domains = max(len(global_latencies), 1)
        report.global_failure_rate = global_failure_count / max(report.total_scrapes, 1)
        report.global_avg_latency_ms = sum(global_latencies) / n_domains if global_latencies else 0.0
        report.global_avg_cost_usd = sum(global_costs) / n_domains if global_costs else 0.0
        report.total_cost_estimated = sum(global_costs)

        # Generate alerts for degrading domains
        for domain in report.degrading_domains:
            trend = report.domain_trends[domain]
            report.alerts.append(
                {
                    "severity": "high",
                    "domain": domain,
                    "message": (
                        f"Domain {domain} health score is {trend.health_score:.0f}/100 "
                        f"(failure rate: {trend.failure_rate:.0%}, "
                        f"quality trend: {trend.quality_trend})"
                    ),
                    "health_score": trend.health_score,
                    "failure_rate": trend.failure_rate,
                }
            )

        # Alerts for accelerating selector decay
        for domain, trend in report.domain_trends.items():
            if trend.selector_decay_accelerating and trend.sample_count >= 3:
                report.alerts.append(
                    {
                        "severity": "medium",
                        "domain": domain,
                        "message": (f"Selector decay accelerating on {domain} — " f"consider forced rediscovery"),
                        "health_score": trend.health_score,
                    }
                )

        # Alerts for anti-bot intensification
        for domain, trend in report.domain_trends.items():
            if trend.anti_bot_trend == "degrading" and trend.sample_count >= 3:
                report.alerts.append(
                    {
                        "severity": "medium",
                        "domain": domain,
                        "message": (
                            f"Anti-bot pressure increasing on {domain} — "
                            f"may need proxy rotation or reduced frequency"
                        ),
                        "health_score": trend.health_score,
                    }
                )

        # Sort alerts by severity (high first), then by health score ascending
        severity_order = {"high": 0, "medium": 1, "low": 2}
        report.alerts.sort(key=lambda a: (severity_order.get(a["severity"], 99), a.get("health_score", 100)))

        return report

    # ── Internal Analysis ─────────────────────────────────────────────

    def analyze_domain(self, domain: str, events: list[dict]) -> DomainTrend:
        """Analyze telemetry events for a single domain.

        This is a public method — callable directly for per-domain
        analysis without running the full multi-domain report.
        """
        trend = DomainTrend(domain=domain)
        trend.sample_count = len(events)

        # Basic counts
        failures = 0
        latencies: list[float] = []
        quality_scores: list[float] = []
        anti_bot_scores: list[float] = []
        costs: list[float] = []
        failure_categories: dict[str, int] = defaultdict(int)
        selector_decay_signals: list[int] = []

        for event in events:
            # Failure detection
            is_failure = event.get("error") is not None or event.get("records_final", 0) == 0
            if is_failure:
                failures += 1

            # Latency
            fetch_ms = event.get("fetch_ms", 0.0)
            if fetch_ms > 0:
                latencies.append(fetch_ms)

            # Quality (selector hit rate as proxy)
            quality = event.get("selector_hit_rate", 0.0)
            if quality > 0:
                quality_scores.append(quality)

            # Anti-bot score
            anti_bot = event.get("anti_bot_score", 0.0)
            anti_bot_scores.append(anti_bot)

            # Cost
            cost = event.get("estimated_cost_usd", 0.0)
            if cost > 0:
                costs.append(cost)

            # Failure categories
            fcat = event.get("failure_category")
            if fcat:
                failure_categories[fcat] += 1

            # Selector decay signals (fallback usage = potential decay)
            if event.get("fallback_triggered"):
                selector_decay_signals.append(1)
            else:
                selector_decay_signals.append(0)

        trend.total_scrapes = len(events)
        trend.total_failures = failures
        trend.failure_rate = failures / max(len(events), 1)

        # Latency stats
        if latencies:
            trend.avg_fetch_ms = sum(latencies) / len(latencies)
            # Trend detection: compare first half vs second half
            trend.fetch_latency_trend = self._detect_trend(latencies, higher_is_worse=True)

        # Quality stats
        if quality_scores:
            trend.avg_quality_score = sum(quality_scores) / len(quality_scores)
            trend.quality_trend = self._detect_trend(quality_scores, higher_is_worse=False)

        # Anti-bot trend
        if anti_bot_scores:
            trend.anti_bot_trend = self._detect_trend(anti_bot_scores, higher_is_worse=True)

        # Cost
        if costs:
            trend.avg_cost_usd = sum(costs) / len(costs)

        # Top failure categories
        sorted_categories = sorted(failure_categories.items(), key=lambda x: -x[1])[:5]
        trend.top_failure_categories = [{"category": cat, "count": count} for cat, count in sorted_categories]

        # Selector decay acceleration
        if len(selector_decay_signals) >= 4:
            half = len(selector_decay_signals) // 2
            recent_decay_rate = sum(selector_decay_signals[half:]) / max(half, 1)
            early_decay_rate = sum(selector_decay_signals[:half]) / max(half, 1)
            trend.selector_decay_accelerating = recent_decay_rate > early_decay_rate * 1.5

        # Composite health score (0 - 100)
        trend.health_score = self._compute_health_score(trend)

        return trend

    # ── Helpers ───────────────────────────────────────────────────────

    def _detect_trend(self, values: list[float], higher_is_worse: bool) -> str:
        """Detect whether a sequence of values is improving, stable, or degrading.

        Compares the mean of the first third to the mean of the last third.
        """
        if len(values) < 3:
            return "stable"

        third = max(len(values) // 3, 1)
        early = values[:third]
        late = values[-third:]

        early_mean = sum(early) / len(early)
        late_mean = sum(late) / len(late)

        if early_mean == 0:
            delta = late_mean
        else:
            delta = (late_mean - early_mean) / abs(early_mean)

        threshold = 0.15  # 15% change required to register as a trend

        if abs(delta) < threshold:
            return "stable"

        if higher_is_worse:
            # Higher values are bad (e.g., latency, anti-bot score)
            return "degrading" if delta > 0 else "improving"
        else:
            # Higher values are good (e.g., quality score)
            return "improving" if delta > 0 else "degrading"

    def _compute_health_score(self, trend: DomainTrend) -> float:
        """Compute a 0 - 100 health score from trend metrics.

        Factors:
          - Failure rate (heaviest penalty)
          - Quality trend
          - Anti-bot trend
          - Latency trend
          - Selector decay acceleration
        """
        score = 100.0

        # Failure rate penalty: 0% = 0 penalty, 100% = -60 points
        # A domain that fails 100% of the time should score very low.
        score -= min(60.0, trend.failure_rate * 60)

        # Quality trend adjustment
        if trend.quality_trend == "degrading":
            score -= 15
        elif trend.quality_trend == "improving":
            score += 5

        # Anti-bot penalty
        if trend.anti_bot_trend == "degrading":
            score -= 10

        # Latency penalty
        if trend.fetch_latency_trend == "degrading":
            score -= 5
        elif trend.fetch_latency_trend == "improving":
            score += 3

        # Selector decay acceleration
        if trend.selector_decay_accelerating:
            score -= 10

        # Low sample count penalty (not enough data to be confident)
        if trend.sample_count < 3:
            score -= 15
        elif trend.sample_count < 6:
            score -= 5

        # Consistent low quality (zero or near-zero selector hit rate)
        if trend.avg_quality_score < 0.1 and trend.sample_count >= 3:
            score -= 10

        return max(0.0, min(100.0, score))

    @staticmethod
    def extract_domain(url: str) -> str:
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() or "unknown"
        except Exception:
            return "unknown"


# ═══════════════════════════════════════════════════════════════════════
# Economic Tracker
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class DomainCostSummary:
    domain: str = ""
    total_scrapes: int = 0
    total_cost_usd: float = 0.0
    avg_cost_per_scrape: float = 0.0
    avg_cost_per_record: float = 0.0
    total_records: int = 0
    cost_breakdown: dict[str, float] = field(default_factory=dict)
    """Estimated costs by category: 'llm', 'browser', 'network'."""

    efficiency_rating: str = "unknown"
    """'excellent' | 'good' | 'fair' | 'poor' based on cost per record."""


@dataclass
class EconomicReport:
    generated_at: float = field(default_factory=time.time)
    total_cost_usd: float = 0.0
    total_scrapes: int = 0
    total_records: int = 0
    avg_cost_per_scrape: float = 0.0
    avg_cost_per_record: float = 0.0
    cost_by_domain: dict[str, DomainCostSummary] = field(default_factory=dict)
    cost_by_category: dict[str, float] = field(default_factory=dict)
    most_expensive_domains: list[dict] = field(default_factory=list)
    least_expensive_domains: list[dict] = field(default_factory=list)
    efficiency_rating: str = "unknown"


class EconomicTracker:
    """Tracks extraction costs and efficiency metrics.

    Costs are estimated based on:
      - LLM calls: ~$0.01 per call (average across providers)
      - Browser time: ~$0.005 per second (Playwright context cost)
      - Network: ~$0.001 per request (bandwidth + proxy)
    """

    LLM_COST_PER_CALL: float = 0.01
    BROWSER_COST_PER_SECOND: float = 0.005
    NETWORK_COST_PER_REQUEST: float = 0.001

    def analyze(self, telemetry_history: list[dict]) -> EconomicReport:
        """Generate a full economic report from telemetry history."""
        report = EconomicReport()
        report.total_scrapes = len(telemetry_history)

        domain_events: dict[str, list[dict]] = defaultdict(list)
        for event in telemetry_history:
            url = event.get("url", "")
            domain = TrendAnalyzer.extract_domain(url)
            domain_events[domain].append(event)

        total_cost = 0.0
        total_records = 0
        category_costs: dict[str, float] = defaultdict(float)

        for domain, events in domain_events.items():
            summary = self._analyze_domain_costs(domain, events)
            report.cost_by_domain[domain] = summary
            total_cost += summary.total_cost_usd
            total_records += summary.total_records

            for cat, cost in summary.cost_breakdown.items():
                category_costs[cat] += cost

        report.total_cost_usd = round(total_cost, 4)
        report.total_records = total_records

        if report.total_scrapes > 0:
            report.avg_cost_per_scrape = round(total_cost / report.total_scrapes, 4)

        if total_records > 0:
            report.avg_cost_per_record = round(total_cost / total_records, 4)
            report.efficiency_rating = self._rate_efficiency(report.avg_cost_per_record)

        report.cost_by_category = dict(category_costs)

        # Sort domains by cost
        sorted_domains = sorted(
            [{"domain": d, "total_cost": s.total_cost_usd} for d, s in report.cost_by_domain.items()],
            key=lambda x: -(x["total_cost"]),  # type: ignore
        )
        report.most_expensive_domains = sorted_domains[:5]
        report.least_expensive_domains = sorted_domains[-5:][::-1]

        return report

    def _analyze_domain_costs(self, domain: str, events: list[dict]) -> DomainCostSummary:
        """Analyze costs for a single domain."""
        summary = DomainCostSummary(domain=domain)
        summary.total_scrapes = len(events)

        total_cost = 0.0
        total_records = 0
        total_llm_cost = 0.0
        total_browser_cost = 0.0
        total_network_cost = 0.0

        for event in events:
            # Use estimated_cost_usd if available
            estimated = event.get("estimated_cost_usd", 0.0)
            if estimated > 0:
                total_cost += estimated
            else:
                # Estimate from components
                llm_calls = event.get("llm_calls_count", 0)
                fetch_ms = event.get("fetch_ms", 0.0)
                fetch_method = event.get("fetch_method", "httpx")

                llm_cost = llm_calls * self.LLM_COST_PER_CALL
                browser_seconds = fetch_ms / 1000.0 if fetch_method == "playwright" else 0.0
                browser_cost = browser_seconds * self.BROWSER_COST_PER_SECOND
                network_cost = self.NETWORK_COST_PER_REQUEST

                total_cost += llm_cost + browser_cost + network_cost
                total_llm_cost += llm_cost
                total_browser_cost += browser_cost
                total_network_cost += network_cost

            total_records += event.get("records_final", 0)

        summary.total_cost_usd = round(total_cost, 4)
        summary.total_records = total_records
        summary.avg_cost_per_scrape = round(total_cost / max(len(events), 1), 4)
        summary.avg_cost_per_record = round(total_cost / max(total_records, 1), 6)
        summary.cost_breakdown = {
            "llm": round(total_llm_cost, 4),
            "browser": round(total_browser_cost, 4),
            "network": round(total_network_cost, 4),
        }
        summary.efficiency_rating = self._rate_efficiency(summary.avg_cost_per_record)

        return summary

    @staticmethod
    def _rate_efficiency(cost_per_record: float) -> str:
        """Rate cost efficiency based on cost per record."""
        if cost_per_record <= 0.01:
            return "excellent"
        elif cost_per_record <= 0.03:
            return "good"
        elif cost_per_record <= 0.10:
            return "fair"
        else:
            return "poor"
