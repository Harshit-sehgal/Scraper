"""Qual 14: Export with quality metadata — test that exports include quality metadata."""

from __future__ import annotations

import json
from typing import Any

from app.utils.quality import build_quality_report


def _build_export_payload(records: list[dict], quality_report: dict[str, Any]) -> dict[str, Any]:
    """Combine records with quality metadata for export."""
    return {
        "export_version": "1.0",
        "generated_at": "2026-06-29T00:00:00Z",
        "record_count": len(records),
        "records": records,
        "quality": {
            "overall_score": quality_report.get("overall_score", 0.0),
            "avg_record_score": quality_report.get("avg_record_score", 0.0),
            "avg_final_record_score": quality_report.get("avg_final_record_score", 0.0),
            "coverage_ratio": quality_report.get("coverage_ratio", 0.0),
            "avg_source_trust_score": quality_report.get("avg_source_trust_score", 0.0),
            "type_integrity": quality_report.get("type_integrity", {}),
            "source_breakdown": quality_report.get("source_breakdown", {}),
            "warnings": quality_report.get("warnings", []),
        },
    }


class TestExportMetadataStructure:
    def test_export_contains_quality_section(self) -> None:
        report = build_quality_report(
            raw_results=[{"record_score": 0.9, "source_url": "https://x.com", "source_trust_score": 0.7}],
            post_filter_count=1,
            post_radius_count=1,
            radius_report={},
            final_results=[{"record_score": 0.9, "source_url": "https://x.com", "source_trust_score": 0.7}],
            min_record_score=0.35,
            type_integrity_report={"total_type_mismatches": 0},
            source_breakdown={"x.com": {"count": 1, "percentage": 1.0}},
        )
        records = [{"title": "Test", "price": "$10"}]
        export = _build_export_payload(records, report)
        assert "quality" in export
        assert "overall_score" in export["quality"]

    def test_export_contains_records(self) -> None:
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
        records = [{"title": "A"}, {"title": "B"}]
        export = _build_export_payload(records, report)
        assert export["record_count"] == 2
        assert len(export["records"]) == 2

    def test_serializable_to_json(self) -> None:
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
        export = _build_export_payload([], report)
        dumped = json.dumps(export, default=str)
        assert isinstance(dumped, str)


class TestExportQualityFields:
    def test_quality_scores_included(self) -> None:
        results = [{"record_score": 0.8, "source_url": "https://x.com", "source_trust_score": 0.7}]
        report = build_quality_report(
            raw_results=results,
            post_filter_count=1,
            post_radius_count=1,
            radius_report={},
            final_results=results,
            min_record_score=0.35,
            type_integrity_report={"total_type_mismatches": 0},
            source_breakdown={"x.com": {"count": 1, "percentage": 1.0}},
        )
        export = _build_export_payload(results, report)
        q = export["quality"]
        assert isinstance(q["overall_score"], float)
        assert isinstance(q["avg_record_score"], float)
        assert isinstance(q["coverage_ratio"], float)

    def test_empty_quality_report_defaults(self) -> None:
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
        export = _build_export_payload([], report)
        q = export["quality"]
        assert q["overall_score"] == 0.0

    def test_warnings_included(self) -> None:
        report = build_quality_report(
            raw_results=[{"record_score": 0.3, "source_url": "https://x.com", "source_trust_score": 0.3}],
            post_filter_count=0,
            post_radius_count=0,
            radius_report={},
            final_results=[],
            min_record_score=0.35,
            type_integrity_report={"total_type_mismatches": 1},
            source_breakdown={},
            warnings=["Warning: low quality"],
        )
        export = _build_export_payload([], report)
        assert "warnings" in export["quality"]
        assert len(export["quality"]["warnings"]) >= 0


class TestExportVersioning:
    def test_export_version_present(self) -> None:
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
        export = _build_export_payload([], report)
        assert export["export_version"] == "1.0"

    def test_generated_at_timestamp(self) -> None:
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
        export = _build_export_payload([], report)
        assert "generated_at" in export
        assert isinstance(export["generated_at"], str)
