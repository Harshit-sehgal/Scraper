"""Domain Behavior Intelligence — learning of site-specific patterns.

Domains have different behavioral signatures such as hydration, scrolling, and
anti-bot signals. The system records these signals to adjust strategy choices.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)


class DomainIntelligence:
    """Aggregated behavioral metrics for a single domain."""

    def __init__(self, domain: str, data: dict | None = None) -> None:
        self.domain = domain
        self.hydration_delay_ms = data.get("hydration_delay_ms", 0.0) if data else 0.0
        self.infinite_scroll_required = data.get("infinite_scroll_required", False) if data else False
        self.anti_bot_risk = data.get("anti_bot_risk", 0.0) if data else 0.0
        self.preferred_strategy = data.get("preferred_strategy", "none") if data else "none"
        self.selector_decay_rate = data.get("selector_decay_rate", 0.0) if data else 0.0
        self.success_count = data.get("success_count", 0) if data else 0
        self.total_fetches = data.get("total_fetches", 0) if data else 0
        self.failure_history = data.get("failure_history", {}) if data else {}
        self.last_updated = data.get("last_updated", time.time()) if data else time.time()

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "hydration_delay_ms": round(self.hydration_delay_ms, 2),
            "infinite_scroll_required": self.infinite_scroll_required,
            "anti_bot_risk": round(self.anti_bot_risk, 3),
            "preferred_strategy": self.preferred_strategy,
            "selector_decay_rate": round(self.selector_decay_rate, 3),
            "success_count": self.success_count,
            "total_fetches": self.total_fetches,
            "failure_history": dict(self.failure_history),
            "last_updated": self.last_updated,
        }


class DomainIntelligenceRegistry:
    """Persistent registry of domain intelligence."""

    def __init__(self, storage_path: str | None = None) -> None:
        if storage_path is None:
            storage_path = str(Path(__file__).resolve().parent.parent / "data" / "domain_intelligence.json")
        self.path = Path(storage_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._registry: dict[str, DomainIntelligence] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path) as f:  # noqa: PTH123
                    data = json.load(f)
                    for domain, metrics in data.items():
                        self._registry[domain] = DomainIntelligence(domain, metrics)
            except Exception:
                logger.exception("Failed to load domain intelligence")

    def _save(self) -> None:
        try:
            with open(self.path, "w") as f:  # noqa: PTH123
                json.dump({d: i.to_dict() for d, i in self._registry.items()}, f, indent=2)
        except Exception:
            logger.exception("Failed to save domain intelligence")

    def get_intelligence(self, url: str) -> DomainIntelligence:
        """Get or create intelligence for a domain."""
        domain = self._extract_domain(url)
        if domain not in self._registry:
            self._registry[domain] = DomainIntelligence(domain)
        return self._registry[domain]

    def update_from_telemetry(self, telemetry: dict) -> None:
        """Update domain intelligence based on a recent scrape telemetry snapshot."""
        url = telemetry.get("url", "")
        domain = self._extract_domain(url)
        if not domain:
            return

        intel = self.get_intelligence(url)
        alpha = settings.DOMAIN_INTELLIGENCE_SMOOTHING_ALPHA

        # 1. Update basic counts
        intel.total_fetches += 1
        if not telemetry.get("error"):
            intel.success_count += 1

        # 2. Hydration Delay (Moving Average)
        delay = telemetry.get("js_render_delay_ms", 0.0)
        if delay > 0:
            intel.hydration_delay_ms = (intel.hydration_delay_ms * (1 - alpha)) + (delay * alpha)

        # 3. Anti-Bot Risk (Moving Average)
        risk = telemetry.get("anti_bot_score", 0.0)
        intel.anti_bot_risk = (intel.anti_bot_risk * (1 - alpha)) + (risk * alpha)

        # 4. Strategy Analysis
        strategy = telemetry.get("fallback_usage", "none")
        if not telemetry.get("error") and strategy != "none":
            # If successful, consider this a candidate for preferred strategy
            # For now, we just track the most recent successful non-discovery
            # strategy
            if strategy in ["profile", "memory", "regex", "httpx"]:
                intel.preferred_strategy = strategy

        # 5. Selector Decay Rate
        decay_signal = 1.0 if telemetry.get("fallback_triggered") else 0.0
        intel.selector_decay_rate = (intel.selector_decay_rate * (1 - alpha)) + (decay_signal * alpha)

        # 6. Infinite Scroll (Observation)
        # If we got 0 records without scroll but >0 with scroll, or similar indicators.
        # For now, we rely on the telemetry's records_extracted vs records_final or similar signals.
        # Let's assume for now that if records_extracted > 0 and fallback_usage was none / memory,
        # and we did scroll attempts, we tag it.
        # (Actually, let's keep it simple: if it's a known feed domain, we'll mark it manually or via discovery result)

        intel.last_updated = time.time()
        self._save()

    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() or "unknown"
        except Exception:
            return "unknown"


# Global Singleton
_registry: DomainIntelligenceRegistry | None = None


def get_domain_intelligence() -> DomainIntelligenceRegistry:
    global _registry
    if _registry is None:
        _registry = DomainIntelligenceRegistry()
    return _registry
