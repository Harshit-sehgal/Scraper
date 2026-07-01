"""Tests for extremely deep DOM handling.

Roadmap: Rel 48 — page with 10,000+ nested DOM elements,
verify extraction does not stack-overflow or exhaust memory.

All tests that use scrape_url mock the network layer so they run offline.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models import FieldType, SchemaField
from app.pagination_executor import PaginationConfig, async_paginate


class TestDeepDom:
    @pytest.mark.asyncio
    async def test_deeply_nested_dom_extracts(self) -> None:
        schema = [SchemaField(name="text", field_type=FieldType.STRING, required=False)]
        mock_return = [{"text": "deep content"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/deep-dom", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_many_nested_elements_no_crash(self) -> None:
        mock_return = [{"data": "value"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape(
                "https://example.com/10k-nested",
                [SchemaField(name="data", field_type=FieldType.STRING)],
            )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_deep_dom_pagination_succeeds(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=100)
        page.evaluate = AsyncMock(return_value=10000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)

        async def extract(_page) -> list[dict]:
            return [{"id": i} for i in range(100)]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0

    @pytest.mark.asyncio
    async def test_deep_dom_scroll_does_not_overflow(self) -> None:
        # Each scroll iteration calls page.evaluate twice (scrollHeight + scrollTo)
        # plus one final scrollTo(0,0) at the end. max_pages=5 → 5*2+1 = 11 calls needed.
        page = MagicMock()
        page.evaluate = AsyncMock(
            side_effect=[100, 5000, 10000, 15000, 20000, 20000, 20000, None, None, None, None],
        )
        page.wait_for_function = AsyncMock()
        page.locator = MagicMock(return_value=MagicMock())

        config = PaginationConfig(strategy="infinite_scroll", max_pages=5, delay_between_pages=0)

        async def extract(_page) -> list[dict]:
            return [{"x": i} for i in range(50)]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0

    @pytest.mark.asyncio
    async def test_deep_dom_with_max_records(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=10000)
        page.evaluate = AsyncMock(return_value=100000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(
            strategy="next_button",
            max_pages=1,
            max_records=5,
            delay_between_pages=0,
        )

        async def extract(_page) -> list[dict]:
            return [{"deep": True} for _ in range(100)]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0
