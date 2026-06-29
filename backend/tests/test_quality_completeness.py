"""Qual 17: Data completeness scoring — test completeness percentage calculation."""

from __future__ import annotations

from typing import Any

from app.models import FieldType, SchemaField


def _sf(name: str, ftype: FieldType = FieldType.STRING, required: bool = False) -> SchemaField:
    return SchemaField(name=name, field_type=ftype, description="", required=required)


def _completeness_score(record: dict[str, Any], schema_fields: list[SchemaField]) -> dict[str, Any]:
    """Compute completeness percentage for a record.

    Returns the percentage of expected fields that have non-null, non-empty values,
    plus per-field breakdown.
    """
    if not schema_fields:
        return {"completeness_pct": 0.0, "present": 0, "expected": 0, "missing": []}

    present = 0
    missing_fields = []
    for field in schema_fields:
        val = record.get(field.name)
        if val is not None and (not isinstance(val, str) or val.strip() != ""):
            present += 1
        else:
            missing_fields.append(field.name)

    pct = round(present / len(schema_fields) * 100, 1)
    return {
        "completeness_pct": pct,
        "present": present,
        "expected": len(schema_fields),
        "missing": missing_fields,
    }


def _overall_completeness(records: list[dict[str, Any]], schema_fields: list[SchemaField]) -> dict[str, Any]:
    """Compute overall completeness across multiple records."""
    if not records:
        return {"overall_pct": 0.0, "total_records": 0}

    scores = [_completeness_score(r, schema_fields) for r in records]
    avg_pct = round(sum(s["completeness_pct"] for s in scores) / len(scores), 1)
    total_present = sum(s["present"] for s in scores)
    total_expected = sum(s["expected"] for s in scores)
    return {
        "overall_pct": avg_pct,
        "overall_pct_raw": round(total_present / max(total_expected, 1) * 100, 1),
        "total_records": len(records),
        "per_record": scores,
    }


class TestSingleRecordCompleteness:
    def test_all_fields_present(self) -> None:
        fields = [_sf("name"), _sf("price"), _sf("desc")]
        record = {"name": "Product", "price": "$10", "desc": "Description"}
        result = _completeness_score(record, fields)
        assert result["completeness_pct"] == 100.0
        assert result["missing"] == []

    def test_some_fields_missing(self) -> None:
        fields = [_sf("name"), _sf("price"), _sf("desc")]
        record = {"name": "Product"}
        result = _completeness_score(record, fields)
        assert result["completeness_pct"] == 33.3
        assert len(result["missing"]) == 2

    def test_all_fields_empty(self) -> None:
        fields = [_sf("name"), _sf("price")]
        record = {"name": None, "price": ""}
        result = _completeness_score(record, fields)
        assert result["completeness_pct"] == 0.0

    def test_empty_schema_zero(self) -> None:
        result = _completeness_score({"x": "y"}, [])
        assert result["completeness_pct"] == 0.0

    def test_whitespace_only_considered_empty(self) -> None:
        fields = [_sf("title")]
        record = {"title": "   "}
        result = _completeness_score(record, fields)
        assert result["completeness_pct"] == 0.0

    def test_zero_is_valid_value(self) -> None:
        fields = [_sf("count", FieldType.INTEGER)]
        record = {"count": 0}
        result = _completeness_score(record, fields)
        assert result["completeness_pct"] == 100.0

    def test_false_is_valid_value(self) -> None:
        fields = [_sf("active", FieldType.BOOLEAN)]
        record = {"active": False}
        result = _completeness_score(record, fields)
        assert result["completeness_pct"] == 100.0


class TestOverallCompleteness:
    def test_multiple_records_completeness(self) -> None:
        fields = [_sf("name"), _sf("price")]
        records: list[dict[str, Any]] = [
            {"name": "A", "price": "$1"},
            {"name": "B", "price": None},
            {"name": None, "price": "$3"},
        ]
        result = _overall_completeness(records, fields)
        assert result["total_records"] == 3
        assert result["overall_pct_raw"] == 66.7

    def test_empty_records(self) -> None:
        result = _overall_completeness([], [_sf("x")])
        assert result["total_records"] == 0
        assert result["overall_pct"] == 0.0

    def test_all_complete_records(self) -> None:
        fields = [_sf("a"), _sf("b")]
        records = [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]
        result = _overall_completeness(records, fields)
        assert result["overall_pct"] == 100.0
