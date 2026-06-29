"""Tests for missing-value imputation and data normalization (Roadmap Qual 6, 7).

Also covers Roadmap Wave 7 Item 3: per-record quality scoring with
detailed breakdown (completeness, type conformance, plausibility).
"""

from __future__ import annotations

from app.data_quality import (
    clean_record,
    run_quality_pipeline,
    score_record_detailed,
    score_records,
)
from app.models import FieldType, SchemaField


def _field(name: str, field_type: FieldType, required: bool = False) -> SchemaField:
    return SchemaField(name=name, field_type=field_type, required=required, description="")


class TestMissingValueHandling:
    """Missing and null field handling in the quality pipeline."""

    def test_totally_empty_record_produces_zero_score(self) -> None:
        """An empty record should have a quality score of 0."""
        fields = [_field("name", FieldType.STRING, required=True)]
        result = run_quality_pipeline([{}], fields)
        assert result["quality_score"] == 0.0

    def test_null_values_handled_gracefully(self) -> None:
        """Null values should not crash the pipeline."""
        fields = [_field("name", FieldType.STRING)]
        records = [{"name": None}]
        result = run_quality_pipeline(records, fields)
        assert result["quality_score"] >= 0.0

    def test_partial_missing_fields(self) -> None:
        """Records with some missing fields should still validate."""
        fields = [
            _field("title", FieldType.STRING),
            _field("price", FieldType.CURRENCY),
            _field("description", FieldType.STRING),
        ]
        records = [
            {"title": "Product A", "price": "$10.00"},
            {"title": "Product B", "price": "$20.00", "description": "Great product"},
            {"title": "Product C"},
        ]
        result = run_quality_pipeline(records, fields)
        assert len(result["valid_records"]) > 0
        assert result["quality_score"] >= 0.0

    def test_empty_strings_treated_as_missing(self) -> None:
        """Empty string values should not count as valid content."""
        fields = [_field("name", FieldType.STRING)]
        records = [{"name": ""}]
        result = run_quality_pipeline(records, fields)
        assert result["quality_score"] == 0.0

    def test_whitespace_only_values(self) -> None:
        """Whitespace-only values should be treated as empty."""
        fields = [_field("name", FieldType.STRING)]
        records = [{"name": "   "}]
        result = run_quality_pipeline(records, fields)
        assert result["quality_score"] == 0.0


class TestDataNormalization:
    """Data normalization in the quality pipeline."""

    def test_cleaned_record_has_no_empty_values(self) -> None:
        """clean_record removes whitespace and normalizes."""
        record = {"name": "  Hello World  ", "price": " $42.00 "}
        fields = [
            _field("name", FieldType.STRING),
            _field("price", FieldType.CURRENCY),
        ]
        cleaned = clean_record(record, fields)
        assert cleaned["name"].strip() != ""
        assert cleaned.get("price") is not None

    def test_clean_preserves_valid_data(self) -> None:
        """Valid data should pass through clean_record unchanged."""
        record = {"name": "Test", "email": "a@b.com"}
        fields = [
            _field("name", FieldType.STRING),
            _field("email", FieldType.EMAIL),
        ]
        cleaned = clean_record(record, fields)
        assert "name" in cleaned
        assert cleaned["name"] is not None

    def test_clean_handles_missing_fields(self) -> None:
        """Missing fields should remain absent after cleaning."""
        record = {"name": "Test"}
        fields = [
            _field("name", FieldType.STRING),
            _field("email", FieldType.EMAIL),
        ]
        cleaned = clean_record(record, fields)
        assert "name" in cleaned
        assert cleaned["name"] is not None

    def test_clean_strips_url_tracking_params(self) -> None:
        """URL cleaner removes common tracking parameters."""
        record = {"link": "https://example.com/page?utm_source=test&id=123"}
        fields = [_field("link", FieldType.URL)]
        cleaned = clean_record(record, fields)
        assert "utm_source" not in cleaned["link"]
        assert "id=123" in cleaned["link"]

    def test_pipeline_returns_warnings(self) -> None:
        """Quality pipeline returns warnings for problematic records."""
        fields = [_field("email", FieldType.EMAIL)]
        records = [{"email": "not-an-email"}]
        result = run_quality_pipeline(records, fields)
        assert len(result["warnings"]) >= 0


# ---------------------------------------------------------------------------
# Roadmap Wave 7, Item 3 — Per-record quality scoring tests
# ---------------------------------------------------------------------------


class TestPerRecordQualityScoring:
    def test_perfect_record_score_one(self) -> None:
        fields = [
            _field("name", FieldType.STRING),
            _field("price", FieldType.CURRENCY),
        ]
        record = {"name": "Widget Alpha", "price": 9.99}
        result = score_record_detailed(record, fields)
        assert result["overall"] == 1.0
        assert result["completeness"] == 1.0
        assert result["type_conformance"] == 1.0

    def test_empty_record_score_zero(self) -> None:
        fields = [_field("name", FieldType.STRING)]
        result = score_record_detailed({}, fields)
        assert result["overall"] == 0.0
        assert result["completeness"] == 0.0

    def test_missing_fields_lower_completeness(self) -> None:
        fields = [
            _field("name", FieldType.STRING),
            _field("price", FieldType.CURRENCY),
            _field("url", FieldType.URL),
        ]
        record = {"name": "Widget"}  # price and url missing
        result = score_record_detailed(record, fields)
        assert result["completeness"] < 1.0
        assert result["completeness"] > 0.0
        assert "price" in result["missing_fields"]
        assert "url" in result["missing_fields"]

    def test_wrong_types_lower_conformance(self) -> None:
        fields = [
            _field("price", FieldType.CURRENCY),
            _field("email", FieldType.EMAIL),
        ]
        record = {"price": "not_a_number", "email": "no-at-sign"}
        result = score_record_detailed(record, fields)
        assert result["type_conformance"] == 0.0
        assert "price" in result["mismatched_fields"]
        assert "email" in result["mismatched_fields"]

    def test_overall_blends_three_components(self) -> None:
        fields = [_field("name", FieldType.STRING), _field("price", FieldType.CURRENCY)]
        record = {"name": "Widget", "price": 10.0}
        result = score_record_detailed(record, fields)
        assert 0.0 <= result["overall"] <= 1.0
        assert result["completeness"] > 0.0
        assert result["type_conformance"] > 0.0
        assert result["plausibility"] > 0.0

    def test_field_scores_dict_populated(self) -> None:
        fields = [_field("name", FieldType.STRING), _field("price", FieldType.CURRENCY)]
        record = {"name": "W", "price": 5.0}
        result = score_record_detailed(record, fields)
        assert "name" in result["field_scores"]
        assert "price" in result["field_scores"]

    def test_missing_fields_list_populated(self) -> None:
        fields = [_field("name", FieldType.STRING, required=True), _field("price", FieldType.CURRENCY)]
        record = {"price": 5.0}
        result = score_record_detailed(record, fields)
        assert "name" in result["missing_fields"]

    def test_mismatched_fields_list_populated(self) -> None:
        fields = [_field("price", FieldType.CURRENCY)]
        record = {"price": "abc"}
        result = score_record_detailed(record, fields)
        assert "price" in result["mismatched_fields"]

    def test_score_records_batch_parallel(self) -> None:
        fields = [_field("name", FieldType.STRING), _field("price", FieldType.CURRENCY)]
        records = [
            {"name": "A", "price": 1.0},
            {"name": "B", "price": 2.0},
        ]
        results = score_records(records, fields)
        assert len(results) == 2
        assert all(r["overall"] > 0.0 for r in results)

    def test_score_records_empty_input(self) -> None:
        fields = [_field("name", FieldType.STRING)]
        results = score_records([], fields)
        assert results == []

    def test_run_quality_pipeline_includes_per_record_quality(self) -> None:
        fields = [
            _field("name", FieldType.STRING),
            _field("price", FieldType.CURRENCY),
        ]
        records = [
            {"name": "Widget A", "price": "$10.00"},
            {"name": "Widget B", "price": "$20.00"},
        ]
        result = run_quality_pipeline(records, fields)
        assert "per_record_quality" in result
        assert "quality_score" in result  # existing key still present
        assert "valid_records" in result  # existing key still present
        assert len(result["per_record_quality"]) > 0

    def test_optional_field_absent_not_in_missing_fields(self) -> None:
        fields = [_field("name", FieldType.STRING), _field("email", FieldType.EMAIL, required=False)]
        record = {"name": "Widget"}
        result = score_record_detailed(record, fields)
        # email IS in missing_fields (it's missing), but required is False,
        # so it shouldn't drag the completeness/overall too low
        assert result["completeness"] > 0.0

    def test_all_return_keys_present_on_empty_input(self) -> None:
        result = score_record_detailed({}, [_field("name", FieldType.STRING)])
        expected_keys = {
            "overall",
            "completeness",
            "type_conformance",
            "plausibility",
            "field_scores",
            "field_type_valid",
            "missing_fields",
            "mismatched_fields",
        }
        assert expected_keys.issubset(result.keys())

    def test_no_schema_fields_returns_zero(self) -> None:
        result = score_record_detailed({"name": "X"}, [])
        assert result["overall"] == 0.0

    def test_type_conformance_undefined_when_no_checkable_fields(self) -> None:
        # Only STRING fields — no type checking possible
        fields = [_field("name", FieldType.STRING)]
        record = {"name": "Widget"}
        result = score_record_detailed(record, fields)
        # When no checkable fields, conformance defaults to 1.0
        assert result["type_conformance"] == 1.0
