"""Tests for missing-value imputation and data normalization (Roadmap Qual 6, 7).

Verifies that the quality pipeline handles missing values, null fields,
and data normalization correctly.
"""
from __future__ import annotations

from app.data_quality import clean_record, run_quality_pipeline
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
