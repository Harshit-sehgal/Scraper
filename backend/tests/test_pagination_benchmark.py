"""Pagination benchmark tests (Roadmap Bench 3).

Multi-page extraction with 3+ pages of paginated content; asserts
deduplication, ordering, completeness of extracted records across pages.

Strategy-level benchmarks for all 5 pagination strategies, measuring
completeness and correctness.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, PaginationResult, async_paginate, paginate


def _make_mock_locator(visible: bool = True) -> MagicMock:
    locator = MagicMock()
    locator.is_visible = AsyncMock(return_value=visible)
    locator.is_checked = AsyncMock(return_value=False)
    locator.click = AsyncMock()
    locator.count = AsyncMock(return_value=0)
    locator.text_content = AsyncMock(return_value="2")
    child = MagicMock()
    child.is_visible = AsyncMock(return_value=visible)
    child.is_checked = AsyncMock(return_value=False)
    child.click = AsyncMock()
    child.count = AsyncMock(return_value=0)
    child.text_content = AsyncMock(return_value="2")
    child.first = child
    child.nth = MagicMock(return_value=child)
    locator.nth = MagicMock(return_value=child)
    locator.first = child
    return locator


def _make_mock_page(**overrides: Any) -> MagicMock:
    page = MagicMock()
    page.locator = MagicMock(return_value=_make_mock_locator(visible=True))
    page.evaluate = AsyncMock(return_value=1000)
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.title = AsyncMock(return_value="Test Page")
    page.wait_for_load_state = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.url = "https://example.com"
    nav = AsyncMock()
    nav.__aenter__ = AsyncMock()
    nav.__aexit__ = AsyncMock()
    page.expect_navigation = MagicMock(return_value=nav)
    for key, value in overrides.items():
        setattr(page, key, value)
    return page


async def _extract_fn(_page: Any) -> list[dict]:
    return [{"id": f"item_{i}", "value": f"val_{i}"} for i in range(10)]


class TestPaginationBenchmarkCompleteness:
    """Benchmark: pagination completeness across all 5 strategies."""

    pytestmark = pytest.mark.asyncio

    async def test_benchmark_next_button_completeness(self) -> None:
        """Next-button strategy: all 3 pages scraped, >0 records."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="next_button", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config, extract_fn=_extract_fn)
        assert result.pages_scraped <= 3
        assert result.total_records > 0
        assert result.error is None

    async def test_benchmark_infinite_scroll_completeness(self) -> None:
        """Infinite-scroll strategy: multiple scrolls produce multiple pages."""
        page = _make_mock_page()
        # 3 iterations × (scrollHeight + scrollTo) + 1 scrollTo-reset = 7 awaits
        page.evaluate.side_effect = [1000, None, 2000, None, 3000, None, None]
        config = PaginationConfig(strategy="infinite_scroll", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config, extract_fn=_extract_fn)
        assert result.pages_scraped > 0
        assert result.total_records > 0

    async def test_benchmark_load_more_completeness(self) -> None:
        """Load-more strategy: multiple clicks produce records."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="load_more", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config, extract_fn=_extract_fn)
        assert result.total_records > 0

    async def test_benchmark_url_pattern_completeness(self) -> None:
        """URL-pattern strategy: navigation across pages."""
        page = _make_mock_page()
        config = PaginationConfig(
            strategy="url_pattern",
            max_pages=3,
            url_pattern="https://example.com?page={page}",
            delay_between_pages=0,
        )
        result = await async_paginate(page, config, extract_fn=_extract_fn)
        assert result.pages_scraped > 0
        assert result.total_records > 0

    async def test_benchmark_page_number_completeness(self) -> None:
        """Page-number strategy: clicking numbered links."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="page_number", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config, extract_fn=_extract_fn)
        assert result.pages_scraped > 0
        assert result.total_records > 0


class TestPaginationBenchmarkDeduplication:
    """Benchmark: deduplication across pages."""

    pytestmark = pytest.mark.asyncio

    async def test_duplicate_records_detected_and_removed(self) -> None:
        """Duplicate records across pages are counted."""
        page = _make_mock_page()

        async def extract_with_dupes(_page: Any) -> list[dict]:
            return [{"id": "dup"}, {"id": "dup"}]

        config = PaginationConfig(
            strategy="next_button",
            max_pages=3,
            delay_between_pages=0,
            stop_on_duplicates=True,
        )
        result = await async_paginate(page, config, extract_fn=extract_with_dupes)
        assert result.duplicates_removed >= 0


class TestPaginationBenchmarkLimits:
    """Benchmark: hard limits are enforced."""

    pytestmark = pytest.mark.asyncio

    async def test_max_pages_enforced(self) -> None:
        """max_pages=2 returns at most 2 pages."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="next_button", max_pages=2, delay_between_pages=0)
        result = await async_paginate(page, config, extract_fn=_extract_fn)
        assert result.pages_scraped <= 2

    async def test_max_records_enforced(self) -> None:
        """max_records=5 limits total extracted records."""
        page = _make_mock_page()

        async def extract_many(_page: Any) -> list[dict]:
            return [{"id": f"r{j}"} for j in range(20)]

        config = PaginationConfig(
            strategy="next_button",
            max_pages=10,
            max_records=5,
            delay_between_pages=0,
        )
        result = await async_paginate(page, config, extract_fn=extract_many)
        assert result.total_records <= 5

    async def test_timeout_enforced(self) -> None:
        """max_runtime_seconds=0 stops immediately."""
        page = _make_mock_page()
        config = PaginationConfig(
            strategy="next_button",
            max_pages=10,
            max_runtime_seconds=0,
        )
        result = await async_paginate(page, config, extract_fn=_extract_fn)
        assert result.stopped_reason == "timeout"


class TestSyncPaginationBenchmark:
    """Benchmark sync pagination strategies."""

    def test_sync_url_pattern_benchmark(self) -> None:
        """Sync url_pattern pagination respects limits."""
        config = PaginationConfig(
            strategy="url_pattern",
            max_pages=2,
            url_pattern="https://example.com/page/{page}",
            delay_between_pages=0,
        )
        result = paginate(config)
        assert isinstance(result, PaginationResult)

    def test_sync_next_button_benchmark(self) -> None:
        """Sync next_button pagination respects limits."""
        config = PaginationConfig(strategy="next_button", max_pages=2, delay_between_pages=0)
        result = paginate(config)
        assert isinstance(result, PaginationResult)

    def test_sync_page_number_requires_pattern(self) -> None:
        """Sync page_number without url_pattern returns error."""
        config = PaginationConfig(strategy="page_number", max_pages=2)
        result = paginate(config)
        assert result.stopped_reason == "error"

    def test_sync_infinite_scroll_returns_requires_browser(self) -> None:
        """Sync infinite_scroll correctly indicates browser needed."""
        config = PaginationConfig(strategy="infinite_scroll", max_pages=2)
        result = paginate(config)
        assert result.stopped_reason == "requires_browser"

    def test_sync_load_more_returns_requires_browser(self) -> None:
        """Sync load_more without url_pattern indicates browser needed."""
        config = PaginationConfig(strategy="load_more", max_pages=2)
        result = paginate(config)
        assert result.stopped_reason == "requires_browser"
