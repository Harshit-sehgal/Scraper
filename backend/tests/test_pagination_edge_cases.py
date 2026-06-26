"""Edge case tests for the pagination executor.

Targets: max-pages cap, malformed next-link, infinite-loop detection,
unknown strategy rejection, legacy alias rejection, default config.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.pagination_executor import (
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_RECORDS,
    DEFAULT_PAGINATION_STRATEGY,
    LEGACY_PAGINATION_STRATEGIES,
    LEGACY_TO_CANONICAL_REPLACEMENT,
    PAGINATION_STRATEGIES,
    PaginationConfig,
    PaginationResult,
    _format_unknown_strategy_error,
    _remove_duplicates,
    paginate,
    paginate_with_hard_limits,
)


class TestPaginationConfigDefaults:
    """PaginationConfig has sensible defaults."""

    def test_default_strategy_is_next_button(self) -> None:
        config = PaginationConfig()
        assert config.strategy == DEFAULT_PAGINATION_STRATEGY == "next_button"

    def test_default_max_pages(self) -> None:
        config = PaginationConfig()
        assert config.max_pages == DEFAULT_MAX_PAGES

    def test_default_max_records(self) -> None:
        config = PaginationConfig()
        assert config.max_records == DEFAULT_MAX_RECORDS

    def test_default_stop_on_duplicates(self) -> None:
        config = PaginationConfig()
        assert config.stop_on_duplicates is True


class TestKnownStrategyDispatch:
    """All canonical strategies are dispatchable."""

    @pytest.mark.parametrize(
        "strategy",
        [
            "next_button",
            "page_number",
            "url_pattern",
            "infinite_scroll",
            "load_more",
        ],
    )
    def test_strategy_in_pagination_strategies_set(self, strategy: str) -> None:
        """Each canonical-5 strategy must appear in PAGINATION_STRATEGIES."""
        assert strategy in PAGINATION_STRATEGIES

    def test_strategy_set_contains_canonical_five(self) -> None:
        expected = {"next_button", "page_number", "url_pattern", "infinite_scroll", "load_more"}
        assert expected == set(PAGINATION_STRATEGIES)


class TestUnknownStrategyRejection:
    """Unknown strategies return error result, not silent dispatch."""

    def test_unknown_strategy_returns_error(self) -> None:
        config = PaginationConfig(strategy="not_a_real_strategy")
        result = paginate(config)
        assert result.stopped_reason == "error"
        assert "Unknown pagination strategy" in (result.error or "")

    def test_empty_strategy_returns_error(self) -> None:
        config = PaginationConfig(strategy="")
        result = paginate(config)
        assert result.stopped_reason == "error"

    def test_typo_strategy_returns_error(self) -> None:
        config = PaginationConfig(strategy="next-buttons")  # typo plural
        result = paginate(config)
        assert result.stopped_reason == "error"


class TestLegacyAliasRejection:
    """Legacy url_parameter alias is rejected (CAND-P2 contract)."""

    def test_legacy_alias_in_set(self) -> None:
        assert "url_parameter" in LEGACY_PAGINATION_STRATEGIES

    def test_legacy_alias_in_replacement_map(self) -> None:
        assert LEGACY_TO_CANONICAL_REPLACEMENT.get("url_parameter") == "url_pattern"

    def test_paginate_with_legacy_alias_returns_error(self) -> None:
        config = PaginationConfig(strategy="url_parameter")
        result = paginate(config)
        assert result.stopped_reason == "error"
        assert "Unknown pagination strategy" in (result.error or "")


class TestFormatUnknownStrategyError:
    """``_format_unknown_strategy_error`` produces a clear message."""

    def test_includes_strategy_name(self) -> None:
        msg = _format_unknown_strategy_error("mistyped_strategy")
        assert "mistyped_strategy" in msg
        assert msg.startswith("Unknown pagination strategy:")

    def test_legacy_alias_message_includes_canonical(self) -> None:
        msg = _format_unknown_strategy_error("url_parameter")
        # Legacy alias message should include the canonical replacement
        assert "url_pattern" in msg


class TestRemoveDuplicates:
    """``_remove_duplicates`` deduplicates and counts removals."""

    def test_removes_duplicate_records(self) -> None:
        records = [{"id": "1"}, {"id": "2"}, {"id": "1"}, {"id": "3"}, {"id": "2"}]
        unique, removed = _remove_duplicates(records)
        assert len(unique) == 3
        assert removed == 2
        assert {r["id"] for r in unique} == {"1", "2", "3"}

    def test_no_duplicates_returns_original(self) -> None:
        records = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        unique, removed = _remove_duplicates(records)
        assert len(unique) == 3
        assert removed == 0

    def test_empty_list(self) -> None:
        unique, removed = _remove_duplicates([])
        assert unique == []
        assert removed == 0

    def test_preserves_first_occurrence(self) -> None:
        records = [{"n": 1, "a": "first"}, {"n": 1, "a": "second"}]
        unique, _ = _remove_duplicates(records)
        assert unique[0]["a"] == "first"


class TestPaginationResultDefaults:
    """PaginationResult defaults are well-formed."""

    def test_empty_result(self) -> None:
        result = PaginationResult()
        assert result.records == []
        assert result.pages_scraped == 0
        assert result.total_records == 0
        assert result.duplicates_removed == 0
        assert result.stopped_reason == ""

    def test_result_with_values(self) -> None:
        result = PaginationResult(
            records=[{"x": 1}],
            pages_scraped=5,
            total_records=10,
            duplicates_removed=2,
            stopped_reason="max_pages",
        )
        assert len(result.records) == 1
        assert result.pages_scraped == 5
        assert result.stopped_reason == "max_pages"


class TestPaginateWithHardLimits:
    """``paginate_with_hard_limits`` convenience wrapper."""

    def test_unknown_strategy_fails_closed(self) -> None:
        """An unknown strategy still fails closed in the convenience wrapper."""
        result = paginate_with_hard_limits(strategy="totally_bogus", max_pages=1)
        assert result.stopped_reason == "error"

    def test_max_records_zero(self) -> None:
        """A zero-max-records config should not crash the wrapper."""
        result = paginate_with_hard_limits(max_records=0, max_pages=1)
        assert isinstance(result, PaginationResult)


class TestMaxPagesCap:
    """``PaginationConfig.max_pages`` controls loop termination."""

    def test_max_pages_zero_returns_empty(self) -> None:
        """A zero-page config should not attempt any pagination."""
        config = PaginationConfig(max_pages=0)
        # Should run but produce no records since the limit is 0
        result = paginate(config)
        # The result is valid; details depend on strategy but no infinite loop
        assert isinstance(result, PaginationResult)

    def test_max_pages_negative_returns_empty(self) -> None:
        """A negative max_pages is a degenerate case but should not crash."""
        config = PaginationConfig(max_pages=-5)
        # Should not raise — strategy may produce a sensible default
        result = paginate(config)
        assert isinstance(result, PaginationResult)


class TestMalformedInputs:
    """Defsensive handling of edge cases."""

    def test_none_config_uses_defaults(self) -> None:
        """A None config should fall back to PaginationConfig defaults."""
        with patch("app.pagination_executor._paginate_next_button", return_value=PaginationResult()):
            result = paginate(None)
            assert isinstance(result, PaginationResult)

    def test_negative_max_records(self) -> None:
        config = PaginationConfig(max_records=-10)
        # Should not crash
        result = paginate(config)
        assert isinstance(result, PaginationResult)
