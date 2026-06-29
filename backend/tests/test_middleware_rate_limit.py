"""Tests for the rate limit middleware (Roadmap Prod 3 / Wave 10 Polish).

Tests that rate limiter correctly enforces global and per-IP
limits, resets counters, attaches headers, and allows bypass
for trusted IPs.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.rate_limiter import RateLimiterMiddleware, SlidingWindowCounter


class TestSlidingWindowCounter:
    """Pure unit tests for the in-memory sliding window counter."""

    def test_allows_up_to_limit(self) -> None:
        c = SlidingWindowCounter(5, 60.0)
        for _ in range(5):
            assert c.allow() is True
        assert c.allow() is False

    def test_remaining_after_requests(self) -> None:
        c = SlidingWindowCounter(10, 60.0)
        assert c.remaining() == 10
        c.allow()
        assert c.remaining() == 9
        c.allow()
        c.allow()
        assert c.remaining() == 7

    def test_reset_in_returns_zero_when_empty(self) -> None:
        c = SlidingWindowCounter(5, 60.0)
        assert c.reset_in() == 0.0

    def test_reset_in_returns_positive_after_request(self) -> None:
        c = SlidingWindowCounter(5, 60.0)
        c.allow()
        assert c.reset_in() > 0.0
        assert c.reset_in() <= 60.0

    def test_is_expired_no_activity(self) -> None:
        c = SlidingWindowCounter(5, 60.0)
        assert c.is_expired() is True

    def test_not_expired_after_request(self) -> None:
        c = SlidingWindowCounter(5, 60.0)
        c.allow()
        assert c.is_expired() is False

    def test_window_slides_after_window_passes(self) -> None:
        c = SlidingWindowCounter(2, 0.05)
        assert c.allow() is True
        assert c.allow() is True
        assert c.allow() is False
        time.sleep(0.06)
        assert c.allow() is True

    def test_remaining_exhausted(self) -> None:
        c = SlidingWindowCounter(3, 60.0)
        c.allow()
        c.allow()
        c.allow()
        assert c.remaining() == 0
        assert c.allow() is False


class TestRateLimiterMiddleware:
    """Tests for RateLimiterMiddleware dispatch and stats."""

    def test_disabled_when_no_limits(self) -> None:
        rl = RateLimiterMiddleware(global_limit="")
        stats = rl.get_stats()
        assert stats["enabled"] is False

    def test_global_limit_parsed(self) -> None:
        rl = RateLimiterMiddleware(global_limit="1000/minute")
        stats = rl.get_stats()
        assert stats["global_limit_per_window"] == 1000
        assert stats["global_window_seconds"] == 60.0

    def test_per_ip_limit_parsed(self) -> None:
        rl = RateLimiterMiddleware(global_limit="10000/minute", per_ip=True, per_ip_limit="50/minute")
        stats = rl.get_stats()
        assert stats["per_ip_enabled"] is True
        assert stats["per_ip_limit_per_window"] == 50

    def test_route_limits_in_stats(self) -> None:
        rl = RateLimiterMiddleware(global_limit="100/minute")
        stats = rl.get_stats()
        assert "/api/jobs" in stats["route_limits"]

    def test_rate_limit_headers_format(self) -> None:
        counter = MagicMock(spec=SlidingWindowCounter)
        counter.max_requests = 100
        counter.remaining.return_value = 95
        counter.reset_in.return_value = 30.0

        rl = RateLimiterMiddleware(global_limit="100/minute")
        response = MagicMock()
        response.headers = {}
        rl._add_rate_limit_headers(response, counter)
        assert response.headers["X-RateLimit-Limit"] == "100"
        assert response.headers["X-RateLimit-Remaining"] == "95"
        assert int(response.headers["X-RateLimit-Reset"]) > 0

    def test_build_429_response_has_headers(self) -> None:
        counter = MagicMock(spec=SlidingWindowCounter)
        counter.max_requests = 10
        counter.remaining.return_value = 0
        counter.reset_in.return_value = 45.0
        counter.window_seconds = 60.0

        rl = RateLimiterMiddleware(global_limit="10/minute")
        resp = rl._build_429_response(counter, "192.168.1.1", "/api/jobs")
        assert resp.status_code == 429
        body = resp.body.decode()
        assert "Rate limit exceeded" in body
        assert "retry_after_seconds" in body
        assert resp.headers["X-RateLimit-Limit"] == "10"
        assert resp.headers["X-RateLimit-Remaining"] == "0"
        assert resp.headers["Retry-After"] == "45"

    def test_get_stats_active_keys(self) -> None:
        rl = RateLimiterMiddleware(global_limit="100/minute")
        c1 = rl._get_or_create_counter("test:key1", 100, 60.0)
        c2 = rl._get_or_create_counter("test:key2", 100, 60.0)
        c1.allow()
        c2.allow()
        stats = rl.get_stats()
        assert stats["active_keys"] == 2

    def test_reset_clears_counters(self) -> None:
        rl = RateLimiterMiddleware(global_limit="100/minute")
        rl._get_or_create_counter("test:k", 100, 60.0)
        assert len(rl._counters) == 1
        rl.reset()
        assert len(rl._counters) == 0

    @pytest.mark.asyncio
    async def test_middleware_bypasses_non_api_paths(self) -> None:
        rl = RateLimiterMiddleware(global_limit="1/minute")
        request = MagicMock()
        request.url.path = "/health"
        request.method = "GET"
        call_next = AsyncMock(return_value=MagicMock())
        _response = await rl.middleware(request, call_next)
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_middleware_bypasses_docs_paths(self) -> None:
        rl = RateLimiterMiddleware(global_limit="1/minute")
        request = MagicMock()
        request.url.path = "/docs"
        request.method = "GET"
        call_next = AsyncMock(return_value=MagicMock())
        _response = await rl.middleware(request, call_next)
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_openapi_path_bypassed(self) -> None:
        rl = RateLimiterMiddleware(global_limit="1/minute")
        request = MagicMock()
        request.url.path = "/openapi.json"
        request.method = "GET"
        call_next = AsyncMock(return_value=MagicMock())
        _response = await rl.middleware(request, call_next)
        call_next.assert_awaited_once()

    def test_trusted_proxy_detection(self) -> None:
        from app.rate_limiter import _is_trusted_proxy

        assert _is_trusted_proxy("127.0.0.1") is True
        assert _is_trusted_proxy("::1") is True
        assert _is_trusted_proxy("8.8.8.8") is False
        assert _is_trusted_proxy("") is False
        assert _is_trusted_proxy("not-an-ip") is False

    def test_limit_parsing(self) -> None:
        from app.rate_limiter import _parse_rate_limit

        assert _parse_rate_limit("100 / minute") == (100, 60.0)
        assert _parse_rate_limit("5/second") == (5, 1.0)
        assert _parse_rate_limit("1000/hour") == (1000, 3600.0)
        assert _parse_rate_limit("") == (0, 0)
        assert _parse_rate_limit("invalid") == (0, 0)

    def test_get_limits_for_path_returns_correct(self) -> None:
        rl = RateLimiterMiddleware(global_limit="10000/minute")
        max_r, window = rl._get_limits_for_path("/api/jobs", "POST")
        assert max_r <= 60
        assert window == 60.0

    def test_get_limits_for_path_default(self) -> None:
        rl = RateLimiterMiddleware(global_limit="10000/minute")
        max_r, window = rl._get_limits_for_path("/api/unknown", "GET")
        assert max_r == 10000
        assert window == 60.0
