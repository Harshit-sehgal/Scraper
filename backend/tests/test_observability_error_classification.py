"""Obs 10: Error classification and aggregation — test error categorization."""

from __future__ import annotations

import pytest
from app.metrics_collector import (
    _EXTRACTION_FAILURE_CATEGORIES,
    get_extraction_failure_counts,
    record_extraction_failure,
    reset_for_testing,
)


@pytest.fixture(autouse=True)
def _reset_metrics():
    reset_for_testing()
    yield


class TestErrorCategories:
    def test_all_categories_accounted(self) -> None:
        expected = {
            "timeout",
            "block",
            "auth_required",
            "ssl_error",
            "network_error",
            "parse_error",
            "empty_page",
            "captcha",
            "rate_limit",
            "browser_crash",
            "unknown",
        }
        assert set(_EXTRACTION_FAILURE_CATEGORIES) == expected

    def test_each_category_increments_independently(self) -> None:
        for cat in _EXTRACTION_FAILURE_CATEGORIES:
            record_extraction_failure(cat)
        counts = get_extraction_failure_counts()
        for cat in _EXTRACTION_FAILURE_CATEGORIES:
            assert counts[cat] == 1

    def test_multiple_failures_aggregate(self) -> None:
        for _ in range(5):
            record_extraction_failure("timeout")
        for _ in range(3):
            record_extraction_failure("block")
        counts = get_extraction_failure_counts()
        assert counts["timeout"] == 5
        assert counts["block"] == 3

    def test_get_all_categories_returns_zero_for_unrecorded(self) -> None:
        counts = get_extraction_failure_counts()
        for cat in _EXTRACTION_FAILURE_CATEGORIES:
            assert cat in counts
            assert counts[cat] == 0

    def test_unknown_category_clamped(self) -> None:
        from app.metrics_collector import record_extraction_failure as rec_failure

        rec_failure("nonexistent_category")
        counts = get_extraction_failure_counts()
        assert counts.get("unknown", 0) == 1


class TestErrorAggregation:
    def test_timeout_spike_detectable(self) -> None:
        for _ in range(100):
            record_extraction_failure("timeout")
        counts = get_extraction_failure_counts()
        assert counts["timeout"] == 100
        total = sum(counts.values())
        timeout_ratio = counts["timeout"] / max(total, 1)
        assert timeout_ratio > 0.9

    def test_mixed_failures(self) -> None:
        record_extraction_failure("timeout")
        record_extraction_failure("network_error")
        record_extraction_failure("parse_error")
        counts = get_extraction_failure_counts()
        assert sum(counts.values()) == 3


class TestErrorReset:
    def test_reset_clears_all_categories(self) -> None:
        for cat in _EXTRACTION_FAILURE_CATEGORIES:
            record_extraction_failure(cat)
        reset_for_testing()
        counts = get_extraction_failure_counts()
        assert all(counts[cat] == 0 for cat in _EXTRACTION_FAILURE_CATEGORIES)

    def test_re_recording_after_reset(self) -> None:
        record_extraction_failure("timeout")
        reset_for_testing()
        record_extraction_failure("block")
        counts = get_extraction_failure_counts()
        assert counts["timeout"] == 0
        assert counts["block"] == 1
