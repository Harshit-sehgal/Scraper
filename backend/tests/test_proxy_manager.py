"""Tests for app.proxy_manager — proxy rotation and health tracking."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.proxy_manager import ProxyManager, get_proxy_manager

# ─── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> ProxyManager:
    monkeypatch.setattr("app.config.settings.PROXY_ROTATION_ENABLED", True)
    monkeypatch.setattr(
        "app.config.settings.PROXY_LIST",
        "http://proxy1:8080,http://proxy2:8080,http://proxy3:8080",
    )
    monkeypatch.setattr("app.config.settings.PROXY_ROTATION_FAILURE_THRESHOLD", 3)
    return ProxyManager()


# ─── Initialisation ─────────────────────────────────────────────────────


class TestInit:
    def test_parses_proxy_list(self) -> None:
        with (
            patch("app.config.settings.PROXY_ROTATION_ENABLED", True),  # noqa: FBT003
            patch("app.config.settings.PROXY_LIST", "http://proxy1:8080,http://proxy2:8080,http://proxy3:8080"),
        ):
            pm = ProxyManager()
            assert pm.enabled is True
            assert len(pm._proxy_list) == 3

    def test_disabled_when_empty_list(self) -> None:
        with (
            patch("app.config.settings.PROXY_ROTATION_ENABLED", True),  # noqa: FBT003
            patch("app.config.settings.PROXY_LIST", ""),
        ):
            pm = ProxyManager()
            assert pm.enabled is False

    def test_disabled_when_rotation_off(self) -> None:
        with patch("app.config.settings.PROXY_ROTATION_ENABLED", False):  # noqa: FBT003
            pm = ProxyManager()
            assert pm.enabled is False


# ─── current_proxy ──────────────────────────────────────────────────────


class TestCurrentProxy:
    def test_returns_current(self, manager: ProxyManager) -> None:
        proxy = manager.current_proxy
        assert proxy == "http://proxy1:8080"

    def test_returns_none_when_disabled(self) -> None:
        pm = ProxyManager()
        assert pm.current_proxy is None


# ─── record_failure / record_success ────────────────────────────────────


class TestRecordFailure:
    def test_increments_failure_count(self, manager: ProxyManager) -> None:
        manager.record_failure()
        assert manager._failure_counts["http://proxy1:8080"] == 1

    def test_rotates_after_threshold(self, manager: ProxyManager) -> None:
        # Threshold is 3 — set failures to 2, then one more triggers rotation
        initial = manager.current_proxy
        manager._failure_counts[manager._proxy_list[manager._current_index]] = 2
        manager.record_failure()  # This should trigger rotation
        assert manager.current_proxy != initial, "Proxy should have rotated after hitting failure threshold"

    def test_resets_failure_after_success(self, manager: ProxyManager) -> None:
        manager.record_failure()
        manager.record_success()
        assert manager._failure_counts["http://proxy1:8080"] == 0


class TestRecordSuccess:
    def test_increments_success_count(self, manager: ProxyManager) -> None:
        manager.record_success()
        assert manager._success_counts["http://proxy1:8080"] == 1

    def test_resets_consecutive_failures(self, manager: ProxyManager) -> None:
        manager.record_failure()
        manager.record_success()
        assert manager._consecutive_failures == 0


# ─── rotate ─────────────────────────────────────────────────────────────


class TestRotate:
    def test_rotates_to_next(self, manager: ProxyManager) -> None:
        first = manager.current_proxy
        second = manager.rotate()
        assert second != first
        assert second == "http://proxy2:8080"

    def test_rotates_back_to_start(self, manager: ProxyManager) -> None:
        manager.rotate()
        manager.rotate()
        third = manager.rotate()  # index wraps around
        assert third == "http://proxy1:8080"

    def test_skips_blocked_domains(self, manager: ProxyManager) -> None:
        manager.rotate(domain="example.com")  # marks proxy1 blocked
        manager._proxy_blocked_domains["http://proxy2:8080"].add("example.com")
        next_proxy = manager.rotate(domain="example.com")
        # proxy1 and proxy2 blocked → should go to proxy3
        assert next_proxy == "http://proxy3:8080"

    def test_resets_all_blocked_when_all_blocked(self, manager: ProxyManager) -> None:
        for p in ["http://proxy1:8080", "http://proxy2:8080", "http://proxy3:8080"]:
            manager._proxy_blocked_domains[p].add("example.com")
        next_proxy = manager.rotate(domain="example.com")
        # All blocked → resets → goes to next in sequence
        assert next_proxy is not None

    def test_returns_none_when_disabled(self) -> None:
        pm = ProxyManager()
        assert pm.rotate() is None


# ─── get_best_proxy ─────────────────────────────────────────────────────


class TestGetBestProxy:
    def test_prefers_highest_success_rate(self, manager: ProxyManager) -> None:
        manager._success_counts["http://proxy2:8080"] = 10
        manager._failure_counts["http://proxy1:8080"] = 10
        best = manager.get_best_proxy()
        assert best == "http://proxy2:8080"

    def test_skips_blocked_proxies(self, manager: ProxyManager) -> None:
        manager._proxy_blocked_domains["http://proxy1:8080"].add("example.com")
        best = manager.get_best_proxy(domain="example.com")
        assert best != "http://proxy1:8080"

    def test_returns_none_when_disabled(self) -> None:
        pm = ProxyManager()
        assert pm.get_best_proxy() is None


# ─── get_health_stats ───────────────────────────────────────────────────


class TestGetHealthStats:
    def test_returns_stats_for_all_proxies(self, manager: ProxyManager) -> None:
        manager.record_success()
        stats = manager.get_health_stats()
        assert "http://proxy1:8080" in stats
        assert len(stats) == 3

    def test_healthy_threshold(self, manager: ProxyManager) -> None:
        manager._success_counts["http://proxy1:8080"] = 10
        manager._failure_counts["http://proxy1:8080"] = 1
        stats = manager.get_health_stats()
        assert stats["http://proxy1:8080"]["health"] == "healthy"

    def test_degraded_threshold(self, manager: ProxyManager) -> None:
        manager._success_counts["http://proxy1:8080"] = 3
        manager._failure_counts["http://proxy1:8080"] = 7
        stats = manager.get_health_stats()
        assert stats["http://proxy1:8080"]["health"] == "degraded"

    def test_unhealthy_threshold(self, manager: ProxyManager) -> None:
        manager._success_counts["http://proxy1:8080"] = 1
        manager._failure_counts["http://proxy1:8080"] = 9
        stats = manager.get_health_stats()
        assert stats["http://proxy1:8080"]["health"] == "unhealthy"


# ─── get_proxy_for_playwright ────────────────────────────────────────────


class TestGetProxyForPlaywright:
    def test_returns_config_dict(self, manager: ProxyManager) -> None:
        config = manager.get_proxy_for_playwright()
        assert config == {"server": "http://proxy1:8080"}

    def test_returns_none_when_disabled(self) -> None:
        pm = ProxyManager()
        assert pm.get_proxy_for_playwright() is None


# ─── Singleton ──────────────────────────────────────────────────────────


def test_get_proxy_manager_singleton() -> None:
    pm1 = get_proxy_manager()
    pm2 = get_proxy_manager()
    assert pm1 is pm2
