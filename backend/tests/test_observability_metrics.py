"""Obs 1: Extraction-specific Prometheus metrics — test metric counters."""

from __future__ import annotations

import pytest
from app.metrics_collector import (
    get_domain_extraction_counts,
    get_extraction_failure_counts,
    record_extraction_attempted,
    record_extraction_failed,
    record_extraction_succeeded,
    reset_for_testing,
)


@pytest.fixture(autouse=True)
def _reset_metrics():
    reset_for_testing()
    yield


class TestExtractionAttemptedMetrics:
    def test_records_attempted_domain(self) -> None:
        record_extraction_attempted(domain="example.com")
        counts = get_domain_extraction_counts()
        assert counts.get("example.com", {}).get("attempted", 0) == 1

    def test_records_attempted_strategy(self) -> None:
        record_extraction_attempted(strategy="playwright_full")
        counts = get_domain_extraction_counts()
        assert counts.get("strategy:playwright_full", {}).get("attempted", 0) == 1

    def test_records_attempted_cascade_layer(self) -> None:
        record_extraction_attempted(cascade_layer="regex")
        counts = get_domain_extraction_counts()
        assert counts.get("layer:regex", {}).get("attempted", 0) == 1

    def test_multiple_attempts_increment(self) -> None:
        record_extraction_attempted(domain="example.com")
        record_extraction_attempted(domain="example.com")
        counts = get_domain_extraction_counts()
        assert counts["example.com"]["attempted"] == 2


class TestExtractionSucceededMetrics:
    def test_records_success(self) -> None:
        record_extraction_succeeded(domain="example.com")
        counts = get_domain_extraction_counts()
        assert counts["example.com"]["succeeded"] == 1

    def test_attempted_and_succeeded_tracked(self) -> None:
        record_extraction_attempted(domain="example.com")
        record_extraction_succeeded(domain="example.com")
        counts = get_domain_extraction_counts()["example.com"]
        assert counts["attempted"] == 1
        assert counts["succeeded"] == 1


class TestExtractionFailedMetrics:
    def test_records_failure_category(self) -> None:
        record_extraction_failed(category="timeout")
        counts = get_extraction_failure_counts()
        assert counts.get("timeout", 0) == 1

    def test_unknown_category_clamped(self) -> None:
        from app.metrics_collector import record_extraction_failure

        record_extraction_failure("unknown_thing")
        counts = get_extraction_failure_counts()
        assert counts.get("unknown", 0) == 1

    def test_all_categories_in_output(self) -> None:
        counts = get_extraction_failure_counts()
        for cat in (
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
        ):
            assert cat in counts

    def test_failure_with_domain(self) -> None:
        record_extraction_failed(category="block", domain="blocked.com")
        counts = get_domain_extraction_counts()
        assert counts.get("blocked.com", {}).get("failed", 0) == 1


class TestExtractionMetricsReset:
    def test_reset_clears_failures(self) -> None:
        record_extraction_failed(category="timeout")
        reset_for_testing()
        assert all(v == 0 for v in get_extraction_failure_counts().values())

    def test_reset_clears_domain_counts(self) -> None:
        record_extraction_attempted(domain="example.com")
        reset_for_testing()
        assert get_domain_extraction_counts() == {}
