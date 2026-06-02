"""Acquisition telemetry — tracks URL acquisition outcomes and recovery metrics.

Collects per-URL acquisition events (direct, session_expired, recovered, etc.)
and exposes aggregate statistics for the /api / system / telemetry endpoint.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Optional

from app.acquisition_state import AcquisitionState
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AcquisitionEvent:
    """A single URL acquisition outcome."""

    url: str = ""
    state: str = ""  # AcquisitionState value
    original_url: str = ""
    final_url: str = ""
    canonical_url: str = ""
    fetch_method: str = ""
    session_bound: bool = False
    ephemeral_params: list[str] = field(default_factory=list)
    recovery_method: Optional[str] = None
    recovered_url: Optional[str] = None
    fetch_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class AcquisitionTelemetryCollector:
    """Collects and aggregates acquisition telemetry events."""

    def __init__(self, max_history: int | None = None) -> None:
        self._history: list[AcquisitionEvent] = []
        self._max_history = max_history if max_history is not None else settings.ACQUISITION_TELEMETRY_MAX_HISTORY
        self._state_counts: Counter = Counter()
        self._recovery_attempts: int = 0
        self._recovery_successes: int = 0
        self._session_bound_count: int = 0

    def record(
        self,
        url: str,
        state: AcquisitionState,
        original_url: str = "",
        final_url: str = "",
        canonical_url: str = "",
        fetch_method: str = "",
        session_bound: bool = False,
        ephemeral_params: list[str] | None = None,
        recovery_method: str | None = None,
        recovered_url: str | None = None,
        fetch_time_ms: float = 0.0,
    ) -> AcquisitionEvent:
        """Record an acquisition event."""
        event = AcquisitionEvent(
            url=url,
            state=state.value if isinstance(state, AcquisitionState) else state,
            original_url=original_url,
            final_url=final_url,
            canonical_url=canonical_url,
            fetch_method=fetch_method,
            session_bound=session_bound,
            ephemeral_params=ephemeral_params or [],
            recovery_method=recovery_method,
            recovered_url=recovered_url,
            fetch_time_ms=fetch_time_ms,
        )
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Update counters
        self._state_counts[event.state] += 1
        if session_bound:
            self._session_bound_count += 1
        if state in (
            AcquisitionState.RECOVERED,
            AcquisitionState.RECOVERY_FAILED,
            AcquisitionState.AWAITING_SEARCH_PARAMS,
            AcquisitionState.NO_SEARCH_FORM,
        ):
            self._recovery_attempts += 1
            if state == AcquisitionState.RECOVERED:
                self._recovery_successes += 1

        return event

    def get_recent(self, n: int | None = None) -> list[dict]:
        """Get the N most recent acquisition events."""
        n = n if n is not None else settings.ACQUISITION_TELEMETRY_RECENT_DEFAULT
        return [e.to_dict() for e in self._history[-n:]]

    def get_summary(self) -> dict:
        """Get aggregate acquisition statistics."""
        total = sum(self._state_counts.values())
        recovery_rate = self._recovery_successes / self._recovery_attempts if self._recovery_attempts > 0 else 0.0
        return {
            "total_acquisitions": total,
            "state_distribution": dict(self._state_counts),
            "session_bound_urls": self._session_bound_count,
            "recovery_attempts": self._recovery_attempts,
            "recovery_successes": self._recovery_successes,
            "recovery_success_rate": round(recovery_rate, 3),
            "recent_events": self.get_recent(10),
        }

    def clear(self) -> None:
        self._history.clear()
        self._state_counts.clear()
        self._recovery_attempts = 0
        self._recovery_successes = 0
        self._session_bound_count = 0


# Module-level singleton
_collector: AcquisitionTelemetryCollector | None = None


def get_acquisition_telemetry() -> AcquisitionTelemetryCollector:
    global _collector
    if _collector is None:
        _collector = AcquisitionTelemetryCollector()
    return _collector
