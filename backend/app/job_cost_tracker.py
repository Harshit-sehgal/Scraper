"""Per-Job Cost Tracker — CPU-seconds, browser-seconds, bandwidth, proxy cost.

Tracks resource consumption per job so that finalization can compute
a detailed ``cost_breakdown`` dict instead of just a flat
``estimated_cost_usd`` scalar.

Usage::

    from app.job_cost_tracker import get_job_cost_tracker

    tracker = get_job_cost_tracker()

    # Called by the scraper for each URL in a job:
    tracker.record_cpu_time(job_id, seconds=1.5)
    tracker.record_browser_time(job_id, seconds=3.2)
    tracker.record_bytes_transferred(job_id, bytes_in=4096, bytes_out=1024)
    tracker.record_proxy_request(job_id, tier="residential")

    # Called by finalization to populate the Job model:
    breakdown = tracker.get_cost_breakdown(job_id)
    job.estimated_cost_usd = breakdown["total_usd"]
    job.cost_breakdown = breakdown

Thread-safe: all counters use ``threading.Lock``.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Cost constants (per unit) ────────────────────────────────────────────

# $/CPU-second (based on typical cloud compute pricing)
COST_PER_CPU_SECOND: float = 0.00005
# $/browser-second (Chromium context cost ≈ 10x compute)
COST_PER_BROWSER_SECOND: float = 0.0005
# $/GB transferred (egress)
COST_PER_GB_TRANSFERRED: float = 0.08
# $/proxy request by tier
PROXY_COST_PER_REQUEST: dict[str, float] = {
    "datacenter": 0.001,
    "residential": 0.01,
    "mobile": 0.03,
}


@dataclass
class JobCostRecord:
    """Accumulated cost metrics for a single job."""

    cpu_seconds: float = 0.0
    browser_seconds: float = 0.0
    bytes_in: int = 0
    bytes_out: int = 0
    proxy_requests: dict[str, int] = field(default_factory=dict)
    """Maps proxy tier → request count."""

    start_time: float = 0.0
    """Monotonic clock at first record for wall-clock tracking."""

    last_cpu_sample: float = 0.0
    """Last CPU time sample for delta calculation."""


class JobCostTracker:
    """Thread-safe per-job resource cost accumulator.

    Keyed by ``job_id`` — each job gets its own ``JobCostRecord``.
    Records are evicted after finalization to bound memory.
    """

    _MAX_TRACKED_JOBS: int = 10_000

    def __init__(self) -> None:
        self._records: dict[str, JobCostRecord] = {}
        self._lock = threading.Lock()

    # ── Recording primitives ────────────────────────────────────────────

    def record_cpu_time(self, job_id: str, seconds: float) -> None:
        """Add CPU time consumed by this job (seconds).

        Typically measured via ``time.process_time()`` deltas or
        OS-level CPU accounting.
        """
        if seconds <= 0:
            return
        with self._lock:
            rec = self._ensure_record(job_id)
            rec.cpu_seconds += seconds

    def record_browser_time(self, job_id: str, seconds: float) -> None:
        """Add browser context time consumed by this job (seconds).

        This is the wall-clock time a Playwright browser context spent
        active (page load + JS execution + DOM extraction) for this job.
        """
        if seconds <= 0:
            return
        with self._lock:
            rec = self._ensure_record(job_id)
            rec.browser_seconds += seconds

    def record_bytes_transferred(self, job_id: str, bytes_in: int = 0, bytes_out: int = 0) -> None:
        """Add network bytes consumed by this job.

        ``bytes_in`` = response payload (HTML, images, etc.)
        ``bytes_out`` = request payload (headers, form data, etc.)
        """
        if bytes_in <= 0 and bytes_out <= 0:
            return
        with self._lock:
            rec = self._ensure_record(job_id)
            rec.bytes_in += max(0, bytes_in)
            rec.bytes_out += max(0, bytes_out)

    def record_proxy_request(self, job_id: str, tier: str = "datacenter") -> None:
        """Record a proxy request under the given tier.

        Tier is one of ``datacenter``, ``residential``, ``mobile``.
        Unknown tiers are counted under ``datacenter``.
        """
        tier = tier if tier in PROXY_COST_PER_REQUEST else "datacenter"
        with self._lock:
            rec = self._ensure_record(job_id)
            rec.proxy_requests[tier] = rec.proxy_requests.get(tier, 0) + 1

    # ── Querying ────────────────────────────────────────────────────────

    def get_cost_breakdown(self, job_id: str) -> dict[str, Any]:
        """Compute the full cost breakdown for a job.

        Returns a dict with keys:
        - ``cpu_seconds``, ``cpu_cost_usd``
        - ``browser_seconds``, ``browser_cost_usd``
        - ``bytes_in``, ``bytes_out``, ``bandwidth_cost_usd``
        - ``proxy_requests`` (by tier), ``proxy_cost_usd``
        - ``total_usd``
        """
        with self._lock:
            rec = self._records.get(job_id)

        if rec is None:
            return self._empty_breakdown()

        cpu_cost = rec.cpu_seconds * COST_PER_CPU_SECOND
        browser_cost = rec.browser_seconds * COST_PER_BROWSER_SECOND
        total_bytes = rec.bytes_in + rec.bytes_out
        bandwidth_cost = (total_bytes / (1024 * 1024 * 1024)) * COST_PER_GB_TRANSFERRED

        proxy_cost = 0.0
        proxy_detail: dict[str, Any] = {}
        for tier, count in rec.proxy_requests.items():
            tier_cost = count * PROXY_COST_PER_REQUEST.get(tier, 0.001)
            proxy_detail[tier] = {"requests": count, "cost_usd": round(tier_cost, 6)}
            proxy_cost += tier_cost

        llm_cost = 0.0  # LLM cost is tracked separately via job.total_llm_calls

        total_usd = round(cpu_cost + browser_cost + bandwidth_cost + proxy_cost + llm_cost, 6)

        return {
            "cpu_seconds": round(rec.cpu_seconds, 3),
            "cpu_cost_usd": round(cpu_cost, 6),
            "browser_seconds": round(rec.browser_seconds, 3),
            "browser_cost_usd": round(browser_cost, 6),
            "bytes_in": rec.bytes_in,
            "bytes_out": rec.bytes_out,
            "bandwidth_cost_usd": round(bandwidth_cost, 6),
            "proxy_requests": proxy_detail,
            "proxy_cost_usd": round(proxy_cost, 6),
            "total_usd": total_usd,
        }

    def get_raw_record(self, job_id: str) -> JobCostRecord | None:
        """Return the raw accumulated record (for inspection/testing)."""
        with self._lock:
            return self._records.get(job_id)

    # ── Lifecycle ──────────────────────────────────────────────────────

    def finalize_job(self, job_id: str) -> dict[str, Any]:
        """Compute cost breakdown and evict the record.

        Called by the finalization service after populating the Job model.
        Returns the cost breakdown dict.
        """
        breakdown = self.get_cost_breakdown(job_id)
        with self._lock:
            self._records.pop(job_id, None)
        return breakdown

    def clear(self) -> None:
        """Drop all tracked records (testing only)."""
        with self._lock:
            self._records.clear()

    # ── Internal ───────────────────────────────────────────────────────

    def _ensure_record(self, job_id: str) -> JobCostRecord:
        """Get or create a JobCostRecord for the given job_id.

        Must be called under ``self._lock``.
        """
        rec = self._records.get(job_id)
        if rec is None:
            if len(self._records) >= self._MAX_TRACKED_JOBS:
                # Evict the oldest entry to bound memory
                oldest_id = next(iter(self._records))
                logger.warning("[JobCostTracker] Evicting oldest job %s to bound memory", oldest_id)
                del self._records[oldest_id]
            rec = JobCostRecord(start_time=time.monotonic())
            self._records[job_id] = rec
        return rec

    @staticmethod
    def _empty_breakdown() -> dict[str, Any]:
        """Return a zero-cost breakdown for jobs with no tracked data."""
        return {
            "cpu_seconds": 0.0,
            "cpu_cost_usd": 0.0,
            "browser_seconds": 0.0,
            "browser_cost_usd": 0.0,
            "bytes_in": 0,
            "bytes_out": 0,
            "bandwidth_cost_usd": 0.0,
            "proxy_requests": {},
            "proxy_cost_usd": 0.0,
            "total_usd": 0.0,
        }


# ── Singleton ──────────────────────────────────────────────────────────

_TRACKER: JobCostTracker | None = None
_TRACKER_LOCK = threading.Lock()


def get_job_cost_tracker() -> JobCostTracker:
    """Return the global per-job cost tracker singleton."""
    global _TRACKER
    with _TRACKER_LOCK:
        if _TRACKER is None:
            _TRACKER = JobCostTracker()
        return _TRACKER


def reset_job_cost_tracker() -> None:
    """Drop the singleton (testing only)."""
    global _TRACKER
    with _TRACKER_LOCK:
        if _TRACKER is not None:
            _TRACKER.clear()
        _TRACKER = None
