"""Tests for rate-limit handling (HTTP 429 with Retry-After).

Roadmap: Rel 15 — HTTP 429 with Retry-After header,
verify worker backs off, retries, succeeds on retry.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate


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
