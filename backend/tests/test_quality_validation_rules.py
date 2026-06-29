"""Qual 18: Automated validation rules engine — test custom validation rules DSL.

Also covers Roadmap Wave 7 Item 2: field-level type validation against
declared FieldType (numeric, email, URL, date, boolean).
"""

from __future__ import annotations

import re
from typing import Any

from app.data_quality import (
    TYPE_CHECKERS,
    FieldTypeMismatch,
    _check_boolean,
    _check_date,
    _check_email,
    _check_numeric,
    _check_url,
    is_record_type_valid,
    validate_field_types,
)
from app.models import FieldType, SchemaField


class ValidationRule:
    """A single validation rule for a field."""

    def __init__(self, field: str, rule_type: str, value: Any) -> None:
        self.field = field
        self.rule_type = rule_type
        self.value = value

    def validate(self, record: dict) -> tuple[bool, str]:
        val = record.get(self.field)
        if self.rule_type == "required":
            if val is None or str(val).strip() == "":
                return False, f"Field '{self.field}' is required"
            return True, ""
        if self.rule_type == "min":
            try:
                num_val = float(val) if val is not None else 0
                if num_val < float(self.value):
                    return False, f"Field '{self.field}' ({val}) is below minimum {self.value}"
            except (TypeError, ValueError):
                pass
            return True, ""
        if self.rule_type == "max":
            try:
                num_val = float(val) if val is not None else 0
                if num_val > float(self.value):
                    return False, f"Field '{self.field}' ({val}) exceeds maximum {self.value}"
            except (TypeError, ValueError):
                pass
            return True, ""
        if self.rule_type == "regex":
            if not re.match(str(self.value), str(val or "")):
                return False, f"Field '{self.field}' ('{val}') does not match pattern"
            return True, ""
        if self.rule_type == "min_length":
            if len(str(val or "")) < int(self.value):
                return False, f"Field '{self.field}' is too short (min {self.value} chars)"
            return True, ""
        if self.rule_type == "max_length":
            if len(str(val or "")) > int(self.value):
                return False, f"Field '{self.field}' is too long (max {self.value} chars)"
            return True, ""
        return True, ""


class ValidationRuleSet:
    """A set of validation rules applied to records."""

    def __init__(self, rules: list[ValidationRule] | None = None) -> None:
        self.rules = rules or []

    def add_rule(self, rule: ValidationRule) -> None:
        self.rules.append(rule)

    def validate(self, record: dict) -> dict[str, Any]:
        errors = []
        for rule in self.rules:
            is_valid, message = rule.validate(record)
            if not is_valid:
                errors.append(message)
        return {"valid": len(errors) == 0, "errors": errors}

    def validate_all(self, records: list[dict]) -> list[dict[str, Any]]:
        return [self.validate(r) for r in records]


class TestValidationRuleTypes:
    def test_required_rule(self) -> None:
        rule = ValidationRule("title", "required", None)
        assert rule.validate({"title": "Hello"})[0] is True
        assert rule.validate({"title": ""})[0] is False
        assert rule.validate({})[0] is False

    def test_min_rule(self) -> None:
        rule = ValidationRule("price", "min", 10)
        assert rule.validate({"price": 15})[0] is True
        assert rule.validate({"price": 5})[0] is False

    def test_max_rule(self) -> None:
        rule = ValidationRule("quantity", "max", 100)
        assert rule.validate({"quantity": 50})[0] is True
        assert rule.validate({"quantity": 200})[0] is False

    def test_regex_rule(self) -> None:
        rule = ValidationRule("email", "regex", r".+@.+\..+")
        assert rule.validate({"email": "a@b.com"})[0] is True
        assert rule.validate({"email": "invalid"})[0] is False

    def test_min_length_rule(self) -> None:
        rule = ValidationRule("name", "min_length", 3)
        assert rule.validate({"name": "John"})[0] is True
        assert rule.validate({"name": "Jo"})[0] is False

    def test_max_length_rule(self) -> None:
        rule = ValidationRule("code", "max_length", 10)
        assert rule.validate({"code": "ABC123"})[0] is True
        assert rule.validate({"code": "A" * 20})[0] is False


class TestValidationRuleSet:
    def test_all_rules_pass(self) -> None:
        rs = ValidationRuleSet(
            [
                ValidationRule("title", "required", None),
                ValidationRule("price", "min", 0),
            ]
        )
        result = rs.validate({"title": "Widget", "price": 25})
        assert result["valid"] is True
        assert result["errors"] == []

    def test_some_rules_fail(self) -> None:
        rs = ValidationRuleSet(
            [
                ValidationRule("title", "required", None),
                ValidationRule("price", "min", 10),
            ]
        )
        result = rs.validate({"title": "", "price": 5})
        assert result["valid"] is False
        assert len(result["errors"]) == 2

    def test_empty_ruleset(self) -> None:
        rs = ValidationRuleSet()
        result = rs.validate({"x": 1})
        assert result["valid"] is True

    def test_validate_all_records(self) -> None:
        rs = ValidationRuleSet(
            [
                ValidationRule("title", "required", None),
            ]
        )
        results = rs.validate_all(
            [
                {"title": "A"},
                {"title": ""},
                {"title": "B"},
            ]
        )
        assert results[0]["valid"] is True
        assert results[1]["valid"] is False
        assert results[2]["valid"] is True

    def test_add_rule_dynamically(self) -> None:
        rs = ValidationRuleSet()
        rs.add_rule(ValidationRule("age", "min", 18))
        assert rs.validate({"age": 25})["valid"] is True
        assert rs.validate({"age": 15})["valid"] is False


class TestValidationRuleEdgeCases:
    def test_none_value_with_required(self) -> None:
        rule = ValidationRule("field", "required", None)
        assert rule.validate({"field": None})[0] is False

    def test_non_numeric_min_on_string(self) -> None:
        rule = ValidationRule("name", "min", 5)
        result = rule.validate({"name": "hello"})
        assert result[0] is True

    def test_regex_no_match(self) -> None:
        rule = ValidationRule("zip", "regex", r"^\d{5}$")
        assert rule.validate({"zip": "12345"})[0] is True
        assert rule.validate({"zip": "ABCDE"})[0] is False
        assert rule.validate({"zip": ""})[0] is False

    def test_descriptive_error_messages(self) -> None:
        rule = ValidationRule("email", "required", None)
        _, msg = rule.validate({})
        assert "email" in msg
        assert "required" in msg


def _field(name: str, field_type: FieldType, required: bool = False) -> SchemaField:
    return SchemaField(name=name, field_type=field_type, required=required, description="")


# ---------------------------------------------------------------------------
# Roadmap Wave 7, Item 2 — Field-level type validation tests
# ---------------------------------------------------------------------------


class TestFieldTypeValidationNumeric:
    def test_numeric_accepts_int(self) -> None:
        ok, _ = _check_numeric(42)
        assert ok

    def test_numeric_accepts_float(self) -> None:
        ok, _ = _check_numeric(3.14)
        assert ok

    def test_numeric_rejects_bool(self) -> None:
        ok, reason = _check_numeric(True)
        assert not ok
        assert reason is not None and "boolean" in reason

    def test_numeric_rejects_non_numeric_string(self) -> None:
        ok, reason = _check_numeric("hello")
        assert not ok
        assert reason is not None and "not a valid number" in reason

    def test_numeric_accepts_parseable_string(self) -> None:
        for val in ["42", "3.14", "$99.99", "1,000.50", "€12.34"]:
            ok, _ = _check_numeric(val)
            assert ok, f"Expected {val!r} to be accepted as numeric"

    def test_numeric_rejects_inf(self) -> None:
        ok, _ = _check_numeric(float("inf"))
        assert not ok

    def test_numeric_rejects_nan(self) -> None:
        ok, _ = _check_numeric(float("nan"))
        assert not ok


class TestFieldTypeValidationEmail:
    def test_email_valid(self) -> None:
        ok, _ = _check_email("user@example.com")
        assert ok

    def test_email_valid_plus(self) -> None:
        ok, _ = _check_email("user+tag@example.co.uk")
        assert ok

    def test_email_invalid_no_at(self) -> None:
        ok, reason = _check_email("userexample.com")
        assert not ok
        assert reason is not None and "invalid email format" in reason

    def test_email_invalid_no_tld(self) -> None:
        ok, reason = _check_email("user@localhost")
        assert not ok
        assert reason is not None and "invalid email format" in reason

    def test_email_non_string_rejected(self) -> None:
        ok, reason = _check_email(123)
        assert not ok
        assert reason is not None and "expected string" in reason

    def test_email_empty_passes(self) -> None:
        # Empty values are a completeness issue, not a type issue
        ok, _ = _check_email("")
        assert ok


class TestFieldTypeValidationUrl:
    def test_url_valid_http(self) -> None:
        ok, _ = _check_url("http://example.com")
        assert ok

    def test_url_valid_https(self) -> None:
        ok, _ = _check_url("https://example.com/path?q=1")
        assert ok

    def test_url_rejects_javascript_uri(self) -> None:
        ok, reason = _check_url("javascript:alert(1)")
        assert not ok
        assert reason is not None and "javascript" in reason

    def test_url_rejects_no_scheme(self) -> None:
        ok, reason = _check_url("example.com")
        assert not ok
        assert reason is not None and "scheme" in reason

    def test_url_rejects_ftp(self) -> None:
        ok, reason = _check_url("ftp://files.example.com")
        assert not ok
        assert reason is not None and "scheme" in reason

    def test_url_empty_passes(self) -> None:
        ok, _ = _check_url("")
        assert ok


class TestFieldTypeValidationDate:
    def test_date_iso_format(self) -> None:
        ok, _ = _check_date("2024-01-15")
        assert ok

    def test_date_iso_datetime(self) -> None:
        ok, _ = _check_date("2024-01-15T10:30:00")
        assert ok

    def test_date_us_format(self) -> None:
        ok, _ = _check_date("01/15/2024")
        assert ok

    def test_date_eu_format(self) -> None:
        ok, _ = _check_date("15/01/2024")
        assert ok

    def test_date_textual_month(self) -> None:
        ok, _ = _check_date("January 15, 2024")
        assert ok

    def test_date_day_month_year(self) -> None:
        ok, _ = _check_date("15 Jan 2024")
        assert ok

    def test_date_rejects_garbage(self) -> None:
        ok, reason = _check_date("not-a-date")
        assert not ok
        assert reason is not None and "unparseable" in reason

    def test_date_empty_passes(self) -> None:
        ok, _ = _check_date("")
        assert ok


class TestFieldTypeValidationBoolean:
    def test_boolean_true(self) -> None:
        ok, _ = _check_boolean(True)
        assert ok

    def test_boolean_false(self) -> None:
        ok, _ = _check_boolean(False)
        assert ok

    def test_boolean_rejects_string(self) -> None:
        ok, reason = _check_boolean("true")
        assert not ok
        assert reason is not None and "expected boolean" in reason

    def test_boolean_rejects_int(self) -> None:
        ok, reason = _check_boolean(1)
        assert not ok
        assert reason is not None and "expected boolean" in reason


class TestValidateFieldTypes:
    def test_validate_field_types_returns_mismatches(self) -> None:
        fields = [
            _field("price", FieldType.CURRENCY),
            _field("email", FieldType.EMAIL),
        ]
        record = {"price": "not_a_number", "email": "bad-email"}
        mismatches = validate_field_types(record, fields)
        assert len(mismatches) == 2

    def test_mismatch_has_all_fields(self) -> None:
        fields = [_field("price", FieldType.CURRENCY)]
        record = {"price": "xyz"}
        mismatches = validate_field_types(record, fields)
        assert len(mismatches) == 1
        m = mismatches[0]
        assert isinstance(m, FieldTypeMismatch)
        assert m.field == "price"
        assert m.declared_type == "currency"
        assert m.actual_value == "xyz"
        assert m.expected == "numeric value"
        assert m.error  # non-empty reason

    def test_empty_value_not_flagged(self) -> None:
        fields = [_field("price", FieldType.CURRENCY)]
        records: list[dict[str, Any]] = [{"price": None}, {"price": ""}, {}]
        for record in records:
            mismatches = validate_field_types(record, fields)
            assert len(mismatches) == 0

    def test_is_record_type_valid_true(self) -> None:
        fields = [_field("price", FieldType.CURRENCY)]
        record = {"price": 9.99}
        assert is_record_type_valid(record, fields) is True

    def test_is_record_type_valid_false(self) -> None:
        fields = [_field("price", FieldType.CURRENCY)]
        record = {"price": "not_a_number"}
        assert is_record_type_valid(record, fields) is False

    def test_string_field_not_type_checked(self) -> None:
        # STRING fields should never appear in TYPE_CHECKERS
        assert FieldType.STRING not in TYPE_CHECKERS
        fields = [_field("name", FieldType.STRING)]
        record = {"name": 12345}
        mismatches = validate_field_types(record, fields)
        assert len(mismatches) == 0  # no type check for STRING

    def test_mismatch_json_serializable(self) -> None:
        fields = [_field("price", FieldType.CURRENCY)]
        record = {"price": "abc"}
        mismatches = validate_field_types(record, fields)
        m = mismatches[0]
        # The dataclass should be convertible to dict for API serialization
        import dataclasses

        d = dataclasses.asdict(m)
        assert isinstance(d, dict)
        assert "field" in d
        assert "error" in d

    def test_multiple_field_types_validated(self) -> None:
        fields = [
            _field("name", FieldType.STRING),
            _field("price", FieldType.NUMBER),
            _field("email", FieldType.EMAIL),
            _field("url", FieldType.URL),
            _field("date", FieldType.DATE),
            _field("active", FieldType.BOOLEAN),
        ]
        record = {
            "name": "Widget",
            "price": 42,
            "email": "user@example.com",
            "url": "https://example.com",
            "date": "2024-01-15",
            "active": True,
        }
        mismatches = validate_field_types(record, fields)
        assert len(mismatches) == 0

    def test_multiple_field_types_with_mismatches(self) -> None:
        fields = [
            _field("price", FieldType.NUMBER),
            _field("email", FieldType.EMAIL),
            _field("date", FieldType.DATE),
        ]
        record = {"price": "xyz", "email": "nope", "date": "????"}
        mismatches = validate_field_types(record, fields)
        assert len(mismatches) == 3
