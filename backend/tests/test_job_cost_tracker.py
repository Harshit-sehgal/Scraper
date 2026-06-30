"""Tests for per-job cost tracker (Prod 23).

Covers:
- Recording primitives: CPU time, browser time, bytes, proxy requests
- Cost breakdown computation
- Negative/zero value handling
- Thread-safe concurrent accumulation
- Finalization evicts record
- Memory caps
"""

from __future__ import annotations

import threading

import pytest
from app.job_cost_tracker import (
    COST_PER_BROWSER_SECOND,
    COST_PER_CPU_SECOND,
    JobCostTracker,
    get_job_cost_tracker,
    reset_job_cost_tracker,
)


@pytest.fixture(autouse=True)
def _reset_tracker():
    """Reset the singleton before and after each test."""
    reset_job_cost_tracker()
    yield
    reset_job_cost_tracker()


# ═══════════════════════════════════════════════════════════════════════════════
# Recording primitives
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecordCpuTime:
    def test_accumulates_positive_seconds(self) -> None:
        tracker = JobCostTracker()
        tracker.record_cpu_time("job-1", seconds=2.5)
        tracker.record_cpu_time("job-1", seconds=1.5)
        rec = tracker.get_raw_record("job-1")
        assert rec is not None
        assert rec.cpu_seconds == pytest.approx(4.0, abs=0.01)

    def test_ignores_zero_and_negative(self) -> None:
        tracker = JobCostTracker()
        tracker.record_cpu_time("job-1", seconds=0.0)
        tracker.record_cpu_time("job-1", seconds=-1.0)
        assert tracker.get_raw_record("job-1") is None


class TestRecordBrowserTime:
    def test_accumulates_browser_seconds(self) -> None:
        tracker = JobCostTracker()
        tracker.record_browser_time("job-1", seconds=3.0)
        tracker.record_browser_time("job-1", seconds=2.0)
        rec = tracker.get_raw_record("job-1")
        assert rec is not None
        assert rec.browser_seconds == pytest.approx(5.0, abs=0.01)


class TestRecordBytesTransferred:
    def test_accumulates_in_and_out(self) -> None:
        tracker = JobCostTracker()
        tracker.record_bytes_transferred("job-1", bytes_in=2048, bytes_out=512)
        tracker.record_bytes_transferred("job-1", bytes_in=1024, bytes_out=256)
        rec = tracker.get_raw_record("job-1")
        assert rec is not None
        assert rec.bytes_in == 3072
        assert rec.bytes_out == 768

    def test_ignores_zero_and_negative(self) -> None:
        tracker = JobCostTracker()
        tracker.record_bytes_transferred("job-1", bytes_in=0, bytes_out=0)
        tracker.record_bytes_transferred("job-1", bytes_in=-100, bytes_out=-100)
        assert tracker.get_raw_record("job-1") is None


class TestRecordProxyRequest:
    def test_tracks_by_tier(self) -> None:
        tracker = JobCostTracker()
        tracker.record_proxy_request("job-1", tier="residential")
        tracker.record_proxy_request("job-1", tier="residential")
        tracker.record_proxy_request("job-1", tier="datacenter")
        rec = tracker.get_raw_record("job-1")
        assert rec is not None
        assert rec.proxy_requests["residential"] == 2
        assert rec.proxy_requests["datacenter"] == 1

    def test_unknown_tier_defaults_to_datacenter(self) -> None:
        tracker = JobCostTracker()
        tracker.record_proxy_request("job-1", tier="unknown_tier")
        rec = tracker.get_raw_record("job-1")
        assert rec is not None
        assert "datacenter" in rec.proxy_requests


# ═══════════════════════════════════════════════════════════════════════════════
# Cost breakdown
# ═══════════════════════════════════════════════════════════════════════════════


class TestCostBreakdown:
    def test_empty_breakdown_for_unknown_job(self) -> None:
        tracker = JobCostTracker()
        bd = tracker.get_cost_breakdown("nonexistent-job")
        assert bd["total_usd"] == 0.0
        assert bd["cpu_seconds"] == 0.0
        assert bd["browser_seconds"] == 0.0

    def test_full_breakdown_with_all_costs(self) -> None:
        tracker = JobCostTracker()
        tracker.record_cpu_time("job-1", seconds=10.0)
        tracker.record_browser_time("job-1", seconds=30.0)
        tracker.record_bytes_transferred("job-1", bytes_in=1_000_000, bytes_out=100_000)
        tracker.record_proxy_request("job-1", tier="residential")
        tracker.record_proxy_request("job-1", tier="datacenter")

        bd = tracker.get_cost_breakdown("job-1")

        # Verify structure
        assert "cpu_seconds" in bd
        assert "cpu_cost_usd" in bd
        assert "browser_seconds" in bd
        assert "browser_cost_usd" in bd
        assert "bytes_in" in bd
        assert "bytes_out" in bd
        assert "bandwidth_cost_usd" in bd
        assert "proxy_requests" in bd
        assert "proxy_cost_usd" in bd
        assert "total_usd" in bd

        # Verify calculations
        assert bd["cpu_seconds"] == pytest.approx(10.0, abs=0.01)
        assert bd["cpu_cost_usd"] == pytest.approx(10.0 * COST_PER_CPU_SECOND, abs=0.001)
        assert bd["browser_seconds"] == pytest.approx(30.0, abs=0.01)
        assert bd["browser_cost_usd"] == pytest.approx(30.0 * COST_PER_BROWSER_SECOND, abs=0.001)
        assert bd["bytes_in"] == 1_000_000
        assert bd["bytes_out"] == 100_000
        assert bd["proxy_requests"]["residential"]["requests"] == 1
        assert bd["proxy_requests"]["datacenter"]["requests"] == 1
        assert bd["total_usd"] > 0

    def test_total_is_sum_of_component_costs(self) -> None:
        tracker = JobCostTracker()
        tracker.record_cpu_time("job-1", seconds=5.0)
        tracker.record_browser_time("job-1", seconds=10.0)
        tracker.record_bytes_transferred("job-1", bytes_in=500_000, bytes_out=50_000)
        tracker.record_proxy_request("job-1", tier="mobile")

        bd = tracker.get_cost_breakdown("job-1")
        expected_total = bd["cpu_cost_usd"] + bd["browser_cost_usd"] + bd["bandwidth_cost_usd"] + bd["proxy_cost_usd"]
        assert bd["total_usd"] == pytest.approx(expected_total, abs=0.001)


# ═══════════════════════════════════════════════════════════════════════════════
# Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestFinalizeJob:
    def test_finalize_returns_breakdown_and_evicts(self) -> None:
        tracker = JobCostTracker()
        tracker.record_cpu_time("job-1", seconds=5.0)
        tracker.record_browser_time("job-1", seconds=3.0)

        bd = tracker.finalize_job("job-1")
        assert bd["cpu_seconds"] == pytest.approx(5.0, abs=0.01)
        assert bd["browser_seconds"] == pytest.approx(3.0, abs=0.01)

        # Record should be evicted after finalization
        assert tracker.get_raw_record("job-1") is None

    def test_finalize_unknown_job_returns_empty(self) -> None:
        tracker = JobCostTracker()
        bd = tracker.finalize_job("nonexistent")
        assert bd["total_usd"] == 0.0


class TestClear:
    def test_clear_drops_all_records(self) -> None:
        tracker = JobCostTracker()
        tracker.record_cpu_time("job-1", seconds=1.0)
        tracker.record_cpu_time("job-2", seconds=2.0)
        tracker.clear()
        assert tracker.get_raw_record("job-1") is None
        assert tracker.get_raw_record("job-2") is None


# ═══════════════════════════════════════════════════════════════════════════════
# Thread safety
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreadSafety:
    def test_concurrent_cpu_accumulation(self) -> None:
        tracker = JobCostTracker()
        errors: list[str] = []

        def worker():
            try:
                for _ in range(100):
                    tracker.record_cpu_time("job-concurrent", seconds=0.01)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        rec = tracker.get_raw_record("job-concurrent")
        assert rec is not None
        # 8 threads × 100 iterations × 0.01s = 8.0s
        assert rec.cpu_seconds == pytest.approx(8.0, abs=0.1)

    def test_concurrent_mixed_recordings(self) -> None:
        tracker = JobCostTracker()
        errors: list[str] = []

        def cpu_worker():
            try:
                for _ in range(50):
                    tracker.record_cpu_time("job-mixed", seconds=0.02)
            except Exception as e:
                errors.append(str(e))

        def browser_worker():
            try:
                for _ in range(50):
                    tracker.record_browser_time("job-mixed", seconds=0.01)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=cpu_worker), threading.Thread(target=browser_worker)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        rec = tracker.get_raw_record("job-mixed")
        assert rec is not None
        assert rec.cpu_seconds == pytest.approx(1.0, abs=0.1)
        assert rec.browser_seconds == pytest.approx(0.5, abs=0.1)


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetJobCostTracker:
    def test_singleton_returns_same_instance(self) -> None:
        t1 = get_job_cost_tracker()
        t2 = get_job_cost_tracker()
        assert t1 is t2

    def test_reset_creates_new_instance(self) -> None:
        t1 = get_job_cost_tracker()
        reset_job_cost_tracker()
        t2 = get_job_cost_tracker()
        assert t1 is not t2


# ═══════════════════════════════════════════════════════════════════════════════
# Memory caps
# ═══════════════════════════════════════════════════════════════════════════════


class TestMemoryCap:
    def test_evicts_oldest_when_cap_reached(self) -> None:
        tracker = JobCostTracker()
        tracker._MAX_TRACKED_JOBS = 3  # type: ignore[attr-defined]
        tracker.record_cpu_time("job-A", seconds=1.0)
        tracker.record_cpu_time("job-B", seconds=2.0)
        tracker.record_cpu_time("job-C", seconds=3.0)
        # Adding a 4th should evict job-A
        tracker.record_cpu_time("job-D", seconds=4.0)
        assert tracker.get_raw_record("job-A") is None
        assert tracker.get_raw_record("job-D") is not None
