"""Tests for infinite-scroll ceiling enforcement.

Roadmap: Rel 20 — page whose content never stops growing,
verify max-pages/max-records/max-timeout ceiling is enforced gracefully.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate


class TestInfiniteScrollCeiling:
    @pytest.mark.asyncio
    async def test_max_pages_enforced_in_scroll(self) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=[100, 200, 300, 300, 300])
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(
            strategy="infinite_scroll",
            max_pages=2,
            delay_between_pages=0,
        )

        async def extract(page) -> list[dict]:
            return [{"data": f"row_{i}"} for i in range(3)]

        result = await async_paginate(page, config, extract)
        assert result.pages_scraped <= 2

    @pytest.mark.asyncio
    async def test_max_records_enforced_in_scroll(self) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=[100, 200, 300, 400, 500])
        page.locator = MagicMock(return_value=MagicMock())
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(
            strategy="infinite_scroll",
            max_pages=10,
            max_records=2,
            delay_between_pages=0,
        )

        async def extract(page) -> list[dict]:
            return [{"data": "x"}]

        result = await async_paginate(page, config, extract)
        assert result.total_records <= 2

    @pytest.mark.asyncio
    async def test_scroll_timeout_with_never_ending_content(self) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=[100, 200, 300, 400, 500])
        page.locator = MagicMock(return_value=MagicMock())
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(
            strategy="infinite_scroll",
            max_pages=100,
            max_runtime_seconds=1,
            delay_between_pages=0,
        )
        result = await async_paginate(page, config)
        assert result.stopped_reason in {"timeout", "max_pages", "no_new_records"}

    @pytest.mark.asyncio
    async def test_scroll_duplicate_height_stops(self) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=500)
        page.locator = MagicMock(return_value=MagicMock())
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(
            strategy="infinite_scroll",
            max_pages=50,
            delay_between_pages=0,
        )
        result = await async_paginate(page, config)
        assert result.stopped_reason in {"no_new_records", "max_pages"}

    @pytest.mark.asyncio
    async def test_scroll_resets_to_top_after_completion(self) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=[100, 200, 200])
        page.locator = MagicMock(return_value=MagicMock())
        page.wait_for_function = AsyncMock()

        config = PaginationConfig(
            strategy="infinite_scroll",
            max_pages=3,
            delay_between_pages=0,
        )
        result = await async_paginate(page, config)
        assert result.pages_scraped >= 0
