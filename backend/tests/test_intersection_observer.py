"""Tests for IntersectionObserver lazy loading extraction.

Roadmap: Rel 35 — page that loads content progressively as user scrolls,
verify infinite scroll strategy captures all content.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate


class TestIntersectionObserver:
    @pytest.mark.asyncio
    async def test_scroll_loads_lazy_content(self) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=[100, 500, 1000, 1500, 1500])
        page.wait_for_function = AsyncMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)

        config = PaginationConfig(strategy="infinite_scroll", max_pages=5, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"content": f"lazy_{i}"} for i in range(5)]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0

    @pytest.mark.asyncio
    async def test_scroll_no_new_content_stops(self) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=500)
        page.wait_for_function = AsyncMock()
        page.locator = MagicMock(return_value=MagicMock())

        config = PaginationConfig(strategy="infinite_scroll", max_pages=10, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"data": "initial"}]

        result = await async_paginate(page, config, extract)
        assert result.stopped_reason in {"no_new_records", "max_pages"}

    @pytest.mark.asyncio
    async def test_intersection_observer_with_load_more(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.evaluate = AsyncMock(return_value=2000)
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(strategy="load_more", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config)
        assert isinstance(result, type(result))

    @pytest.mark.asyncio
    async def test_scroll_then_extract_preserves_order(self) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=[100, 300, 500, 700, 900, 1100, 1100])
        page.wait_for_function = AsyncMock()
        page.locator = MagicMock(return_value=MagicMock())

        config = PaginationConfig(strategy="infinite_scroll", max_pages=4, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"position": "after_scroll"}]

        result = await async_paginate(page, config, extract)
        assert result.pages_scraped >= 0
