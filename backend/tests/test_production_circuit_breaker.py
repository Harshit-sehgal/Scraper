from __future__ import annotations

import pytest
from app.rate_limiter import (
    DatabaseSlidingWindowCounter,
    RateLimiterMiddleware,
    SlidingWindowCounter,
)


class TestSlidingWindowCounter:
    def test_allows_within_limit(self) -> None:
        c = SlidingWindowCounter(5, 10.0)
        for _ in range(5):
            assert c.allow() is True

    def test_denies_when_exceeded(self) -> None:
        c = SlidingWindowCounter(3, 60.0)
        for _ in range(3):
            c.allow()
        assert c.allow() is False

    def test_remaining_counts_down(self) -> None:
        c = SlidingWindowCounter(5, 60.0)
        assert c.remaining() == 5
        c.allow()
        assert c.remaining() == 4
        for _ in range(4):
            c.allow()
        assert c.remaining() == 0

    def test_reset_in_returns_zero_when_empty(self) -> None:
        c = SlidingWindowCounter(5, 60.0)
        assert c.reset_in() == 0.0

    def test_is_expired_when_empty(self) -> None:
        c = SlidingWindowCounter(5, 60.0)
        assert c.is_expired() is True

    def test_not_expired_with_recent_activity(self) -> None:
        c = SlidingWindowCounter(5, 60.0)
        c.allow()
        assert c.is_expired() is False


class TestRateLimiterLRUCap:
    def test_lru_eviction_with_many_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_RATE_LIMITER_MAX_COUNTERS", "3")
        rl = RateLimiterMiddleware(global_limit="100/minute", per_ip=False)
        assert len(rl._counters) == 0
        keys = [f"key{i}" for i in range(5)]
        for k in keys:
            rl._get_or_create_counter(k, 100, 60.0)
        assert len(rl._counters) <= 3


class TestDatabaseSlidingWindowCounter:
    def test_fallback_counter_used_when_uninitialized(self) -> None:
        c = DatabaseSlidingWindowCounter(3, 60.0, "test_key_cb_001")
        assert c._fallback_counter is not None
        assert c._fallback_counter.max_requests == 3

    def test_allow_falls_back_to_in_memory(self) -> None:
        c = DatabaseSlidingWindowCounter(100, 60.0, "test_fallback_cb_002")
        assert c.allow() is True


class TestCircuitBreakerPattern:
    def test_rate_limiter_disabled_when_no_limits(self) -> None:
        rl = RateLimiterMiddleware(global_limit="", per_ip=False)
        assert rl._global_max == 0
        assert rl._per_ip_max == 0
        stats = rl.get_stats()
        assert stats["enabled"] is False
