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

STR_FIELD = SchemaField(name="name", field_type=FieldType.STRING, description="", required=False)
INT_FIELD = SchemaField(name="count", field_type=FieldType.INTEGER, description="", required=False)
FLOAT_FIELD = SchemaField(name="price", field_type=FieldType.FLOAT, description="", required=False)
EMAIL_FIELD = SchemaField(name="email", field_type=FieldType.EMAIL, description="", required=False)
PHONE_FIELD = SchemaField(name="phone", field_type=FieldType.PHONE, description="", required=False)

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
        schema = [
            SchemaField(
                name="code",
                field_type=FieldType.STRING,
                description="",
                required=False),
            SchemaField(
                name="price",
                field_type=FieldType.FLOAT,
                description="",
                required=False)]
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


# ─── align_profile_keys_to_schema ─────────────────────────────────────────────

class TestAlignProfileKeysToSchema:
    """Tests for align_profile_keys_to_schema()."""

    def test_exact_matches_preserved(self):
        from app.data_utils import align_profile_keys_to_schema
        records = [{"name": "Acme", "price": "100"}]
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, description="", required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, description="", required=False),
        ]
        aligned = align_profile_keys_to_schema(records, schema)
        assert aligned[0]["name"] == "Acme"
        assert aligned[0]["price"] == "100"

    def test_fuzzy_substring_mapping(self):
        from app.data_utils import align_profile_keys_to_schema
        records = [{"origin": "LON", "destination": "PAR"}]
        schema = [
            SchemaField(name="origin_airport", field_type=FieldType.STRING, description="", required=False),
            SchemaField(name="destination_airport", field_type=FieldType.STRING, description="", required=False),
        ]
        aligned = align_profile_keys_to_schema(records, schema)
        assert aligned[0]["origin_airport"] == "LON"
        assert aligned[0]["destination_airport"] == "PAR"

    def test_synonym_group_mapping(self):
        from app.data_utils import align_profile_keys_to_schema
        records = [{"fee": "250"}]
        schema = [
            SchemaField(name="ticket_price", field_type=FieldType.CURRENCY, description="", required=False),
        ]
        aligned = align_profile_keys_to_schema(records, schema)
        assert aligned[0]["ticket_price"] == "250"

    def test_t15_custom_schema_mapping(self):
        """Regression: custom schema must map full profile field set via semantic alignment."""
        from app.data_utils import align_profile_keys_to_schema

        # Use an inline profile so this test is hermetic (independent of disk state).
        profile_fields = {
            "airline": {"selector": ".airline", "type": "text"},
            "origin": {"selector": ".origin", "type": "text"},
            "destination": {"selector": ".dest", "type": "text"},
            "date": {"selector": ".dep-date", "type": "text"},
            "return_date": {"selector": ".ret-date", "type": "text"},
            "price": {"selector": ".price", "type": "currency"},
            "stops": {"selector": ".stops", "type": "text"},
        }
        sample_values = {
            "airline": "Sample Air", "origin": "AAA", "destination": "BBB",
            "date": "01-01-2026", "return_date": "02-01-2026", "price": "100", "stops": "Direct",
        }
        record = {key: sample_values.get(key, f"sample_{key}") for key in profile_fields}
        schema = [
            SchemaField(name="airlines_name", field_type=FieldType.STRING, description="Name of the airline", required=False),
            SchemaField(name="origin_airport", field_type=FieldType.STRING, description="Airport of origin", required=False),
            SchemaField(name="destination_airport", field_type=FieldType.STRING, description="Airport of destination", required=False),  # noqa: E501
            SchemaField(name="prices", field_type=FieldType.CURRENCY, description="Price of the flight", required=False),
            SchemaField(name="departure_date", field_type=FieldType.DATE, description="Date of departure", required=False),
            SchemaField(name="arrival_date", field_type=FieldType.DATE, description="Date of arrival", required=False),
        ]
        aligned = align_profile_keys_to_schema([record], schema, profile_fields=profile_fields)
        row = aligned[0]
        assert row["airlines_name"] == "Sample Air"
        assert row["origin_airport"] == "AAA"
        assert row["destination_airport"] == "BBB"
        assert row["prices"] == "100"
        assert row["departure_date"] == "01-01-2026"
        assert row["arrival_date"] == "02-01-2026"
        assert "stops" not in row

    def test_return_date_maps_to_arrival_date(self):
        from app.data_utils import align_profile_keys_to_schema
        records = [{"return_date": "01-06-2026", "date": "30-05-2026"}]
        schema = [
            SchemaField(name="departure_date", field_type=FieldType.DATE, description="Date of departure", required=False),
            SchemaField(name="arrival_date", field_type=FieldType.DATE, description="Date of arrival", required=False),
        ]
        aligned = align_profile_keys_to_schema(
            records, schema, profile_fields={
                "return_date": {
                    "type": "text"}, "date": {
                    "type": "text"}})
        assert aligned[0]["departure_date"] == "30-05-2026"
        assert aligned[0]["arrival_date"] == "01-06-2026"

    def test_intent_boost_mapping(self):
        from app.data_utils import align_extracted_keys_to_schema
        records = [{"fee": "250"}]
        schema = [
            SchemaField(name="ticket_price", field_type=FieldType.CURRENCY, description="", required=False)]
        aligned = align_extracted_keys_to_schema(
            records,
            schema,
            user_intent="find cheap fees and ticket prices",
        )
        assert aligned[0]["ticket_price"] == "250"

    def test_stops_not_mapped_to_arrival_date(self):
        from app.data_utils import align_profile_keys_to_schema
        records = [{"stops": "1 Stop", "date": "30-05-2026"}]
        schema = [
            SchemaField(name="departure_date", field_type=FieldType.DATE, description="", required=False),
            SchemaField(name="arrival_date", field_type=FieldType.DATE, description="", required=False),
        ]
        aligned = align_profile_keys_to_schema(records, schema)
        assert aligned[0]["departure_date"] == "30-05-2026"
        assert aligned[0].get("arrival_date") is None
