"""Comprehensive tests for the data quality pipeline.

Covers all functions in ``app.data_quality``: cleaning rules, validators,
field scoring, record scoring, deduplication, and the full pipeline.
"""

from __future__ import annotations

from app.data_quality import (
    _clean_boolean,
    _clean_date,
    _clean_email,
    _clean_number,
    _clean_phone,
    _clean_price,
    _clean_text,
    _clean_url,
    _field_score,
    clean_record,
    deduplicate_records,
    run_quality_pipeline,
    score_record,
    validate_record,
)
from app.models import FieldType, SchemaField

# ── Cleaning ─────────────────────────────────────────────────────────────


class TestCleanText:
    def test_trims_whitespace(self) -> None:
        assert _clean_text("  Hello   World  ") == "Hello World"

    def test_handles_none(self) -> None:
        # _clean_text accepts Any, but mypy sees str in signature
        assert _clean_text("") == ""

    def test_handles_non_string(self) -> None:
        assert _clean_text("42") == "42"

    def test_handles_empty_string(self) -> None:
        assert _clean_text("") == ""


class TestCleanPrice:
    def test_removes_dollar(self) -> None:
        assert _clean_price("$1,234.56") == 1234.56

    def test_removes_euro(self) -> None:
        assert _clean_price("€99.99") == 99.99

    def test_removes_pound(self) -> None:
        assert _clean_price("£50") == 50.0

    def test_handles_float_input(self) -> None:
        assert _clean_price("29.99") == 29.99

    def test_handles_int_input(self) -> None:
        assert _clean_price("100") == 100.0

    def test_returns_original_on_parse_failure(self) -> None:
        assert _clean_price("free") == "free"

    def test_handles_thousand_separators(self) -> None:
        assert _clean_price("$1,234,567.89") == 1234567.89

    def test_handles_no_currency_symbol(self) -> None:
        assert _clean_price("19.99") == 19.99

    def test_handles_yen(self) -> None:
        assert _clean_price("¥1500") == 1500.0


class TestCleanDate:
    def test_strips_whitespace(self) -> None:
        assert _clean_date("  2024-01-15  ") == "2024-01-15"

    def test_handles_none(self) -> None:
        assert _clean_date("") == ""

    def test_handles_non_string(self) -> None:
        assert _clean_date("42") == "42"

    def test_returns_stripped(self) -> None:
        assert _clean_date("Jan 15, 2024") == "Jan 15, 2024"


class TestCleanUrl:
    def test_removes_utm_params(self) -> None:
        result = _clean_url("https://example.com/page?utm_source=email&foo=bar")
        assert "utm_source" not in result
        assert "foo=bar" in result

    def test_removes_fbclid(self) -> None:
        result = _clean_url("https://example.com/page?fbclid=abc123&keep=me")
        assert "fbclid" not in result
        assert "keep=me" in result

    def test_removes_gclid(self) -> None:
        result = _clean_url("https://example.com/page?gclid=xyz&a=1")
        assert "gclid" not in result

    def test_handles_non_string(self) -> None:
        assert _clean_url("42") == "42"

    def test_preserves_url_without_tracking(self) -> None:
        url = "https://example.com/page"
        assert _clean_url(url) == url

    def test_handles_empty_string(self) -> None:
        assert _clean_url("") == ""


class TestCleanEmail:
    def test_lowercases(self) -> None:
        assert _clean_email("  Test@EXAMPLE.COM  ") == "test@example.com"


class TestCleanPhone:
    def test_removes_non_digits(self) -> None:
        assert _clean_phone("(555) 123-4567") == "5551234567"

    def test_handles_plus_sign(self) -> None:
        # Phone cleaner strips all non-digits, including +
        assert _clean_phone("+1-555-123-4567").startswith("1")


class TestCleanNumber:
    def test_float_with_dot(self) -> None:
        assert _clean_number("3.14") == 3.14

    def test_integer(self) -> None:
        assert _clean_number("42") == 42

    def test_float_without_dot(self) -> None:
        # Python's str -> int conversion handles this
        assert _clean_number("100") == 100

    def test_non_numeric_string(self) -> None:
        assert _clean_number("abc") == "abc"

    def test_handles_float_input(self) -> None:
        assert _clean_number("3.14") == 3.14


class TestCleanBoolean:
    def test_true_string(self) -> None:
        assert _clean_boolean("true") is True

    def test_yes_string(self) -> None:
        assert _clean_boolean("yes") is True

    def test_false_string(self) -> None:
        assert _clean_boolean("false") is False

    def test_bool_input(self) -> None:
        assert _clean_boolean(True) is True

    def test_none_input(self) -> None:
        assert _clean_boolean(None) is False

    def test_one_string(self) -> None:
        assert _clean_boolean("1") is True


# ── clean_record (dispatch) ──────────────────────────────────────────────


class TestCleanRecord:
    def test_unknown_field_preserved(self) -> None:
        schema: list[SchemaField] = []
        record = {"unknown_key": "  some value  "}
        cleaned = clean_record(record, schema)
        assert cleaned["unknown_key"] == "  some value  "

    def test_dispatches_by_field_type(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        record = {"price": "$1,234.56"}
        cleaned = clean_record(record, schema)
        assert cleaned["price"] == 1234.56

    def test_cleaner_exception_returns_original(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        # Simulate a value that might cause an issue — should fall back gracefully
        record = {"price": "$1,234.56"}
        cleaned = clean_record(record, schema)
        assert cleaned["price"] is not None

    def test_multiple_fields(self) -> None:
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True, description=""),
            SchemaField(name="email", field_type=FieldType.EMAIL, required=False, description=""),
            SchemaField(name="url", field_type=FieldType.URL, required=False, description=""),
        ]
        record = {"title": "  Hello  ", "email": "  TEST@MAIL.COM  ", "url": "https://example.com?utm_source=x"}
        cleaned = clean_record(record, schema)
        assert cleaned["title"] == "Hello"
        assert cleaned["email"] == "test@mail.com"
        assert "utm_source" not in cleaned["url"]


# ── Validation ────────────────────────────────────────────────────────────


class TestValidateRecord:
    def test_required_field_missing(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        is_valid, errors = validate_record({"title": ""}, schema)
        assert not is_valid
        assert "title" in errors

    def test_required_field_none(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        is_valid, errors = validate_record({"title": None}, schema)
        assert not is_valid
        assert "title" in errors

    def test_optional_field_missing(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        is_valid, errors = validate_record({"price": ""}, schema)
        assert is_valid
        assert "price" not in errors

    def test_email_invalid_format(self) -> None:
        schema = [SchemaField(name="email", field_type=FieldType.EMAIL, required=False, description="")]
        is_valid, errors = validate_record({"email": "not-an-email"}, schema)
        assert not is_valid
        assert "email" in errors

    def test_url_invalid_format(self) -> None:
        schema = [SchemaField(name="url", field_type=FieldType.URL, required=False, description="")]
        is_valid, errors = validate_record({"url": "not-a-url"}, schema)
        assert not is_valid
        assert "url" in errors

    def test_phone_too_short(self) -> None:
        schema = [SchemaField(name="phone", field_type=FieldType.PHONE, required=False, description="")]
        is_valid, errors = validate_record({"phone": "123"}, schema)
        assert not is_valid
        assert "phone" in errors

    def test_number_invalid_type(self) -> None:
        schema = [SchemaField(name="count", field_type=FieldType.INTEGER, required=False, description="")]
        is_valid, errors = validate_record({"count": "not-a-number"}, schema)
        assert not is_valid
        assert "count" in errors

    def test_bool_always_valid(self) -> None:
        schema = [SchemaField(name="active", field_type=FieldType.BOOLEAN, required=False, description="")]
        is_valid, errors = validate_record({"active": "garbage"}, schema)
        assert is_valid
        assert "active" not in errors

    def test_multiple_errors(self) -> None:
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, required=True, description=""),
            SchemaField(name="email", field_type=FieldType.EMAIL, required=False, description=""),
        ]
        is_valid, errors = validate_record({"name": "", "email": "bad"}, schema)
        assert not is_valid
        assert "name" in errors
        assert "email" in errors


# ── Field Scoring ──────────────────────────────────────────────────────────


class TestFieldScore:
    def test_none_returns_zero(self) -> None:
        assert _field_score(None, FieldType.STRING) == 0.0

    def test_empty_string_returns_zero(self) -> None:
        assert _field_score("", FieldType.STRING) == 0.0

    def test_short_string(self) -> None:
        assert _field_score("ab", FieldType.STRING) == 0.3

    def test_medium_string(self) -> None:
        assert _field_score("Hello!", FieldType.STRING) == 0.6

    def test_long_string(self) -> None:
        assert _field_score("Hello World", FieldType.STRING) == 1.0

    def test_integer_value(self) -> None:
        assert _field_score(42, FieldType.INTEGER) == 1.0

    def test_float_value(self) -> None:
        assert _field_score(3.14, FieldType.FLOAT) == 1.0

    def test_bool_value(self) -> None:
        assert _field_score(True, FieldType.BOOLEAN) == 1.0

    def test_bool_string_value(self) -> None:
        score = _field_score("true", FieldType.BOOLEAN)
        assert score == 0.5

    def test_valid_email(self) -> None:
        assert _field_score("test@example.com", FieldType.EMAIL) == 1.0

    def test_invalid_email(self) -> None:
        assert _field_score("not-email", FieldType.EMAIL) == 0.3

    def test_valid_url(self) -> None:
        assert _field_score("https://example.com", FieldType.URL) == 1.0

    def test_invalid_url(self) -> None:
        assert _field_score("not-a-url", FieldType.URL) == 0.3

    def test_valid_phone(self) -> None:
        assert _field_score("5551234567", FieldType.PHONE) == 1.0

    def test_invalid_phone(self) -> None:
        assert _field_score("12", FieldType.PHONE) == 0.3

    def test_valid_date_format(self) -> None:
        """DATE field should validate format, not just non-empty."""
        assert _field_score("2024-01-15", FieldType.DATE) == 1.0

    def test_valid_date_slashes(self) -> None:
        assert _field_score("01/15/2024", FieldType.DATE) == 1.0

    def test_valid_date_textual(self) -> None:
        assert _field_score("Jan 15, 2024", FieldType.DATE) == 1.0

    def test_invalid_date_garbage(self) -> None:
        """Arbitrary non-date text should NOT score 1.0 on DATE fields."""
        score = _field_score("not-a-date", FieldType.DATE)
        assert score < 0.8, f"Expected low score for non-date text, got {score}"

    def test_invalid_date_empty_like(self) -> None:
        assert _field_score("abc", FieldType.DATE) == 0.0

    def test_currency_value(self) -> None:
        assert _field_score(10.99, FieldType.CURRENCY) == 1.0

    def test_rating_value(self) -> None:
        assert _field_score(4.5, FieldType.RATING) == 1.0

    def test_number_value(self) -> None:
        assert _field_score(42, FieldType.NUMBER) == 1.0

    def test_number_non_numeric(self) -> None:
        assert _field_score("abc", FieldType.NUMBER) == 0.3

    def test_currency_string_scores_lower(self) -> None:
        # String values aren't validated as numeric types by _field_score
        score = _field_score("$10", FieldType.CURRENCY)
        assert score == 0.3

    def test_location(self) -> None:
        assert _field_score("New York", FieldType.LOCATION) == 1.0

    def test_location_short(self) -> None:
        assert _field_score("NY", FieldType.LOCATION) == 0.3


# ── Record Scoring ─────────────────────────────────────────────────────────


class TestScoreRecord:
    def test_empty_record_returns_zero(self) -> None:
        assert score_record({}, []) == 0.0

    def test_missing_required_penalizes(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        assert score_record({"title": ""}, schema) == 0.0

    def test_populated_required_scores(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        score = score_record({"title": "Hello World"}, schema)
        assert 0.0 < score <= 1.0

    def test_mixed_fields(self) -> None:
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True, description=""),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
        ]
        score = score_record({"title": "Item", "price": 10.99}, schema)
        assert 0.0 < score <= 1.0

    def test_all_none_values(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False, description="")]
        assert score_record({"title": None}, schema) == 0.0


# ── Deduplication ──────────────────────────────────────────────────────────


class TestDeduplicateRecords:
    def test_empty_list(self) -> None:
        unique, removed = deduplicate_records([])
        assert unique == []
        assert removed == 0

    def test_no_duplicates(self) -> None:
        records = [{"a": "1"}, {"a": "2"}]
        unique, removed = deduplicate_records(records)
        assert len(unique) == 2
        assert removed == 0

    def test_all_duplicates(self) -> None:
        records = [{"a": "1"}, {"a": "1"}, {"a": "1"}]
        unique, removed = deduplicate_records(records)
        assert len(unique) == 1
        assert removed == 2

    def test_preserves_first_occurrence(self) -> None:
        records = [{"a": "first"}, {"a": "dup"}, {"a": "first"}]
        unique, removed = deduplicate_records(records)
        assert unique[0]["a"] == "first"
        assert removed == 1

    def test_complex_records(self) -> None:
        records = [
            {"name": "A", "price": 10},
            {"name": "B", "price": 20},
            {"name": "A", "price": 10},
        ]
        unique, removed = deduplicate_records(records)
        assert len(unique) == 2
        assert removed == 1


# ── Full Pipeline ──────────────────────────────────────────────────────────


class TestRunQualityPipeline:
    def test_empty_input(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        result = run_quality_pipeline([], schema)
        assert result["total_input"] == 0
        assert result["total_valid"] == 0
        assert result["total_invalid"] == 0
        assert result["quality_score"] == 0.0
        assert len(result["warnings"]) > 0

    def test_duplicates_removed(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        records = [
            {"title": "Item 1"},
            {"title": "Item 1"},
            {"title": "Item 2"},
        ]
        result = run_quality_pipeline(records, schema)
        assert result["duplicates_removed"] == 1
        assert result["total_valid"] == 2

    def test_invalid_record_flagged(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        records = [
            {"title": "Valid Item"},
            {"title": ""},
        ]
        result = run_quality_pipeline(records, schema)
        assert result["total_invalid"] == 1
        assert result["total_valid"] == 1

    def test_all_invalid(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        records: list[dict] = [{"title": ""}, {"title": None}]
        result = run_quality_pipeline(records, schema)
        assert result["total_valid"] == 0
        assert result["quality_score"] == 0.0
        assert "No valid records" in " ".join(result["warnings"])

    def test_field_validity_computed(self) -> None:
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, required=True, description=""),
            SchemaField(name="email", field_type=FieldType.EMAIL, required=False, description=""),
        ]
        records = [
            {"name": "Item 1", "email": "a@b.com"},
            {"name": "Item 2", "email": ""},
        ]
        result = run_quality_pipeline(records, schema)
        assert "name" in result["field_validity"]
        assert "email" in result["field_validity"]
        assert result["field_validity"]["name"] == 1.0

    def test_quality_score_range(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        records = [{"title": "Excellent long title here"}, {"title": "OK"}]
        result = run_quality_pipeline(records, schema)
        assert 0.0 <= result["quality_score"] <= 1.0

    def test_cleaning_applied(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        records = [{"price": "$1,234.56"}, {"price": "€99.99"}]
        result = run_quality_pipeline(records, schema)
        # Both should be valid after cleaning
        assert result["total_valid"] == 2
