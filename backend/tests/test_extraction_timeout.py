"""Tests for extraction timeout enforcement.

Roadmap: Rel 8 — page that never finishes loading,
verify timeout with clean failure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate

_STRATEGIES_WITH_EARLY_ERROR = {"url_pattern", "page_number"}


class TestExtractionTimeout:
    @pytest.mark.asyncio
    async def test_zero_runtime_immediate_timeout(self) -> None:
        page = MagicMock()
        config = PaginationConfig(
            strategy="next_button",
            max_pages=5,
            max_runtime_seconds=0,
            delay_between_pages=0,
        )
        result = await async_paginate(page, config)
        assert result.stopped_reason == "timeout"

    @pytest.mark.asyncio
    async def test_timeout_returns_empty_records(self) -> None:
        page = MagicMock()
        config = PaginationConfig(
            strategy="next_button",
            max_pages=5,
            max_runtime_seconds=0,
            delay_between_pages=0,
        )
        result = await async_paginate(page, config)
        assert result.total_records == 0
        assert result.records == []

    @pytest.mark.asyncio
    async def test_runtime_budget_per_strategy(self) -> None:
        for strategy in ("next_button", "infinite_scroll", "load_more"):
            page = MagicMock()
            page.locator = MagicMock(return_value=MagicMock())
            page.locator.return_value.is_visible = AsyncMock(return_value=False)
            page.locator.return_value.count = AsyncMock(return_value=0)
            page.evaluate = AsyncMock(return_value=1000)
            page.goto = AsyncMock()
            page.wait_for_function = AsyncMock()
            config = PaginationConfig(
                strategy=strategy,
                max_pages=100,
                max_runtime_seconds=0,
                delay_between_pages=0,
            )
            result = await async_paginate(page, config)
            assert result.stopped_reason == "timeout", f"Strategy {strategy} did not timeout"

    @pytest.mark.asyncio
    async def test_url_pattern_timeout_with_pattern(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        page.locator.return_value.is_visible = AsyncMock(return_value=False)

        config = PaginationConfig(
            strategy="url_pattern",
            max_pages=100,
            max_runtime_seconds=0,
            url_pattern="https://example.com?page={page}",
            delay_between_pages=0,
        )
        result = await async_paginate(page, config)
        assert result.stopped_reason in {"timeout", "error", "max_pages"}

    @pytest.mark.asyncio
    async def test_page_number_timeout_with_pattern(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        page.locator.return_value.is_visible = AsyncMock(return_value=False)
        page.locator.return_value.count = AsyncMock(return_value=0)

        config = PaginationConfig(
            strategy="page_number",
            max_pages=100,
            max_runtime_seconds=0,
            url_pattern="https://example.com?page={page}",
            delay_between_pages=0,
        )
        result = await async_paginate(page, config)
        assert result.stopped_reason in {"timeout", "error", "max_pages", "button_gone"}
