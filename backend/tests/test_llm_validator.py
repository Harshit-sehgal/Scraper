"""Unit Tests for LLM Output Validator.

Tests schema validation, retry wrappers, and specific validators
used to ensure LLM JSON responses conform to expected structures.
"""

from __future__ import annotations

import pytest

from app.llm_validator import (
    validate_llm_json,
    validate_llm_record_list,
    llm_call_with_validation,
    validate_selector_response,
    validate_insight_response,
)


# ─── validate_llm_json ──────────────────────────────────────────────


class TestValidateLlmJson:
    def test_none_returns_false(self):
        is_valid, error = validate_llm_json(None)
        assert is_valid is False
        assert "None" in (error or "")

    def test_wrong_type_returns_false(self):
        is_valid, error = validate_llm_json("not a dict", expected_type=dict)
        assert is_valid is False
        assert "Expected type dict" in (error or "")

    def test_valid_dict_returns_true(self):
        is_valid, error = validate_llm_json({"key": "value"})
        assert is_valid is True
        assert error is None

    def test_missing_required_keys(self):
        is_valid, error = validate_llm_json(
            {"name": "test"},
            required_keys=["name", "price"],
        )
        assert is_valid is False
        assert "Missing required keys" in (error or "")
        assert "price" in (error or "")

    def test_all_required_keys_present(self):
        is_valid, error = validate_llm_json(
            {"name": "test", "price": 100},
            required_keys=["name", "price"],
        )
        assert is_valid is True

    def test_extra_keys_not_allowed(self):
        is_valid, error = validate_llm_json(
            {"name": "test", "extra": "bad"},
            required_keys=["name"],
            allow_extra_keys=False,
        )
        assert is_valid is False
        assert "Unexpected extra keys" in (error or "")

    def test_key_types_match(self):
        is_valid, error = validate_llm_json(
            {"name": "test", "count": 5},
            key_types={"name": str, "count": int},
        )
        assert is_valid is True

    def test_key_types_mismatch(self):
        is_valid, error = validate_llm_json(
            {"name": "test", "count": "five"},
            key_types={"count": int},
        )
        assert is_valid is False
        assert "expected type int" in (error or "")

    def test_key_type_none_is_skipped(self):
        """None values should not trigger key type mismatch."""
        is_valid, error = validate_llm_json(
            {"name": None},
            key_types={"name": str},
        )
        assert is_valid is True

    def test_list_type_validation(self):
        is_valid, error = validate_llm_json(
            [1, 2, 3],
            expected_type=list,
            list_item_type=int,
        )
        assert is_valid is True

    def test_list_item_type_mismatch(self):
        is_valid, error = validate_llm_json(
            [1, "two", 3],
            expected_type=list,
            list_item_type=int,
        )
        assert is_valid is False
        assert "List item 1" in (error or "")

    def test_list_with_dict_items(self):
        is_valid, error = validate_llm_json(
            [{"a": 1}, {"b": 2}],
            expected_type=list,
            list_item_type=dict,
        )
        assert is_valid is True


# ─── validate_llm_record_list ───────────────────────────────────────


class TestValidateLlmRecordList:
    def test_valid_record_list(self):
        data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        is_valid, error = validate_llm_record_list(data)
        assert is_valid is True

    def test_not_a_list(self):
        is_valid, error = validate_llm_record_list({"name": "test"})
        assert is_valid is False

    def test_list_of_non_dicts(self):
        is_valid, error = validate_llm_record_list(["a", "b"])
        assert is_valid is False

    def test_required_keys_in_records(self):
        data = [{"name": "Alice", "price": 100}, {"name": "Bob"}]
        is_valid, error = validate_llm_record_list(
            data,
            required_record_keys=["name", "price"],
        )
        assert is_valid is False
        assert "Record 1" in (error or "")

    def test_key_types_in_records(self):
        data = [{"name": "Alice", "price": "free"}]
        is_valid, error = validate_llm_record_list(
            data,
            record_key_types={"price": (int, float)},
        )
        assert is_valid is True  # isinstance supports tuple-of-types natively

    def test_all_records_pass(self):
        data = [{"name": "Alice"}, {"name": "Bob"}]
        is_valid, error = validate_llm_record_list(
            data,
            required_record_keys=["name"],
            record_key_types={"name": str},
        )
        assert is_valid is True


# ─── llm_call_with_validation ───────────────────────────────────────


class TestLlmCallWithValidation:
    def test_valid_call_returns_result(self):
        result = llm_call_with_validation(
            call_fn=lambda: {"name": "test"},
            validator=lambda x: (True, None),
            max_retries=1,
        )
        assert result == {"name": "test"}

    def test_invalid_call_retries(self):
        call_count = 0

        def call_fn():
            nonlocal call_count
            call_count += 1
            return {"status": "ok"}

        def validator(x):
            return (False, "bad data") if call_count < 2 else (True, None)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.llm_validator.settings.LLM_VALIDATE_JSON", True)
            mp.setattr("app.llm_validator.settings.LLM_VALIDATION_MAX_RETRIES", 3)
            result = llm_call_with_validation(call_fn, validator, max_retries=3)

        assert result == {"status": "ok"}
        assert call_count == 2

    def test_all_retries_exhausted_returns_none(self):
        def call_fn():
            return {"bad": "data"}

        def validator(x):
            return (False, "always fails")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.llm_validator.settings.LLM_VALIDATE_JSON", True)
            mp.setattr("app.llm_validator.settings.LLM_VALIDATION_MAX_RETRIES", 1)
            result = llm_call_with_validation(call_fn, validator, max_retries=1)

        assert result is None

    def test_disabled_validation_passes_through(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.llm_validator.settings.LLM_VALIDATE_JSON", False)
            result = llm_call_with_validation(
                call_fn=lambda: {"raw": True},
                validator=lambda x: (False, "would reject"),
                max_retries=2,
            )
        assert result == {"raw": True}

    def test_call_fn_exception_triggers_retry(self):
        call_count = 0

        def call_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("transient error")
            return {"ok": True}

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.llm_validator.settings.LLM_VALIDATE_JSON", True)
            mp.setattr("app.llm_validator.settings.LLM_VALIDATION_MAX_RETRIES", 3)
            result = llm_call_with_validation(
                call_fn,
                validator=lambda x: (True, None),
                max_retries=3,
            )

        assert result == {"ok": True}
        assert call_count == 2

    def test_none_result_retries(self):
        call_count = 0

        def call_fn():
            nonlocal call_count
            call_count += 1
            return None if call_count < 2 else {"data": "ok"}

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.llm_validator.settings.LLM_VALIDATE_JSON", True)
            mp.setattr("app.llm_validator.settings.LLM_VALIDATION_MAX_RETRIES", 3)
            result = llm_call_with_validation(
                call_fn,
                validator=lambda x: (isinstance(x, dict), None),
                max_retries=3,
            )

        assert result == {"data": "ok"}
        assert call_count == 2


# ─── validate_selector_response ─────────────────────────────────────


class TestValidateSelectorResponse:
    def test_valid_selector_response(self):
        raw = {
            "item_container": "div.product",
            "fields": {
                "name": "h2.title",
                "price": "span.price",
            },
        }
        is_valid, error = validate_selector_response(raw)
        assert is_valid is True

    def test_missing_item_container(self):
        is_valid, error = validate_selector_response({"fields": {}})
        assert is_valid is False
        assert "item_container" in (error or "")

    def test_non_string_item_container(self):
        is_valid, error = validate_selector_response({
            "item_container": 42,
            "fields": {},
        })
        assert is_valid is False
        assert "must be a string" in (error or "")

    def test_non_dict_fields(self):
        is_valid, error = validate_selector_response({
            "item_container": "div",
            "fields": "not a dict",
        })
        assert is_valid is False

    def test_non_string_field_selector(self):
        is_valid, error = validate_selector_response({
            "item_container": "div",
            "fields": {"name": 123},
        })
        assert is_valid is False
        assert "must be a string" in (error or "")

    def test_missing_fields_is_ok(self):
        is_valid, error = validate_selector_response({"item_container": "div"})
        assert is_valid is True


# ─── validate_insight_response ──────────────────────────────────────


class TestValidateInsightResponse:
    def test_string_is_valid(self):
        is_valid, error = validate_insight_response("This is an insight")
        assert is_valid is True

    def test_dict_with_insight_key(self):
        is_valid, error = validate_insight_response({"insight": "key finding"})
        assert is_valid is True

    def test_dict_missing_insight_key(self):
        is_valid, error = validate_insight_response({"data": "value"})
        assert is_valid is False

    def test_dict_with_non_string_insight(self):
        is_valid, error = validate_insight_response({"insight": 42})
        assert is_valid is False

    def test_number_is_invalid(self):
        is_valid, error = validate_insight_response(42)
        assert is_valid is False
        assert "Expected string or dict" in (error or "")
