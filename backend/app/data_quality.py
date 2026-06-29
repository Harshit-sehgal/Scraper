"""Data Quality Pipeline — cleaning, validation, deduplication, scoring.

Provides a deterministic pipeline for improving extracted data quality:
  1. Clean (normalize values based on field type)
  2. Validate (check schema compliance)
  3. Deduplicate (remove exact duplicates)
  4. Score (compute quality score per record and overall)
"""

from __future__ import annotations

import json
import math
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any

from app.models import FieldType, SchemaField

# ---------------------------------------------------------------------------
# Cleaning rules
# ---------------------------------------------------------------------------


def _clean_text(value: str) -> str:
    """Trim and normalize whitespace."""
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    return " ".join(value.split())


def _clean_price(value: str) -> str | float:
    """Remove currency symbols and convert to float."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return value
    # Remove currency symbols and whitespace
    cleaned = re.sub(r"[$€£¥]", "", value).strip()
    cleaned = cleaned.replace(",", "")  # Remove thousand separators
    try:
        return float(cleaned)
    except ValueError:
        return value


def _clean_date(value: str) -> str:
    """Normalize common date formats."""
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    # Basic normalization: strip and standardize
    return value.strip()


def _clean_url(value: str) -> str:
    """Normalize URL: ensure absolute, remove tracking params."""
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    url = value.strip()
    if not url:
        return url
    # Remove common tracking params
    tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qsl(parsed.query)
        filtered = [(k, v) for k, v in query if k not in tracking_params]
        new_query = urllib.parse.urlencode(filtered)
        return urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment),
        )
    except (ValueError, UnicodeDecodeError):
        return url


def _clean_email(value: str) -> str:
    """Normalize email: lowercase and strip."""
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    return value.strip().lower()


def _clean_phone(value: str) -> str:
    """Normalize phone: extract digits and standard format."""
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    return re.sub(r"\D", "", value)


def _clean_number(value: str) -> int | float | str:
    """Convert to number."""
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return value
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _clean_boolean(value: Any) -> bool | Any:
    """Convert to boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "on")
    return bool(value) if value is not None else False


CLEANERS = {
    FieldType.STRING: _clean_text,
    FieldType.INTEGER: _clean_number,
    FieldType.FLOAT: _clean_number,
    FieldType.BOOLEAN: _clean_boolean,
    FieldType.EMAIL: _clean_email,
    FieldType.URL: _clean_url,
    FieldType.PHONE: _clean_phone,
    FieldType.DATE: _clean_date,
    FieldType.LOCATION: _clean_text,
    FieldType.CURRENCY: _clean_price,
    FieldType.PERCENTAGE: _clean_number,
    FieldType.LIST_STRING: _clean_text,
    FieldType.CODE: _clean_text,
    FieldType.RATING: _clean_number,
    FieldType.NUMBER: _clean_number,
}


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------


def _validate_text(value: str, field: SchemaField) -> tuple[bool, str]:
    if not isinstance(value, str):
        return False, f"Expected string, got {type(value).__name__}"
    if field.required and not value.strip():
        return False, "Required field is empty"
    return True, ""


def _validate_email(value: str, _field: SchemaField) -> tuple[bool, str]:
    if not isinstance(value, str) or not value.strip():
        if _field.required:
            return False, "Required email field is empty"
        return True, ""
    if "@" not in value:
        return False, "Invalid email format (missing @)"
    return True, ""


def _validate_url(value: str, _field: SchemaField) -> tuple[bool, str]:
    if not isinstance(value, str) or not value.strip():
        if _field.required:
            return False, "Required URL field is empty"
        return True, ""
    if not value.startswith(("http://", "https://")):
        return False, "Invalid URL format"
    return True, ""


def _validate_number(value: Any, _field: SchemaField) -> tuple[bool, str]:
    if isinstance(value, bool):
        return False, "Expected number, got boolean"
    if not isinstance(value, (int, float)):
        return False, f"Expected number, got {type(value).__name__}"
    return True, ""


def _validate_phone(value: str, _field: SchemaField) -> tuple[bool, str]:
    if not isinstance(value, str) or not value.strip():
        if _field.required:
            return False, "Required phone field is empty"
        return True, ""
    digits = re.sub(r"\D", "", value)
    if len(digits) < 7 or len(digits) > 15:
        return False, f"Phone number has {len(digits)} digits (expected 7-15)"
    return True, ""


VALIDATORS = {
    FieldType.STRING: _validate_text,
    FieldType.INTEGER: _validate_number,
    FieldType.FLOAT: _validate_number,
    FieldType.BOOLEAN: lambda _v, _f: (True, ""),
    FieldType.EMAIL: _validate_email,
    FieldType.URL: _validate_url,
    FieldType.PHONE: _validate_phone,
    FieldType.DATE: _validate_text,
    FieldType.LOCATION: _validate_text,
    FieldType.CURRENCY: _validate_number,
    FieldType.PERCENTAGE: _validate_number,
    FieldType.LIST_STRING: _validate_text,
    FieldType.CODE: _validate_text,
    FieldType.RATING: _validate_number,
    FieldType.NUMBER: _validate_number,
}


# ---------------------------------------------------------------------------
# Field-level type validation (Roadmap Wave 7, Item 2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldTypeMismatch:
    """Single field-level type violation with diagnostic detail."""

    field: str  # SchemaField.name
    declared_type: str  # FieldType.value string
    actual_value: Any  # The raw value as it arrived (pre-cleaning)
    expected: str  # Human description, e.g. "numeric value"
    error: str  # Short reason, e.g. "invalid email format"


def _check_numeric(value: Any) -> tuple[bool, str | None]:
    """Return (True, None) if *value* is numeric; (False, reason) otherwise."""
    # bool subclasses int — reject it explicitly
    if isinstance(value, bool):
        return False, "expected numeric value, got boolean"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return False, "numeric value is not finite (inf/nan)"
        return True, None
    if isinstance(value, str):
        cleaned = re.sub(r"[$€£¥₹%,]", "", value.strip()).replace(",", "")
        try:
            float(cleaned)
            return True, None
        except ValueError:
            return False, f"string '{value}' is not a valid number"
    return False, f"expected numeric value, got {type(value).__name__}"


def _check_email(value: Any) -> tuple[bool, str | None]:
    """Return (True, None) if *value* is a valid email; (False, reason) otherwise."""
    if not isinstance(value, str):
        return False, f"expected string, got {type(value).__name__}"
    if not value.strip():
        return True, None  # emptiness handled by completeness, not type check
    # Practical RFC 5322 subset (matches existing pattern in quality._value_quality)
    if re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", value.strip()):
        return True, None
    return False, "invalid email format"


def _check_url(value: Any) -> tuple[bool, str | None]:
    """Return (True, None) if *value* is a valid URL; (False, reason) otherwise."""
    if not isinstance(value, str):
        return False, f"expected string, got {type(value).__name__}"
    if not value.strip():
        return True, None  # emptiness handled by completeness
    try:
        parsed = urllib.parse.urlparse(value.strip())
    except (ValueError, UnicodeDecodeError):
        return False, "invalid URL format"
    if parsed.scheme.lower() == "javascript":
        return False, "javascript: URI scheme is not a valid URL"
    if parsed.scheme not in ("http", "https"):
        return False, "invalid URL scheme (expected http or https)"
    if not parsed.netloc:
        return False, "URL is missing network location (host)"
    return True, None


def _check_date(value: Any) -> tuple[bool, str | None]:
    """Return (True, None) if *value* is a parseable date; (False, reason) otherwise."""
    if not isinstance(value, str):
        return False, f"expected string, got {type(value).__name__}"
    if not value.strip():
        return True, None  # emptiness handled by completeness
    import datetime as _dt

    text = value.strip()
    # Try ISO 8601 first
    try:
        _dt.date.fromisoformat(text[:10])
        return True, None
    except (ValueError, IndexError):
        pass
    try:
        _dt.datetime.fromisoformat(text)
        return True, None
    except (ValueError, IndexError):
        pass
    # Common formats: YYYY-M[M]-D[D], D[D]/M[M]/YYYY, month name forms
    if re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", text):
        return True, None
    if re.search(r"\d{1,2}[-/]\d{1,2}[-/]\d{4}", text):
        return True, None
    if re.search(
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}",
        text,
        re.IGNORECASE,
    ):
        return True, None
    if re.search(
        r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}",
        text,
        re.IGNORECASE,
    ):
        return True, None
    return False, "unparseable date"


def _check_boolean(value: Any) -> tuple[bool, str | None]:
    """Return (True, None) if *value* is a boolean; (False, reason) otherwise."""
    if isinstance(value, bool):
        return True, None
    return False, f"expected boolean, got {type(value).__name__}"


# Registry mapping FieldType to type-checker functions.
# Absent keys are "not type-checkable" and are omitted from conformance ratios.
TYPE_CHECKERS: dict[FieldType, Any] = {
    FieldType.INTEGER: _check_numeric,
    FieldType.FLOAT: _check_numeric,
    FieldType.NUMBER: _check_numeric,
    FieldType.CURRENCY: _check_numeric,
    FieldType.PERCENTAGE: _check_numeric,
    FieldType.RATING: _check_numeric,
    FieldType.EMAIL: _check_email,
    FieldType.URL: _check_url,
    FieldType.DATE: _check_date,
    FieldType.BOOLEAN: _check_boolean,
}


def validate_field_types(
    record: dict,
    schema_fields: list[SchemaField],
) -> list[FieldTypeMismatch]:
    """Validate every non-empty value against its declared FieldType.

    Returns a (possibly empty) list of mismatches.  Empty / missing values
    are *not* flagged — emptiness is captured by the completeness score.
    """
    mismatches: list[FieldTypeMismatch] = []
    for field in schema_fields:
        checker = TYPE_CHECKERS.get(field.field_type)
        if checker is None:
            continue  # not type-checkable (STRING, CODE, etc.)
        value = record.get(field.name)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue  # emptiness is a completeness issue, not a type issue
        ok, reason = checker(value)
        if not ok:
            expected = {
                FieldType.INTEGER: "numeric value",
                FieldType.FLOAT: "numeric value",
                FieldType.NUMBER: "numeric value",
                FieldType.CURRENCY: "numeric value",
                FieldType.PERCENTAGE: "numeric value",
                FieldType.RATING: "numeric value",
                FieldType.EMAIL: "RFC 5322 email address",
                FieldType.URL: "http(s) URL",
                FieldType.DATE: "parseable date",
                FieldType.BOOLEAN: "boolean value",
            }.get(field.field_type, "valid value")
            mismatches.append(
                FieldTypeMismatch(
                    field=field.name,
                    declared_type=field.field_type.value,
                    actual_value=value,
                    expected=expected,
                    error=reason or "type mismatch",
                )
            )
    return mismatches


def is_record_type_valid(record: dict, schema_fields: list[SchemaField]) -> bool:
    """True iff no type mismatches found in *record*."""
    return len(validate_field_types(record, schema_fields)) == 0


# ---------------------------------------------------------------------------
# Quality Score
# ---------------------------------------------------------------------------


def _field_score(value: Any, field_type: FieldType) -> float:
    """Return a quality score for a single field (0.0 to 1.0)."""
    if value is None or value == "":
        return 0.0
    if field_type in (FieldType.STRING, FieldType.LIST_STRING, FieldType.CODE):
        text = str(value)
        if len(text) < 3:
            return 0.3
        if len(text) < 10:
            return 0.6
        return 1.0
    if field_type in (
        FieldType.INTEGER,
        FieldType.FLOAT,
        FieldType.NUMBER,
        FieldType.CURRENCY,
        FieldType.PERCENTAGE,
        FieldType.RATING,
    ):
        return 1.0 if isinstance(value, (int, float)) else 0.3
    if field_type == FieldType.BOOLEAN:
        return 1.0 if isinstance(value, bool) else 0.5
    if field_type == FieldType.EMAIL:
        text = str(value)
        return 1.0 if "@" in text and "." in text.split("@")[-1] else 0.3
    if field_type == FieldType.URL:
        text = str(value)
        return 1.0 if text.startswith(("http://", "https://")) else 0.3
    if field_type == FieldType.PHONE:
        digits = re.sub(r"\D", "", str(value))
        return 1.0 if 7 <= len(digits) <= 15 else 0.3
    if field_type == FieldType.DATE:
        text = str(value)
        if not text:
            return 0.0
        # Validate date-like format: ISO (2024-01-15), US (01/15/2024),
        # EU (15/01/2024), or textual (15 Jan 2024, January 15, 2024)
        import re as _date_re

        if _date_re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}", text):
            return 1.0
        if _date_re.search(
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}", text, _date_re.IGNORECASE
        ):
            return 1.0
        if _date_re.search(
            r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}", text, _date_re.IGNORECASE
        ):
            return 1.0
        # Has digits and reasonable length but didn't match known formats
        if len(text) >= 6 and any(c.isdigit() for c in text):
            return 0.5
        return 0.0
    if field_type == FieldType.LOCATION:
        return 1.0 if len(str(value)) > 3 else 0.3
    return 0.5


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def clean_record(record: dict, schema_fields: list[SchemaField]) -> dict:
    """Apply cleaning rules to a record based on schema field types."""
    cleaned: dict[str, Any] = {}
    field_map = {f.name: f for f in schema_fields}

    for key, value in record.items():
        field = field_map.get(key)
        if field is None:
            cleaned[key] = value
            continue
        cleaner = CLEANERS.get(field.field_type, _clean_text)
        try:
            cleaned[key] = cleaner(value)
        except (ValueError, TypeError, AttributeError):
            cleaned[key] = value

    return cleaned


def validate_record(record: dict, schema_fields: list[SchemaField]) -> tuple[bool, dict[str, str]]:
    """Validate a record against the schema. Returns (is_valid, errors)."""
    errors: dict[str, str] = {}

    for field in schema_fields:
        value = record.get(field.name)
        if value is None or value == "":
            if field.required:
                errors[field.name] = "Required field is missing or empty"
            continue

        validator = VALIDATORS.get(field.field_type, _validate_text)
        is_valid, error = validator(value, field)
        if not is_valid:
            errors[field.name] = error

    return len(errors) == 0, errors


def score_record(record: dict, schema_fields: list[SchemaField]) -> float:
    """Compute a quality score for a single record (0.0 to 1.0)."""
    if not record:
        return 0.0

    field_scores = []
    for field in schema_fields:
        value = record.get(field.name)
        s = _field_score(value, field.field_type)
        if field.required and value in (None, ""):
            s = 0.0
        field_scores.append(s)

    if not field_scores:
        return 0.0

    return sum(field_scores) / len(field_scores)


def score_record_detailed(
    record: dict,
    schema_fields: list[SchemaField],
) -> dict[str, Any]:
    """Compute a per-record quality score with diagnostic breakdown.

    Returns dict with keys:
        overall: float              # 0..1 weighted blend
        completeness: float         # populated_fields / total_fields
        type_conformance: float     # type-valid checkable fields / total_checkable_fields
        plausibility: float         # average _field_score
        field_scores: dict[str, float]     # per-field plausibility
        field_type_valid: dict[str, bool]  # per-field type pass/fail
        missing_fields: list[str]          # fields with None/""
        mismatched_fields: list[str]       # fields with type mismatches
    """
    from app.config import settings

    if not schema_fields:
        return {
            "overall": 0.0,
            "completeness": 0.0,
            "type_conformance": 1.0,
            "plausibility": 0.0,
            "field_scores": {},
            "field_type_valid": {},
            "missing_fields": [],
            "mismatched_fields": [],
        }

    # 1. Completeness
    populated = 0
    missing: list[str] = []
    for field in schema_fields:
        value = record.get(field.name)
        if value is None or (isinstance(value, str) and not value.strip()) or value == "":
            missing.append(field.name)
        else:
            populated += 1
    completeness = populated / len(schema_fields)

    # 2. Type conformance
    mismatches = validate_field_types(record, schema_fields)
    mismatched_names = [m.field for m in mismatches]
    field_type_valid: dict[str, bool] = {}
    checkable_count = 0
    for field in schema_fields:
        value = record.get(field.name)
        if TYPE_CHECKERS.get(field.field_type) is None:
            continue  # not type-checkable
        if value is None or (isinstance(value, str) and not str(value).strip()) or value == "":
            continue  # empty — not counted in conformance
        checkable_count += 1
        field_type_valid[field.name] = field.name not in mismatched_names
    type_conformance = (checkable_count - len(mismatches)) / checkable_count if checkable_count > 0 else 1.0

    # 3. Plausibility
    field_scores: dict[str, float] = {}
    total_plaus = 0.0
    for field in schema_fields:
        value = record.get(field.name)
        s = _field_score(value, field.field_type)
        if field.required and (value is None or value == ""):
            s = 0.0
        field_scores[field.name] = round(s, 3)
        total_plaus += s
    plausibility = total_plaus / len(schema_fields) if schema_fields else 0.0

    # 4. Weighted blend
    type_weight = settings.QUALITY_TYPE_CONFORMANCE_WEIGHT
    completeness_weight = settings.QUALITY_COMPLETENESS_WEIGHT
    plaus_weight = settings.SCORE_QUALITY_WEIGHT

    # Redistribute if type conformance is undefined (0 checkable fields)
    if checkable_count == 0:
        total_w = plaus_weight + completeness_weight
        plaus_w_norm = plaus_weight / total_w if total_w > 0 else 0.0
        comp_w_norm = completeness_weight / total_w if total_w > 0 else 0.0
        overall = (plausibility * plaus_w_norm) + (completeness * comp_w_norm)
    else:
        overall = (plausibility * plaus_weight) + (type_conformance * type_weight) + (completeness * completeness_weight)

    overall = max(0.0, min(1.0, overall))

    return {
        "overall": round(overall, 3),
        "completeness": round(completeness, 3),
        "type_conformance": round(type_conformance, 3),
        "plausibility": round(plausibility, 3),
        "field_scores": field_scores,
        "field_type_valid": field_type_valid,
        "missing_fields": missing,
        "mismatched_fields": mismatched_names,
    }


def score_records(
    records: list[dict],
    schema_fields: list[SchemaField],
) -> list[dict[str, Any]]:
    """Score multiple records. Returns a list parallel to *records*.

    Empty input yields an empty list.
    """
    return [score_record_detailed(r, schema_fields) for r in records]


def deduplicate_records(records: list[dict]) -> tuple[list[dict], int]:
    """Remove exact duplicate records. Returns (unique_records, removed_count)."""
    seen: set[str] = set()
    unique: list[dict] = []

    for record in records:
        fp = json.dumps(record, sort_keys=True, default=str)
        if fp not in seen:
            seen.add(fp)
            unique.append(record)
    return unique, len(records) - len(unique)


def run_quality_pipeline(
    records: list[dict],
    schema_fields: list[SchemaField],
) -> dict[str, Any]:
    """Run the full data quality pipeline on extracted records.

    Returns a dict with:
        - cleaned_records: list of cleaned records
        - valid_records: list of records passing validation
        - invalid_records: list of records failing validation
        - duplicates_removed: int
        - quality_score: float (0.0 to 1.0)
        - field_validity: dict of per-field validity percentages
        - warnings: list of warning strings
    """
    warnings: list[str] = []

    # 1. Clean
    cleaned = [clean_record(r, schema_fields) for r in records]

    # 2. Validate
    valid_records: list[dict] = []
    invalid_records: list[dict] = []
    for record in cleaned:
        is_valid, errors = validate_record(record, schema_fields)
        if is_valid:
            valid_records.append(record)
        else:
            invalid_records.append({"record": record, "errors": errors})

    # 3. Deduplicate
    unique_valid, duplicates_removed = deduplicate_records(valid_records)

    # 4. Score
    if unique_valid:
        scores = [score_record(r, schema_fields) for r in unique_valid]
        overall_score = sum(scores) / len(scores)
    else:
        overall_score = 0.0

    # Per-field validity
    field_validity: dict[str, float] = {}
    for field in schema_fields:
        valid_count = sum(1 for r in unique_valid if r.get(field.name) not in (None, ""))
        if unique_valid:
            field_validity[field.name] = valid_count / len(unique_valid)
        else:
            field_validity[field.name] = 0.0

    # Warnings
    if invalid_records:
        warnings.append(f"{len(invalid_records)} records failed validation")
    if duplicates_removed > 0:
        warnings.append(f"{duplicates_removed} duplicate records removed")
    if not unique_valid:
        warnings.append("No valid records after quality pipeline")

    # 5. Per-record detailed quality
    per_record_quality = score_records(unique_valid, schema_fields)

    return {
        "cleaned_records": cleaned,
        "valid_records": unique_valid,
        "invalid_records": invalid_records,
        "duplicates_removed": duplicates_removed,
        "total_input": len(records),
        "total_valid": len(unique_valid),
        "total_invalid": len(invalid_records),
        "quality_score": round(overall_score, 2),
        "field_validity": field_validity,
        "warnings": warnings,
        "per_record_quality": per_record_quality,
    }
