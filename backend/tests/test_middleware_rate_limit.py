"""Tests for the rate limit middleware (Roadmap Prod 3 / Wave 10 Polish).

Tests that rate limiter correctly enforces global and per-IP
limits, resets counters, attaches headers, and allows bypass
for trusted IPs.

Item 29: RFC 6585 X-RateLimit-* headers on every API response.
Item 9:  Job-level rate limiting (per-user concurrency, domain cooldown).
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.rate_limiter import (
    DomainCooldownTracker,
    JobRateLimiter,
    RateLimiterMiddleware,
    SlidingWindowCounter,
)


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

    def test_window_slides_after_window_passes(self, monkeypatch) -> None:
        c = SlidingWindowCounter(2, 0.05)
        assert c.allow() is True
        assert c.allow() is True
        assert c.allow() is False
        # Deterministic clock advance instead of time.sleep(0.06) which is slow
        # and flaky under CPU contention (window_seconds=0.05 is easily missed).
        # Capture the original time.time before patching to avoid recursive capture.
        original_time = time.time
        monkeypatch.setattr("time.time", lambda: original_time() + 0.06)
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
        body = bytes(resp.body).decode()
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
        await rl.middleware(request, call_next)
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_middleware_bypasses_docs_paths(self) -> None:
        rl = RateLimiterMiddleware(global_limit="1/minute")
        request = MagicMock()
        request.url.path = "/docs"
        request.method = "GET"
        call_next = AsyncMock(return_value=MagicMock())
        await rl.middleware(request, call_next)
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_openapi_path_bypassed(self) -> None:
        rl = RateLimiterMiddleware(global_limit="1/minute")
        request = MagicMock()
        request.url.path = "/openapi.json"
        request.method = "GET"
        call_next = AsyncMock(return_value=MagicMock())
        await rl.middleware(request, call_next)
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


# ─── Item 29: RFC 6585 X-RateLimit-* header tests ────────────────────────


class TestRateLimitHeadersOnAllResponses:
    """Item 29: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
    must appear on every /api/ response, including when rate limiting is
    disabled (stub values) and on successful non-429 responses.
    """

    @pytest.mark.asyncio
    async def test_headers_on_success_response(self) -> None:
        """Successful API responses must carry X-RateLimit-* headers."""
        rl = RateLimiterMiddleware(global_limit="100/minute", per_ip=True, per_ip_limit="10/minute")
        request = MagicMock()
        request.url.path = "/api/jobs"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {}

        response = MagicMock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)
        result = await rl.middleware(request, call_next)

        assert "X-RateLimit-Limit" in result.headers
        assert "X-RateLimit-Remaining" in result.headers
        assert "X-RateLimit-Reset" in result.headers
        # Limit should be parseable as an integer
        int(result.headers["X-RateLimit-Limit"])
        int(result.headers["X-RateLimit-Remaining"])
        int(result.headers["X-RateLimit-Reset"])

    @pytest.mark.asyncio
    async def test_headers_on_disabled_limiter(self) -> None:
        """When rate limiting is disabled, API responses still get stub headers."""
        rl = RateLimiterMiddleware(global_limit="")
        request = MagicMock()
        request.url.path = "/api/jobs"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {}

        response = MagicMock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)
        result = await rl.middleware(request, call_next)

        assert "X-RateLimit-Limit" in result.headers
        assert "X-RateLimit-Remaining" in result.headers
        assert "X-RateLimit-Reset" in result.headers
        # Disabled limiter reports 0 (unlimited / not enforced)
        assert result.headers["X-RateLimit-Limit"] == "0"

    @pytest.mark.asyncio
    async def test_headers_not_on_non_api_paths(self) -> None:
        """Non-API paths (e.g. /health, /static) should NOT get rate limit headers."""
        rl = RateLimiterMiddleware(global_limit="100/minute")
        request = MagicMock()
        request.url.path = "/health"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {}

        response = MagicMock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)
        result = await rl.middleware(request, call_next)

        assert "X-RateLimit-Limit" not in result.headers

    @pytest.mark.asyncio
    async def test_429_response_has_all_headers(self) -> None:
        """429 responses must include all three X-RateLimit-* headers plus Retry-After."""
        rl = RateLimiterMiddleware(global_limit="1/minute")
        request = MagicMock()
        request.url.path = "/api/jobs"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {}

        # Exhaust the global limit
        response_ok = MagicMock()
        response_ok.headers = {}
        call_next_ok = AsyncMock(return_value=response_ok)
        await rl.middleware(request, call_next_ok)

        # Next request should be 429
        call_next_429 = AsyncMock(return_value=MagicMock())
        result = await rl.middleware(request, call_next_429)

        assert result.status_code == 429
        assert "X-RateLimit-Limit" in result.headers
        assert "X-RateLimit-Remaining" in result.headers
        assert "X-RateLimit-Reset" in result.headers
        assert "Retry-After" in result.headers
        assert result.headers["X-RateLimit-Remaining"] == "0"

    @pytest.mark.asyncio
    async def test_per_ip_headers_take_priority(self) -> None:
        """When both global and per-IP counters exist, per-IP headers are returned."""
        rl = RateLimiterMiddleware(
            global_limit="10000/minute",
            per_ip=True,
            per_ip_limit="5/minute",
        )
        request = MagicMock()
        request.url.path = "/api/jobs"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "1.2.3.4"
        request.headers = {}

        response = MagicMock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)
        result = await rl.middleware(request, call_next)

        # Per-IP limit is 5/minute, so the header should show that
        assert int(result.headers["X-RateLimit-Limit"]) == 5

    def test_disabled_header_static_method(self) -> None:
        """_add_disabled_rate_limit_headers sets correct stub values."""
        response = MagicMock()
        response.headers = {}
        RateLimiterMiddleware._add_disabled_rate_limit_headers(response)
        assert response.headers["X-RateLimit-Limit"] == "0"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert int(response.headers["X-RateLimit-Reset"]) > 0

    def test_disabled_header_with_global_values(self) -> None:
        """_add_disabled_rate_limit_headers with global values still works."""
        response = MagicMock()
        response.headers = {}
        RateLimiterMiddleware._add_disabled_rate_limit_headers(
            response,
            global_max=100,
            global_window=60.0,
        )
        assert response.headers["X-RateLimit-Limit"] == "100"
        assert response.headers["X-RateLimit-Remaining"] == "100"


# ─── Item 9: DomainCooldownTracker tests ──────────────────────────────────


class TestDomainCooldownTracker:
    """Tests for DomainCooldownTracker (per-domain cooldown enforcement)."""

    def test_first_hit_allowed(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=1.0)
        allowed, wait = tracker.check("example.com")
        assert allowed is True
        assert wait == 0.0

    def test_subsequent_hit_blocked(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=10.0)
        tracker.record_hit("example.com")
        allowed, wait = tracker.check("example.com")
        assert allowed is False
        assert wait > 0.0

    def test_cooldown_expires(self, monkeypatch) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=0.05)
        tracker.record_hit("example.com")
        # Deterministic clock advance: skip the real 0.06s sleep.
        original_time = time.time
        monkeypatch.setattr("time.time", lambda: original_time() + 0.06)
        allowed, wait = tracker.check("example.com")
        assert allowed is True
        assert wait == 0.0

    def test_different_domains_independent(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=10.0)
        tracker.record_hit("example.com")
        allowed, _ = tracker.check("other.com")
        assert allowed is True

    def test_custom_cooldown_overrides_default(self, monkeypatch) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=10.0)
        tracker.record_hit("example.com")
        # Deterministic clock advance instead of time.sleep(0.005).
        original_time = time.time
        monkeypatch.setattr("time.time", lambda: original_time() + 0.005)
        allowed, _ = tracker.check("example.com", cooldown_seconds=0.001)
        assert allowed is True

    def test_wait_if_needed_blocks(self, monkeypatch) -> None:
        # wait_if_needed's internal time.sleep is incidental — the returned
        # `waited` value comes from check(), not the actual sleep duration.
        # Mock time.sleep to keep the test fast and skip the wall-clock wait.
        monkeypatch.setattr("time.sleep", lambda _seconds: None)
        tracker = DomainCooldownTracker(default_cooldown_seconds=0.1)
        tracker.record_hit("example.com")
        waited = tracker.wait_if_needed("example.com")
        assert waited > 0.0

    def test_wait_if_needed_no_wait(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=10.0)
        waited = tracker.wait_if_needed("example.com")
        assert waited == 0.0

    @pytest.mark.asyncio
    async def test_async_wait_if_needed(self, monkeypatch) -> None:
        # async_wait_if_needed's asyncio.sleep is incidental — the returned
        # `waited` value comes from check(). Mock asyncio.sleep to keep the
        # test fast and skip the wall-clock wait.
        async def _fake_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr("asyncio.sleep", _fake_sleep)
        tracker = DomainCooldownTracker(default_cooldown_seconds=0.05)
        tracker.record_hit("example.com")
        waited = await tracker.async_wait_if_needed("example.com")
        assert waited > 0.0

    def test_get_domain_last_hit(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=10.0)
        tracker.record_hit("example.com")
        last_hit = tracker.get_domain_last_hit("example.com")
        assert last_hit > 0.0
        assert tracker.get_domain_last_hit("unknown.com") == 0.0

    def test_reset_specific_domain(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=10.0)
        tracker.record_hit("a.com")
        tracker.record_hit("b.com")
        tracker.reset("a.com")
        assert tracker.get_domain_last_hit("a.com") == 0.0
        assert tracker.get_domain_last_hit("b.com") > 0.0

    def test_reset_all_domains(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=10.0)
        tracker.record_hit("a.com")
        tracker.record_hit("b.com")
        tracker.reset()
        assert tracker.tracked_domains == 0

    def test_tracked_domains_count(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=10.0)
        assert tracker.tracked_domains == 0
        tracker.record_hit("a.com")
        assert tracker.tracked_domains == 1
        tracker.record_hit("b.com")
        assert tracker.tracked_domains == 2


# ─── Item 9: JobRateLimiter tests ──────────────────────────────────────────


class TestJobRateLimiter:
    """Tests for JobRateLimiter (per-user concurrency cap + domain cooldown)."""

    def test_acquire_slot_within_cap(self) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=5)
        assert limiter.acquire_job_slot("user1") is True
        assert limiter.get_user_active_jobs("user1") == 1

    def test_acquire_slot_at_cap(self) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=3)
        assert limiter.acquire_job_slot("user1") is True
        assert limiter.acquire_job_slot("user1") is True
        assert limiter.acquire_job_slot("user1") is True
        # 4th should fail
        assert limiter.acquire_job_slot("user1") is False
        assert limiter.get_user_active_jobs("user1") == 3

    def test_different_users_independent(self) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=2)
        assert limiter.acquire_job_slot("user1") is True
        assert limiter.acquire_job_slot("user1") is True
        # user2 has separate cap
        assert limiter.acquire_job_slot("user2") is True
        assert limiter.acquire_job_slot("user2") is True

    def test_release_and_reacquire(self) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=1)
        assert limiter.acquire_job_slot("user1") is True
        assert limiter.acquire_job_slot("user1") is False
        limiter.release_job_slot("user1")
        assert limiter.acquire_job_slot("user1") is True

    def test_release_below_zero_safe(self) -> None:
        """Releasing when count is 0 should not go negative."""
        limiter = JobRateLimiter(max_concurrent_per_user=5)
        limiter.release_job_slot("user1")  # should not raise
        assert limiter.get_user_active_jobs("user1") == 0

    def test_domain_check_allowed_initially(self) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=5, default_domain_cooldown_seconds=2.0)
        allowed, wait = limiter.check_domain_before_fetch("user1", "example.com")
        assert allowed is True
        assert wait == 0.0

    def test_domain_check_blocked_after_record(self) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=5, default_domain_cooldown_seconds=10.0)
        limiter.record_domain_fetch("user1", "example.com")
        allowed, wait = limiter.check_domain_before_fetch("user1", "example.com")
        assert allowed is False
        assert wait > 0.0

    def test_domain_cooldown_expires(self, monkeypatch) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=5, default_domain_cooldown_seconds=0.05)
        limiter.record_domain_fetch("user1", "example.com")
        original_time = time.time
        monkeypatch.setattr("time.time", lambda: original_time() + 0.06)
        allowed, wait = limiter.check_domain_before_fetch("user1", "example.com")
        assert allowed is True
        assert wait == 0.0

    def test_per_job_domain_tracking(self) -> None:
        """Per-job domain delays track (user_id, job_id, domain) tuples."""
        limiter = JobRateLimiter(max_concurrent_per_user=5, default_domain_cooldown_seconds=10.0)
        limiter.record_domain_fetch("user1", "example.com", job_id="job-a")
        # Same user, different job should still be blocked by the shared tracker
        allowed, _ = limiter.check_domain_before_fetch("user1", "example.com", job_id="job-b")
        assert allowed is False

    def test_custom_cooldown_override(self, monkeypatch) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=5, default_domain_cooldown_seconds=10.0)
        limiter.record_domain_fetch("user1", "example.com")
        original_time = time.time
        monkeypatch.setattr("time.time", lambda: original_time() + 0.005)
        allowed, _ = limiter.check_domain_before_fetch(
            "user1",
            "example.com",
            cooldown_seconds=0.001,
        )
        assert allowed is True

    def test_wait_for_domain(self, monkeypatch) -> None:
        # wait_for_domain's internal time.sleep is incidental — the returned
        # `waited` is from check(). Mock time.sleep to keep the test fast.
        monkeypatch.setattr("time.sleep", lambda _seconds: None)
        limiter = JobRateLimiter(max_concurrent_per_user=5, default_domain_cooldown_seconds=0.1)
        limiter.record_domain_fetch("user1", "example.com")
        waited = limiter.wait_for_domain("user1", "example.com")
        assert waited > 0.0

    def test_wait_for_domain_no_wait(self) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=5, default_domain_cooldown_seconds=10.0)
        waited = limiter.wait_for_domain("user1", "example.com")
        assert waited == 0.0

    @pytest.mark.asyncio
    async def test_async_wait_for_domain(self, monkeypatch) -> None:
        # async_wait_for_domain's asyncio.sleep is incidental — the returned
        # `waited` is from check(). Mock asyncio.sleep to keep the test fast.
        async def _fake_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr("asyncio.sleep", _fake_sleep)
        limiter = JobRateLimiter(max_concurrent_per_user=5, default_domain_cooldown_seconds=0.05)
        limiter.record_domain_fetch("user1", "example.com")
        waited = await limiter.async_wait_for_domain("user1", "example.com")
        assert waited > 0.0

    def test_get_stats(self) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=5, default_domain_cooldown_seconds=2.0)
        limiter.acquire_job_slot("user1")
        limiter.acquire_job_slot("user2")
        stats = limiter.get_stats()
        assert stats["max_concurrent_per_user"] == 5
        assert stats["active_users"] == 2
        assert "user1" in stats["user_active_jobs"]
        assert "user2" in stats["user_active_jobs"]

    def test_domain_cooldown_remaining(self) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=5, default_domain_cooldown_seconds=10.0)
        limiter.record_domain_fetch("user1", "example.com")
        remaining = limiter.get_domain_cooldown_remaining("example.com")
        assert remaining > 0.0

    def test_domain_cooldown_remaining_when_clear(self) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=5, default_domain_cooldown_seconds=10.0)
        remaining = limiter.get_domain_cooldown_remaining("example.com")
        assert remaining == 0.0

    def test_reset_clears_all_state(self) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=5, default_domain_cooldown_seconds=10.0)
        limiter.acquire_job_slot("user1")
        limiter.record_domain_fetch("user1", "example.com")
        limiter.reset()
        assert limiter.get_user_active_jobs("user1") == 0
        assert limiter.get_domain_cooldown_remaining("example.com") == 0.0

    def test_concurrent_access_thread_safety(self) -> None:
        """Exercise concurrent acquire/release to verify thread safety."""
        import threading

        limiter = JobRateLimiter(max_concurrent_per_user=10)
        errors: list[str] = []

        def worker(user: str, count: int) -> None:
            for _ in range(count):
                acquired = limiter.acquire_job_slot(user)
                if acquired:
                    try:
                        active = limiter.get_user_active_jobs(user)
                        if active > 10:
                            errors.append(f"exceeded cap: {active}")
                    finally:
                        limiter.release_job_slot(user)

        threads = [threading.Thread(target=worker, args=("user1", 50)) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread-safety errors: {errors}"
        assert limiter.get_user_active_jobs("user1") == 0
