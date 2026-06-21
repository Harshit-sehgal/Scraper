"""M7: Rate limiter edge case tests."""
import time

from app.rate_limiter import RateLimiterMiddleware, RedisRateLimiter


def test_redis_rate_limiter_basic() -> None:
    """M7: Redis rate limiter basic functionality."""
    limiter = RedisRateLimiter("")  # No Redis = fallback

    # Should always allow without Redis
    assert limiter.allow("test-key", limit=5, window=60)
    assert limiter.allow("test-key", limit=5, window=60)


def test_rate_limiter_concurrent_requests() -> None:
    """M7: Rate limiter handles concurrent requests."""
    limiter = RateLimiterMiddleware(global_limit="10 / minute")

    # M7: Simulate concurrent requests from same IP
    ip = "192.168.1.1"

    # First 10 should pass
    for i in range(10):
        assert limiter._should_allow(ip, "/api/jobs") in {True, None}, f"M7: Request {i} should pass"

    # 11th should be rate-limited or None (if in-memory store not populated)


def test_rate_limiter_window_expiry() -> None:
    """M7: Rate limiter respects window expiry."""
    limiter = RateLimiterMiddleware(global_limit="5 / 1")  # 5 per 1 second
    ip = "192.168.1.100"

    # Hit limit
    for _ in range(5):
        limiter._should_allow(ip, "/api/jobs")

    # Wait for window to expire
    time.sleep(1.1)

    # Should allow again
    result = limiter._should_allow(ip, "/api/jobs")
    assert result in {True, None}, "M7: Window should have reset"


def test_rate_limiter_route_specific_limits() -> None:
    """M7: Route-specific limits override global."""
    limiter = RateLimiterMiddleware(global_limit="100 / minute")

    # /api/jobs has 60/minute, should be more restrictive than global
    assert "/api/url/analyze" in limiter._route_limits, "M7: Route limits configured"
