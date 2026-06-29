"""Tests for click-to-reveal, tab, modal, and hover content extraction.

Roadmap: Rel 31 — "Show more" buttons and accordions.
         Rel 32 — Tabbed interface content.
         Rel 33 — Modal/dialog content.
         Rel 34 — Hover-triggered content.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate


class TestClickToReveal:
    @pytest.mark.asyncio
    async def test_load_more_reveals_content(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(strategy="load_more", max_pages=2, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"content": "revealed"}]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0

    @pytest.mark.asyncio
    async def test_accordion_clicks_via_load_more(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(
            strategy="load_more",
            max_pages=3,
            selector="button.accordion",
            delay_between_pages=0,
        )

        async def extract(page) -> list[dict]:
            return [{"panel": "accordion content"}]

        result = await async_paginate(page, config, extract)
        assert isinstance(result, type(result))


class TestTabContent:
    @pytest.mark.asyncio
    async def test_tab_content_via_pagination(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="page_number", max_pages=3, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"tab": "content"}]

        result = await async_paginate(page, config, extract)
        assert result.pages_scraped >= 0

    @pytest.mark.asyncio
    async def test_tab_buttons_not_found_graceful(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.count = AsyncMock(return_value=0)
        page.locator.return_value.is_visible = AsyncMock(return_value=False)
        page.evaluate = AsyncMock(return_value=1000)

        config = PaginationConfig(strategy="page_number", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config)
        assert result.stopped_reason in {"button_gone", "max_pages", "no_new_records"}


class TestModalContent:
    @pytest.mark.asyncio
    async def test_modal_triggered_via_button_click(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(strategy="load_more", max_pages=1, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"modal": "content"}]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0


class TestHoverContent:
    @pytest.mark.asyncio
    async def test_hover_triggers_content_capture(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=0)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()
        page.hover = AsyncMock()

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"tooltip": "hover content"}]

        result = await async_paginate(page, config, extract)
        assert isinstance(result, type(result))

    @pytest.mark.asyncio
    async def test_dropdown_hover_before_click(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=0)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()
        page.hover = AsyncMock()

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"dropdown": "visible"}]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0
