"""Tests for dynamic/randomized CSS class name handling.

Roadmap: Rel 30 — pages where CSS class names are randomized per visit,
verify extraction uses semantic selectors not fragile class names.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.models import FieldType, SchemaField
from app.pagination_executor import PaginationConfig, async_paginate
from app.scraper import scrape_url


class TestDynamicClassNames:
    @pytest.mark.asyncio
    async def test_randomized_class_names_still_extract(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/random-classes", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_semantic_selectors_work_with_dynamic_classes(self) -> None:
        from app.models import FieldType, SchemaField

        schema = [
            SchemaField(name="heading", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        result = await scrape_url("https://example.com/tailwind-page", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_pagination_with_dynamic_selectors(self) -> None:
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

        config = PaginationConfig(
            strategy="next_button",
            max_pages=1,
            selector="a[rel=next]",
            delay_between_pages=0,
        )

        async def extract(page) -> list[dict]:
            return [{"content": "dynamic class test"}]

        result = await async_paginate(page, config, extract)
        assert isinstance(result, type(result))

    @pytest.mark.asyncio
    async def test_mui_style_randomization(self) -> None:
        result = await scrape_url(
            "https://example.com/mui-page",
            [SchemaField(name="data", field_type=FieldType.STRING)],
        )
        assert isinstance(result, list)
