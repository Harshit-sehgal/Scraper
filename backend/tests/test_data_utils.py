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

    def test_normalizes_values(self) -> None:
        record = {"name": "  Acme  ", "count": "5"}
        result = normalize_scraped_record(record, SIMPLE_SCHEMA)
        assert result["name"] == "  Acme  "
        assert result["count"] == "5"

    def test_empty_value_becomes_none(self) -> None:
        record = {"name": "", "count": None}
        result = normalize_scraped_record(record, SIMPLE_SCHEMA)
        assert result["name"] is None
        assert result["count"] is None

    def test_preserves_metadata_fields(self) -> None:
        record = {"name": "A", "count": "1", "source_url": "http://example.com", "record_score": 0.9, "_key": "abc123"}
        result = normalize_scraped_record(record, SIMPLE_SCHEMA)
        assert result["source_url"] == "http://example.com"
        assert result["record_score"] == 0.9
        assert result["_key"] == "abc123"

    def test_missing_field_is_none(self) -> None:
        record = {"name": "A"}
        result = normalize_scraped_record(record, SIMPLE_SCHEMA)
        assert result["name"] == "A"
        assert result["count"] is None


# ─── _validate_extracted_data ─────────────────────────────────────────────────


class TestValidateExtractedData:
    """Tests for _validate_extracted_data()."""

    def test_valid_if_meaningful_data_exists(self) -> None:
        record = {"name": "Acme Corp", "count": "42"}
        assert _validate_extracted_data(record, SIMPLE_SCHEMA) is True

    def test_invalid_if_all_empty(self) -> None:
        record = {"name": "", "count": None}
        assert _validate_extracted_data(record, SIMPLE_SCHEMA) is False

    def test_invalid_if_all_none(self) -> None:
        record = {"name": None, "count": None}
        assert _validate_extracted_data(record, SIMPLE_SCHEMA) is False


# ─── _dedupe_records ──────────────────────────────────────────────────────────


class TestDedupeRecords:
    """Tests for _dedupe_records()."""

    def test_dedupe_name_field(self) -> None:
        schema = [STR_FIELD]
        records = [{"name": "Alpha"}, {"name": "Beta"}, {"name": "alpha"}]
        result = _dedupe_records(records, schema)
        assert len(result) == 2  # "Alpha" and "alpha" are same after normalization
        assert result[0]["name"] == "Alpha"
        assert result[1]["name"] == "Beta"

    def test_empty_input_returns_empty(self) -> None:
        assert _dedupe_records([], [STR_FIELD]) == []

    def test_all_duplicates(self) -> None:
        schema = [STR_FIELD]
        records = [{"name": "X"}, {"name": "X"}, {"name": "X"}]
        result = _dedupe_records(records, schema)
        assert len(result) == 1

    def test_fallback_to_all_fields(self) -> None:
        """When no name/company/title fields, use all fields as identity."""
        schema = [
            SchemaField(name="code", field_type=FieldType.STRING, description="", required=False),
            SchemaField(name="price", field_type=FieldType.FLOAT, description="", required=False),
        ]
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

    def test_under_limit_returns_all(self) -> None:
        records = [{"name": str(i)} for i in range(5)]
        result = _limit_source_records(records, FULL_SCHEMA, max_records=10)
        assert len(result) == 5

    def test_over_limit_prioritizes_email_phone(self) -> None:
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

    def test_over_limit_preserves_order_without_contact_fields(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, description="", required=False)]
        records = [{"title": f"Record {i}", "record_score": 1.0 - (i * 0.01)} for i in range(5)]
        result = _limit_source_records(records, schema, max_records=3)
        assert [r["title"] for r in result] == ["Record 0", "Record 1", "Record 2"]

    def test_empty_returns_all(self) -> None:
        assert _limit_source_records([], FULL_SCHEMA) == []


# ─── _trim_prompt_value ───────────────────────────────────────────────────────


class TestTrimPromptValue:
    """Tests for _trim_prompt_value()."""

    def test_none_returns_empty_string(self) -> None:
        assert _trim_prompt_value(None) == ""

    def test_short_value_unchanged(self) -> None:
        assert _trim_prompt_value("hello") == "hello"

    def test_long_value_trimmed(self) -> None:
        long_val = "a" * 200
        result = _trim_prompt_value(long_val, max_chars=180)
        assert len(result) == 183  # 180 chars + "..."
        assert result.endswith("...")

    def test_exact_length_unchanged(self) -> None:
        val = "a" * 180
        assert _trim_prompt_value(val, max_chars=180) == val


# ─── _prepare_records_for_ai ──────────────────────────────────────────────────


class TestPrepareRecordsForAi:
    """Tests for _prepare_records_for_ai()."""

    def test_prepares_records(self) -> None:
        records = [{"name": "Acme", "count": "42", "extra": "ignored"}, {"name": "Beta", "count": "7"}]
        schema = [STR_FIELD, INT_FIELD]
        result = _prepare_records_for_ai(records, schema)
        assert len(result) == 2
        assert "extra" not in result[0]  # Not in schema

    def test_empty_values_excluded(self) -> None:
        records = [{"name": "", "count": None}]
        result = _prepare_records_for_ai(records, [STR_FIELD, INT_FIELD])
        assert result == []  # Both values empty

    def test_long_values_trimmed(self) -> None:
        long_name = "x" * 200
        records = [{"name": long_name, "count": "1"}]
        result = _prepare_records_for_ai(records, [STR_FIELD, INT_FIELD])
        assert len(result) == 1
        assert len(result[0]["name"]) == 183  # 180 + "..."


# ─── process_raw_records ──────────────────────────────────────────────────────


class TestProcessRawRecords:
    """Tests for process_raw_records()."""

    def test_schema_complete_short_entity_is_not_removed_as_semantic_noise(self) -> None:
        schema = [
            SchemaField(name="availability", field_type=FieldType.BOOLEAN),
            SchemaField(name="name", field_type=FieldType.STRING),
            SchemaField(name="price", field_type=FieldType.CURRENCY),
        ]
        records = [{"availability": True, "name": "Olio", "price": "£23.88"}]

        result = process_raw_records(records, schema, 0.35)

        assert len(result) == 1
        assert result[0]["name"] == "Olio"

    def test_empty_input_returns_empty(self) -> None:
        assert process_raw_records([], SIMPLE_SCHEMA, 0.0) == []

    def test_processes_records(self) -> None:
        records = [{"name": "Acme", "count": "42"}]
        with patch("app.semantic_pipeline.run_pipeline", return_value=[{"name": "Acme", "count": "42"}]):
            result = process_raw_records(records, SIMPLE_SCHEMA, 0.0)
            assert len(result) == 1
            assert result[0]["name"] == "Acme"

    def test_min_score_filters_low_quality(self) -> None:
        records = [{"name": "", "count": None}]
        with patch("app.semantic_pipeline.run_pipeline", return_value=[]):
            result = process_raw_records(records, SIMPLE_SCHEMA, 0.5)
            # Empty record gets low score and gets filtered
            assert result == []


# ─── align_profile_keys_to_schema ─────────────────────────────────────────────


class TestAlignProfileKeysToSchema:
    """Tests for align_profile_keys_to_schema()."""

    def test_exact_matches_preserved(self) -> None:
        from app.data_utils import align_profile_keys_to_schema

        records = [{"name": "Acme", "price": "100"}]
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, description="", required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, description="", required=False),
        ]
        aligned = align_profile_keys_to_schema(records, schema)
        assert aligned[0]["name"] == "Acme"
        assert aligned[0]["price"] == "100"

    def test_fuzzy_substring_mapping(self) -> None:
        from app.data_utils import align_profile_keys_to_schema

        records = [{"origin": "LON", "destination": "PAR"}]
        schema = [
            SchemaField(name="origin_airport", field_type=FieldType.STRING, description="", required=False),
            SchemaField(name="destination_airport", field_type=FieldType.STRING, description="", required=False),
        ]
        aligned = align_profile_keys_to_schema(records, schema)
        assert aligned[0]["origin_airport"] == "LON"
        assert aligned[0]["destination_airport"] == "PAR"

    def test_synonym_group_mapping(self) -> None:
        from app.data_utils import align_profile_keys_to_schema

        records = [{"fee": "250"}]
        schema = [
            SchemaField(name="ticket_price", field_type=FieldType.CURRENCY, description="", required=False),
        ]
        aligned = align_profile_keys_to_schema(records, schema)
        assert aligned[0]["ticket_price"] == "250"

    def test_t15_custom_schema_mapping(self) -> None:
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
            "airline": "Sample Air",
            "origin": "AAA",
            "destination": "BBB",
            "date": "01-01-2026",
            "return_date": "02-01-2026",
            "price": "100",
            "stops": "Direct",
        }
        record = {key: sample_values.get(key, f"sample_{key}") for key in profile_fields}
        schema = [
            SchemaField(name="airlines_name", field_type=FieldType.STRING, description="Name of the airline", required=False),
            SchemaField(name="origin_airport", field_type=FieldType.STRING, description="Airport of origin", required=False),
            SchemaField(
                name="destination_airport",
                field_type=FieldType.STRING,
                description="Airport of destination",
                required=False,
            ),
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

    def test_return_date_maps_to_arrival_date(self) -> None:
        from app.data_utils import align_profile_keys_to_schema

        records = [{"return_date": "01-06-2026", "date": "30-05-2026"}]
        schema = [
            SchemaField(name="departure_date", field_type=FieldType.DATE, description="Date of departure", required=False),
            SchemaField(name="arrival_date", field_type=FieldType.DATE, description="Date of arrival", required=False),
        ]
        aligned = align_profile_keys_to_schema(
            records,
            schema,
            profile_fields={"return_date": {"type": "text"}, "date": {"type": "text"}},
        )
        assert aligned[0]["departure_date"] == "30-05-2026"
        assert aligned[0]["arrival_date"] == "01-06-2026"

    def test_intent_boost_mapping(self) -> None:
        from app.data_utils import align_extracted_keys_to_schema

        records = [{"fee": "250"}]
        schema = [SchemaField(name="ticket_price", field_type=FieldType.CURRENCY, description="", required=False)]
        aligned = align_extracted_keys_to_schema(
            records,
            schema,
            user_intent="find cheap fees and ticket prices",
        )
        assert aligned[0]["ticket_price"] == "250"

    def test_stops_not_mapped_to_arrival_date(self) -> None:
        from app.data_utils import align_profile_keys_to_schema

        records = [{"stops": "1 Stop", "date": "30-05-2026"}]
        schema = [
            SchemaField(name="departure_date", field_type=FieldType.DATE, description="", required=False),
            SchemaField(name="arrival_date", field_type=FieldType.DATE, description="", required=False),
        ]
        aligned = align_profile_keys_to_schema(records, schema)
        assert aligned[0]["departure_date"] == "30-05-2026"
        assert aligned[0].get("arrival_date") is None


class TestValidateAgainstSchema:
    """Schema validation gate — Roadmap §1 #6.

    The validation gate enforces type compatibility between extracted
    field values and the declared schema types. Required fields MUST
    be present and non-empty. Populated fields must match their type
    (e.g., a phone field containing a URL is a violation).
    """

    def test_valid_record_passes(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, description="", required=True),
            SchemaField(name="age", field_type=FieldType.INTEGER, description="", required=False),
            SchemaField(name="email", field_type=FieldType.EMAIL, description="", required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, description="", required=False),
        ]
        record = {"name": "Alice", "age": "30", "email": "alice@example.com", "price": "$9.99"}
        valid, violations = validate_against_schema(record, schema)
        assert valid is True
        assert violations == []

    def test_required_missing_fails(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [SchemaField(name="name", field_type=FieldType.STRING, description="", required=True)]
        valid, violations = validate_against_schema({"name": ""}, schema)
        assert valid is False
        assert len(violations) == 1
        assert "required" in violations[0]

    def test_required_null_fails(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [SchemaField(name="name", field_type=FieldType.STRING, description="", required=True)]
        valid, violations = validate_against_schema({"name": None}, schema)
        assert valid is False
        assert "required" in violations[0]

    def test_type_mismatch_email_fails(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [SchemaField(name="email", field_type=FieldType.EMAIL, description="", required=False)]
        valid, violations = validate_against_schema({"email": "not-an-email"}, schema)
        assert valid is False
        assert "email" in violations[0]

    def test_type_mismatch_phone_fails(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [SchemaField(name="phone", field_type=FieldType.PHONE, description="", required=False)]
        valid, violations = validate_against_schema({"phone": "https://example.com"}, schema)
        assert valid is False
        assert "phone" in violations[0]

    def test_type_mismatch_url_fails(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [SchemaField(name="url", field_type=FieldType.URL, description="", required=False)]
        valid, violations = validate_against_schema({"url": "example.com"}, schema)  # no scheme
        assert valid is False

    def test_type_mismatch_url_passes_with_scheme(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [SchemaField(name="url", field_type=FieldType.URL, description="", required=False)]
        valid, _ = validate_against_schema({"url": "https://example.com"}, schema)
        assert valid is True

    def test_type_mismatch_integer_fails(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [SchemaField(name="count", field_type=FieldType.INTEGER, description="", required=False)]
        valid, violations = validate_against_schema({"count": "abc"}, schema)
        assert valid is False

    def test_type_mismatch_date_fails(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [SchemaField(name="date", field_type=FieldType.DATE, description="", required=False)]
        valid, violations = validate_against_schema({"date": "yesterday"}, schema)
        assert valid is False

    def test_mixed_valid_and_invalid_fields(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, description="", required=False),
            SchemaField(name="email", field_type=FieldType.EMAIL, description="", required=False),
            SchemaField(name="phone", field_type=FieldType.PHONE, description="", required=False),
        ]
        record = {"name": "Alice", "email": "alice@example.com", "phone": "nope"}
        valid, violations = validate_against_schema(record, schema)
        assert valid is False
        assert len(violations) == 1
        assert "phone" in violations[0]

    def test_empty_optional_field_passes(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, description="", required=True),
            SchemaField(name="age", field_type=FieldType.INTEGER, description="", required=False),
        ]
        valid, _ = validate_against_schema({"name": "Alice", "age": None}, schema)
        assert valid is True

    def test_currency_accepts_decimal_and_symbol(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, description="", required=False)]
        valid, _ = validate_against_schema({"price": "$1,299.50"}, schema)
        assert valid is True

    def test_boolean_accepts_strings(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [SchemaField(name="active", field_type=FieldType.BOOLEAN, description="", required=False)]
        for value in ("true", "false", "yes", "no"):
            valid, _ = validate_against_schema({"active": value}, schema)
            assert valid is True, f"Boolean should accept {value!r}"

    def test_text_field_accepts_any_non_empty(self) -> None:
        from app.data_utils import validate_against_schema

        schema = [SchemaField(name="note", field_type=FieldType.STRING, description="", required=False)]
        for value in ("hello", "123 Main St", "https://example.com", "$100"):
            valid, _ = validate_against_schema({"note": value}, schema)
            assert valid is True, f"String field should accept {value!r}"


# ─── _value_matches_schema_type (direct unit tests) ──────────────────────────


class TestValueMatchesSchemaType:
    """Direct tests for the core type-matching primitive."""

    def _call(self, value, field_type):
        from app.data_utils import _value_matches_schema_type

        return _value_matches_schema_type(value, field_type)

    # ── NUMBER ──

    def test_number_accepts_int_string(self) -> None:
        assert self._call("42", FieldType.NUMBER) is True

    def test_number_accepts_float_string(self) -> None:
        assert self._call("3.14", FieldType.NUMBER) is True

    def test_number_accepts_negative(self) -> None:
        assert self._call("-5", FieldType.NUMBER) is True

    def test_number_rejects_non_numeric(self) -> None:
        assert self._call("abc", FieldType.NUMBER) is False

    def test_number_rejects_empty(self) -> None:
        assert self._call("", FieldType.NUMBER) is False

    def test_number_accepts_python_int(self) -> None:
        assert self._call(42, FieldType.NUMBER) is True

    def test_number_accepts_python_float(self) -> None:
        assert self._call(3.14, FieldType.NUMBER) is True

    def test_number_rejects_none(self) -> None:
        assert self._call(None, FieldType.NUMBER) is False

    # ── INTEGER ──

    def test_integer_accepts_int_string(self) -> None:
        assert self._call("42", FieldType.INTEGER) is True

    def test_integer_accepts_float_string(self) -> None:
        assert self._call("3.14", FieldType.INTEGER) is True  # regex matches digits with optional decimal

    def test_integer_rejects_non_numeric(self) -> None:
        assert self._call("abc", FieldType.INTEGER) is False

    def test_integer_accepts_python_int(self) -> None:
        assert self._call(42, FieldType.INTEGER) is True

    def test_integer_rejects_none(self) -> None:
        assert self._call(None, FieldType.INTEGER) is False

    # ── FLOAT ──

    def test_float_accepts_float_string(self) -> None:
        assert self._call("3.14", FieldType.FLOAT) is True

    def test_float_accepts_int_string(self) -> None:
        assert self._call("42", FieldType.FLOAT) is True

    def test_float_rejects_non_numeric(self) -> None:
        assert self._call("abc", FieldType.FLOAT) is False

    def test_float_accepts_python_float(self) -> None:
        assert self._call(3.14, FieldType.FLOAT) is True

    def test_float_rejects_none(self) -> None:
        assert self._call(None, FieldType.FLOAT) is False

    # ── CURRENCY ──

    def test_currency_accepts_dollar_amount(self) -> None:
        assert self._call("$1,299.50", FieldType.CURRENCY) is True

    def test_currency_accepts_simple_number(self) -> None:
        assert self._call("100", FieldType.CURRENCY) is True

    def test_currency_accepts_euro_format(self) -> None:
        assert self._call("€50", FieldType.CURRENCY) is True

    def test_currency_accepts_python_number(self) -> None:
        assert self._call(99.99, FieldType.CURRENCY) is True

    def test_currency_rejects_empty(self) -> None:
        assert self._call("", FieldType.CURRENCY) is False

    def test_currency_rejects_none(self) -> None:
        assert self._call(None, FieldType.CURRENCY) is False

    # ── EMAIL ──

    def test_email_accepts_valid(self) -> None:
        assert self._call("alice@example.com", FieldType.EMAIL) is True

    def test_email_accepts_plus_addressing(self) -> None:
        assert self._call("alice+tag@example.co.uk", FieldType.EMAIL) is True

    def test_email_rejects_no_domain(self) -> None:
        assert self._call("not-an-email", FieldType.EMAIL) is False

    def test_email_rejects_empty(self) -> None:
        assert self._call("", FieldType.EMAIL) is False

    def test_email_rejects_none(self) -> None:
        assert self._call(None, FieldType.EMAIL) is False

    # ── URL ──

    def test_url_accepts_https(self) -> None:
        assert self._call("https://example.com", FieldType.URL) is True

    def test_url_accepts_http(self) -> None:
        assert self._call("http://example.com", FieldType.URL) is True

    def test_url_rejects_no_scheme(self) -> None:
        assert self._call("example.com", FieldType.URL) is False

    def test_url_rejects_empty(self) -> None:
        assert self._call("", FieldType.URL) is False

    def test_url_rejects_none(self) -> None:
        assert self._call(None, FieldType.URL) is False

    # ── DATE ──

    def test_date_accepts_iso_format(self) -> None:
        assert self._call("2026-06-15", FieldType.DATE) is True

    def test_date_accepts_slash_format(self) -> None:
        assert self._call("06/15/2026", FieldType.DATE) is True

    def test_date_rejects_non_date(self) -> None:
        assert self._call("hello", FieldType.DATE) is False

    def test_date_rejects_empty(self) -> None:
        assert self._call("", FieldType.DATE) is False

    def test_date_rejects_none(self) -> None:
        assert self._call(None, FieldType.DATE) is False

    # ── PHONE ──

    def test_phone_accepts_formatted(self) -> None:
        assert self._call("+1-555-123-4567", FieldType.PHONE) is True

    def test_phone_accepts_spaces(self) -> None:
        assert self._call("+1 555 123 4567", FieldType.PHONE) is True

    def test_phone_accepts_bare_digits(self) -> None:
        assert self._call("1234567890", FieldType.PHONE) is True

    def test_phone_rejects_short(self) -> None:
        assert self._call("12", FieldType.PHONE) is False

    def test_phone_rejects_empty(self) -> None:
        assert self._call("", FieldType.PHONE) is False

    def test_phone_rejects_none(self) -> None:
        assert self._call(None, FieldType.PHONE) is False

    # ── BOOLEAN ──

    def test_boolean_accepts_true_string(self) -> None:
        assert self._call("true", FieldType.BOOLEAN) is True

    def test_boolean_accepts_false_string(self) -> None:
        assert self._call("false", FieldType.BOOLEAN) is True

    def test_boolean_accepts_yes_string(self) -> None:
        assert self._call("yes", FieldType.BOOLEAN) is True

    def test_boolean_accepts_no_string(self) -> None:
        assert self._call("no", FieldType.BOOLEAN) is True

    def test_boolean_accepts_python_bool(self) -> None:
        assert self._call(True, FieldType.BOOLEAN) is True
        assert self._call(False, FieldType.BOOLEAN) is True

    def test_boolean_rejects_numeric_as_bool(self) -> None:
        assert self._call(1, FieldType.BOOLEAN) is False

    def test_boolean_rejects_none(self) -> None:
        assert self._call(None, FieldType.BOOLEAN) is False

    def test_boolean_rejects_random_text(self) -> None:
        assert self._call("maybe", FieldType.BOOLEAN) is False

    # ── TEXT / STRING ──

    def test_text_accepts_any_non_empty(self) -> None:
        assert self._call("hello", FieldType.STRING) is True
        assert self._call("123", FieldType.STRING) is True
        assert self._call("https://example.com", FieldType.STRING) is True

    def test_text_rejects_empty(self) -> None:
        assert self._call("", FieldType.STRING) is False

    def test_text_rejects_none(self) -> None:
        assert self._call(None, FieldType.STRING) is False
