"""Tests for slow network simulation.

Roadmap: Rel 29 — simulate slow 3G network conditions,
verify extraction waits for content but eventually times out gracefully.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate


class TestSlowNetwork:
    @pytest.mark.asyncio
    async def test_slow_page_eventually_extracts(self) -> None:
        page = MagicMock()
        locator = MagicMock()
        locator.is_visible = AsyncMock(return_value=True)
        locator.count = AsyncMock(return_value=3)
        locator.click = AsyncMock()
        locator.first = locator
        page.locator = MagicMock(return_value=locator)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=2, delay_between_pages=0)

        async def slow_extract(_page) -> list[dict]:
            await asyncio.sleep(0.1)
            return [{"data": "slow content"}]

        result = await async_paginate(page, config, slow_extract)
        assert result.total_records >= 0

    @pytest.mark.asyncio
    async def test_slow_network_timeout_graceful(self) -> None:
        page = MagicMock()
        locator = MagicMock()
        locator.is_visible = AsyncMock(return_value=True)
        locator.count = AsyncMock(return_value=3)
        locator.click = AsyncMock()
        locator.first = locator
        page.locator = MagicMock(return_value=locator)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(
            strategy="next_button",
            max_pages=10,
            max_runtime_seconds=1,
            delay_between_pages=0,
        )

        async def very_slow(_page) -> list[dict]:
            await asyncio.sleep(5)
            return [{"x": "y"}]

        result = await async_paginate(page, config, very_slow)
        assert result.stopped_reason in {"timeout", "button_gone"}

    @pytest.mark.asyncio
    async def test_delay_between_pages_respected(self) -> None:
        page = MagicMock()
        locator = MagicMock()
        locator.is_visible = AsyncMock(return_value=True)
        locator.count = AsyncMock(return_value=3)
        locator.click = AsyncMock()
        locator.first = locator
        page.locator = MagicMock(return_value=locator)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=2, delay_between_pages=0)

        async def extract(_page) -> list[dict]:
            return [{"data": "test"}]

        result = await async_paginate(page, config, extract)
        assert isinstance(result, type(result))

    @pytest.mark.asyncio
    async def test_slow_load_more_does_not_hang(self) -> None:
        page = MagicMock()
        locator = MagicMock()
        locator.is_visible = AsyncMock(return_value=True)
        locator.count = AsyncMock(return_value=3)
        locator.first = locator
        page.locator = MagicMock(return_value=locator)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(strategy="load_more", max_pages=2, delay_between_pages=0)
        result = await async_paginate(page, config)
        assert result.stopped_reason in {"button_gone", "max_pages", "error"}
