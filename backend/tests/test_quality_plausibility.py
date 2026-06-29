"""Qual 16: Value plausibility checks — test per-field validation rules."""
from __future__ import annotations

import re
from typing import Any


def _check_plausibility(value: Any, field_name: str, rules: dict[str, Any] | None = None) -> tuple[bool, str]:
    """Check if a field value passes plausibility rules.
    
    Returns (is_plausible, reason_if_not).
    """
    if value is None or value == "":
        return True, ""

    text = str(value)
    name_lower = field_name.lower()

    if rules:
        if "min" in rules and isinstance(value, (int, float)):
            if value < rules["min"]:
                return False, f"Value {value} below minimum {rules['min']}"
        if "max" in rules and isinstance(value, (int, float)):
            if value > rules["max"]:
                return False, f"Value {value} above maximum {rules['max']}"
        if "regex" in rules and isinstance(value, str):
            if not re.match(rules["regex"], value):
                return False, f"Value '{value}' does not match pattern {rules['regex']}"
        if rules.get("not_future"):
            import datetime
            try:
                import dateutil.parser
                dt = dateutil.parser.parse(text)
                if dt > datetime.datetime.now(datetime.UTC):
                    return False, "Date is in the future"
            except (ImportError, ValueError, TypeError):
                pass
        return True, ""

    if "email" in name_lower and "@" not in text:
        return False, "Email must contain @"
    if "price" in name_lower or "amount" in name_lower:
        try:
            cleaned = re.sub(r"[$€£¥,]", "", text)
            val = float(cleaned)
            if val <= 0:
                return False, f"Price must be positive, got {val}"
            if val > 1_000_000:
                return False, f"Price {val} exceeds maximum $1,000,000"
        except (ValueError, TypeError):
            return False, f"Price '{value}' is not a valid number"
    if "rating" in name_lower or "score" in name_lower:
        try:
            val = float(text)
            if val < 0 or val > 10:
                return False, f"Rating/score must be between 0-10, got {val}"
        except (ValueError, TypeError):
            return False, f"Rating '{value}' is not a valid number"
    if "year" in name_lower:
        try:
            val = int(text)
            if val < 1900 or val > 2100:
                return False, f"Year must be between 1900-2100, got {val}"
        except (ValueError, TypeError):
            return False, f"Year '{value}' is not a valid integer"
    if "phone" in name_lower:
        digits = re.sub(r"\D", "", text)
        if len(digits) < 7 or len(digits) > 15:
            return False, f"Phone has {len(digits)} digits (expected 7-15)"
    return True, ""


class TestPlausibilityPrices:
    def test_valid_price_passes(self) -> None:
        assert _check_plausibility("$25.99", "price")[0] is True

    def test_zero_price_fails(self) -> None:
        is_ok, reason = _check_plausibility("$0", "price")
        assert is_ok is False
        assert "positive" in reason.lower()

    def test_negative_price_fails(self) -> None:
        is_ok, _ = _check_plausibility("-$5", "price")
        assert is_ok is False

    def test_extremely_high_price_fails(self) -> None:
        is_ok, _ = _check_plausibility("$9,999,999", "price")
        assert is_ok is False

    def test_non_numeric_price_fails(self) -> None:
        is_ok, _ = _check_plausibility("free", "price")
        assert is_ok is False

    def test_amount_field_also_checked(self) -> None:
        assert _check_plausibility("100", "total_amount")[0] is True
        assert _check_plausibility("-1", "total_amount")[0] is False


class TestPlausibilityRatings:
    def test_valid_rating_passes(self) -> None:
        assert _check_plausibility("7.5", "rating")[0] is True
        assert _check_plausibility("10", "rating")[0] is True

    def test_rating_above_max_fails(self) -> None:
        is_ok, _ = _check_plausibility("11", "rating")
        assert is_ok is False

    def test_rating_below_zero_fails(self) -> None:
        is_ok, _ = _check_plausibility("-1", "rating")
        assert is_ok is False

    def test_score_field_also_checked(self) -> None:
        assert _check_plausibility("8", "score")[0] is True
        assert _check_plausibility("100", "score")[0] is False


class TestPlausibilityYears:
    def test_valid_year_passes(self) -> None:
        assert _check_plausibility("2024", "year")[0] is True

    def test_year_too_old_fails(self) -> None:
        is_ok, _ = _check_plausibility("1800", "year")
        assert is_ok is False

    def test_year_too_future_fails(self) -> None:
        is_ok, _ = _check_plausibility("2200", "year")
        assert is_ok is False

    def test_non_integer_year_fails(self) -> None:
        is_ok, _ = _check_plausibility("last year", "year")
        assert is_ok is False


class TestPlausibilityEmail:
    def test_email_with_at_passes(self) -> None:
        assert _check_plausibility("user@example.com", "email")[0] is True

    def test_email_without_at_fails(self) -> None:
        is_ok, _ = _check_plausibility("userexample.com", "email")
        assert is_ok is False


class TestPlausibilityPhone:
    def test_valid_phone_passes(self) -> None:
        assert _check_plausibility("+1-555-123-4567", "phone")[0] is True

    def test_phone_too_short_fails(self) -> None:
        is_ok, _ = _check_plausibility("123", "phone")
        assert is_ok is False

    def test_empty_phone_passes(self) -> None:
        assert _check_plausibility(None, "phone")[0] is True


class TestPlausibilityCustomRules:
    def test_min_rule(self) -> None:
        is_ok, _ = _check_plausibility(5, "age", rules={"min": 0})
        assert is_ok is True
        is_ok, _ = _check_plausibility(-1, "age", rules={"min": 0})
        assert is_ok is False

    def test_max_rule(self) -> None:
        is_ok, _ = _check_plausibility(50, "quantity", rules={"max": 100})
        assert is_ok is True
        is_ok, _ = _check_plausibility(200, "quantity", rules={"max": 100})
        assert is_ok is False

    def test_regex_rule(self) -> None:
        is_ok, _ = _check_plausibility("ABC", "code", rules={"regex": r"^[A-Z]{3}$"})
        assert is_ok is True
        is_ok, _ = _check_plausibility("abcd", "code", rules={"regex": r"^[A-Z]{3}$"})
        assert is_ok is False

    def test_unknown_field_no_error(self) -> None:
        assert _check_plausibility("anything", "custom_field")[0] is True
