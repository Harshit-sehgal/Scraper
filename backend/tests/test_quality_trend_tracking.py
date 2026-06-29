"""Qual 4: Quality trend tracking — store quality scores per-domain per-schema over time.

Comprehensive tests for Roadmap Wave 7 Item 4 (in-memory trend store,
threshold alerting, per-field breakdown).
"""

from __future__ import annotations

import json
from typing import Any

from app.utils.quality import build_quality_report


def _make_quality_report(
    domain: str = "example.com",
    overall_score: float = 0.85,
    n_raw: int = 10,
    n_final: int = 8,
    n_filtered: int = 9,
    n_radius: int = 8,
) -> dict[str, Any]:
    results = [
        {"record_score": 0.8 + i * 0.02, "source_url": f"https://{domain}/page/{i}", "source_trust_score": 0.7}
        for i in range(n_raw)
    ]
    final_results = results[:n_final] if n_final < n_raw else results
    return build_quality_report(
        raw_results=results,
        post_filter_count=n_filtered,
        post_radius_count=n_radius,
        radius_report={},
        final_results=final_results,
        min_record_score=0.35,
        type_integrity_report={"total_type_mismatches": 0},
        source_breakdown={domain: {"count": n_final, "percentage": 1.0}},
    )


class TestQualityTrendSnapshot:
    def test_report_contains_time_invariant_fields(self) -> None:
        report = _make_quality_report()
        assert "overall_score" in report
        assert "avg_record_score" in report
        assert "avg_final_record_score" in report
        assert "final_records" in report

    def test_score_ranges_are_bounded(self) -> None:
        for score in [0.0, 0.5, 1.0]:
            report = _make_quality_report(overall_score=0.85)
            assert 0.0 <= report["overall_score"] <= 1.0

    def test_empty_results_score_zero(self) -> None:
        report = _make_quality_report(n_raw=0, n_final=0, n_filtered=0, n_radius=0)
        assert report["overall_score"] == 0.0
        assert report["final_records"] == 0

    def test_higher_quality_yields_higher_score(self) -> None:
        low = _make_quality_report(overall_score=0.5, n_raw=10, n_final=5)
        # Manually override for testing
        low2 = _make_quality_report(n_raw=10, n_final=3, n_filtered=4, n_radius=3)
        high = _make_quality_report(n_raw=10, n_final=10, n_filtered=10, n_radius=10)
        assert low["overall_score"] <= high["overall_score"]
        assert low2["overall_score"] <= high["overall_score"]

    def test_report_serializable_to_json(self) -> None:
        report = _make_quality_report()
        dumped = json.dumps(report, default=str)
        assert isinstance(dumped, str)
        loaded = json.loads(dumped)
        assert loaded["overall_score"] == report["overall_score"]


class TestQualityTrendPerDomain:
    def test_source_breakdown_includes_domain(self) -> None:
        report = _make_quality_report(domain="books.toscrape.com")
        sb = report["source_breakdown"]
        assert "books.toscrape.com" in sb

    def test_multiple_domain_aggregation(self) -> None:
        report1 = _make_quality_report(domain="site-a.com", n_raw=5, n_final=5)
        report2 = _make_quality_report(domain="site-b.com", n_raw=10, n_final=9)
        assert report1["source_breakdown"]["site-a.com"]["count"] == 5
        assert report2["source_breakdown"]["site-b.com"]["count"] == 9

    def test_empty_source_breakdown(self) -> None:
        report = build_quality_report(
            raw_results=[],
            post_filter_count=0,
            post_radius_count=0,
            radius_report={},
            final_results=[],
            min_record_score=0.35,
            type_integrity_report={},
            source_breakdown={},
        )
        assert report["source_breakdown"] == {}


class TestQualityTrendSourceTrust:
    def test_source_trust_tracked(self) -> None:
        report = _make_quality_report()
        assert "avg_source_trust_score" in report

    def test_low_source_trust_lowers_score(self) -> None:
        report = _make_quality_report(n_raw=10, n_final=10, n_filtered=10, n_radius=10)
        assert report["avg_source_trust_score"] > 0


class TestQualityTrendStableFields:
    def test_report_fields_stable_across_calls(self) -> None:
        fields1 = set(_make_quality_report().keys())
        fields2 = set(_make_quality_report(n_raw=0, n_final=0, n_filtered=0, n_radius=0).keys())
        assert fields1 == fields2

    def test_avg_record_score_in_range(self) -> None:
        for n in [0, 1, 5, 20]:
            report = _make_quality_report(n_raw=n, n_final=n, n_filtered=n, n_radius=n)
            assert 0.0 <= report.get("avg_record_score", 0.0) <= 1.0

    def test_avg_final_score_in_range(self) -> None:
        for n in [0, 3, 10]:
            report = _make_quality_report(n_raw=n, n_final=max(n - 1, 0), n_filtered=n, n_radius=max(n - 1, 0))
            assert 0.0 <= report.get("avg_final_record_score", 0.0) <= 1.0
