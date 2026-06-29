from __future__ import annotations

from unittest.mock import patch

from app.config import settings
from app.proxy_manager import ProxyManager


class TestProxyHealthScoring:
    """Anti 22: Proxy health tracking, success rate, and eviction."""

    def _make_manager(self, proxies: list[str] | None = None) -> ProxyManager:
        import threading
        from collections import defaultdict

        mgr = ProxyManager.__new__(ProxyManager)
        mgr._lock = threading.Lock()
        if proxies is None:
            proxies = ["http://p1:8080", "http://p2:8080"]
        mgr._proxy_list = proxies
        mgr._current_index = 0
        mgr._failure_counts = defaultdict(int)
        mgr._success_counts = defaultdict(int)
        mgr._total_failure_counts = defaultdict(int)
        mgr._consecutive_failures = 0
        mgr._proxy_blocked_domains = defaultdict(set)
        mgr._enabled = True
        mgr._provider = None
        return mgr

    def test_record_failure_increments_count(self) -> None:
        mgr = self._make_manager()
        mgr.record_failure()
        key = "http://p1:8080"
        assert mgr._failure_counts[key] == 1
        assert mgr._total_failure_counts[key] == 1

    def test_record_success_increments_count(self) -> None:
        mgr = self._make_manager()
        mgr.record_success()
        key = "http://p1:8080"
        assert mgr._success_counts[key] == 1

    def test_record_success_decays_failure(self) -> None:
        mgr = self._make_manager()
        key = "http://p1:8080"
        mgr._failure_counts[key] = 5
        mgr.record_success()
        assert mgr._failure_counts[key] == 4

    def test_health_stats_returned(self) -> None:
        mgr = self._make_manager()
        mgr._failure_counts["http://p1:8080"] = 3
        mgr._success_counts["http://p1:8080"] = 7
        stats = mgr.get_health_stats()
        assert "http://p1:8080" in stats
        assert stats["http://p1:8080"]["success_rate"] == 70.0

    def test_health_stats_healthy_threshold(self) -> None:
        mgr = self._make_manager()
        mgr._success_counts["http://p1:8080"] = 8
        mgr._failure_counts["http://p1:8080"] = 2
        stats = mgr.get_health_stats()
        assert stats["http://p1:8080"]["health"] == "healthy"

    def test_health_stats_degraded_threshold(self) -> None:
        mgr = self._make_manager()
        mgr._success_counts["http://p1:8080"] = 4
        mgr._failure_counts["http://p1:8080"] = 6
        stats = mgr.get_health_stats()
        assert stats["http://p1:8080"]["health"] == "degraded"

    def test_health_stats_unhealthy_threshold(self) -> None:
        mgr = self._make_manager()
        mgr._success_counts["http://p1:8080"] = 1
        mgr._failure_counts["http://p1:8080"] = 9
        stats = mgr.get_health_stats()
        assert stats["http://p1:8080"]["health"] == "unhealthy"

    def test_eviction_after_total_failures(self) -> None:
        mgr = self._make_manager()
        key = "http://p1:8080"
        for _ in range(15):
            mgr._total_failure_counts[key] += 1
            mgr._failure_counts[key] += 1
        assert key in mgr._proxy_list
        mgr.record_failure()
        assert key not in mgr._proxy_list

    def test_failure_threshold_triggers_rotation(self) -> None:

        mgr = self._make_manager()
        key = "http://p1:8080"
        threshold = 5
        with patch.object(settings, "PROXY_ROTATION_FAILURE_THRESHOLD", threshold):
            mgr._failure_counts[key] = threshold
            with patch.object(mgr, "_rotate_locked", return_value="http://p2:8080") as mock:
                mgr.record_failure()
                mock.assert_called_once()

    def test_get_best_proxy_returns_healthiest(self) -> None:
        mgr = self._make_manager()
        mgr._success_counts["http://p1:8080"] = 9
        mgr._failure_counts["http://p1:8080"] = 1
        mgr._success_counts["http://p2:8080"] = 5
        mgr._failure_counts["http://p2:8080"] = 5
        best = mgr.get_best_proxy()
        assert best == "http://p1:8080"

    def test_enabled_false_skips_recording(self) -> None:
        mgr = self._make_manager()
        mgr._enabled = False
        mgr.record_failure()
        mgr.record_success()
        assert not mgr._failure_counts
        assert not mgr._success_counts

    def test_empty_proxy_list_no_crash(self) -> None:
        mgr = self._make_manager(proxies=[])
        mgr.record_failure()
        mgr.record_success()
        assert mgr.get_health_stats() == {}
