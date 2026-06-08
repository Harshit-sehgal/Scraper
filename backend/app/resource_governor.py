"""Resource Governor — operational economics and bounded resource budgets.

Provides:
  - Memory bounds tracking for browser pools, closing stale contexts when threshold is exceeded.
  - Frontier queue-shedding for low-priority targets when capacity is saturated.
  - Automatic historical log and telemetry compaction / pruning.
  - Token consumption budgets with adaptive throttling triggers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ResourceBudgets:
    """Configurable resource caps to guarantee system longevity under high load."""

    max_browser_memory_mb: float = 1024.0
    max_retry_depth: int = field(default_factory=lambda: settings.MAX_RECOVERY_ATTEMPTS)
    max_queue_size: int = 1000
    max_telemetry_records: int = field(default_factory=lambda: settings.TELEMETRY_STREAM_MAXLEN)
    max_token_spend: float = 5.0  # Dollar limit


class ResourceGovernor:
    """Enforces boundaries and resource economics across DataForge processes."""

    def __init__(self, budgets: ResourceBudgets | None = None) -> None:
        self.budgets = budgets or ResourceBudgets()
        self.accumulated_tokens = 0
        self.token_spend = 0.0
        self.metrics = {
            "browser_prunes": 0,
            "queue_sheds": 0,
            "telemetry_prunes": 0,
            "throttled_cycles": 0,
        }

    async def check_browser_memory(self) -> dict[str, Any]:
        """Inspect and prune the browser pool context pool if memory limits are exceeded."""
        from app.browser_pool import get_browser_pool

        pool = get_browser_pool()

        # Simple simulated RSS page memory tracking
        async with pool._lock:
            num_contexts = len(pool._contexts)
            estimated_memory_mb = num_contexts * 150.0  # Assumes ~150MB per running context

            pruned = 0
            if estimated_memory_mb > self.budgets.max_browser_memory_mb:
                logger.warning(
                    "[Governor] Browser memory limit exceeded: %.2fMB > %.2fMB. Pruning stale contexts.",
                    estimated_memory_mb,
                    self.budgets.max_browser_memory_mb,
                )
                # Prune / close half of active contexts
                to_prune = num_contexts // 2
                keys = list(pool._contexts.keys())
                for i in range(min(to_prune, len(keys))):
                    key = keys[i]
                    ctx = pool._contexts.pop(key, None)
                    if ctx:
                        try:
                            await ctx.close()
                        except Exception as e:
                            logger.debug("Failed to close context during prune: %s", e)
                        pruned += 1

                self.metrics["browser_prunes"] += pruned
                estimated_memory_mb = len(pool._contexts) * 150.0

        return {
            "num_contexts": num_contexts,
            "estimated_memory_mb": estimated_memory_mb,
            "pruned": pruned,
        }

    def enforce_queue_limits(self, queue: list[Any]) -> list[Any]:
        """Shed lower-priority seeds when queue capacity is saturated."""
        if len(queue) > self.budgets.max_queue_size:
            logger.warning(
                "[Governor] Crawl frontier queue size exceeded: %d > %d. Trimming excess seeds.",
                len(queue),
                self.budgets.max_queue_size,
            )
            excess = len(queue) - self.budgets.max_queue_size
            # Retain only the highest-priority seeds (assumes queue is sorted)
            trimmed = queue[: self.budgets.max_queue_size]
            self.metrics["queue_sheds"] += excess
            return trimmed
        return queue

    def prune_telemetry(self) -> int:
        """Compact telemetry records to prevent memory inflation."""
        from app.scrape_telemetry import get_scrape_telemetry

        telemetry = get_scrape_telemetry()

        recent = telemetry.get_recent(10000)
        num_records = len(recent)
        pruned = 0

        if num_records > self.budgets.max_telemetry_records:
            logger.info(
                "[Governor] Telemetry count exceeded: %d > %d. Pruning historical logs.",
                num_records,
                self.budgets.max_telemetry_records,
            )
            # Retain only the limit bounds
            telemetry.clear()
            for r in recent[-self.budgets.max_telemetry_records :]:
                data = dict(r)
                url = data.pop("url", "unknown")
                telemetry.record(url, **data)
            pruned = num_records - self.budgets.max_telemetry_records
            self.metrics["telemetry_prunes"] += pruned

        return pruned

    def track_token_spend(self, tokens_used: int, price_per_million: float = 1.0) -> bool:
        """Register LLM token spend and check if budget is exhausted."""
        self.accumulated_tokens += tokens_used
        cost = (tokens_used / 1000000.0) * price_per_million
        self.token_spend += cost

        if self.token_spend > self.budgets.max_token_spend:
            self.metrics["throttled_cycles"] += 1
            logger.warning(
                "[Governor] LLM token dollar budget exhausted: $%.4f > $%.2f. Triggering throttle.",
                self.token_spend,
                self.budgets.max_token_spend,
            )
            return False  # Throttle / block further calls
        return True

    def get_governance_report(self) -> dict[str, Any]:
        """Aggregate the status report of the resource governor."""
        return {
            "accumulated_tokens": self.accumulated_tokens,
            "token_spend_dollars": round(self.token_spend, 6),
            "token_budget_remaining": max(0.0, round(self.budgets.max_token_spend - self.token_spend, 4)),
            "metrics": self.metrics,
        }


# Global singleton
_resource_governor: ResourceGovernor | None = None


def get_resource_governor() -> ResourceGovernor:
    """Get the global resource governor context."""
    global _resource_governor
    if _resource_governor is None:
        _resource_governor = ResourceGovernor()
    return _resource_governor
