"""
Regression State Adapter — isolated state management for tracking archived failures and regressions.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, List, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class RegressionStateAdapter:
    """Delegated state manager for extraction failure categorization, history, and severity analytics."""

    def __init__(self) -> None:
        # Maps domain -> list of failure record dicts
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        # Maps domain -> failure count per category
        self._counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def record_failure(self, domain: str, failure_type: str, severity: str = "medium", context: Optional[dict] = None) -> None:
        """Record and log a new classified regression/failure event."""
        import time
        record = {
            "failure_type": failure_type,
            "severity": severity,
            "context": context or {},
            "timestamp": time.time(),
        }
        self._history[domain].append(record)
        self._counts[domain][failure_type] += 1
        
        # Keep history bounded (last 100 failures per domain)
        if len(self._history[domain]) > 100:
            self._history[domain].pop(0)

        logger.debug(
            "[RegressionState] Archived failure for domain %s: %s (severity: %s)",
            domain, failure_type, severity
        )

    def get_failure_history(self, domain: str) -> list[dict[str, Any]]:
        """Retrieve failure history list for a target domain."""
        return self._history.get(domain, [])

    def get_failure_counts(self, domain: str) -> dict[str, int]:
        """Fetch categorized failure counts for a target domain."""
        return dict(self._counts.get(domain, {}))

    def get_regression_rate(self, domain: str, window_seconds: float = 3600.0) -> float:
        """Calculate the regression rate (failures per hour) within a sliding time window."""
        import time
        now = time.time()
        recent_failures = [
            f for f in self._history.get(domain, [])
            if now - f["timestamp"] < window_seconds
        ]
        return len(recent_failures)

    def clear(self) -> None:
        """Wipe all archived failure telemetry records."""
        self._history.clear()
        self._counts.clear()


_regression_state: Optional[RegressionStateAdapter] = None

def get_regression_state() -> RegressionStateAdapter:
    global _regression_state
    if _regression_state is None:
        _regression_state = RegressionStateAdapter()
    return _regression_state
