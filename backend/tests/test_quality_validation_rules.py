"""Qual 18: Automated validation rules engine — test custom validation rules DSL."""
from __future__ import annotations

import re
from typing import Any


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
        rs = ValidationRuleSet([
            ValidationRule("title", "required", None),
            ValidationRule("price", "min", 0),
        ])
        result = rs.validate({"title": "Widget", "price": 25})
        assert result["valid"] is True
        assert result["errors"] == []

    def test_some_rules_fail(self) -> None:
        rs = ValidationRuleSet([
            ValidationRule("title", "required", None),
            ValidationRule("price", "min", 10),
        ])
        result = rs.validate({"title": "", "price": 5})
        assert result["valid"] is False
        assert len(result["errors"]) == 2

    def test_empty_ruleset(self) -> None:
        rs = ValidationRuleSet()
        result = rs.validate({"x": 1})
        assert result["valid"] is True

    def test_validate_all_records(self) -> None:
        rs = ValidationRuleSet([
            ValidationRule("title", "required", None),
        ])
        results = rs.validate_all([
            {"title": "A"},
            {"title": ""},
            {"title": "B"},
        ])
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
