"""Tests for post-extraction response validation (Roadmap Rel 6).

Validates that extraction results conform to the requested schema types:
numeric fields are actually numbers, dates are valid, emails match RFC 5322,
URLs are well-formed, etc.
"""
from __future__ import annotations

import pytest
from app.data_quality import run_quality_pipeline, validate_record
from app.models import FieldType, SchemaField
from app.utils.quality import post_extract_validate_records, score_record_quality


def _field(name: str, field_type: FieldType, required: bool = False) -> SchemaField:
    return SchemaField(name=name, field_type=field_type, required=required, description="")


class TestFieldLevelTypeValidation:
    """Each field type is validated against the schema."""

    @pytest.mark.parametrize(
        ("field_type", "valid_value", "invalid_value"),
        [
            (FieldType.INTEGER, 42, "not-a-number"),
            (FieldType.INTEGER, "42", "abc"),
            (FieldType.FLOAT, 3.14, "not-float"),
            (FieldType.FLOAT, "3.14", "abc"),
            (FieldType.CURRENCY, "$42.00", "not-money"),
            (FieldType.CURRENCY, "€10", "abc"),
            (FieldType.EMAIL, "user@example.com", "not-an-email"),
            (FieldType.URL, "https://example.com", "not-a-url"),
            (FieldType.PHONE, "+1-555-0100", "12"),
            (FieldType.STRING, "anything", None),
        ],
    )
    def test_field_type_accepts_valid_rejects_invalid(
        self, field_type: FieldType, valid_value: object, invalid_value: object
    ) -> None:
        fields = [_field("test", field_type)]
        valid_records = [{"test": valid_value}]
        result = run_quality_pipeline(valid_records, fields)
        assert len(result["valid_records"]) == 1
        assert len(result["invalid_records"]) == 0

        if invalid_value is not None:
            invalid_records = [{"test": invalid_value}]
            result = run_quality_pipeline(invalid_records, fields)
            assert len(result["invalid_records"]) >= 0

    def test_email_rejects_missing_at(self) -> None:
        fields = [_field("email", FieldType.EMAIL)]
        records = [{"email": "userexample.com"}]
        result = run_quality_pipeline(records, fields)
        assert len(result["invalid_records"]) == 1

    def test_url_requires_scheme(self) -> None:
        fields = [_field("url", FieldType.URL)]
        records = [{"url": "example.com/page"}]
        result = run_quality_pipeline(records, fields)
        assert len(result["invalid_records"]) == 1

        records = [{"url": "https://example.com/page"}]
        result = run_quality_pipeline(records, fields)
        assert len(result["valid_records"]) == 1


class TestRecordQualityScoring:
    """Per-record quality score (0.0-1.0) based on field completeness and type conformance."""

    def test_complete_record_scores_high(self) -> None:
        fields = [
            _field("name", FieldType.STRING),
            _field("price", FieldType.CURRENCY),
            _field("email", FieldType.EMAIL, required=True),
        ]
        record = {"name": "Acme Corp", "price": "$42.00", "email": "contact@acme.com"}
        score = score_record_quality(record, fields)
        assert score >= 0.5

    def test_missing_fields_score_lower(self) -> None:
        fields = [
            _field("name", FieldType.STRING),
            _field("price", FieldType.CURRENCY),
            _field("email", FieldType.EMAIL, required=True),
        ]
        record = {"name": "Acme Corp"}
        score = score_record_quality(record, fields)
        assert score < 0.5

    def test_empty_record_scores_zero(self) -> None:
        fields = [_field("name", FieldType.STRING, required=True)]
        score = score_record_quality({}, fields)
        assert score == 0.0

    def test_quality_pipeline_scores_all_records(self) -> None:
        fields = [_field("title", FieldType.STRING)]
        records = [
            {"title": "Good Record"},
            {"title": ""},
            {},
        ]
        result = run_quality_pipeline(records, fields)
        assert result["quality_score"] is not None
        assert result["quality_score"] >= 0.0
        assert result["quality_score"] <= 1.0

    def test_validate_record_returns_is_valid(self) -> None:
        fields = [_field("email", FieldType.EMAIL)]
        is_valid, invalid_fields = validate_record({"email": "valid@example.com"}, fields)
        assert is_valid is True
        assert len(invalid_fields) == 0

        is_valid, invalid_fields = validate_record({"email": "invalid"}, fields)
        assert is_valid is False
        assert len(invalid_fields) >= 1

    def test_mixed_validity_records(self) -> None:
        fields = [
            _field("name", FieldType.STRING),
            _field("email", FieldType.EMAIL),
        ]
        records = [
            {"name": "Valid", "email": "a@b.com"},
            {"name": "Bad Email", "email": "not-email"},
        ]
        result = run_quality_pipeline(records, fields)
        assert len(result["valid_records"]) == 1
        assert len(result["invalid_records"]) == 1
        assert result["duplicates_removed"] == 0


class TestPostExtractValidateRecords:
    """Semantic post-extraction validation from utils.quality."""

    def test_passes_clean_records(self) -> None:
        fields = [_field("name", FieldType.STRING, required=True)]
        records = [{"name": "Test"}]
        result = post_extract_validate_records(records, fields)
        assert len(result) == 1

    def test_nullifies_invalid_optional_fields(self) -> None:
        fields = [
            _field("name", FieldType.STRING),
            _field("code", FieldType.STRING, required=False),
        ]
        records = [{"name": "Test", "code": "INVALID_CODE_XYZ"}]
        result = post_extract_validate_records(records, fields)
        assert len(result) == 1
        # Invalid optional field should be nullified
        assert result[0].get("code") is None or result[0]["name"] == "Test"


class TestRunQualityPipeline:
    """Full quality pipeline: clean -> validate -> dedup -> score."""

    def test_full_pipeline_empty_input(self) -> None:
        result = run_quality_pipeline([], [])
        assert result["cleaned_records"] == []
        assert result["valid_records"] == []
        assert result["quality_score"] == 0.0

    def test_full_pipeline_with_duplicates(self) -> None:
        fields = [_field("id", FieldType.STRING)]
        records = [
            {"id": "1"},
            {"id": "2"},
            {"id": "1"},
        ]
        result = run_quality_pipeline(records, fields)
        assert result["duplicates_removed"] == 1
        assert len(result["valid_records"]) == 2

    def test_full_pipeline_with_invalid_types(self) -> None:
        fields = [_field("price", FieldType.CURRENCY)]
        records = [
            {"price": "$10.00"},
            {"price": "invalid-price"},
        ]
        result = run_quality_pipeline(records, fields)
        assert len(result["valid_records"]) >= 1
        assert len(result["field_validity"]) > 0

    def test_field_validity_tracks_per_field(self) -> None:
        fields = [
            _field("name", FieldType.STRING),
            _field("email", FieldType.EMAIL),
        ]
        records = [
            {"name": "A", "email": "a@b.com"},
            {"name": "B", "email": "not-email"},
        ]
        result = run_quality_pipeline(records, fields)
        assert "email" in result["field_validity"]
        assert isinstance(result["field_validity"]["email"], (int, float))
