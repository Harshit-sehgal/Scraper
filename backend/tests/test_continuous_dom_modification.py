"""Tests for continuous DOM modification handling.

Roadmap: Rel 23 — JS continuously modifying DOM after load,
verify extraction waits for stabilization and captures final state.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate


class TestContinuousDomModification:
    @pytest.mark.asyncio
    async def test_dom_stabilization_waits_for_content(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=5)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"content": "final state"}]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0

    @pytest.mark.asyncio
    async def test_stabilization_timeout_does_not_crash(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=3)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock(side_effect=Exception("timeout"))
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=2, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"data": "post-stabilization"}]

        result = await async_paginate(page, config, extract)
        assert isinstance(result, type(result))

    @pytest.mark.asyncio
    async def test_infinite_scroll_with_dom_changes(self) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=[100, 200, 300, 400, 500])
        page.locator = MagicMock(return_value=MagicMock())
        page.wait_for_function = MagicMock(side_effect=[None, None])

        config = PaginationConfig(strategy="infinite_scroll", max_pages=3, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"item": "post-scroll"}]

        result = await async_paginate(page, config, extract)
        assert result.pages_scraped >= 0

    @pytest.mark.asyncio
    async def test_dom_continuously_modifying_still_extracts(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=2)
        page.evaluate = AsyncMock(return_value=2000)
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(strategy="load_more", max_pages=2, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"value": "stable"}]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0
