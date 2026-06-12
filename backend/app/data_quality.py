"""Data Quality Pipeline — cleaning, validation, deduplication, scoring.

Provides a deterministic pipeline for improving extracted data quality:
  1. Clean (normalize values based on field type)
  2. Validate (check schema compliance)
  3. Deduplicate (remove exact duplicates)
  4. Score (compute quality score per record and overall)
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

from app.models import FieldType, SchemaField

logger = logging.getLogger(__name__)


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
    except Exception:
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
        return 1.0 if str(value) else 0.0
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
        except Exception:
            cleaned[key] = value

    return cleaned


def validate_record(record: dict, schema_fields: list[SchemaField]) -> tuple[bool, dict[str, str]]:
    """Validate a record against the schema. Returns (is_valid, errors)."""
    errors: dict[str, str] = {}
    {f.name: f for f in schema_fields}

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


def deduplicate_records(records: list[dict]) -> tuple[list[dict], int]:
    """Remove exact duplicate records. Returns (unique_records, removed_count)."""
    seen: set[str] = set()
    unique: list[dict] = []
    import json

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
    }
