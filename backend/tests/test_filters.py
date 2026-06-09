"""Tests for app.filters — type coercion, geocoding, and data filtering."""

from __future__ import annotations

import pytest
from app.filters import (
    _infer_location_field_names,
    _is_entity_name_field,
    _looks_like_email,
    _looks_like_phone,
    _looks_like_url,
    _pick_record_location,
    calculate_distance,
    coerce_record,
    coerce_value,
    enforce_schema_integrity,
    normalize_record,
)
from app.models import FieldType, FilterOperator, FilterRule, SchemaField

# ─── _looks_like_email ──────────────────────────────────────────────────


class TestLooksLikeEmail:
    def test_valid_emails(self) -> None:
        assert _looks_like_email("user@example.com") is True
        assert _looks_like_email("first.last@sub.example.co.uk") is True
        assert _looks_like_email("user+tag@example.org") is True

    def test_invalid_emails(self) -> None:
        assert _looks_like_email("") is False
        assert _looks_like_email("not-an-email") is False
        assert _looks_like_email("@example.com") is False
        assert _looks_like_email("user@") is False
        assert _looks_like_email(None) is False  # type: ignore[arg-type]


# ─── _looks_like_phone ──────────────────────────────────────────────────


class TestLooksLikePhone:
    def test_valid_phones(self) -> None:
        assert _looks_like_phone("+1234567890") is True
        assert _looks_like_phone("+1 (555) 123-4567") is True
        assert _looks_like_phone("1234567890") is True  # 10 digits
        assert _looks_like_phone("+911234567890") is True  # 12 digits

    def test_invalid_phones(self) -> None:
        assert _looks_like_phone("") is False
        assert _looks_like_phone("12345") is False  # too short
        assert _looks_like_phone("+" + "1" * 16) is False  # too long
        assert _looks_like_phone(None) is False  # type: ignore[arg-type]


# ─── _looks_like_url ────────────────────────────────────────────────────


class TestLooksLikeUrl:
    def test_valid_urls(self) -> None:
        assert _looks_like_url("https://example.com") is True
        assert _looks_like_url("http://example.com/page") is True
        assert _looks_like_url("www.example.com") is True
        assert _looks_like_url("https://sub.example.co.uk/path?q=1") is True

    def test_invalid_urls(self) -> None:
        assert _looks_like_url("") is False
        assert _looks_like_url("just text") is False
        assert _looks_like_url("user@example.com") is False  # email, not URL
        assert _looks_like_url(None) is False  # type: ignore[arg-type]


# ─── _is_entity_name_field ──────────────────────────────────────────────


class TestIsEntityNameField:
    def test_entity_name_fields(self) -> None:
        assert _is_entity_name_field("company_name") is True
        assert _is_entity_name_field("name") is True
        assert _is_entity_name_field("studio") is True
        assert _is_entity_name_field("firm_name") is True
        assert _is_entity_name_field("agency") is True

    def test_non_entity_fields(self) -> None:
        assert _is_entity_name_field("email") is False
        assert _is_entity_name_field("phone") is False
        assert _is_entity_name_field("address") is False
        assert _is_entity_name_field("") is False


# ─── coerce_value ───────────────────────────────────────────────────────


class TestCoerceValue:
    def test_coerce_integer(self) -> None:
        assert coerce_value("42", FieldType.INTEGER) == 42
        assert coerce_value(42, FieldType.INTEGER) == 42
        assert coerce_value(42.7, FieldType.INTEGER) == 42
        assert coerce_value("Age: 25 years", FieldType.INTEGER) == 25
        assert coerce_value("no digits", FieldType.INTEGER) is None
        assert coerce_value(None, FieldType.INTEGER) is None

    def test_coerce_float(self) -> None:
        assert coerce_value("3.14", FieldType.FLOAT) == 3.14
        assert coerce_value(3.14, FieldType.FLOAT) == 3.14
        assert coerce_value(42, FieldType.FLOAT) == 42.0
        assert coerce_value("Price: 99.99", FieldType.FLOAT) == 99.99
        assert coerce_value(None, FieldType.FLOAT) is None

    def test_coerce_boolean(self) -> None:
        assert coerce_value(True, FieldType.BOOLEAN) is True
        assert coerce_value(False, FieldType.BOOLEAN) is False
        assert coerce_value("true", FieldType.BOOLEAN) is True
        assert coerce_value("yes", FieldType.BOOLEAN) is True
        assert coerce_value("1", FieldType.BOOLEAN) is True
        assert coerce_value("false", FieldType.BOOLEAN) is False
        assert coerce_value("no", FieldType.BOOLEAN) is False
        assert coerce_value("0", FieldType.BOOLEAN) is False
        assert coerce_value("maybe", FieldType.BOOLEAN) is None
        assert coerce_value(None, FieldType.BOOLEAN) is None

    def test_coerce_email(self) -> None:
        assert coerce_value("user@example.com", FieldType.EMAIL) == "user@example.com"
        assert coerce_value("Contact: user@example.com", FieldType.EMAIL) == "user@example.com"
        assert coerce_value(None, FieldType.EMAIL) is None

    def test_coerce_phone(self) -> None:
        result = coerce_value("+1 (555) 123-4567", FieldType.PHONE)
        assert result is not None
        assert all(c in result for c in ["+", "1", "5", "5", "5"])
        assert coerce_value(None, FieldType.PHONE) is None

    def test_coerce_list_string(self) -> None:
        assert coerce_value(["a", "b"], FieldType.LIST_STRING) == ["a", "b"]
        assert coerce_value("single", FieldType.LIST_STRING) == ["single"]
        assert coerce_value(None, FieldType.LIST_STRING) is None

    def test_coerce_currency(self) -> None:
        assert coerce_value("$1,200.50", FieldType.CURRENCY) == 1200.50
        assert coerce_value("₹5000", FieldType.CURRENCY) == 5000.0
        assert coerce_value(None, FieldType.CURRENCY) is None

    def test_coerce_percentage(self) -> None:
        assert coerce_value("85%", FieldType.PERCENTAGE) == 85.0
        assert coerce_value("85 percent", FieldType.PERCENTAGE) == 85.0
        assert coerce_value(None, FieldType.PERCENTAGE) is None

    def test_coerce_string_fallback(self) -> None:
        assert coerce_value("hello", FieldType.STRING) == "hello"
        assert coerce_value(None, FieldType.STRING) is None


# ─── coerce_record ──────────────────────────────────────────────────────


class TestCoerceRecord:
    def test_coerce_all_fields(self) -> None:
        schema = [
            SchemaField(name="age", field_type=FieldType.INTEGER),
            SchemaField(name="active", field_type=FieldType.BOOLEAN),
            SchemaField(name="email", field_type=FieldType.EMAIL),
        ]
        record = {"age": "25", "active": "true", "email": "user@example.com", "extra": "keep"}
        result = coerce_record(record, schema)
        assert result["age"] == 25
        assert result["active"] is True
        assert result["email"] == "user@example.com"
        assert result["extra"] == "keep"

    def test_none_values(self) -> None:
        schema = [SchemaField(name="age", field_type=FieldType.INTEGER)]
        result = coerce_record({"age": None}, schema)
        assert result["age"] is None


# ─── normalize_record ───────────────────────────────────────────────────


class TestNormalizeRecord:
    def test_normalize_orders_by_schema(self) -> None:
        schema = [
            SchemaField(name="b", field_type=FieldType.STRING),
            SchemaField(name="a", field_type=FieldType.STRING),
        ]
        record = {"a": "1", "b": "2", "extra": "keep"}
        result = normalize_record(record, schema)
        keys = list(result.keys())
        # 'b' should come first (schema order), then 'a', then extras
        assert keys.index("b") < keys.index("a")
        assert result["extra"] == "keep"

    def test_missing_schema_fields_get_none(self) -> None:
        schema = [SchemaField(name="name", field_type=FieldType.STRING)]
        result = normalize_record({}, schema)
        assert result["name"] is None


# ─── enforce_schema_integrity ───────────────────────────────────────────


class TestEnforceSchemaIntegrity:
    def test_passes_clean_record(self) -> None:
        schema = [
            SchemaField(name="company_name", field_type=FieldType.STRING),
            SchemaField(name="email", field_type=FieldType.EMAIL),
        ]
        record = {"company_name": "Acme Corp", "email": "acme@example.com"}
        cleaned, mismatches = enforce_schema_integrity(record, schema)
        assert cleaned["company_name"] == "Acme Corp"
        assert cleaned["email"] == "acme@example.com"
        assert mismatches == []

    def test_flags_invalid_email(self) -> None:
        schema = [SchemaField(name="email", field_type=FieldType.EMAIL)]
        record = {"email": "not-an-email"}
        cleaned, mismatches = enforce_schema_integrity(record, schema)
        assert cleaned["email"] is None
        assert "email:expected_email" in mismatches

    def test_moves_email_from_name_field(self) -> None:
        schema = [
            SchemaField(name="company_name", field_type=FieldType.STRING),
            SchemaField(name="email", field_type=FieldType.EMAIL),
        ]
        record = {"company_name": "user@example.com", "email": None}
        cleaned, mismatches = enforce_schema_integrity(record, schema)
        assert cleaned["company_name"] is None  # name was cleared
        assert cleaned["email"] == "user@example.com"  # moved to email
        assert any("moved_to_email" in m for m in mismatches)

    def test_moves_phone_from_name_field(self) -> None:
        schema = [
            SchemaField(name="company_name", field_type=FieldType.STRING),
            SchemaField(name="phone", field_type=FieldType.PHONE),
        ]
        record = {"company_name": "+1-555-123-4567", "phone": None}
        cleaned, mismatches = enforce_schema_integrity(record, schema)
        assert cleaned["company_name"] is None
        assert cleaned["phone"] is not None
        assert any("moved_to_phone" in m for m in mismatches)

    def test_flags_url_in_name(self) -> None:
        schema = [SchemaField(name="name", field_type=FieldType.STRING)]
        record = {"name": "https://example.com"}
        cleaned, mismatches = enforce_schema_integrity(record, schema)
        assert cleaned["name"] is None
        assert any("url_in_name" in m for m in mismatches)

    def test_adds_type_mismatch_flags_key(self) -> None:
        schema = [SchemaField(name="phone", field_type=FieldType.PHONE)]
        record = {"phone": "not-a-phone"}
        cleaned, _mismatches = enforce_schema_integrity(record, schema)
        assert "type_mismatch_flags" in cleaned
        assert cleaned["type_mismatch_flags"] == ["phone:expected_phone"]


# ─── calculate_distance ────────────────────────────────────────────────


class TestCalculateDistance:
    def test_known_distance_km(self) -> None:
        # Distance between roughly the same point should be ~0
        d = calculate_distance((12.97, 77.59), (12.97, 77.59))
        assert d < 0.1

    def test_known_distance_miles(self) -> None:
        d = calculate_distance((12.97, 77.59), (12.97, 77.59), unit="miles")
        assert d < 0.1

    def test_significant_distance(self) -> None:
        # Delhi to Mumbai ~1100 km
        d = calculate_distance((28.61, 77.23), (19.07, 72.87))
        assert 1000 < d < 1300


# ─── _infer_location_field_names ────────────────────────────────────────


class TestInferLocationFieldNames:
    def test_preferred_field_first(self) -> None:
        schema = [SchemaField(name="address", field_type=FieldType.STRING)]
        result = _infer_location_field_names(schema, preferred_field="address")
        assert result[0] == "address"

    def test_location_type_preferred(self) -> None:
        schema = [
            SchemaField(name="desc", field_type=FieldType.STRING),
            SchemaField(name="loc", field_type=FieldType.LOCATION),
        ]
        result = _infer_location_field_names(schema)
        # LOCATION-type field should come before STRING hints
        assert "loc" in result

    def test_name_hints(self) -> None:
        schema = [
            SchemaField(name="city", field_type=FieldType.STRING),
            SchemaField(name="zip_code", field_type=FieldType.STRING),
        ]
        result = _infer_location_field_names(schema)
        assert "city" in result
        assert "zip_code" in result


# ─── _pick_record_location ──────────────────────────────────────────────


class TestPickRecordLocation:
    def test_picks_first_nonempty(self) -> None:
        result = _pick_record_location(
            {"location": "", "city": "Bangalore"},
            ["location", "city"],
        )
        assert result == "Bangalore"

    def test_returns_none_when_all_empty(self) -> None:
        result = _pick_record_location({"loc": "", "city": ""}, ["loc", "city"])
        assert result is None

    def test_returns_none_when_no_candidates(self) -> None:
        result = _pick_record_location({"name": "Acme"}, [])
        assert result is None


# ─── process_results (integration-style) ────────────────────────────────


@pytest.mark.asyncio
async def test_process_results_empty() -> None:
    """process_results with empty input returns empty."""
    from app.filters import process_results

    cleaned, total, filtered_count, _report = await process_results([], [], [])
    assert cleaned == []
    assert total == 0
    assert filtered_count == 0


@pytest.mark.asyncio
async def test_process_results_no_filters() -> None:
    """process_results without filters coerces types and normalizes."""
    from app.filters import process_results

    schema = [SchemaField(name="age", field_type=FieldType.INTEGER)]
    raw = [{"age": "25"}, {"age": "thirty"}]
    cleaned, total, filtered_count, _report = await process_results(raw, schema, [])
    assert total == 2
    assert filtered_count == 2
    assert cleaned[0]["age"] == 25
    # "thirty" has no digits → coerces to None
    assert cleaned[1]["age"] is None


@pytest.mark.asyncio
async def test_process_results_with_filter() -> None:
    """process_results applies filters correctly."""
    from app.filters import process_results

    schema = [SchemaField(name="age", field_type=FieldType.INTEGER)]
    filters = [
        FilterRule(field_name="age", operator=FilterOperator.GREATER_THAN, value="18"),
    ]
    raw = [{"age": "25"}, {"age": "15"}, {"age": "30"}]
    cleaned, total, filtered_count, _report = await process_results(raw, schema, filters)
    assert total == 3
    assert filtered_count == 2
    ages = {r["age"] for r in cleaned}
    assert ages == {25, 30}


@pytest.mark.asyncio
async def test_process_results_integrity_report() -> None:
    """process_results returns integrity report with mismatch counts."""
    from app.filters import process_results

    schema = [SchemaField(name="email", field_type=FieldType.EMAIL)]
    raw = [{"email": "user@example.com"}, {"email": "not-an-email"}]
    _cleaned, _total, _filtered_count, report = await process_results(raw, schema, [])
    assert report["records_with_type_mismatch"] == 1
    assert report["total_type_mismatches"] == 1


# ─── asyncio apply_filter (targeted) ────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_filter_equals() -> None:
    from app.filters import apply_filter

    rule = FilterRule(field_name="status", operator=FilterOperator.EQUALS, value="active")
    assert await apply_filter({"status": "active"}, rule, []) is True
    assert await apply_filter({"status": "inactive"}, rule, []) is False


@pytest.mark.asyncio
async def test_apply_filter_greater_than() -> None:
    from app.filters import apply_filter

    rule = FilterRule(field_name="price", operator=FilterOperator.GREATER_THAN, value="100")
    assert await apply_filter({"price": "150"}, rule, []) is True
    assert await apply_filter({"price": "50"}, rule, []) is False


@pytest.mark.asyncio
async def test_apply_filter_regex() -> None:
    from app.filters import apply_filter

    rule = FilterRule(field_name="email", operator=FilterOperator.MATCHES_REGEX, value=r".*@example\.com")
    assert await apply_filter({"email": "user@example.com"}, rule, []) is True
    assert await apply_filter({"email": "user@other.com"}, rule, []) is False


@pytest.mark.asyncio
async def test_apply_filter_is_empty() -> None:
    from app.filters import apply_filter

    rule = FilterRule(field_name="name", operator=FilterOperator.IS_EMPTY, value="")
    assert await apply_filter({"name": ""}, rule, []) is True
    assert await apply_filter({"name": "Acme"}, rule, []) is False
    assert await apply_filter({"name": None}, rule, []) is True


@pytest.mark.asyncio
async def test_apply_filter_in_list() -> None:
    from app.filters import apply_filter

    rule = FilterRule(field_name="city", operator=FilterOperator.IN_LIST, value="New York, London, Tokyo")
    assert await apply_filter({"city": "New York"}, rule, []) is True
    assert await apply_filter({"city": "Tokyo"}, rule, []) is True
    assert await apply_filter({"city": "Paris"}, rule, []) is False
