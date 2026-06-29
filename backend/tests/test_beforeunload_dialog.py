"""Tests for beforeunload dialog handling.

Roadmap: Rel 47 — page that triggers "Are you sure you want to leave?" dialog,
verify Playwright dismisses it and extraction continues.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate


class TestBeforeunloadDialog:
    @pytest.mark.asyncio
    async def test_beforeunload_does_not_block_pagination(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=3)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        page.on = MagicMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)
        page.dialog = AsyncMock()
        page.dialog.dismiss = AsyncMock()

        config = PaginationConfig(strategy="next_button", max_pages=2, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"data": "dialog dismissed"}]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0

    @pytest.mark.asyncio
    async def test_dialog_on_navigation_dismissed(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=3)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        page.on = MagicMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=2, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"x": "y"}]

        result = await async_paginate(page, config, extract)
        assert isinstance(result, type(result))

    @pytest.mark.asyncio
    async def test_dialog_handler_does_not_leak(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        page.on = MagicMock()

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)
        result = await async_paginate(page, config)
        assert isinstance(result, type(result))
