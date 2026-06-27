"""Dead proxy eviction — verify permanently failed proxies are removed from pool.

Tests that ProxyManager._evict_proxy is called when cumulative failures
exceed _EVICTION_TOTAL_FAILURES, and that evicted proxies:
- Are removed from _proxy_list
- Have all tracking state cleaned up
- Don't cause IndexError on subsequent rotation
"""

from __future__ import annotations

from app.proxy_manager import ProxyManager


class TestProxyDeadEviction:
    """Verify proxy eviction logic."""

    def test_single_batch_failure_does_not_evict(self) -> None:
        """A one-time batch of failures below eviction threshold must not evict."""
        mgr = ProxyManager()
        mgr._proxy_list = ["http://proxy1:8080", "http://proxy2:8080"]
        mgr._enabled = True

        # Failures within rotation threshold (PROXY_ROTATION_FAILURE_THRESHOLD)
        for _ in range(3):
            mgr.record_failure("http://proxy1:8080")

        assert "http://proxy1:8080" in mgr._proxy_list
        # Cumulative failures = 3, which is < _EVICTION_TOTAL_FAILURES (15)
        assert mgr._total_failure_counts["http://proxy1:8080"] < mgr._EVICTION_TOTAL_FAILURES

    def test_cumulative_failures_evict(self) -> None:
        """Cumulative failures across rotates must eventually evict the proxy."""
        mgr = ProxyManager()
        mgr._proxy_list = ["http://proxy1:8080", "http://proxy2:8080"]
        mgr._enabled = True

        eviction_threshold = mgr._EVICTION_TOTAL_FAILURES
        proxy = "http://proxy1:8080"

        for i in range(eviction_threshold):
            # Record failures, rotating periodically to simulate
            # the real rotation-after-threshold behavior
            mgr.record_failure(proxy)

        assert proxy not in mgr._proxy_list, f"Proxy {proxy} should be evicted after {eviction_threshold} cumulative failures"

    def test_evicted_proxy_state_cleaned(self) -> None:
        """All tracking state must be cleaned up on eviction."""
        mgr = ProxyManager()
        mgr._proxy_list = ["http://proxy1:8080", "http://proxy2:8080"]
        mgr._enabled = True

        proxy = "http://proxy1:8080"
        # Push it past eviction
        for _ in range(mgr._EVICTION_TOTAL_FAILURES):
            mgr.record_failure(proxy)

        assert proxy not in mgr._failure_counts
        assert proxy not in mgr._success_counts
        assert proxy not in mgr._total_failure_counts
        assert proxy not in mgr._proxy_blocked_domains

    def test_rotation_after_eviction(self) -> None:
        """Rotation must work correctly after eviction (no IndexError)."""
        mgr = ProxyManager()
        mgr._proxy_list = ["http://proxy1:8080", "http://proxy2:8080"]
        mgr._enabled = True

        # Evict proxy1
        for _ in range(mgr._EVICTION_TOTAL_FAILURES):
            mgr.record_failure("http://proxy1:8080")

        assert "http://proxy1:8080" not in mgr._proxy_list
        assert len(mgr._proxy_list) == 1
        assert mgr._proxy_list[0] == "http://proxy2:8080"

        # Rotation after eviction should work on the remaining proxy
        new_proxy = mgr.rotate()
        assert new_proxy == "http://proxy2:8080"

    def test_last_proxy_eviction_disables(self) -> None:
        """When all proxies are evicted, proxy rotation must be disabled."""
        mgr = ProxyManager()
        mgr._proxy_list = ["http://proxy1:8080"]
        mgr._enabled = True

        for _ in range(mgr._EVICTION_TOTAL_FAILURES):
            mgr.record_failure("http://proxy1:8080")

        assert mgr._enabled is False
        assert len(mgr._proxy_list) == 0

    def test_evicted_proxy_not_returned_by_get_best(self) -> None:
        """get_best_proxy must not return an evicted proxy."""
        mgr = ProxyManager()
        mgr._proxy_list = [
            "http://proxy1:8080",
            "http://proxy2:8080",
            "http://proxy3:8080",
        ]
        mgr._enabled = True

        # Record some successes on proxy2 & proxy3 to make them preferred
        mgr._success_counts["http://proxy2:8080"] = 10
        mgr._success_counts["http://proxy3:8080"] = 5

        # Evict proxy1
        for _ in range(mgr._EVICTION_TOTAL_FAILURES):
            mgr.record_failure("http://proxy1:8080")

        best = mgr.get_best_proxy()
        assert best is not None
        assert "proxy1" not in best

    def test_non_pool_proxy_noop(self) -> None:
        """A proxy not in the pool cannot be evicted (no crash)."""
        mgr = ProxyManager()
        mgr._proxy_list = ["http://proxy1:8080"]
        mgr._enabled = True

        # This should not crash
        mgr._evict_proxy("http://not-in-pool:8080")
        assert len(mgr._proxy_list) == 1

    def test_record_failure_on_disabled_manager_noop(self) -> None:
        """record_failure on disabled manager must not track or evict."""
        mgr = ProxyManager()
        mgr._proxy_list = []
        mgr._enabled = False

        for _ in range(100):
            mgr.record_failure("http://proxy1:8080")

        # Should not crash and no state changes
        assert not mgr._total_failure_counts
