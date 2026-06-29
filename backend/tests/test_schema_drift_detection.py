"""Tests for schema drift detection in extraction diff (Roadmap Qual 13).

Builds on the existing extraction_diff tests with additional scenarios
for field-level drift, quality regression, and full-run comparison.
"""

from __future__ import annotations

from typing import Any

from app.extraction_diff import compute_extraction_diff


def _record(**kwargs: Any) -> dict[str, Any]:
    return kwargs


class TestSchemaFieldDrift:
    """Field-level schema drift detection (Qual 13)."""

    def test_no_drift_with_identical_schemas(self) -> None:
        baseline = [_record(id="1", title="A", price=10)]
        current = [_record(id="1", title="A", price=10)]
        diff = compute_extraction_diff(baseline, current)
        assert diff.schema_changed is False
        assert diff.added_fields == []
        assert diff.removed_fields == []

    def test_field_added_to_some_records_is_drift(self) -> None:
        baseline = [_record(id="1", title="A"), _record(id="2", title="B")]
        current = [_record(id="1", title="A", rating=4.5), _record(id="2", title="B")]
        diff = compute_extraction_diff(baseline, current)
        assert "rating" in diff.added_fields
        assert diff.schema_changed is True

    def test_field_removed_from_all_records_is_drift(self) -> None:
        baseline = [_record(id="1", title="A", price=10), _record(id="2", title="B", price=20)]
        current = [_record(id="1", title="A"), _record(id="2", title="B")]
        diff = compute_extraction_diff(baseline, current)
        assert "price" in diff.removed_fields
        assert diff.schema_changed is True

    def test_multiple_fields_added(self) -> None:
        baseline = [_record(id="1", title="A")]
        current = [_record(id="1", title="A", price=10, rating=4.5, in_stock=True)]
        diff = compute_extraction_diff(baseline, current)
        assert set(diff.added_fields) == {"price", "rating", "in_stock"}
        assert diff.removed_fields == []

    def test_multiple_fields_removed(self) -> None:
        baseline = [_record(id="1", title="A", price=10, rating=4.5, in_stock=True)]
        current = [_record(id="1", title="A")]
        diff = compute_extraction_diff(baseline, current)
        assert set(diff.removed_fields) == {"price", "rating", "in_stock"}
        assert diff.added_fields == []

    def test_drift_with_threshold_below_ratio(self) -> None:
        baseline = [_record(id="1", title="A", price=10, brand="Acme")]
        current = [_record(id="1", title="A", price=10, brand="Acme", rating=4.5)]
        diff = compute_extraction_diff(baseline, current, field_threshold=0.5)
        assert diff.added_fields == ["rating"]
        assert diff.schema_changed is False

    def test_drift_with_threshold_above_ratio(self) -> None:
        baseline = [_record(id="1", title="A", price=10)]
        current = [_record(id="1", title="A", price=10, rating=4.5, in_stock=True)]
        diff = compute_extraction_diff(baseline, current, field_threshold=0.3)
        assert diff.schema_changed is True

    def test_type_change_same_field_name(self) -> None:
        baseline = [_record(id="1", price=10), _record(id="2", price=20)]
        current = [_record(id="1", price="10.00"), _record(id="2", price="20.00")]
        diff = compute_extraction_diff(baseline, current)
        assert diff.modified_records
        assert diff.schema_changed is False


class TestQualityRegression:
    """Quality regression detection alongside schema drift."""

    def test_minor_record_loss_no_regression(self) -> None:
        baseline = [_record(id=str(i), price=i) for i in range(20)]
        current = [_record(id=str(i), price=i) for i in range(18)]
        diff = compute_extraction_diff(baseline, current)
        assert diff.quality_regression is False

    def test_fifty_percent_plus_loss_is_regression(self) -> None:
        baseline = [_record(id=str(i), price=i) for i in range(20)]
        current = [_record(id=str(i), price=i) for i in range(9)]
        diff = compute_extraction_diff(baseline, current)
        assert diff.quality_regression is True

    def test_fifty_percent_loss_is_major_regression(self) -> None:
        baseline = [_record(id=str(i), price=i) for i in range(20)]
        current = [_record(id=str(i), price=i) for i in range(5)]
        diff = compute_extraction_diff(baseline, current)
        assert diff.quality_regression is True
        assert diff.severity == "major"

    def test_severity_is_minor_for_small_loss(self) -> None:
        baseline = [_record(id=str(i), price=i) for i in range(20)]
        current = [_record(id=str(i), price=i) for i in range(19)]
        diff = compute_extraction_diff(baseline, current)
        assert diff.severity == "minor"

    def test_drift_with_quality_regression_sets_major(self) -> None:
        baseline = [_record(id="1", price=10), _record(id="2", price=20)]
        current: list[dict] = []
        diff = compute_extraction_diff(baseline, current)
        assert diff.quality_regression is True
        assert diff.severity == "major"

    def test_empty_baseline_no_regression(self) -> None:
        diff = compute_extraction_diff([], [_record(id="1", title="A")])
        assert diff.quality_regression is False


class TestRecordModifications:
    """Modified record detection in diff output."""

    def test_modified_record_fields_reported(self) -> None:
        baseline = [_record(id="a", title="Alpha", price=10)]
        current = [_record(id="a", title="Alpha", price=15)]
        diff = compute_extraction_diff(baseline, current)
        assert len(diff.modified_records) == 1
        modified = diff.modified_records[0]
        assert modified["key"] == "a"
        assert modified["baseline"]["price"] == 10
        assert modified["current"]["price"] == 15

    def test_multiple_modified_records(self) -> None:
        baseline = [_record(id="a", price=10), _record(id="b", price=20)]
        current = [_record(id="a", price=11), _record(id="b", price=22)]
        diff = compute_extraction_diff(baseline, current)
        assert len(diff.modified_records) == 2

    def test_added_field_detected_as_schema_change(self) -> None:
        baseline = [_record(id="a", price=10)]
        current = [_record(id="a", price=10, rating=4.5)]
        diff = compute_extraction_diff(baseline, current)
        assert "rating" in diff.added_fields
        assert diff.schema_changed is True

    def test_summary_contains_field_drift_info(self) -> None:
        baseline = [_record(id="1", title="A"), _record(id="2", title="B")]
        current = [_record(id="1", title="A", price=10), _record(id="2", title="B", price=20)]
        diff = compute_extraction_diff(baseline, current)
        assert "new fields" in diff.summary.lower()
        assert "price" in diff.summary.lower()

    def test_summary_contains_record_changes(self) -> None:
        baseline = [_record(id="1", title="A")]
        current = [_record(id="1", title="B")]
        diff = compute_extraction_diff(baseline, current)
        assert "modified" in diff.summary.lower()

    def test_summary_for_major_regression(self) -> None:
        baseline = [_record(id=str(i), price=i) for i in range(20)]
        current = [_record(id=str(i), price=i) for i in range(3)]
        diff = compute_extraction_diff(baseline, current)
        assert "QUALITY REGRESSION" in diff.summary
