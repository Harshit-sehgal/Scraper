# ───────────────────────────────────────────────────────────────────────
# Pure-logic unit tests for uncovered rate limiter methods
# ───────────────────────────────────────────────────────────────────────


from app.rate_limiter import (
    DatabaseSlidingWindowCounter,
    RateLimiterMiddleware,
    SlidingWindowCounter,
    _parse_rate_limit,
)


class TestParseRateLimit:
    """Tests for the _parse_rate_limit pure function."""

    def test_parses_minute(self) -> None:
        assert _parse_rate_limit("100/minute") == (100, 60.0)
        assert _parse_rate_limit("5/minutes") == (5, 60.0)
        assert _parse_rate_limit("50/m") == (50, 60.0)

    def test_parses_second(self) -> None:
        assert _parse_rate_limit("10/second") == (10, 1.0)
        assert _parse_rate_limit("30/seconds") == (30, 1.0)
        assert _parse_rate_limit("1/s") == (1, 1.0)

    def test_parses_hour(self) -> None:
        assert _parse_rate_limit("1000/hour") == (1000, 3600.0)
        assert _parse_rate_limit("500/hours") == (500, 3600.0)
        assert _parse_rate_limit("100/h") == (100, 3600.0)

    def test_returns_zero_on_invalid_input(self) -> None:
        assert _parse_rate_limit("") == (0, 0)
        assert _parse_rate_limit("not-a-number/minute") == (0, 0)
        assert _parse_rate_limit("100/decade") == (0, 0)
        assert _parse_rate_limit("invalid-format") == (0, 0)
        assert _parse_rate_limit(None) == (0, 0)  # type: ignore[arg-type]
        assert _parse_rate_limit(123) == (0, 0)  # type: ignore[arg-type]


class TestSlidingWindowCounter:
    """Tests for the in-memory SlidingWindowCounter."""

    def test_allows_up_to_limit(self) -> None:
        counter = SlidingWindowCounter(max_requests=3, window_seconds=60.0)
        assert counter.allow() is True
        assert counter.allow() is True
        assert counter.allow() is True
        assert counter.allow() is False  # 4th request exceeds limit

    def test_remaining_decreases(self) -> None:
        counter = SlidingWindowCounter(max_requests=5, window_seconds=60.0)
        assert counter.remaining() == 5
        counter.allow()
        assert counter.remaining() == 4
        counter.allow()
        assert counter.remaining() == 3

    def test_reset_in_returns_time(self) -> None:
        counter = SlidingWindowCounter(max_requests=3, window_seconds=60.0)
        assert counter.reset_in() == 0.0  # No timestamps yet
        counter.allow()
        assert counter.reset_in() > 0.0
        assert counter.reset_in() <= 60.0

    def test_is_expired_no_activity(self) -> None:
        counter = SlidingWindowCounter(max_requests=3, window_seconds=60.0)
        assert counter.is_expired() is True

    def test_is_expired_with_recent_activity(self) -> None:
        counter = SlidingWindowCounter(max_requests=3, window_seconds=60.0)
        counter.allow()
        assert counter.is_expired() is False


class TestRateLimiterMiddlewareUnit:
    """Tests for RateLimiterMiddleware pure-logic methods."""

    def test_disabled_when_no_global_limit(self) -> None:
        rl = RateLimiterMiddleware(global_limit="")
        stats = rl.get_stats()
        assert stats["enabled"] is False

    def test_get_stats_returns_route_limits(self) -> None:
        rl = RateLimiterMiddleware(global_limit="100/minute")
        stats = rl.get_stats()
        assert stats["enabled"] is True
        assert stats["global_limit_per_window"] == 100
        assert stats["global_window_seconds"] == 60.0
        assert "/api/jobs" in stats["route_limits"]
        assert stats["active_keys"] == 0

    def test_get_stats_per_ip_enabled(self) -> None:
        rl = RateLimiterMiddleware(
            global_limit="10000/minute",
            per_ip=True,
            per_ip_limit="100/minute",
        )
        stats = rl.get_stats()
        assert stats["per_ip_enabled"] is True
        assert stats["per_ip_limit_per_window"] == 100
        assert stats["per_ip_window_seconds"] == 60.0

    def test_get_stats_per_ip_disabled(self) -> None:
        rl = RateLimiterMiddleware(
            global_limit="10000/minute",
            per_ip=False,
        )
        stats = rl.get_stats()
        assert stats["per_ip_enabled"] is False
        assert stats["per_ip_limit_per_window"] == 0

    def test_get_stats_only_per_ip(self) -> None:
        """Rate limiter can be enabled with only a per-IP limit and no global."""
        rl = RateLimiterMiddleware(
            global_limit="",
            per_ip=True,
            per_ip_limit="50/minute",
        )
        stats = rl.get_stats()
        assert stats["enabled"] is True
        assert stats["global_limit_per_window"] == 0
        assert stats["per_ip_enabled"] is True
        assert stats["per_ip_limit_per_window"] == 50

    def test_reset_clears_counters(self) -> None:
        rl = RateLimiterMiddleware(global_limit="10/minute")
        # Access a key to create a counter
        key = "test:POST:127.0.0.1"
        rl._counters[key] = SlidingWindowCounter(10, 60.0)
        assert len(rl._counters) == 1
        rl.reset()
        assert len(rl._counters) == 0

    def test_get_limits_for_path(self, monkeypatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "RATE_LIMIT_JOB_CREATE", None)
        rl = RateLimiterMiddleware(global_limit="100/minute")
        max_req, window = rl._get_limits_for_path("/api/jobs")
        assert max_req == 60  # Route-specific limit (stricter than global)
        assert window == 60.0

    def test_get_limits_for_default_path(self) -> None:
        rl = RateLimiterMiddleware(global_limit="50/minute")
        max_req, window = rl._get_limits_for_path("/api/some-unmounted-path")
        assert max_req == 50  # Falls back to global
        assert window == 60.0

    def test_database_counter_has_fallback(self) -> None:
        """DatabaseSlidingWindowCounter initializes with an in-memory fallback."""
        counter = DatabaseSlidingWindowCounter(max_requests=10, window_seconds=60.0, key="test")
        assert counter._fallback_counter is not None
        assert counter._fallback_counter.max_requests == 10
        assert counter._fallback_counter.allow() is True
        assert counter._fallback_counter.remaining() == 9
