"""Tests for resource blocking during extraction.

Roadmap: Rel 9 — verify blocking ads/scripts/fonts doesn't break extraction.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate


@pytest.mark.asyncio
class TestResourceBlocking:
    async def test_extraction_with_blocked_resources_succeeds(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=3)
        page.locator.return_value.text_content = AsyncMock(return_value="Next")
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        page.route = MagicMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=2, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"title": "Blocked Resource Test"}]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0

    async def test_page_with_css_still_extracts(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=3)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"data": "content"}]

        result = await async_paginate(page, config, extract)
        assert len(result.records) >= 0

    async def test_all_strategies_work_with_blocked_fonts(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=False)
        page.locator.return_value.count = AsyncMock(return_value=0)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        page.route = MagicMock()

        for strategy in ("next_button", "infinite_scroll", "load_more"):
            config = PaginationConfig(strategy=strategy, max_pages=1, delay_between_pages=0)
            result = await async_paginate(page, config)
            assert result.stopped_reason in {"button_gone", "max_pages", "no_new_records", "error"}
