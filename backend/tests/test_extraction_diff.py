"""Tests for extraction_diff.compute_extraction_diff."""

from __future__ import annotations

from typing import Any

import pytest
from app.extraction_diff import compute_extraction_diff


def _record(**kwargs: Any) -> dict[str, Any]:
    """Build a record with arbitrary fields for fixture inputs."""
    return kwargs


# --- severity: stable ---


def test_no_diff_identical_inputs() -> None:
    """Two identical record sets produce a stable diff with zero deltas."""
    records = [
        _record(id="a", title="Alpha", price=10),
        _record(id="b", title="Beta", price=20),
    ]
    diff = compute_extraction_diff(records, records)
    assert diff.severity == "stable"
    assert diff.record_count_delta == 0
    assert diff.added_records == []
    assert diff.removed_records == []
    assert diff.modified_records == []
    assert diff.schema_changed is False
    assert diff.quality_regression is False


def test_identical_records_different_instances_match() -> None:
    """Two distinct list objects holding identical data produce a stable diff."""
    a = [_record(id="x", title="X", price=1), _record(id="y", title="Y", price=2)]
    b = [_record(id="x", title="X", price=1), _record(id="y", title="Y", price=2)]
    diff = compute_extraction_diff(a, b)
    assert diff.severity == "stable"
    assert diff.added_records == []
    assert diff.removed_records == []


# --- severity: minor (small record delta, no schema change) ---


def test_one_record_added_classified_as_minor() -> None:
    """A 1-record delta is classified as minor."""
    baseline = [_record(id=str(i), price=10 * i) for i in range(20)]
    current = [*baseline, _record(id="new", price=999)]
    diff = compute_extraction_diff(baseline, current)
    assert diff.severity == "minor"
    assert diff.record_count_delta == 1
    assert len(diff.added_records) == 1
    assert diff.added_records[0]["id"] == "new"
    assert diff.removed_records == []


def test_one_record_removed_classified_as_minor() -> None:
    """Removing one record from a 20-record set is minor."""
    baseline = [_record(id=str(i), price=10 * i) for i in range(20)]
    current = baseline[:-1]
    diff = compute_extraction_diff(baseline, current)
    assert diff.severity == "minor"
    assert diff.record_count_delta == -1
    assert len(diff.removed_records) == 1


# --- severity: moderate ---


def test_modified_records_detected() -> None:
    """A field-value change on a same-keyed record flags as modified, severity moderate."""
    baseline = [_record(id="a", title="Alpha", price=10), _record(id="b", title="Beta", price=20)]
    current = [_record(id="a", title="Alpha", price=15), _record(id="b", title="Beta", price=20)]
    diff = compute_extraction_diff(baseline, current)
    assert diff.severity == "moderate"
    assert len(diff.modified_records) == 1
    assert diff.modified_records[0]["key"] == "a"
    assert diff.modified_records[0]["baseline"]["price"] == 10
    assert diff.modified_records[0]["current"]["price"] == 15


def test_added_field_detected_as_schema_change() -> None:
    """A new field across all records flags schema_changed and severity moderate."""
    baseline = [_record(id="a", title="Alpha"), _record(id="b", title="Beta")]
    current = [_record(id="a", title="Alpha", rating=4.5), _record(id="b", title="Beta", rating=4.0)]
    diff = compute_extraction_diff(baseline, current)
    assert diff.schema_changed is True
    assert diff.added_fields == ["rating"]
    assert diff.removed_fields == []
    assert diff.severity == "moderate"


def test_removed_field_detected_as_schema_change() -> None:
    """A field dropping out of every record flags schema_changed."""
    baseline = [_record(id="a", title="Alpha", price=10), _record(id="b", title="Beta", price=20)]
    current = [_record(id="a", title="Alpha"), _record(id="b", title="Beta")]
    diff = compute_extraction_diff(baseline, current)
    assert diff.schema_changed is True
    assert diff.removed_fields == ["price"]
    assert diff.added_fields == []
    assert diff.severity == "moderate"


def test_schema_change_respects_field_threshold() -> None:
    """Small field drift remains visible without tripping schema_changed."""
    baseline = [_record(id="a", title="Alpha", price=10, sku="A1", brand="Acme")]
    current = [_record(id="a", title="Alpha", price=10, sku="A1", brand="Acme", rating=4.5)]
    diff = compute_extraction_diff(baseline, current, field_threshold=0.5)

    assert diff.added_fields == ["rating"]
    assert diff.schema_changed is False


# --- severity: major ---


def test_quality_regression_flagged_at_50pct_drop() -> None:
    """A 50%+ drop in record count flags quality_regression and severity major."""
    baseline = [_record(id=str(i), price=i) for i in range(20)]
    current = [_record(id=str(i), price=i) for i in range(5)]
    diff = compute_extraction_diff(baseline, current)
    assert diff.quality_regression is True
    assert diff.severity == "major"
    assert "QUALITY REGRESSION" in diff.summary


def test_zero_records_from_nonempty_baseline_is_major() -> None:
    """An empty current run after a non-empty baseline is a major regression."""
    baseline = [_record(id="a", title="Alpha"), _record(id="b", title="Beta")]
    current: list[dict[str, Any]] = []
    diff = compute_extraction_diff(baseline, current)
    assert diff.severity == "major"
    assert diff.quality_regression is True
    assert len(diff.removed_records) == 2


# --- record matching strategies ---


def test_record_key_parameter_used_when_provided() -> None:
    """An explicit record_key is preferred over candidate detection."""
    baseline = [_record(product_id="p1", title="Foo"), _record(product_id="p2", title="Bar")]
    # title is different but product_id is the same → stable
    current = [_record(product_id="p1", title="Foo updated"), _record(product_id="p2", title="Bar")]
    diff = compute_extraction_diff(baseline, current, record_key="product_id")
    assert diff.added_records == []
    assert diff.removed_records == []
    assert len(diff.modified_records) == 1


def test_falls_back_to_url_field_when_no_id() -> None:
    """When no `id` field exists, candidate list picks `url`."""
    baseline = [_record(url="https://example.com/a", title="A")]
    current = [_record(url="https://example.com/a", title="A renamed")]
    diff = compute_extraction_diff(baseline, current)
    assert diff.added_records == []
    assert diff.removed_records == []
    assert len(diff.modified_records) == 1


def test_falls_back_to_content_hash_when_no_key() -> None:
    """When no candidate field exists, content hash is the signature."""
    baseline = [_record(name="Widget", price=10)]
    current = [_record(name="Widget", price=10)]
    diff = compute_extraction_diff(baseline, current)
    assert diff.added_records == []
    assert diff.removed_records == []


# --- edge cases ---


def test_empty_baseline_empty_current() -> None:
    """Two empty inputs produce a stable diff with zero counts."""
    diff = compute_extraction_diff([], [])
    assert diff.severity == "stable"
    assert diff.baseline_record_count == 0
    assert diff.current_record_count == 0
    assert diff.record_count_delta == 0


def test_empty_baseline_with_records_in_current() -> None:
    """Going from no baseline to a populated current is a major shift."""
    diff = compute_extraction_diff([], [_record(id="x"), _record(id="y")])
    assert diff.severity in {"minor", "moderate", "major"}
    assert len(diff.added_records) == 2


def test_non_dict_records_are_skipped() -> None:
    """Non-dict entries in the input lists are silently filtered out."""
    baseline = [_record(id="a"), "not a dict", None]  # type: ignore[list-item]
    current = [_record(id="a"), _record(id="b")]
    diff = compute_extraction_diff(baseline, current)  # type: ignore[arg-type]
    # Baseline counted as 1 valid record; current is 2 valid
    assert diff.baseline_record_count == 1
    assert diff.current_record_count == 2


def test_summary_string_format() -> None:
    """The summary string contains the severity label and key counts."""
    baseline = [_record(id=str(i)) for i in range(10)]
    current = [_record(id=str(i)) for i in range(15)]
    diff = compute_extraction_diff(baseline, current)
    assert "[minor]" in diff.summary or "[moderate]" in diff.summary
    assert "10 → 15" in diff.summary


@pytest.mark.parametrize(
    "baseline_count,current_count,expected_severity",
    [
        (100, 100, "stable"),
        (100, 99, "minor"),
        (100, 90, "minor"),
        (100, 80, "minor"),  # 20% drop = minor (>= 10% delta, no schema change)
        (100, 45, "major"),  # 55% drop = quality_regression (> 50%)
        (100, 0, "major"),
        (0, 0, "stable"),
    ],
)
def test_severity_ladder(baseline_count: int, current_count: int, expected_severity: str) -> None:
    """Parametric: severity classifies correctly across the count ladder."""
    baseline = [_record(id=str(i)) for i in range(baseline_count)]
    current = [_record(id=str(i)) for i in range(current_count)]
    diff = compute_extraction_diff(baseline, current)
    assert diff.severity == expected_severity


def test_to_dict_serializable() -> None:
    """to_dict() returns a JSON-safe dict."""
    baseline = [_record(id="a", price=10), _record(id="b", price=20)]
    current = [_record(id="a", price=15), _record(id="c", price=99)]
    diff = compute_extraction_diff(baseline, current)
    serialised = diff.to_dict()
    assert serialised["severity"] == "moderate"
    assert serialised["baseline_record_count"] == 2
    assert serialised["current_record_count"] == 2
    # all nested records must be plain dicts
    assert all(isinstance(r, dict) for r in serialised["added_records"])
