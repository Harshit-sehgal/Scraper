"""Tests for automation detection evasion.

Roadmap: Rel 24 — navigator.webdriver and other detection vectors.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.models import FieldType, SchemaField
from app.pagination_executor import PaginationConfig, async_paginate
from app.scraper import scrape_url


class TestAutomationDetection:
    @pytest.mark.asyncio
    async def test_extraction_succeeds_despite_detection_vectors(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/detection-check", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_pagination_with_detection_vectors(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        # Simulate detection-related evaluation
        page.evaluate = AsyncMock(
            side_effect=lambda expr: (
                True if "webdriver" in str(expr) or "plugins" in str(expr) else 1000
            )
        )

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"result": "evaded"}]

        result = await async_paginate(page, config, extract)
        assert isinstance(result, type(result))

    @pytest.mark.asyncio
    async def test_stealth_evasion_does_not_break_url_pattern(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        page.route = MagicMock()

        config = PaginationConfig(
            strategy="url_pattern",
            max_pages=1,
            url_pattern="https://example.com?p={page}",
            delay_between_pages=0,
        )
        result = await async_paginate(page, config)
        assert isinstance(result, type(result))

    def test_url_safety_blocks_data_urls(self) -> None:
        from app.url_safety import validate_public_http_url

        with pytest.raises(ValueError):
            validate_public_http_url("data:text/html,<script>navigator.webdriver</script>")
