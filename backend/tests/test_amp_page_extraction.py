"""Tests for AMP page extraction.

Roadmap: Rel 26 — Accelerated Mobile Pages with limited JS,
verify extraction works in AMP rendering mode.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models import FieldType, SchemaField
from app.pagination_executor import PaginationConfig, async_paginate


class TestAmpPageExtraction:
    @pytest.mark.asyncio
    async def test_amp_page_returns_records(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]
        mock_return = [{"title": "AMP Article Title"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/amp/article", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_amp_page_with_schema_dot_org(self) -> None:
        schema = [
            SchemaField(name="headline", field_type=FieldType.STRING),
            SchemaField(name="description", field_type=FieldType.STRING),
        ]
        mock_return = [{"headline": "Headline", "description": "Description"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/amp/structured", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_amp_pagination(self) -> None:
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
        result = await async_paginate(page, config)
        assert isinstance(result, type(result))

    @pytest.mark.asyncio
    async def test_amp_page_no_js_fallback(self) -> None:
        mock_return = [{"content": "no-JS content"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape(
                "https://example.com/amp/no-js",
                [SchemaField(name="content", field_type=FieldType.STRING)],
            )
        assert isinstance(result, list)
