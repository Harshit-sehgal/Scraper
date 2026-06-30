"""Extraction Cascade Telemetry — per-extraction cascade layer logging.

Records which cascade layers were attempted, their quality scores,
duration, and the reason the cascade stopped for each extraction job.

The store is an in-memory ring buffer that retains traces for up to
``_MAX_TRACES`` concurrent jobs and evicts entries older than
``_TRACE_TTL_SECONDS`` on each access.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_MAX_TRACES = 10_000
_TRACE_TTL_SECONDS = 3600  # 1 hour

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

_cascade_traces: dict[str, list[dict[str, Any]]] = {}
_cascade_traces_lock = threading.Lock()

# Per-job metadata (start_time, final_status, stopped_reason)
_cascade_meta: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Recording API
# ---------------------------------------------------------------------------


def record_cascade_step(
    job_id: str,
    *,
    url: str = "",
    layer_name: str = "",
    quality_score: float = -1.0,
    success: bool = False,
    duration_ms: float = 0.0,
    reason_stopped: str = "",
) -> None:
    """Record one cascade step for *job_id*.

    Called by the extraction orchestrator after each cascade layer
    finishes (succeeds, fails, or is skipped).

    The trace entry schema::

        {
            "layer": str,
            "url": str,
            "quality_score": float,
            "success": bool,
            "duration_ms": float,
            "reason_stopped": str,
            "timestamp": float,   # time.time() monotonic-ish
        }
    """
    entry: dict[str, Any] = {
        "layer": layer_name,
        "url": url,
        "quality_score": round(quality_score, 4),
        "success": success,
        "duration_ms": round(duration_ms, 1),
        "reason_stopped": reason_stopped,
        "timestamp": time.time(),
    }
    with _cascade_traces_lock:
        _cascade_traces.setdefault(job_id, []).append(entry)
        _cascade_meta[job_id] = {
            "last_update": time.time(),
            "status": _cascade_meta.get(job_id, {}).get("status", "running"),
        }


def set_cascade_final_status(job_id: str, status: str, stopped_reason: str = "") -> None:
    """Mark *job_id* as completed/failed/empty and record the terminal reason."""
    with _cascade_traces_lock:
        _cascade_meta[job_id] = {
            **_cascade_meta.get(job_id, {}),
            "last_update": time.time(),
            "status": status,
            "stopped_reason": stopped_reason,
        }


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------


def get_cascade_trace(job_id: str) -> list[dict[str, Any]]:
    """Return the ordered cascade log for *job_id*.

    Each entry is the dict recorded by :func:`record_cascade_step`,
    augmented with job-level ``meta`` in a separate key.
    """
    _evict_stale()
    with _cascade_traces_lock:
        steps = list(_cascade_traces.get(job_id, []))
        meta = dict(_cascade_meta.get(job_id, {}))
    # Attach meta to first entry if any
    if steps and meta:
        steps[0]["_meta"] = meta
    return steps


def get_all_cascade_traces(prefix: str = "") -> dict[str, list[dict[str, Any]]]:
    """Return a snapshot of all cascade traces, optionally filtered by *prefix*."""
    _evict_stale()
    with _cascade_traces_lock:
        keys = list(_cascade_traces)
    result: dict[str, list[dict[str, Any]]] = {}
    for k in keys:
        if not prefix or k.startswith(prefix):
            result[k] = get_cascade_trace(k)
    return result


def clear_cascade_traces() -> None:
    """Drop all traces (used by tests and reset)."""
    with _cascade_traces_lock:
        _cascade_traces.clear()
        _cascade_meta.clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _evict_stale() -> None:
    """Remove traces older than ``_TRACE_TTL_SECONDS``."""
    now = time.time()
    with _cascade_traces_lock:
        stale = [jid for jid, meta in _cascade_meta.items() if now - meta.get("last_update", 0) > _TRACE_TTL_SECONDS]
        for jid in stale:
            _cascade_traces.pop(jid, None)
            _cascade_meta.pop(jid, None)
        # Hard cap on total entries
        if len(_cascade_traces) > _MAX_TRACES:
            oldest = sorted(
                _cascade_meta.items(),
                key=lambda kv: kv[1].get("last_update", 0),
            )
            for jid, _ in oldest[: len(_cascade_traces) - _MAX_TRACES]:
                _cascade_traces.pop(jid, None)
                _cascade_meta.pop(jid, None)
