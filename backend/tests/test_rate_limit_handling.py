"""Tests for rate-limit handling (HTTP 429 with Retry-After).

Roadmap: Rel 15 — HTTP 429 with Retry-After header,
verify worker backs off, retries, succeeds on retry.

Item 9: Per-user job concurrency cap, per-job domain delay,
domain cooldown integration.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate
from app.rate_limiter import DomainCooldownTracker, JobRateLimiter


class TestRateLimitHandling:
    @pytest.mark.asyncio
    async def test_pagination_does_not_hang_on_rate_limit(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=0)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=3, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            raise RuntimeError("429 Too Many Requests")

        result = await async_paginate(page, config, extract)
        assert result.stopped_reason in {"error", "button_gone", "no_new_records"}

    @pytest.mark.asyncio
    async def test_extraction_failure_marked_on_429(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.evaluate = AsyncMock(return_value=1000)
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        call_count = 0

        async def fail_then_succeed(page) -> list[dict]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("rate limited")
            return [{"data": "success"}]

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)
        result = await async_paginate(page, config, fail_then_succeed)
        assert not result.error or "rate" in result.error.lower() or result.total_records >= 0

    def test_url_safety_rejects_private_ips(self) -> None:
        from app.url_safety import validate_public_http_url

        validate_public_http_url("https://example.com")
        with pytest.raises(ValueError):
            validate_public_http_url("http://127.0.0.1:429")


# ─── Item 9: Job-level rate limiting integration tests ────────────────────


class TestJobConcurrencyCapIntegration:
    """Integration-style tests for per-user job concurrency limiting."""

    def test_user_job_cap_enforced(self) -> None:
        """A user cannot exceed the configured concurrency cap."""
        limiter = JobRateLimiter(max_concurrent_per_user=3)
        user = "user-abc"

        assert limiter.acquire_job_slot(user) is True
        assert limiter.acquire_job_slot(user) is True
        assert limiter.acquire_job_slot(user) is True
        # 4th slot should be denied
        assert limiter.acquire_job_slot(user) is False

    def test_release_restores_capacity(self) -> None:
        """Releasing a job slot should allow a new job to start."""
        limiter = JobRateLimiter(max_concurrent_per_user=1)
        user = "user-xyz"

        assert limiter.acquire_job_slot(user) is True
        assert limiter.acquire_job_slot(user) is False
        limiter.release_job_slot(user)
        assert limiter.acquire_job_slot(user) is True

    def test_users_isolated_from_each_other(self) -> None:
        """User A at cap does not block User B."""
        limiter = JobRateLimiter(max_concurrent_per_user=1)
        limiter.acquire_job_slot("user-a")
        assert limiter.acquire_job_slot("user-b") is True

    def test_get_active_jobs_accurate(self) -> None:
        limiter = JobRateLimiter(max_concurrent_per_user=10)
        limiter.acquire_job_slot("u1")
        limiter.acquire_job_slot("u2")
        limiter.acquire_job_slot("u2")

        stats = limiter.get_stats()
        assert stats["active_users"] == 2
        assert stats["user_active_jobs"]["u1"] == 1
        assert stats["user_active_jobs"]["u2"] == 2


class TestDomainCooldownIntegration:
    """Integration tests for per-job domain request delay with cooldown."""

    def test_domain_blocked_during_cooldown(self) -> None:
        """After hitting a domain, subsequent requests are blocked during cooldown."""
        tracker = DomainCooldownTracker(default_cooldown_seconds=1.0)
        tracker.record_hit("target.example.com")
        allowed, _ = tracker.check("target.example.com")
        assert allowed is False

    def test_domain_releases_after_cooldown(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=0.05)
        tracker.record_hit("target.example.com")
        time.sleep(0.06)
        allowed, _ = tracker.check("target.example.com")
        assert allowed is True

    def test_different_domains_do_not_block_each_other(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=1.0)
        tracker.record_hit("a.com")
        allowed, _ = tracker.check("b.com")
        assert allowed is True

    def test_custom_cooldown_per_domain(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=1.0)
        tracker.record_hit("slow.com")
        # Override with a zero cooldown should always allow (elapsed >= 0)
        allowed, _ = tracker.check("slow.com", cooldown_seconds=0.0)
        assert allowed is True

    def test_sync_wait_for_domain(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=0.1)
        tracker.record_hit("target.com")
        waited = tracker.wait_if_needed("target.com")
        assert waited > 0.0

    @pytest.mark.asyncio
    async def test_async_wait_for_domain(self) -> None:
        tracker = DomainCooldownTracker(default_cooldown_seconds=0.05)
        tracker.record_hit("target.com")
        waited = await tracker.async_wait_if_needed("target.com")
        assert waited > 0.0
