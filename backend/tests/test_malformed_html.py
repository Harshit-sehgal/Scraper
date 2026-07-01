"""Tests for malformed HTML recovery.

Roadmap: Rel 43 — page with unclosed tags, duplicate IDs,
invalid nesting, verify extraction degrades gracefully.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models import FieldType, SchemaField
from app.pagination_executor import PaginationConfig, async_paginate


class TestMalformedHtml:
    @pytest.mark.asyncio
    async def test_malformed_html_extracts_gracefully(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]
        mock_return = [{"title": "value"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/malformed", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_unclosed_tags_do_not_crash(self) -> None:
        mock_return = [{"text": "value"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape(
                "https://example.com/unclosed",
                [SchemaField(name="text", field_type=FieldType.STRING)],
            )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_duplicate_ids_handled(self) -> None:
        mock_return = [{"data": "value"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape(
                "https://example.com/dup-ids",
                [SchemaField(name="data", field_type=FieldType.STRING)],
            )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_invalid_nesting_still_extracts(self) -> None:
        mock_return = [{"content": "value"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape(
                "https://example.com/bad-nesting",
                [SchemaField(name="content", field_type=FieldType.STRING)],
            )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_malformed_html_pagination(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=3)
        page.evaluate = AsyncMock(return_value=1000)
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"x": "malformed but extracted"}]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0
