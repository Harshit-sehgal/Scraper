"""Structured Job Events — in-memory ring buffer for per-job structured log events.

Emitted by :func:`log_job_event` and queried via :func:`get_job_events`.
Events are JSON-serialisable dicts with ``job_id``, ``event_type``,
``timestamp``, and arbitrary ``details``.

Each job retains at most ``_MAX_EVENTS_PER_JOB`` events; the overall store
keeps at most ``_MAX_TOTAL_EVENTS`` before evicting the oldest entries.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_LOGGER_MAX = __import__("logging").getLogger(__name__)

_MAX_EVENTS_PER_JOB = 1000
_MAX_TOTAL_EVENTS = 50_000

# ---------------------------------------------------------------------------
# In-memory store:  job_id -> list[event_dict]
# ---------------------------------------------------------------------------

_job_events: dict[str, list[dict[str, Any]]] = {}
_job_events_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Recording API
# ---------------------------------------------------------------------------


def log_job_event(
    job_id: str,
    event_type: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Emit a structured event for *job_id*.

    The event is::

        {
            "job_id": str,
            "event_type": str,
            "timestamp": float,
            "details": dict | None,
        }

    Events are also forwarded to the standard ``logging`` system so
    structured JSON handlers can capture them.
    """
    event: dict[str, Any] = {
        "job_id": job_id,
        "event_type": event_type,
        "timestamp": time.time(),
        "details": details,
    }
    with _job_events_lock:
        lst = _job_events.setdefault(job_id, [])
        lst.append(event)
        # Per-job cap
        if len(lst) > _MAX_EVENTS_PER_JOB:
            _job_events[job_id] = lst[-_MAX_EVENTS_PER_JOB:]
        # Global cap
        _evict_if_over_limit()

    # Also emit via stdlib logging for log aggregation
    _LOGGER_MAX.info(
        "job_event type=%s job=%s",
        event_type,
        job_id,
        extra={"job_event": event},
    )


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------


def get_job_events(job_id: str, *, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    """Return events for *job_id*, paginated by *limit* and *offset*."""
    with _job_events_lock:
        events = list(_job_events.get(job_id, []))
    return events[offset : offset + limit]


def get_recent_events(limit: int = 500) -> list[dict[str, Any]]:
    """Return the most recent ``limit`` events across all jobs."""
    with _job_events_lock:
        all_events = [e for events in _job_events.values() for e in events]
    all_events.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
    return all_events[:limit]


def clear_job_events() -> None:
    """Drop all stored events (used by tests and reset)."""
    with _job_events_lock:
        _job_events.clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _evict_if_over_limit() -> None:
    """Evict oldest entries if the total count exceeds the cap."""
    total = sum(len(v) for v in _job_events.values())
    if total <= _MAX_TOTAL_EVENTS:
        return
    # Remove oldest events from the oldest jobs first (sorted by first event timestamp)
    job_order = sorted(
        _job_events.items(),
        key=lambda kv: kv[1][0].get("timestamp", 0) if kv[1] else 0,
    )
    for jid, events in job_order:
        excess = total - _MAX_TOTAL_EVENTS
        if excess <= 0:
            break
        drop = min(excess, len(events))
        _job_events[jid] = events[drop:]
        total -= drop
        if not _job_events[jid]:
            del _job_events[jid]
