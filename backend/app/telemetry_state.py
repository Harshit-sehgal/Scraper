"""
Telemetry State Adapter — isolated state management for runtime performance metrics.
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any
from app.scrape_telemetry import get_scrape_telemetry

logger = logging.getLogger(__name__)


class TelemetryStateAdapter:
    """Delegated state manager for scraping latency, hit rates, and execution costs."""

    def __init__(self) -> None:
        self._telemetry = get_scrape_telemetry()
        self._domain_stabilization_times: Dict[str, List[float]] = {}

    def record_scrape(self, url: str, **kwargs: Any) -> None:
        """Record scrape event statistics and telemetry parameters."""
        self._telemetry.record(url, **kwargs)

    def record_stabilization(self, domain: str, settle_ms: float) -> None:
        """Record the actual time it took for a domain's DOM to stabilize."""
        if domain not in self._domain_stabilization_times:
            self._domain_stabilization_times[domain] = []
        self._domain_stabilization_times[domain].append(settle_ms)
        if len(self._domain_stabilization_times[domain]) > 10:
            self._domain_stabilization_times[domain].pop(0)

    def get_avg_stabilization(self, domain: str) -> float:
        """Retrieve the adaptive average DOM stabilization time for a domain in ms."""
        times = self._domain_stabilization_times.get(domain)
        if not times:
            return 1500.0  # Default base wait: 1.5 seconds
        # Bound between 500ms and 5000ms to avoid infinite delay or flash exits
        return max(500.0, min(5000.0, sum(times) / len(times)))

    def get_recent_snapshots(self, count: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent scrape telemetry snapshots."""
        return self._telemetry.get_recent(count)

    def get_confidence_histogram(self, count: int = 100) -> Dict[str, int]:
        """Fetch the extraction confidence histogram."""
        return self._telemetry.get_confidence_histogram(count)

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate high-level scraping runtime statistics."""
        recent = self._telemetry.get_recent(100)
        if not recent:
            return {
                "total_scrapes": 0,
                "avg_fetch_ms": 0.0,
                "fallback_rate": 0.0,
                "avg_confidence": 0.0,
            }

        total_scrapes = len(recent)
        total_fetch_ms = sum(r.get("fetch_ms", 0.0) for r in recent)
        fallbacks = sum(1 for r in recent if r.get("fallback_triggered", False))

        confidence_scores = [
            r.get("confidence_map", {}).get("overall_avg", 0.0) for r in recent if r.get("confidence_map")
        ]
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

        return {
            "total_scrapes": total_scrapes,
            "avg_fetch_ms": round(total_fetch_ms / total_scrapes, 2),
            "fallback_rate": round(fallbacks / total_scrapes, 3),
            "avg_confidence": round(avg_confidence, 2),
        }

    def clear(self) -> None:
        """Wipe all cached telemetry records."""
        self._telemetry.clear()


_telemetry_state: Optional[TelemetryStateAdapter] = None


def get_telemetry_state() -> TelemetryStateAdapter:
    global _telemetry_state
    if _telemetry_state is None:
        _telemetry_state = TelemetryStateAdapter()
    return _telemetry_state
