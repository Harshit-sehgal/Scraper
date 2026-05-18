"""
LLM Output Validator — structured output validation for LLM responses.

Ensures LLM JSON outputs conform to expected schemas with automatic
retries on malformed or type-mismatched responses.

Reduces the risk of:
  - Hallucinated keys
  - Wrong types (string instead of number, etc.)
  - Missing required fields
  - Nested structure violations
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ─── Schema Validation Helpers ──────────────────────────────────────────

def validate_llm_json(
    raw: Any,
    expected_type: type = dict,
    required_keys: Optional[list[str]] = None,
    key_types: Optional[dict[str, type]] = None,
    list_item_type: Optional[type] = None,
    allow_extra_keys: bool = True,
) -> tuple[bool, str | None]:
    """Validate that an LLM JSON response matches expected structure.

    Args:
        raw: The parsed JSON value.
        expected_type: Expected top-level type (dict or list).
        required_keys: Keys that must be present (for dict responses).
        key_types: Dict of {key: expected_type} for field-level validation.
        list_item_type: If expecting a list, the type each item must be.
        allow_extra_keys: Whether extra keys beyond required_keys are OK.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if raw is None:
        return False, "Response is None"

    if not isinstance(raw, expected_type):
        return False, (
            f"Expected type {expected_type.__name__}, "
            f"got {type(raw).__name__}: {str(raw)[:200]}"
        )

    if expected_type is dict and isinstance(raw, dict):
        if required_keys:
            missing = [k for k in required_keys if k not in raw]
            if missing:
                return False, f"Missing required keys: {missing}"

            if not allow_extra_keys:
                extra = [k for k in raw if required_keys and k not in required_keys]
                if extra:
                    return False, f"Unexpected extra keys: {extra}"

        if key_types:
            for key, expected in key_types.items():
                if key in raw and raw[key] is not None:
                    if not isinstance(raw[key], expected):
                        return False, (
                            f"Key '{key}' expected type {expected.__name__}, "
                            f"got {type(raw[key]).__name__}: {str(raw[key])[:100]}"
                        )

    if expected_type is list and isinstance(raw, list):
        if list_item_type and raw:
            for i, item in enumerate(raw):
                if not isinstance(item, list_item_type):
                    return False, (
                        f"List item {i} expected type {list_item_type.__name__}, "
                        f"got {type(item).__name__}: {str(item)[:100]}"
                    )

    return True, None


def validate_llm_record_list(
    raw: Any,
    required_record_keys: Optional[list[str]] = None,
    record_key_types: Optional[dict[str, type]] = None,
) -> tuple[bool, str | None]:
    """Validate an LLM response that should be a list of dict records.

    Common pattern for scraper cleaning and structuring results.
    """
    is_valid, error = validate_llm_json(
        raw,
        expected_type=list,
        list_item_type=dict,
    )
    if not is_valid:
        return False, error

    record_list: list[dict] = raw
    if required_record_keys:
        for i, record in enumerate(record_list):
            rec_valid, rec_error = validate_llm_json(
                record,
                expected_type=dict,
                required_keys=required_record_keys,
                key_types=record_key_types,
            )
            if not rec_valid:
                return False, f"Record {i}: {rec_error}"

    return True, None


# ─── Retry Wrappers ─────────────────────────────────────────────────────

def llm_call_with_validation(
    call_fn: Callable[[], Any],
    validator: Callable[[Any], tuple[bool, str | None]],
    max_retries: int = 2,
) -> Any:
    """Call an LLM function and validate its output, retrying on failure.

    The call_fn is expected to return parsed JSON data synchronously.
    Retries append a correction hint to the function's internal logic
    (e.g. by calling an LLM again).

    Args:
        call_fn: Callable that returns parsed JSON.
        validator: Function that takes parsed output and returns (valid, error).
        max_retries: How many times to retry after schema mismatch.

    Returns:
        Validated LLM output, or None if all retries exhausted.
    """
    if not settings.LLM_VALIDATE_JSON:
        return call_fn()

    effective_retries = max(max_retries, settings.LLM_VALIDATION_MAX_RETRIES)

    for attempt in range(effective_retries + 1):
        try:
            result = call_fn()
            if result is not None:
                is_valid, error = validator(result)
                if is_valid:
                    return result
                logger.warning(
                    "LLM output validation failed (attempt %d/%d): %s",
                    attempt + 1, effective_retries + 1, error,
                )
        except Exception as e:
            logger.warning(
                "LLM call failed (attempt %d/%d): %s",
                attempt + 1, effective_retries + 1, e,
            )

        if attempt < effective_retries:
            # The call_fn should handle its own retry logic internally.
            # We just re-invoke it for another attempt.
            pass

    logger.error("LLM output validation failed after %d attempts", effective_retries + 1)
    return None


async def llm_call_with_validation_async(
    call_fn: Callable[[], Any],
    validator: Callable[[Any], tuple[bool, str | None]],
    run_in_thread_fn: Optional[Callable] = None,
    max_retries: int = 2,
) -> Any:
    """Async version of llm_call_with_validation.

    Runs call_fn via run_in_thread_fn if provided (to avoid blocking the event loop).
    """
    if not settings.LLM_VALIDATE_JSON:
        if run_in_thread_fn:
            return await run_in_thread_fn(call_fn)
        return call_fn()

    effective_retries = max(max_retries, settings.LLM_VALIDATION_MAX_RETRIES)

    for attempt in range(effective_retries + 1):
        try:
            if run_in_thread_fn:
                result = await run_in_thread_fn(call_fn)
            else:
                result = call_fn()

            if result is not None:
                is_valid, error = validator(result)
                if is_valid:
                    return result
                logger.warning(
                    "LLM output validation failed (attempt %d/%d): %s",
                    attempt + 1, effective_retries + 1, error,
                )
        except Exception as e:
            logger.warning(
                "LLM call failed (attempt %d/%d): %s",
                attempt + 1, effective_retries + 1, e,
            )

    logger.error("LLM output validation failed after %d attempts", effective_retries + 1)
    return None


# ─── Specific Validators ────────────────────────────────────────────────

def validate_selector_response(raw: Any) -> tuple[bool, str | None]:
    """Validate an LLM selector generation response."""
    is_valid, error = validate_llm_json(raw, expected_type=dict)
    if not is_valid:
        return False, error

    d: dict = raw

    if "item_container" not in d:
        return False, "Missing required key 'item_container'"

    if not isinstance(d["item_container"], str):
        return False, f"'item_container' must be a string, got {type(d['item_container']).__name__}"

    if "fields" in d and d["fields"] is not None:
        fields = d["fields"]
        if not isinstance(fields, dict):
            return False, f"'fields' must be a dict, got {type(fields).__name__}"
        for field_name, selector in fields.items():
            if not isinstance(selector, str):
                return False, f"Field '{field_name}' selector must be a string, got {type(selector).__name__}"

    return True, None


def validate_insight_response(raw: Any) -> tuple[bool, str | None]:
    """Validate an LLM insight generation response (string or dict with insight key)."""
    if isinstance(raw, str):
        return True, None
    if isinstance(raw, dict):
        is_valid, error = validate_llm_json(
            raw,
            expected_type=dict,
            required_keys=["insight"],
            key_types={"insight": str},
        )
        return is_valid, error
    return False, f"Expected string or dict, got {type(raw).__name__}"
