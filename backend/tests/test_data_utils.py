"""Unit Tests for Data Utilities.

Tests normalize_scraped_record, _validate_extracted_data, _dedupe_records,
_limit_source_records, _trim_prompt_value, _prepare_records_for_ai,
and process_raw_records.
"""

from __future__ import annotations

from unittest.mock import patch

from app.data_utils import (
    _dedupe_records,
    _limit_source_records,
    _prepare_records_for_ai,
    _trim_prompt_value,
    _validate_extracted_data,
    normalize_scraped_record,
    process_raw_records,
)
from app.models import FieldType, SchemaField


# ─── Schema Fixtures ───────────────────────────────────────────────────────────

STR_FIELD = SchemaField(name="name", field_type=FieldType.STRING)
INT_FIELD = SchemaField(name="count", field_type=FieldType.INTEGER)
FLOAT_FIELD = SchemaField(name="price", field_type=FieldType.FLOAT)
EMAIL_FIELD = SchemaField(name="email", field_type=FieldType.EMAIL)
PHONE_FIELD = SchemaField(name="phone", field_type=FieldType.PHONE)

SIMPLE_SCHEMA = [STR_FIELD, INT_FIELD]
FULL_SCHEMA = [STR_FIELD, INT_FIELD, FLOAT_FIELD, EMAIL_FIELD, PHONE_FIELD]


# ─── normalize_scraped_record ─────────────────────────────────────────────────

class TestNormalizeScrapedRecord:
    """Tests for normalize_scraped_record()."""

    def test_normalizes_values(self):
        record = {"name": "  Acme  ", "count": "5"}
        result = normalize_scraped_record(record, SIMPLE_SCHEMA)
        assert result["name"] == "  Acme  "
        assert result["count"] == "5"

    def test_empty_value_becomes_none(self):
        record = {"name": "", "count": None}
        result = normalize_scraped_record(record, SIMPLE_SCHEMA)
        assert result["name"] is None
        assert result["count"] is None

    def test_preserves_metadata_fields(self):
        record = {"name": "A", "count": "1", "source_url": "http://example.com", "record_score": 0.9, "_key": "abc123"}
        result = normalize_scraped_record(record, SIMPLE_SCHEMA)
        assert result["source_url"] == "http://example.com"
        assert result["record_score"] == 0.9
        assert result["_key"] == "abc123"

    def test_missing_field_is_none(self):
        record = {"name": "A"}
        result = normalize_scraped_record(record, SIMPLE_SCHEMA)
        assert result["name"] == "A"
        assert result["count"] is None


# ─── _validate_extracted_data ─────────────────────────────────────────────────

class TestValidateExtractedData:
    """Tests for _validate_extracted_data()."""

    def test_valid_if_meaningful_data_exists(self):
        record = {"name": "Acme Corp", "count": "42"}
        assert _validate_extracted_data(record, SIMPLE_SCHEMA) is True

    def test_invalid_if_all_empty(self):
        record = {"name": "", "count": None}
        assert _validate_extracted_data(record, SIMPLE_SCHEMA) is False

    def test_invalid_if_all_none(self):
        record = {"name": None, "count": None}
        assert _validate_extracted_data(record, SIMPLE_SCHEMA) is False


# ─── _dedupe_records ──────────────────────────────────────────────────────────

class TestDedupeRecords:
    """Tests for _dedupe_records()."""

    def test_dedupe_name_field(self):
        schema = [STR_FIELD]
        records = [{"name": "Alpha"}, {"name": "Beta"}, {"name": "alpha"}]
        result = _dedupe_records(records, schema)
        assert len(result) == 2  # "Alpha" and "alpha" are same after normalization
        assert result[0]["name"] == "Alpha"
        assert result[1]["name"] == "Beta"

    def test_empty_input_returns_empty(self):
        assert _dedupe_records([], [STR_FIELD]) == []

    def test_all_duplicates(self):
        schema = [STR_FIELD]
        records = [{"name": "X"}, {"name": "X"}, {"name": "X"}]
        result = _dedupe_records(records, schema)
        assert len(result) == 1

    def test_fallback_to_all_fields(self):
        """When no name/company/title fields, use all fields as identity."""
        schema = [SchemaField(name="code", field_type=FieldType.STRING), SchemaField(name="price", field_type=FieldType.FLOAT)]
        records = [
            {"code": "A1", "price": "10"},
            {"code": "A1", "price": "10"},
            {"code": "B2", "price": "20"},
        ]
        result = _dedupe_records(records, schema)
        assert len(result) == 2


# ─── _limit_source_records ────────────────────────────────────────────────────

class TestLimitSourceRecords:
    """Tests for _limit_source_records()."""

    def test_under_limit_returns_all(self):
        records = [{"name": str(i)} for i in range(5)]
        result = _limit_source_records(records, FULL_SCHEMA, max_records=10)
        assert len(result) == 5

    def test_over_limit_prioritizes_email_phone(self):
        records = [
            {"name": "No Contact"},
            {"name": "Has Email", "email": "a@b.com"},
            {"name": "Has Phone", "phone": "123"},
            {"name": "Has Both", "email": "x@y.com", "phone": "456"},
        ]
        result = _limit_source_records(records, FULL_SCHEMA, max_records=2)
        assert len(result) == 2
        # Should prioritize records with phone/email
        assert result[0]["name"] == "Has Both"
        assert result[1]["name"] in ("Has Email", "Has Phone")

    def test_empty_returns_all(self):
        assert _limit_source_records([], FULL_SCHEMA) == []


# ─── _trim_prompt_value ───────────────────────────────────────────────────────

class TestTrimPromptValue:
    """Tests for _trim_prompt_value()."""

    def test_none_returns_empty_string(self):
        assert _trim_prompt_value(None) == ""

    def test_short_value_unchanged(self):
        assert _trim_prompt_value("hello") == "hello"

    def test_long_value_trimmed(self):
        long_val = "a" * 200
        result = _trim_prompt_value(long_val, max_chars=180)
        assert len(result) == 183  # 180 chars + "..."
        assert result.endswith("...")

    def test_exact_length_unchanged(self):
        val = "a" * 180
        assert _trim_prompt_value(val, max_chars=180) == val


# ─── _prepare_records_for_ai ──────────────────────────────────────────────────

class TestPrepareRecordsForAi:
    """Tests for _prepare_records_for_ai()."""

    def test_prepares_records(self):
        records = [{"name": "Acme", "count": "42", "extra": "ignored"}, {"name": "Beta", "count": "7"}]
        schema = [STR_FIELD, INT_FIELD]
        result = _prepare_records_for_ai(records, schema)
        assert len(result) == 2
        assert "extra" not in result[0]  # Not in schema

    def test_empty_values_excluded(self):
        records = [{"name": "", "count": None}]
        result = _prepare_records_for_ai(records, [STR_FIELD, INT_FIELD])
        assert result == []  # Both values empty

    def test_long_values_trimmed(self):
        long_name = "x" * 200
        records = [{"name": long_name, "count": "1"}]
        result = _prepare_records_for_ai(records, [STR_FIELD, INT_FIELD])
        assert len(result) == 1
        assert len(result[0]["name"]) == 183  # 180 + "..."


# ─── process_raw_records ──────────────────────────────────────────────────────

class TestProcessRawRecords:
    """Tests for process_raw_records()."""

    def test_empty_input_returns_empty(self):
        assert process_raw_records([], SIMPLE_SCHEMA, 0.0) == []

    def test_processes_records(self):
        records = [{"name": "Acme", "count": "42"}]
        with patch("app.semantic_pipeline.run_pipeline", return_value=[{"name": "Acme", "count": "42"}]):
            result = process_raw_records(records, SIMPLE_SCHEMA, 0.0)
            assert len(result) == 1
            assert result[0]["name"] == "Acme"

    def test_min_score_filters_low_quality(self):
        records = [{"name": "", "count": None}]
        with patch("app.semantic_pipeline.run_pipeline", return_value=[]):
            result = process_raw_records(records, SIMPLE_SCHEMA, 0.5)
            # Empty record gets low score and gets filtered
            assert result == []
