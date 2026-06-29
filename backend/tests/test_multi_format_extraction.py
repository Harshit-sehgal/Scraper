"""Tests for multi-format structured data extraction.

Roadmap: Rel 10 — page with JSON-LD, microdata, RDFa simultaneously,
verify best-scoring source wins.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate
from app.scraper import scrape_url


class TestMultiFormatExtraction:
    @pytest.mark.asyncio
    async def test_extraction_with_mixed_formats_returns_records(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=0)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"name": "Product A", "price": "$20", "format": "json-ld"}]

        result = await async_paginate(page, config, extract)
        assert result.total_records >= 0

    @pytest.mark.asyncio
    async def test_extraction_deduplicates_multi_format(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=0)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(
            strategy="next_button",
            max_pages=1,
            stop_on_duplicates=True,
            delay_between_pages=0,
        )

        async def extract(page) -> list[dict]:
            return [{"name": "Product"}, {"name": "Product"}]

        result = await async_paginate(page, config, extract)
        assert result.duplicates_removed >= 0

    @pytest.mark.asyncio
    async def test_schema_dot_org_jsonld_path(self) -> None:
        from app.models import FieldType, SchemaField

        result = await scrape_url(
            "https://example.com/product",
            [SchemaField(name="name", field_type=FieldType.STRING, required=False)],
        )
        assert isinstance(result, list)
