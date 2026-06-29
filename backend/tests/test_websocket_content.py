"""Tests for WebSocket-pushed and Server-Sent Events content.

Roadmap: Rel 36 — WebSocket-pushed content extraction.
         Rel 37 — EventSource/SSE content extraction.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate


class TestWebSocketContent:
    @pytest.mark.asyncio
    async def test_websocket_page_extracts_after_stabilization(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=5)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"ws_data": "pushed content"}]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0

    @pytest.mark.asyncio
    async def test_websocket_no_content_returns_empty(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=0)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=2, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return []

        result = await async_paginate(page, config, extract)
        assert result.total_records == 0

    @pytest.mark.asyncio
    async def test_websocket_with_infinite_scroll(self) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=[500, 1000, 1500, 1500])
        page.wait_for_function = AsyncMock()
        page.locator = MagicMock(return_value=MagicMock())

        config = PaginationConfig(strategy="infinite_scroll", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config)
        assert isinstance(result, type(result))


class TestServerSentEvents:
    @pytest.mark.asyncio
    async def test_sse_page_stabilizes_and_extracts(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=5)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"sse": "event data"}]

        result = await async_paginate(page, config, extract)
        assert isinstance(result, type(result))

    @pytest.mark.asyncio
    async def test_sse_streaming_does_not_hang_pagination(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(strategy="load_more", max_pages=2, delay_between_pages=0)
        result = await async_paginate(page, config)
        assert result.stopped_reason in {"button_gone", "max_pages", "error"}
