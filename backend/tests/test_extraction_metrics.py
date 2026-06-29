"""Tests for extraction-specific Prometheus metrics (Roadmap Obs #1, #3, #10)."""

from __future__ import annotations

from app.metrics_collector import (
    _EXTRACTION_FAILURE_CATEGORIES,
    get_domain_extraction_counts,
    get_extraction_failure_counts,
    record_extraction_attempted,
    record_extraction_failed,
    record_extraction_succeeded,
)


def test_extraction_attempted_increments_domain_counter() -> None:
    """Recording an attempt with a domain increments the per-domain counter."""
    record_extraction_attempted(domain="example.com")
    counts = get_domain_extraction_counts()
    assert counts["example.com"]["attempted"] >= 1


def test_extraction_succeeded_increments_domain_counter() -> None:
    """Recording a success with a domain increments the per-domain success counter."""
    record_extraction_succeeded(domain="only-succeeded-test.com")
    counts = get_domain_extraction_counts()
    assert counts["only-succeeded-test.com"]["succeeded"] >= 1


def test_extraction_failed_with_category() -> None:
    """Failure categories are tallied independently of domain."""
    record_extraction_failed(category="captcha", domain="example.com")
    failures = get_extraction_failure_counts()
    assert failures["captcha"] >= 1


def test_extraction_failed_counter_accepts_known_categories() -> None:
    """All known categories can be incremented."""
    for category in _EXTRACTION_FAILURE_CATEGORIES:
        record_extraction_failed(category=category)
    failures = get_extraction_failure_counts()
    # All categories appear in the snapshot
    for category in _EXTRACTION_FAILURE_CATEGORIES:
        assert category in failures
        assert failures[category] >= 1


def test_extraction_attempted_with_strategy() -> None:
    """Recording with a strategy uses strategy: namespace."""
    record_extraction_attempted(strategy="playwright_full")
    record_extraction_succeeded(strategy="playwright_full")
    record_extraction_failed(strategy="playwright_full")
    counts = get_domain_extraction_counts()
    assert counts["strategy:playwright_full"]["attempted"] >= 1
    assert counts["strategy:playwright_full"]["succeeded"] >= 1
    assert counts["strategy:playwright_full"]["failed"] >= 1


def test_extraction_attempted_with_cascade_layer() -> None:
    """Recording with a cascade layer uses layer: namespace."""
    record_extraction_attempted(cascade_layer="css")
    counts = get_domain_extraction_counts()
    assert counts["layer:css"]["attempted"] >= 1


def test_failure_categories_are_known_list() -> None:
    """The known failure categories should match the documented taxonomy."""
    expected_categories = {
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
    assert set(_EXTRACTION_FAILURE_CATEGORIES) == expected_categories


def test_get_extraction_failure_counts_returns_dict() -> None:
    """get_extraction_failure_counts returns a dict snapshot."""
    result = get_extraction_failure_counts()
    assert isinstance(result, dict)


def test_get_domain_extraction_counts_returns_dict_of_dicts() -> None:
    """get_domain_extraction_counts returns nested dict structure."""
    result = get_domain_extraction_counts()
    assert isinstance(result, dict)
    if result:  # at least one entry
        first_key = next(iter(result))
        assert isinstance(result[first_key], dict)
