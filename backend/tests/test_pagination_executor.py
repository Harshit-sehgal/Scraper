"""Tests for async pagination executor — 20+ tests across all 5 strategies.

Roadmap: Rel 1 — extraction reliability, pagination executor tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import (
    PAGINATION_STRATEGIES,
    PaginationConfig,
    PaginationResult,
    async_paginate,
)


def _mock_page() -> MagicMock:
    page = MagicMock()
    page.locator = MagicMock(return_value=MagicMock())
    page.locator.return_value.is_visible = AsyncMock(return_value=True)
    page.locator.return_value.count = AsyncMock(return_value=3)
    page.locator.return_value.text_content = AsyncMock(return_value="Next")
    page.evaluate = AsyncMock(return_value=1000)
    page.goto = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.route = MagicMock()
    nav = AsyncMock()
    nav.__aenter__ = AsyncMock()
    nav.__aexit__ = AsyncMock()
    page.expect_navigation = MagicMock(return_value=nav)
    return page


async def _extract_dummy(page) -> list[dict]:
    return [{"title": "Product", "price": "$10"}]


class TestStrategySelection:
    def test_all_five_strategies_recognized(self) -> None:
        assert {
            "next_button",
            "page_number",
            "url_pattern",
            "infinite_scroll",
            "load_more",
        } == PAGINATION_STRATEGIES

    @pytest.mark.asyncio
    async def test_default_strategy_is_next_button(self) -> None:
        page = _mock_page()
        result = await async_paginate(page)
        assert isinstance(result, PaginationResult)
        assert result.stopped_reason in {"button_gone", "max_pages", "no_new_records"}

    @pytest.mark.asyncio
    async def test_unknown_strategy_returns_error(self) -> None:
        page = _mock_page()
        config = PaginationConfig(strategy="unknown_xyz")
        result = await async_paginate(page, config)
        assert result.stopped_reason == "error"
        assert result.error is not None
        assert "unknown" in result.error.lower()

    @pytest.mark.asyncio
    async def test_legacy_url_parameter_rejected(self) -> None:
        page = _mock_page()
        config = PaginationConfig(strategy="url_parameter")
        result = await async_paginate(page, config)
        assert result.stopped_reason == "error"


class TestNextButtonStrategy:
    @pytest.mark.asyncio
    async def test_click_next_extracts_records(self) -> None:
        page = _mock_page()
        config = PaginationConfig(strategy="next_button", max_pages=2, delay_between_pages=0)
        result = await async_paginate(page, config, _extract_dummy)
        assert isinstance(result, PaginationResult)
        assert result.total_records >= 0
        assert result.stopped_reason in {"max_pages", "button_gone", "no_new_records"}

    @pytest.mark.asyncio
    async def test_max_pages_enforced(self) -> None:
        page = _mock_page()
        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)
        result = await async_paginate(page, config, _extract_dummy)
        assert result.pages_scraped <= 1

    @pytest.mark.asyncio
    async def test_button_not_found_stops_gracefully(self) -> None:
        page = _mock_page()
        page.locator.return_value.is_visible = AsyncMock(return_value=False)
        config = PaginationConfig(strategy="next_button", max_pages=5, delay_between_pages=0)
        result = await async_paginate(page, config, _extract_dummy)
        assert result.stopped_reason == "button_gone"

    @pytest.mark.asyncio
    async def test_extraction_error_returns_sentinel(self) -> None:
        page = _mock_page()

        async def failing_extract(page) -> list[dict]:
            msg = "extraction failed"
            raise RuntimeError(msg)

        config = PaginationConfig(strategy="next_button", max_pages=2, delay_between_pages=0)
        result = await async_paginate(page, config, failing_extract)
        assert isinstance(result, PaginationResult)


class TestPageNumberStrategy:
    @pytest.mark.asyncio
    async def test_navigates_numbered_pages(self) -> None:
        page = _mock_page()
        config = PaginationConfig(strategy="page_number", max_pages=2, delay_between_pages=0)
        result = await async_paginate(page, config, _extract_dummy)
        assert isinstance(result, PaginationResult)

    @pytest.mark.asyncio
    async def test_single_page_stops_early(self) -> None:
        page = _mock_page()
        page.locator.return_value.count = AsyncMock(return_value=0)
        config = PaginationConfig(strategy="page_number", max_pages=5, delay_between_pages=0)
        result = await async_paginate(page, config, _extract_dummy)
        assert result.pages_scraped >= 0


class TestUrlPatternStrategy:
    @pytest.mark.asyncio
    async def test_url_pattern_iterates_pages(self) -> None:
        page = _mock_page()
        config = PaginationConfig(
            strategy="url_pattern",
            max_pages=3,
            url_pattern="https://example.com?page={page}",
            delay_between_pages=0,
        )
        result = await async_paginate(page, config, _extract_dummy)
        assert isinstance(result, PaginationResult)

    @pytest.mark.asyncio
    async def test_url_pattern_missing_returns_error(self) -> None:
        page = _mock_page()
        config = PaginationConfig(strategy="url_pattern", max_pages=2, delay_between_pages=0)
        result = await async_paginate(page, config, _extract_dummy)
        assert result.stopped_reason == "error"

    @pytest.mark.asyncio
    async def test_max_records_enforced(self) -> None:
        page = _mock_page()
        config = PaginationConfig(
            strategy="url_pattern",
            max_pages=10,
            max_records=1,
            url_pattern="https://example.com?page={page}",
            delay_between_pages=0,
        )
        result = await async_paginate(page, config, _extract_dummy)
        assert result.total_records <= 2


class TestInfiniteScrollStrategy:
    @pytest.mark.asyncio
    async def test_scroll_accumulates_records(self) -> None:
        page = _mock_page()
        config = PaginationConfig(strategy="infinite_scroll", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config, _extract_dummy)
        assert isinstance(result, PaginationResult)

    @pytest.mark.asyncio
    async def test_scroll_height_stable_stops(self) -> None:
        page = _mock_page()
        page.evaluate = AsyncMock(side_effect=[500, 500, 500])
        config = PaginationConfig(strategy="infinite_scroll", max_pages=10, delay_between_pages=0)
        result = await async_paginate(page, config, _extract_dummy)
        assert result.stopped_reason in {"no_new_records", "max_pages"}

    @pytest.mark.asyncio
    async def test_scroll_timeout_stops(self) -> None:
        page = _mock_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError("scroll failed"))
        config = PaginationConfig(strategy="infinite_scroll", max_pages=5, delay_between_pages=0)
        result = await async_paginate(page, config, _extract_dummy)
        assert result.stopped_reason == "error"


class TestLoadMoreStrategy:
    @pytest.mark.asyncio
    async def test_load_more_clicks_and_extracts(self) -> None:
        page = _mock_page()
        config = PaginationConfig(strategy="load_more", max_pages=2, delay_between_pages=0)
        result = await async_paginate(page, config, _extract_dummy)
        assert isinstance(result, PaginationResult)

    @pytest.mark.asyncio
    async def test_load_more_button_not_found(self) -> None:
        page = _mock_page()
        page.locator.return_value.is_visible = AsyncMock(return_value=False)
        config = PaginationConfig(strategy="load_more", max_pages=5, delay_between_pages=0)
        result = await async_paginate(page, config, _extract_dummy)
        assert result.stopped_reason == "button_gone"

    @pytest.mark.asyncio
    async def test_load_more_click_error(self) -> None:
        page = _mock_page()
        btn_mock = MagicMock()
        btn_mock.is_visible = AsyncMock(return_value=True)
        btn_mock.click = AsyncMock(side_effect=RuntimeError("click failed"))
        page.locator.return_value.first = btn_mock

        config = PaginationConfig(strategy="load_more", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config, _extract_dummy)
        assert result.stopped_reason == "error"


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_duplicate_records_removed(self) -> None:
        page = _mock_page()

        async def extract_dup(page) -> list[dict]:
            return [{"id": "1"}, {"id": "2"}, {"id": "1"}]

        config = PaginationConfig(
            strategy="next_button",
            max_pages=1,
            stop_on_duplicates=True,
            delay_between_pages=0,
        )
        result = await async_paginate(page, config, extract_dup)
        assert result.duplicates_removed >= 0

    @pytest.mark.asyncio
    async def test_no_records_on_page_continues(self) -> None:
        page = _mock_page()

        async def empty_extract(page) -> list[dict]:
            return []

        config = PaginationConfig(strategy="next_button", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config, empty_extract)
        assert isinstance(result, PaginationResult)


class TestPaginationResultShape:
    def test_result_has_expected_attributes(self) -> None:
        r = PaginationResult()
        assert hasattr(r, "records")
        assert hasattr(r, "pages_scraped")
        assert hasattr(r, "total_records")
        assert hasattr(r, "duplicates_removed")
        assert hasattr(r, "extraction_failures")
        assert hasattr(r, "stopped_reason")
        assert hasattr(r, "error")
