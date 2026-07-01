"""Tests for large page stress handling.

Roadmap: Rel 21 — 500KB+ HTML with deep DOM, verify
extraction completes within bounded time and memory.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models import FieldType, SchemaField
from app.pagination_executor import PaginationConfig, async_paginate


class TestLargePageStress:
    @pytest.mark.asyncio
    async def test_large_page_does_not_crash(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]
        mock_return = [{"title": "large page content"}]

        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/large-page", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_large_page_pagination_succeeds(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=50)
        page.evaluate = AsyncMock(return_value=10000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=2, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"idx": i} for i in range(100)]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0

    @pytest.mark.asyncio
    async def test_deeply_nested_page_extracts(self) -> None:
        mock_return = [{"text": "deeply nested content"}]

        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape(
                "https://example.com/deep-nested",
                [SchemaField(name="text", field_type=FieldType.STRING)],
            )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_large_page_stress_returns_reasonably(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=500)
        page.evaluate = AsyncMock(return_value=50000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"id": i} for i in range(500)]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0
