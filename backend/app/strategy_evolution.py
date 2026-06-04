"""Strategy Evolution Engine — adaptive selection of fetch strategies.

Provides:
  - Multiple fetch strategies (Playwright, httpx, JavaScript-based, etc.)
  - Per-domain strategy performance tracking
  - Automatic strategy selection based on domain characteristics
  - Strategy adjustments for persistent failures
  - Learning from successful / failed attempts

This system adjusts extraction strategies based on observed outcomes:
  - Starts with default strategy (Playwright)
  - Learns which strategies work best for each domain
  - Can switch strategies when performance degrades
  - Explores new strategy combinations when stuck
  - Optimizes for speed vs. compatibility trade-offs

LAW: Strategy is not fixed. Domains require different approaches.
Telemetry helps choose what works best per domain.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class FetchStrategy(StrEnum):
    """Available fetch strategies."""

    PLAYWRIGHT_FULL = "playwright_full"  # Full browser render
    # Minimal render, no media / fonts
    PLAYWRIGHT_LIGHTWEIGHT = "playwright_lightweight"
    PLAYWRIGHT_STEALTH = "playwright_stealth"  # Extra stealth evasion
    HTTPX_BASIC = "httpx_basic"  # Raw HTTP, no JS
    HTTPX_WITH_UA = "httpx_with_ua"  # HTTP with browser user agent
    HTTPX_SMART = "httpx_smart"  # HTTP with session / cookies simulation
    HYBRID = "hybrid"  # Try HTTPX first, fallback to Playwright
    CACHED = "cached"  # Use cached response from domain


@dataclass
class StrategyPerformance:
    """Performance metrics for a fetch strategy on a domain."""

    domain: str
    strategy: FetchStrategy
    success_count: int = 0
    failure_count: int = 0
    total_time_ms: float = 0.0  # Total time spent
    last_used: float = 0.0  # Timestamp
    avg_quality: float = 0.0  # Average extraction quality
    consecutive_failures: int = 0  # Current failure streak
    error_patterns: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def success_rate(self) -> float:
        """Success rate [0, 1]."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    @property
    def avg_time_ms(self) -> float:
        """Average time per attempt."""
        total = self.success_count + self.failure_count
        return self.total_time_ms / total if total > 0 else 0.0

    @property
    def is_healthy(self) -> bool:
        """Strategy is performing well."""
        return self.success_rate >= 0.8 and self.consecutive_failures == 0

    @property
    def is_degraded(self) -> bool:
        """Strategy performance is declining."""
        return self.success_rate < 0.6 or self.consecutive_failures >= 3

    def to_dict(self) -> dict:
        d = asdict(self)
        d["error_patterns"] = dict(self.error_patterns)
        return d


@dataclass
class StrategyRecommendation:
    """Recommendation for which strategy to use."""

    recommended_strategy: FetchStrategy
    alternatives: list[FetchStrategy]
    reason: str
    confidence: float  # 0 - 1: how confident in recommendation
    estimated_success_rate: float  # Expected success rate


class DomainStrategyState:
    """Tracks strategy performance per domain."""

    def __init__(self, domain: str) -> None:
        self.domain = domain
        self.strategies: dict[FetchStrategy, StrategyPerformance] = {}
        self.current_strategy: FetchStrategy = FetchStrategy.PLAYWRIGHT_FULL
        self.last_strategy_switch: float = 0.0
        self.strategy_switch_count: int = 0
        self.learned_from_failures: int = 0

        # Initialize all strategies
        for strategy in FetchStrategy:
            self.strategies[strategy] = StrategyPerformance(
                domain=domain,
                strategy=strategy,
            )

    def record_attempt(
        self,
        strategy: FetchStrategy,
        success: bool,
        time_ms: float,
        quality: float = 0.0,
        failure_reason: str | None = None,
    ) -> None:
        """Record a fetch attempt result."""
        perf = self.strategies[strategy]

        if success:
            perf.success_count += 1
            perf.consecutive_failures = 0
            # Exponential moving average for quality
            alpha = 0.3
            perf.avg_quality = (1 - alpha) * perf.avg_quality + alpha * quality
        else:
            perf.failure_count += 1
            perf.consecutive_failures += 1
            if failure_reason:
                perf.error_patterns[failure_reason] += 1

        perf.total_time_ms += time_ms
        perf.last_used = time.time()

    def get_best_strategy(self) -> FetchStrategy:
        """Get best performing strategy."""
        candidates = [s for s in self.strategies.values() if s.success_count > 0]

        if not candidates:
            # Fallback to safest strategy
            return FetchStrategy.PLAYWRIGHT_FULL

        # Score strategies: prioritize success rate and quality, then speed
        def score(perf: StrategyPerformance) -> float:
            success_score = perf.success_rate * 60
            quality_score = perf.avg_quality * 30
            # Prefer faster strategies (like HTTPX) if they work
            speed_bonus = 10 if perf.avg_time_ms < 2000 else 0

            # Penalize consecutive failures heavily
            stability_penalty = perf.consecutive_failures * 20

            return success_score + quality_score + speed_bonus - stability_penalty

        best = max(candidates, key=score)
        return best.strategy

    def get_worst_strategy(self) -> FetchStrategy:
        """Get worst performing strategy based on success rate."""
        candidates = [s for s in self.strategies.values() if s.success_count > 0]

        if not candidates:
            return FetchStrategy.PLAYWRIGHT_FULL

        # Lower score = worse strategy; reuse the same scoring as
        # get_best_strategy
        def score(perf: StrategyPerformance) -> float:
            success_score = perf.success_rate * 60
            quality_score = perf.avg_quality * 30
            stability_penalty = perf.consecutive_failures * 20
            return success_score + quality_score - stability_penalty

        worst = min(candidates, key=score)
        return worst.strategy


class StrategyEvolutionEngine:
    """Adjusts fetch strategies per domain based on observed outcomes."""

    def __init__(self) -> None:
        """Initialize strategy evolution engine."""
        self.domain_states: dict[str, DomainStrategyState] = {}

        # Evolution parameters
        self.min_samples_for_recommendation = 3
        self.exploration_probability = 0.15  # 15% chance to explore
        self.learning_enabled = True

    def _get_or_create_state(self, domain: str) -> DomainStrategyState:
        """Get or create state for a domain."""
        if domain not in self.domain_states:
            self.domain_states[domain] = DomainStrategyState(domain)
        return self.domain_states[domain]

    def record_fetch_attempt(
        self,
        domain: str,
        strategy: FetchStrategy | str,
        success: bool,
        time_ms: float,
        quality: float = 0.0,
        failure_reason: str | None = None,
    ) -> None:
        """Record a fetch strategy attempt."""
        # Convert string to enum if needed
        if isinstance(strategy, str):
            try:
                # Try exact match first
                strategy = FetchStrategy(strategy)
            except ValueError:
                # Map common strings to FetchStrategy
                s_lower = strategy.lower()
                if "playwright" in s_lower:
                    if "stealth" in s_lower:
                        strategy = FetchStrategy.PLAYWRIGHT_STEALTH
                    elif "light" in s_lower:
                        strategy = FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT
                    else:
                        strategy = FetchStrategy.PLAYWRIGHT_FULL
                elif "httpx" in s_lower:
                    if "ua" in s_lower:
                        strategy = FetchStrategy.HTTPX_WITH_UA
                    elif "smart" in s_lower:
                        strategy = FetchStrategy.HTTPX_SMART
                    else:
                        strategy = FetchStrategy.HTTPX_BASIC
                elif "hybrid" in s_lower:
                    strategy = FetchStrategy.HYBRID
                else:
                    strategy = FetchStrategy.PLAYWRIGHT_FULL

        state = self._get_or_create_state(domain)
        state.record_attempt(strategy, success, time_ms, quality, failure_reason)

    def recommend_strategy(self, domain: str) -> StrategyRecommendation:
        """Recommend a fetch strategy for a domain."""
        import random

        state = self._get_or_create_state(domain)

        total_attempts = sum(s.success_count + s.failure_count for s in state.strategies.values())

        if total_attempts < self.min_samples_for_recommendation:
            # Cold start: use dynamic evidence, not domain-name lists
            try:
                from app.domain_intelligence import get_domain_intelligence

                intel = get_domain_intelligence().get_intelligence(domain)

                from app.anti_bot_engine import get_anti_bot_engine

                anti_bot = get_anti_bot_engine()

                if intel.anti_bot_risk > 0.6 or anti_bot.should_evolve_to_stealth(domain):
                    return StrategyRecommendation(
                        recommended_strategy=FetchStrategy.PLAYWRIGHT_STEALTH,
                        alternatives=[FetchStrategy.PLAYWRIGHT_FULL],
                        reason="Anti-bot signals detected: selecting stealth mode",
                        confidence=0.7,
                        estimated_success_rate=0.5,
                    )
            except Exception:  # nosec B110
                pass  # nosec B110

            return StrategyRecommendation(
                recommended_strategy=FetchStrategy.PLAYWRIGHT_FULL,
                alternatives=[FetchStrategy.HYBRID],
                reason="Cold start: using default safe strategy",
                confidence=0.4,
                estimated_success_rate=0.6,
            )

        # Exploration vs exploitation is only useful after the cold-start safe
        # path has gathered enough samples. Exploring before that can choose a
        # non-browser fetch for JavaScript-backed pages and miss network data.
        if random.random() < self.exploration_probability:  # nosec B311
            # Randomly pick a strategy we haven't failed too much on
            untried = [s for s in FetchStrategy if state.strategies[s].failure_count < 3]
            if untried:
                selected = random.choice(untried)  # nosec B311
                return StrategyRecommendation(
                    recommended_strategy=selected,
                    alternatives=[FetchStrategy.PLAYWRIGHT_FULL],
                    reason="Exploration: testing alternative strategy",
                    confidence=0.3,
                    estimated_success_rate=0.5,
                )

        # Check anti-bot feedback even if we have samples
        try:
            from app.anti_bot_engine import get_anti_bot_engine

            if get_anti_bot_engine().should_evolve_to_stealth(domain):
                return StrategyRecommendation(
                    recommended_strategy=FetchStrategy.PLAYWRIGHT_STEALTH,
                    alternatives=[FetchStrategy.PLAYWRIGHT_FULL],
                    reason="Anti-bot feedback: escalating to stealth mode",
                    confidence=0.8,
                    estimated_success_rate=0.6,
                )
        except Exception:  # nosec B110
            pass  # nosec B110

        best_strategy = state.get_best_strategy()
        best_perf = state.strategies[best_strategy]

        # Timeout-aware: if PLAYWRIGHT_FULL has timeout errors, prefer
        # LIGHTWEIGHT
        full_perf = state.strategies.get(FetchStrategy.PLAYWRIGHT_FULL)
        if full_perf and full_perf.failure_count > 0:
            timeout_count = full_perf.error_patterns.get("TimeoutError", 0) + full_perf.error_patterns.get(
                "asyncio.TimeoutError",
                0,
            )
            if timeout_count >= 2 and best_strategy == FetchStrategy.PLAYWRIGHT_FULL:
                lightweight_perf = state.strategies.get(FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT)
                if lightweight_perf and lightweight_perf.success_count > 0:
                    return StrategyRecommendation(
                        recommended_strategy=FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT,
                        alternatives=[FetchStrategy.PLAYWRIGHT_FULL, FetchStrategy.HYBRID],
                        reason=f"Timeout-aware: PLAYWRIGHT_FULL had {timeout_count} timeouts, LIGHTWEIGHT has {
                            lightweight_perf.success_count
                        } successes",
                        confidence=0.7,
                        estimated_success_rate=lightweight_perf.success_rate,
                    )
                return StrategyRecommendation(
                    recommended_strategy=FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT,
                    alternatives=[FetchStrategy.PLAYWRIGHT_FULL, FetchStrategy.HYBRID],
                    reason=f"Timeout-aware: PLAYWRIGHT_FULL had {timeout_count} timeouts, switching to LIGHTWEIGHT",
                    confidence=0.6,
                    estimated_success_rate=0.4,
                )

        # If best strategy is still poor, try STEALTH
        if best_perf.success_rate < 0.3 and best_strategy != FetchStrategy.PLAYWRIGHT_STEALTH:
            return StrategyRecommendation(
                recommended_strategy=FetchStrategy.PLAYWRIGHT_STEALTH,
                alternatives=[best_strategy],
                reason="Escalation: previous strategies failing consistently",
                confidence=0.6,
                estimated_success_rate=0.3,
            )

        return StrategyRecommendation(
            recommended_strategy=best_strategy,
            alternatives=[s for s in FetchStrategy if s != best_strategy][:2],
            reason=f"Optimal choice: {best_perf.success_rate:.0%} success rate, avg {best_perf.avg_time_ms:.0f}ms",
            confidence=min(0.95, best_perf.success_rate + 0.2),
            estimated_success_rate=best_perf.success_rate,
        )

    def evolve_strategy(self, domain: str) -> FetchStrategy:
        """Evolve strategy based on performance history."""
        rec = self.recommend_strategy(domain)
        state = self._get_or_create_state(domain)

        if rec.recommended_strategy != state.current_strategy:
            logger.info(
                "Evolving strategy for %s: %s → %s (%s)",
                domain,
                state.current_strategy.value,
                rec.recommended_strategy.value,
                rec.reason,
            )
            state.current_strategy = rec.recommended_strategy
            state.strategy_switch_count += 1
            state.last_strategy_switch = time.time()

        return state.current_strategy

    def get_domain_strategy_report(self, domain: str) -> dict:
        """Get detailed strategy analysis for a domain."""
        state = self._get_or_create_state(domain)

        strategies_report = []
        for strategy, perf in state.strategies.items():
            if perf.success_count + perf.failure_count > 0:
                strategies_report.append(
                    {
                        "strategy": strategy.value,
                        "success_rate": round(perf.success_rate, 3),
                        "success_count": perf.success_count,
                        "failure_count": perf.failure_count,
                        "avg_time_ms": round(perf.avg_time_ms, 0),
                        "avg_quality": round(perf.avg_quality, 3),
                        "consecutive_failures": perf.consecutive_failures,
                        "health": "healthy" if perf.is_healthy else ("degraded" if perf.is_degraded else "neutral"),
                    },
                )

        # Include all strategies even if untried (for complete reporting)
        all_strategies_report = []
        for strategy in FetchStrategy:
            perf = state.strategies[strategy]
            if perf.success_count + perf.failure_count > 0:
                all_strategies_report.append(
                    {
                        "strategy": strategy.value,
                        "success_rate": round(perf.success_rate, 3),
                        "success_count": perf.success_count,
                        "failure_count": perf.failure_count,
                        "avg_time_ms": round(perf.avg_time_ms, 0),
                        "avg_quality": round(perf.avg_quality, 3),
                        "consecutive_failures": perf.consecutive_failures,
                        "health": "healthy" if perf.is_healthy else ("degraded" if perf.is_degraded else "neutral"),
                    },
                )
            else:
                all_strategies_report.append(
                    {
                        "strategy": strategy.value,
                        "success_rate": 0.0,
                        "success_count": 0,
                        "failure_count": 0,
                        "avg_time_ms": 0.0,
                        "avg_quality": 0.0,
                        "consecutive_failures": 0,
                        "health": "untried",
                    },
                )

        all_strategies_report.sort(key=lambda x: x["success_rate"], reverse=True)

        return {
            "domain": domain,
            "current_strategy": state.current_strategy.value,
            "strategy_switches": state.strategy_switch_count,
            "total_attempts": sum(s.success_count + s.failure_count for s in state.strategies.values()),
            "strategies": all_strategies_report,
        }

    def should_switch_strategy(self, domain: str) -> bool:
        """Check if the current strategy should be switched.

        Returns True if the current strategy is degraded and a better
        alternative exists.
        """
        state = self._get_or_create_state(domain)
        current_perf = state.strategies.get(state.current_strategy)

        if not current_perf:
            return False

        # Switch if current strategy is degraded
        if current_perf.is_degraded:
            return True

        # Switch if there's a significantly better alternative
        best = state.get_best_strategy()
        if best != state.current_strategy:
            best_perf = state.strategies[best]
            if best_perf.success_rate - current_perf.success_rate > 0.2:
                return True

        return False

    def get_all_domains_strategy_report(self) -> dict:
        """Get strategy report for all domains."""
        if not self.domain_states:
            return {
                "total_domains": 0,
                "domains": [],
                "avg_success_rate": 0.0,
            }

        domains_report = []
        total_success_rate = 0.0

        for domain, state in self.domain_states.items():
            attempts = sum(s.success_count + s.failure_count for s in state.strategies.values())
            if attempts > 0:
                total_success = sum(s.success_count for s in state.strategies.values())
                success_rate = total_success / attempts
            else:
                success_rate = 0.0

            domains_report.append(
                {
                    "domain": domain,
                    "current_strategy": state.current_strategy.value,
                    "strategy_switches": state.strategy_switch_count,
                    "total_attempts": attempts,
                    "overall_success_rate": round(success_rate, 3),
                },
            )
            total_success_rate += success_rate

        return {
            "total_domains": len(self.domain_states),
            "domains": domains_report,
            "avg_success_rate": round(total_success_rate / max(1, len(self.domain_states)), 3),
        }


# Global singleton
_evolution_engine: StrategyEvolutionEngine | None = None


def get_strategy_evolution_engine() -> StrategyEvolutionEngine:
    """Get the global strategy evolution engine."""
    global _evolution_engine
    if _evolution_engine is None:
        _evolution_engine = StrategyEvolutionEngine()
    return _evolution_engine
