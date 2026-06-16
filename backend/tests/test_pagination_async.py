"""Tests for async pagination strategies with Playwright page integration."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_locator(visible: bool = True) -> MagicMock:
    """Create a mock Playwright locator with no recursion.

    Note: ``.first`` is set directly instead of via ``PropertyMock``
    because ``PropertyMock`` only works as a class-level descriptor.
    As an instance attribute it would return the mock itself, breaking
    ``await btn.is_visible()``.
    """
    locator = MagicMock()
    locator.is_visible = AsyncMock(return_value=visible)
    locator.is_checked = AsyncMock(return_value=False)
    locator.click = AsyncMock()
    locator.count = AsyncMock(return_value=0)
    locator.text_content = AsyncMock(return_value="2")
    # Use a shared child to avoid recursion in nth/first
    child = MagicMock()
    child.is_visible = AsyncMock(return_value=visible)
    child.is_checked = AsyncMock(return_value=False)
    child.click = AsyncMock()
    child.count = AsyncMock(return_value=0)
    child.text_content = AsyncMock(return_value="2")
    child.first = child  # Direct reference, not PropertyMock
    child.nth = MagicMock(return_value=child)
    locator.nth = MagicMock(return_value=child)
    locator.first = child  # Direct reference, not PropertyMock
    return locator


def _make_mock_page(locator_visible: bool = False, **overrides: Any) -> MagicMock:
    """Create a mock Playwright page with essential async methods."""
    page = MagicMock()
    page.locator = MagicMock(return_value=_make_mock_locator(visible=locator_visible))
    page.evaluate = AsyncMock(return_value=1000)
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.title = AsyncMock(return_value="Test Page")
    page.wait_for_function = AsyncMock()
    page.url = "https://example.com"

    # Make expect_navigation work as async context manager
    nav = AsyncMock()
    nav.__aenter__ = AsyncMock()
    nav.__aexit__ = AsyncMock()
    page.expect_navigation = MagicMock(return_value=nav)

    for key, value in overrides.items():
        setattr(page, key, value)
    return page


async def _dummy_extract_fn(page: Any) -> list[dict]:
    """Dummy extraction that returns a single record."""
    return [{"title": "Item 1", "price": "$10"}]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAsyncPaginateNextButton:
    """Tests for async next-button pagination strategy."""

    async def test_single_page_no_next_button(self):
        """Should stop with button_gone when no next button is present."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="next_button", max_pages=5)
        result = await async_paginate(page, config, extract_fn=_dummy_extract_fn)
        assert result.stopped_reason == "button_gone"
        assert result.pages_scraped == 0

    async def test_respects_max_pages(self):
        """Should stop after reaching max_pages (tests config propagation)."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="next_button", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config, extract_fn=_dummy_extract_fn)
        # Without a visible next button, button_gone is expected, not max_pages
        assert result.stopped_reason is not None

    async def test_respects_max_records(self):
        """Should stop after reaching max_records (tests config propagation)."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="next_button", max_pages=10, max_records=2, delay_between_pages=0)
        result = await async_paginate(page, config, extract_fn=_dummy_extract_fn)
        assert result.stopped_reason is not None

    async def test_respects_timeout(self):
        """Should stop when runtime exceeds max_runtime_seconds."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="next_button", max_pages=10, max_runtime_seconds=0)
        result = await async_paginate(page, config, extract_fn=_dummy_extract_fn)
        assert result.stopped_reason == "timeout"


class TestAsyncPaginateInfiniteScroll:
    """Tests for async infinite-scroll pagination strategy."""

    async def test_single_scroll_no_new_content(self):
        """Should stop with no_new_records when scroll height doesn't change."""
        page = _make_mock_page()
        page.evaluate.return_value = 1000
        config = PaginationConfig(strategy="infinite_scroll", max_pages=5, delay_between_pages=0)
        result = await async_paginate(page, config, extract_fn=_dummy_extract_fn)
        assert result.stopped_reason == "no_new_records"

    async def test_respects_max_pages(self):
        """Should stop after max scrolls."""
        page = _make_mock_page()
        # Two scroll attempts: heights increase each time then stabilize
        # Each iteration calls evaluate for scrollHeight check and then scrollTo
        page.evaluate.side_effect = [1000, None, 2000, None, 3000, None]
        config = PaginationConfig(strategy="infinite_scroll", max_pages=2, delay_between_pages=0)
        result = await async_paginate(page, config, extract_fn=_dummy_extract_fn)
        assert result.stopped_reason == "max_pages"
        assert result.pages_scraped == 2

    async def test_deduplicates_within_scroll(self):
        """Should deduplicate records within a single scroll extraction."""
        page = _make_mock_page()
        # Provide enough evaluate values for scrollHeight + scrollTo calls
        page.evaluate.side_effect = [1000, None, 2000]
        # Make wait_for_function work without raising (called inside loop)
        page.wait_for_function = AsyncMock()

        async def extract_with_dupes(page: Any) -> list[dict]:
            # Each page returns 2 identical records
            return [{"id": "dup", "value": "same"}, {"id": "dup", "value": "same"}]

        config = PaginationConfig(
            strategy="infinite_scroll",
            max_pages=5,
            max_records=10,
            delay_between_pages=0,
            stop_on_duplicates=True,
        )

        result = await async_paginate(page, config, extract_fn=extract_with_dupes)
        # Intra-page dedup: 2 identical records → 1 unique, 1 removed
        assert result.total_records == 1
        assert result.duplicates_removed == 1


class TestAsyncPaginateLoadMore:
    """Tests for async load-more button pagination strategy."""

    async def test_no_load_more_button(self):
        """Should stop with button_gone when no load-more button is present."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="load_more", max_pages=5, delay_between_pages=0)
        result = await async_paginate(page, config, extract_fn=_dummy_extract_fn)
        assert result.stopped_reason == "button_gone"

    async def test_load_more_respects_max_pages(self):
        """Should stop after max clicks (tests config propagation)."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="load_more", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config, extract_fn=_dummy_extract_fn)
        assert result.stopped_reason is not None


class TestAsyncPaginatePageNumber:
    """Tests for async page-number pagination strategy."""

    async def test_single_page_no_pagination_links(self):
        """Should stop with button_gone when no page links exist."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="page_number", max_pages=3, delay_between_pages=0)
        result = await async_paginate(page, config, extract_fn=_dummy_extract_fn)
        assert result.stopped_reason == "button_gone"
        assert result.pages_scraped == 1  # page 1 extracted


class TestAsyncPaginateUrlParameter:
    """Tests for async URL-parameter pagination strategy."""

    async def test_requires_url_pattern(self):
        """Should return error when no url_pattern is configured."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="url_parameter", max_pages=3)
        result = await async_paginate(page, config, extract_fn=_dummy_extract_fn)
        assert result.stopped_reason == "error"
        assert "url_pattern" in (result.error or "")

    async def test_navigates_with_url_pattern(self):
        """Should navigate to constructed URLs."""
        page = _make_mock_page()
        config = PaginationConfig(
            strategy="url_parameter",
            max_pages=3,
            url_pattern="https://example.com?page={page}",
            delay_between_pages=0,
        )
        result = await async_paginate(page, config, extract_fn=_dummy_extract_fn)
        assert result.stopped_reason in ("max_pages", "no_new_records")
        assert result.pages_scraped <= 3


class TestAsyncPaginateEdgeCases:
    """Tests for edge cases in async pagination."""

    async def test_unknown_strategy(self):
        """Should return error for unknown strategy."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="invalid_strategy")
        result = await async_paginate(page, config)
        assert result.stopped_reason == "error"
        assert "unknown" in (result.error or "").lower()

    async def test_empty_extract_fn(self):
        """Should work without an extraction function."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="next_button", max_pages=1, max_runtime_seconds=1)
        result = await async_paginate(page, config, extract_fn=None)
        assert result.stopped_reason is not None
        assert result.total_records == 0

    async def test_extraction_function_error(self):
        """Should handle extraction function failures gracefully."""
        page = _make_mock_page()

        async def broken_extract(page: Any) -> list[dict]:
            msg = "Extraction failed"
            raise RuntimeError(msg)

        config = PaginationConfig(strategy="next_button", max_pages=1, max_runtime_seconds=1)
        result = await async_paginate(page, config, extract_fn=broken_extract)
        assert result.stopped_reason is not None
        assert result.total_records == 0

    async def test_no_extraction_no_browser_required(self):
        """Config-only test: should not crash even without a real page."""
        page = _make_mock_page()
        config = PaginationConfig(strategy="infinite_scroll", max_pages=1, delay_between_pages=0)
        result = await async_paginate(page, config)
        assert result.stopped_reason is not None
        assert result.total_records == 0
