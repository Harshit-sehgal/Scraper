"""Tests for synchronous pagination implementations.

Roadmap: Rel 5 — sync pagination implementations.
Tests the async-to-sync wrappers that use httpx + BeautifulSoup.
"""

from __future__ import annotations

from app.pagination_executor import (
    PAGINATION_STRATEGIES,
    PaginationConfig,
    PaginationResult,
    paginate,
    paginate_with_hard_limits,
)


class TestSyncPaginateDispatch:
    def test_default_config_returns_result(self) -> None:
        result = paginate()
        assert isinstance(result, PaginationResult)

    def test_next_button_strategy_dispatches(self) -> None:
        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)
        result = paginate(config)
        assert isinstance(result, PaginationResult)

    def test_page_number_strategy_dispatches(self) -> None:
        config = PaginationConfig(
            strategy="page_number",
            max_pages=1,
            url_pattern="https://example.com?p={page}",
            delay_between_pages=0,
        )
        result = paginate(config)
        assert isinstance(result, PaginationResult)

    def test_url_pattern_strategy_dispatches(self) -> None:
        config = PaginationConfig(
            strategy="url_pattern",
            max_pages=1,
            url_pattern="https://example.com?page={page}",
            delay_between_pages=0,
        )
        result = paginate(config)
        assert isinstance(result, PaginationResult)

    def test_infinite_scroll_returns_requires_browser(self) -> None:
        config = PaginationConfig(strategy="infinite_scroll", delay_between_pages=0)
        result = paginate(config)
        assert result.stopped_reason == "requires_browser"

    def test_load_more_returns_requires_browser(self) -> None:
        config = PaginationConfig(strategy="load_more", delay_between_pages=0)
        result = paginate(config)
        assert result.stopped_reason == "requires_browser"

    def test_load_more_with_url_pattern_falls_back(self) -> None:
        config = PaginationConfig(
            strategy="load_more",
            max_pages=1,
            url_pattern="https://example.com?p={page}",
            delay_between_pages=0,
        )
        result = paginate(config)
        assert isinstance(result, PaginationResult)

    def test_unknown_strategy_returns_error(self) -> None:
        config = PaginationConfig(strategy="bogus")
        result = paginate(config)
        assert result.stopped_reason == "error"

    def test_legacy_url_parameter_rejected(self) -> None:
        config = PaginationConfig(strategy="url_parameter")
        result = paginate(config)
        assert result.stopped_reason == "error"


class TestSyncPaginateHardLimits:
    def test_max_records_enforced(self) -> None:
        result = paginate_with_hard_limits(
            strategy="next_button",
            max_pages=100,
            max_records=3,
            delay_between_pages=0,
        )
        assert result.total_records <= 3

    def test_max_pages_enforced(self) -> None:
        result = paginate_with_hard_limits(
            strategy="next_button",
            max_pages=1,
            max_records=999,
            delay_between_pages=0,
        )
        assert result.pages_scraped <= 1

    def test_zero_runtime_returns_timeout(self) -> None:
        result = paginate_with_hard_limits(
            strategy="next_button",
            max_pages=10,
            max_runtime_seconds=0,
            delay_between_pages=0,
        )
        assert result.stopped_reason == "timeout"


class TestSyncPaginationResultShape:
    def test_page_number_requires_url_pattern(self) -> None:
        config = PaginationConfig(strategy="page_number", max_pages=1, delay_between_pages=0)
        result = paginate(config)
        assert result.stopped_reason == "error"
        assert result.error is not None
        assert "requires" in result.error.lower()

    def test_url_pattern_requires_placeholder(self) -> None:
        config = PaginationConfig(
            strategy="url_pattern",
            max_pages=1,
            url_pattern="https://example.com?no_template",
            delay_between_pages=0,
        )
        result = paginate(config)
        assert result.stopped_reason == "error"

    def test_all_results_have_stopped_reason(self) -> None:
        for strategy in PAGINATION_STRATEGIES:
            config = PaginationConfig(strategy=strategy, max_pages=1, delay_between_pages=0)
            r = paginate(config)
            assert r.stopped_reason, f"Strategy {strategy} has no stopped_reason"
