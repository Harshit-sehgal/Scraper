
"""
Layer 4: Validation & Repair
============================
Confidence-based validation that:
- Computes per-field confidence scores
- Rejects low-confidence mappings
- Allows empty fields, rejects wrong values
- Repairs bad mappings via AI when needed

Core principle: Empty fields are OK; wrong values are NOT.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from app.intent_parser import IntentSchema
from app.models import FieldType, SchemaField


@dataclass
class ValidationResult:
    """Result of validating a single record."""
    is_valid: bool  # Overall validity
    field_confidences: Dict[str, float]  # Per-field confidence scores
    rejected_fields: List[str] = field(default_factory=list)  # Fields below threshold
    allowed_empty: List[str] = field(default_factory=list)  # Empty but OK
    issues: List[str] = field(default_factory=list)  # Human-readable issues
    overall_score: float = 0.0  # Overall record quality score


# Confidence thresholds
DEFAULT_MIN_CONFIDENCE = 0.5
STRICT_CONFIDENCE = 0.7  # For required fields
LENIENT_CONFIDENCE = 0.3  # For optional fields


# Pattern-based validation rules (universal, not domain-specific)
VALIDATION_PATTERNS = {
    FieldType.EMAIL: [
        r"[\w.+-]+@[\w-]+\.[\w.-]+",
    ],
    FieldType.PHONE: [
        r"\+?\d[\d\s\-\(\)]{8,}",
    ],
    FieldType.URL: [
        r"https?://[^\s]+",
        r"www\.[^\s]+",
    ],
    FieldType.CURRENCY: [
        r"[\$\u20a8\u20ac\u00a3\u00a5\u20b9]\s*\d+[\d,]*\.?\d*",
        r"\d+[\d,]*\s*(inr|usd|eur|gbp)",
        r"\d+\.?\d*\s*(cr|crore|l|lakh|k|m|mn|million|thousand)",
    ],
    FieldType.DATE: [
        r"\d{1,2}[-\/]\d{1,2}[-\/]\d{2,4}",  # 22-05-2026, 05/22/2026
        r"\d{4}[-\/]\d{2}[-\/]\d{1,2}",  # 2026-05-22
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}",  # May 22
        r"\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",  # 22 May
        r"\d{1,2}:\d{2}",  # 14:30, 2:30
    ],
    FieldType.FLOAT: [
        r"\d+\.?\d*",
    ],
}


def compute_field_confidence(
    value: str,
    field_type: FieldType,
    semantic_need: str
) -> float:
    """
    Compute confidence (0.0-1.0) that a value matches its field type.

    Key principle: Check if the value LOOKS like what the field expects,
    not whether it came from the right place.
    """
    if not value or value == "—" or value.lower() in ["null", "none", "undefined"]:
        return 0.0  # Empty values have no confidence

    value_str = str(value).strip()
        # value_str.lower() used later

    # Check for noise patterns (domain-agnostic)
    if _is_invalid_for_any_field(value_str):
        return 0.0

    # If field type has validation patterns, check against them
    if field_type in VALIDATION_PATTERNS:
        patterns = VALIDATION_PATTERNS[field_type]
        for pattern in patterns:
            if re.search(pattern, value_str, re.IGNORECASE):
                # Value matches expected pattern - high confidence
                return 0.95

        # Value doesn't match pattern - check if it's at least reasonable
        # Allow numeric values in numeric fields even if format differs
        if field_type in [FieldType.INTEGER, FieldType.FLOAT, FieldType.CURRENCY]:
            try:
                float(re.sub(r"[^\d.]", "", value_str))
                return 0.5  # Could be parsed
            except ValueError:
                pass

        # For other types, if no pattern match, give low confidence
        return 0.2

    # For STRING and other types, use semantic need matching
    if semantic_need:
        confidence = _semantic_need_match_confidence(value_str, semantic_need)
        return confidence

    # Default: moderate confidence for string fields
    if len(value_str) > 1 and len(value_str) < 200:
        return 0.5

    return 0.0


def _is_invalid_for_any_field(value: str) -> bool:
    """Check if a value is clearly invalid for any field type."""
    value_lower = value.lower()

    invalid_patterns = [
        "info@",  # Email in wrong field
        "call us", "contact us",  # Contact in wrong field
        "price:", "price :",  # Label in value field
        "select", "choose",  # UI element
        "n/a", "na", "-",  # Placeholder
    ]

    return any(p in value_lower for p in invalid_patterns)


def _semantic_need_match_confidence(value: str, semantic_need: str) -> float:
    """Check how well a value matches a semantic need."""
    value_lower = value.lower()

    # Semantic need to pattern mapping (universal)
    need_patterns = {
        "price": [
            r"[\$₹€£¥]", r"\d+[\d,]*", r"(inr|usd|eur|gbp|price|cost|fare)",
        ],
        "date": [
            r"\d{1,2}", r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
            r"20\d{2}", r"\d{4}", r":\d{2}",
        ],
        "rating": [
            r"[\d\.]+/[\d\.]+", r"[★☆]+", r"star", r"rating",
        ],
        "location": [
            r"\b[A-Z]{3}\b", r"\b[A-Z][a-z]+\b", r"address", r"city",
        ],
        "phone": [
            r"\+?\d", r"\(\d+\)", r"call",
        ],
        "email": [
            r"@", r"\.com", r"\.in",
        ],
        "duration": [
            r"\d+h", r"\d+:\d{2}", r"hour", r"min",
        ],
    }

    patterns = need_patterns.get(semantic_need, [])
    if not patterns:
        return 0.5  # Default

    for pattern in patterns:
        if re.search(pattern, value_lower, re.IGNORECASE):
            return 0.85

    return 0.3  # No match


def validate_record(
    record: Dict,
    schema_fields: List[SchemaField],
    intent: IntentSchema,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
) -> ValidationResult:
    """
    Validate a single record against user intent and schema.

    Rules:
    - REJECT if any REQUIRED field has wrong-type value (confidence < threshold)
    - ALLOW if optional field is empty
    - FLAG low-confidence mappings
    """
    field_confidences = {}
    rejected_fields = []
    allowed_empty = []
    issues = []

    # Get semantic needs from intent
    semantic_needs = intent.semantic_needs if intent else {}

    for schema_field in schema_fields:
        field_name = schema_field.name
        value = record.get(field_name)
        field_type = schema_field.field_type

        # Get semantic need for this field
        semantic_need = None
        for need, keywords in semantic_needs.items():
            if field_name in keywords or need in field_name.lower():
                semantic_need = need
                break

        # Compute confidence
        if value and str(value).strip() not in ["", "—", "null", "None"]:
            confidence = compute_field_confidence(str(value), field_type, semantic_need or field_name)
        else:
            confidence = 0.0

        field_confidences[field_name] = confidence

        # Check against requirements
        if schema_field.required:
            if confidence < min_confidence and confidence > 0:
                rejected_fields.append(field_name)
                issues.append(f"Required field '{field_name}' has low confidence ({confidence:.2f})")
            elif confidence == 0:
                # Empty required field - this is an issue but different from wrong value
                issues.append(f"Required field '{field_name}' is empty")
        else:
            # Optional field
            if confidence == 0:
                allowed_empty.append(field_name)
                # Empty optional field is OK - no issue
            elif confidence < min_confidence:
                issues.append(f"Optional field '{field_name}' has low confidence ({confidence:.2f})")

    # Determine overall validity
    # Record is invalid if any required field has wrong-type value (low confidence but not 0)
    is_valid = len(rejected_fields) == 0

    # Compute overall score
    overall_score = _compute_overall_validation_score(field_confidences, schema_fields)

    return ValidationResult(
        is_valid=is_valid,
        field_confidences=field_confidences,
        rejected_fields=rejected_fields,
        allowed_empty=allowed_empty,
        issues=issues,
        overall_score=overall_score
    )


def validate_records(
    records: List[Dict],
    schema_fields: List[SchemaField],
    intent: IntentSchema,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    keep_invalid: bool = False  # If True, keep invalid records but mark them
) -> Tuple[List[Dict], Dict]:
    """
    Validate multiple records and optionally filter/flag invalid ones.

    Returns: (valid_records, validation_summary)
    """
    valid_records = []
    invalid_records = []
    validation_summary = {
        "total": len(records),
        "valid": 0,
        "invalid": 0,
        "rejected_fields": {},
        "empty_allowed": 0,
    }

    for record in records:
        result = validate_record(record, schema_fields, intent, min_confidence)

        if result.is_valid:
            # Add confidence info to record
            record["_validation"] = {
                "score": result.overall_score,
                "field_confidences": result.field_confidences,
                "issues": result.issues,
            }
            valid_records.append(record)
            validation_summary["valid"] += 1
        else:
            if keep_invalid:
                # Keep but mark as invalid
                record["_validation"] = {
                    "score": result.overall_score,
                    "field_confidences": result.field_confidences,
                    "issues": result.issues,
                    "is_valid": False,
                }
                valid_records.append(record)
                validation_summary["valid"] += 1
            else:
                invalid_records.append(record)
                validation_summary["invalid"] += 1

            # Track rejected field counts
            for _field in result.rejected_fields:
                validation_summary["rejected_fields"][_field] = \
                    validation_summary["rejected_fields"].get(_field, 0) + 1

    validation_summary["empty_allowed"] = len([r for r in valid_records if "_validation" in r and r["_validation"]["score"] > 0])

    return valid_records, validation_summary


def _compute_overall_validation_score(
    field_confidences: Dict[str, float],
    schema_fields: List[SchemaField]
) -> float:
    """Compute overall validation score from per-field confidences."""
    if not field_confidences:
        return 0.0

    required_fields = [f for f in schema_fields if f.required]
    optional_fields = [f for f in schema_fields if not f.required]

    # Required fields: weighted heavily
    if required_fields:
        required_scores = [field_confidences.get(f.name, 0.0) for f in required_fields]
        required_avg = sum(required_scores) / len(required_scores)
    else:
        required_avg = 0.0

    # Optional fields: weighted less
    if optional_fields:
        optional_scores = [field_confidences.get(f.name, 0.0) for f in optional_fields]
        optional_avg = sum(optional_scores) / len(optional_scores)
    else:
        optional_avg = 0.0

    # If any required field is 0 (empty), penalize but don't zero
    has_empty_required = any(
        field_confidences.get(f.name, 0.0) == 0.0
        for f in required_fields
    )

    if has_empty_required:
        required_avg *= 0.7

    # Weighted overall score
    overall = (0.7 * required_avg) + (0.3 * optional_avg)

    return round(max(min(overall, 1.0), 0.0), 3)


def get_validation_summary_text(summary: Dict) -> str:
    """Generate human-readable validation summary."""
    lines = [
        f"Total records: {summary['total']}",
        f"Valid: {summary['valid']}",
        f"Invalid: {summary['invalid']}",
    ]

    if summary.get("rejected_fields"):
        lines.append("Rejected fields:")
        for _f_name, count in summary["rejected_fields"].items():
            lines.append(f"  - {_f_name}: {count} records")

    return "\n".join(lines)