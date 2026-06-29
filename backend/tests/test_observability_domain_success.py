"""Obs 3: Per-domain success rate tracking — test rolling 24h success/failure rate."""

from __future__ import annotations

from typing import Any

import pytest
from app.metrics_collector import (
    get_domain_extraction_counts,
    record_domain_extraction,
    reset_for_testing,
)


@pytest.fixture(autouse=True)
def _reset_metrics():
    reset_for_testing()
    yield


def _domain_success_rate(domain: str) -> dict[str, Any]:
    """Compute success/failure rate for a domain from metrics."""
    counts = get_domain_extraction_counts()
    entry = counts.get(domain, {})
    success = entry.get("success", 0)
    failure = entry.get("failure", 0)
    total = success + failure
    return {
        "domain": domain,
        "attempts": total,
        "success": success,
        "failure": failure,
        "success_rate": round(success / max(total, 1), 3),
        "failure_rate": round(failure / max(total, 1), 3),
    }


class TestDomainSuccessRate:
    def test_all_successful(self) -> None:
        for _ in range(10):
            record_domain_extraction("example.com", success=True)
        rate = _domain_success_rate("example.com")
        assert rate["success_rate"] == 1.0
        assert rate["failure_rate"] == 0.0

    def test_all_failures(self) -> None:
        for _ in range(5):
            record_domain_extraction("example.com", success=False)
        rate = _domain_success_rate("example.com")
        assert rate["success_rate"] == 0.0

    def test_mixed_results(self) -> None:
        for _ in range(8):
            record_domain_extraction("example.com", success=True)
        for _ in range(2):
            record_domain_extraction("example.com", success=False)
        rate = _domain_success_rate("example.com")
        assert rate["success_rate"] == 0.8
        assert rate["failure_rate"] == 0.2

    def test_no_attempts(self) -> None:
        rate = _domain_success_rate("unknown.com")
        assert rate["attempts"] == 0
        assert rate["success_rate"] == 0.0

    def test_multiple_domains(self) -> None:
        record_domain_extraction("good.com", success=True)
        record_domain_extraction("good.com", success=True)
        record_domain_extraction("bad.com", success=False)
        good_rate = _domain_success_rate("good.com")
        bad_rate = _domain_success_rate("bad.com")
        assert good_rate["success_rate"] == 1.0
        assert bad_rate["success_rate"] == 0.0

    def test_large_volume(self) -> None:
        for _ in range(100):
            record_domain_extraction("example.com", success=True)
        for _ in range(100):
            record_domain_extraction("example.com", success=False)
        rate = _domain_success_rate("example.com")
        assert rate["success_rate"] == 0.5
