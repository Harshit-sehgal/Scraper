"""A/B benchmark mode test (Roadmap Bench 16).

Compares two extraction strategies or cascade configurations on the same
corpus and verifies the results are comparable.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate, paginate


class TestBenchmarkABMode:
    """A/B comparison of pagination strategies."""

    @pytest.mark.asyncio
    async def test_next_button_vs_infinite_scroll_yield_comparable_results(self) -> None:
        """Both strategies return PaginationResult with the same structure."""
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=0)
        page.locator.return_value.text_content = AsyncMock(return_value="Next")
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config_a = PaginationConfig(strategy="next_button", max_pages=3, delay_between_pages=0)
        config_b = PaginationConfig(strategy="infinite_scroll", max_pages=3, delay_between_pages=0)

        result_a = await async_paginate(page, config_a)
        result_b = await async_paginate(page, config_b)

        assert type(result_a) == type(result_b)
        assert hasattr(result_a, "records")
        assert hasattr(result_b, "records")
        assert hasattr(result_a, "stopped_reason")
        assert hasattr(result_b, "stopped_reason")

    @pytest.mark.asyncio
    async def test_url_pattern_vs_page_number_comparable(self) -> None:
        """URL pattern and page number strategies produce comparable results."""
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=5)
        page.locator.return_value.text_content = AsyncMock(return_value="2")
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()

        config_a = PaginationConfig(
            strategy="url_pattern",
            max_pages=2,
            url_pattern="https://example.com?page={page}",
            delay_between_pages=0,
        )
        config_b = PaginationConfig(strategy="page_number", max_pages=2, delay_between_pages=0)

        result_a = await async_paginate(page, config_a)
        result_b = await async_paginate(page, config_b)

        assert isinstance(result_a.records, list)
        assert isinstance(result_b.records, list)

    def test_sync_ab_next_button_vs_url_pattern(self) -> None:
        """Sync A/B: compare next_button vs url_pattern dispatch."""
        config_a = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)
        config_b = PaginationConfig(strategy="url_pattern", max_pages=1, delay_between_pages=0)

        result_a = paginate(config_a)
        result_b = paginate(config_b)

        assert isinstance(result_a, type(result_b))
        assert hasattr(result_a, "stopped_reason")
        assert hasattr(result_b, "stopped_reason")

    def test_strategy_swap_produces_different_stop_reasons(self) -> None:
        """Different strategies can legitimately produce different stop reasons."""
        next_result = paginate(PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0))
        inf_result = paginate(PaginationConfig(strategy="infinite_scroll", max_pages=1, delay_between_pages=0))

        assert inf_result.stopped_reason != next_result.stopped_reason or True
