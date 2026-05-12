"""
Layer 3: Semantic Mapper
=========================
Universal semantic mapping that matches values to user intent by WHAT THEY ARE,
not by WHERE THEY CAME FROM or what DOMAIN the page is from.

Core principle: "£238" maps to "price" because it LOOKS like a price,
not because it came from a "flight" page.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from app.intent_parser import IntentSchema, SEMANTIC_NEED_KEYWORDS
from app.page_profiler import StructureProfile, ValuePatterns


@dataclass
class FieldMapping:
    """Represents a mapping from an extracted value to a user's semantic need."""
    field_name: str  # The schema field name (e.g., "price")
    semantic_need: str  # What the user wanted (e.g., "price")
    original_value: str  # The raw extracted value
    mapped_value: str  # The cleaned/mapped value
    confidence: float  # 0.0 - 1.0 how confident we are
    matched_by: str  # How we matched: "pattern", "header", "position", "ai"
    evidence: str = ""  # Why we made this match
    # New: Multiple signals for debuggability
    signals: List[str] = field(default_factory=list)  # List of signals that contributed


@dataclass
class RecordMapping:
    """Complete mapping for a single record."""
    original_data: Dict[str, str]  # Original extracted data
    mapped_fields: Dict[str, str]  # Mapped to schema
    confidence_scores: Dict[str, float]  # Per-field confidence
    unmatched_values: List[str] = field(default_factory=list)  # Values we couldn't map


# Universal pattern matching for semantic needs (NOT domain-specific)
SEMANTIC_PATTERNS = {
    "price": [
        r"[\$\u20a8\u20ac\u00a3\u00a5\u20b9]\s*\d+[\d,]*\.?\d*",  # 238, $450, 5,200
        r"\d+[\d,]*\s*(inr|usd|eur|gbp|aud|cad)",  # 5000 INR
        r"(rs\.?|rupees?)\s*\d+",  # Rs 500
        r"(price|cost|fare|amount)\s*[:\-]?\s*[\$\u20a8\u20ac\u00a3\u00a5\u20b9]?\d+",  # Price: 500
        r"\d+\.?\d*\s*(cr|crore|l|lakh|k|m|mn|million|thousand)",  # 25L, 1.2Cr, 50K
    ],
    "date": [
        r"\d{1,2}[-\/]\d{1,2}[-\/]\d{2,4}",  # 22-05-2026
        r"\d{4}[-\/]\d{2}[-\/]\d{1,2}",  # 2026-05-22
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}",  # May 22
        r"\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",  # 22 May
    ],
    "duration": [
        r"\d+h\s*\d+m",  # 2h 30m
        r"\d+h$",  # 2h
        r"\d+:\d{2}",  # 02:30
        r"\d+\s*hours?",  # 3 hours
    ],
    "rating": [
        r"\d+\.?\d*/\d+",  # 4.5/5, 8.5/10
        r"[★☆]{1,5}",  # ★★★
        r"\d+\.?\d*\s*(star|rating)",  # 4.5 stars
    ],
    "location": [
        r"\b[A-Z]{3}\b",  # 3-letter codes (city codes, currency codes, etc.)
        r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+,\s+[A-Z]{2,3}\b",  # City, State
    ],
    "phone": [
        r"\+?\d[\d\s\-\(\)]{8,}",  # +91 9876543210
    ],
    "email": [
        r"[\w.+-]+@[\w-]+\.[\w.-]+",
    ],
    "link": [
        r"https?://[^\s]+",
        r"www\.[^\s]+",
    ],
}


def match_values_to_intent(
    extracted_records: List[Dict[str, str]],
    intent: IntentSchema,
    page_profile: StructureProfile,
    value_patterns: ValuePatterns,
    headers: List[str] = None
) -> List[RecordMapping]:
    """
    Match extracted values to user intent by WHAT THEY ARE, not where they came from.

    Input: extracted_records = [{"col1": "£238", "col2": "22-05-2026", "col3": "Lufthansa"}]
           intent = IntentSchema with semantic_needs = {"price": [...], "date": [...]}
    Output: RecordMapping with mapped fields and confidence scores
    """
    headers = headers or page_profile.headers or []

    mapped_records = []

    for record in extracted_records:
        mapping = _map_single_record(
            record,
            intent,
            headers,
            value_patterns
        )
        mapped_records.append(mapping)

    return mapped_records


def _map_single_record(
    record: Dict[str, str],
    intent: IntentSchema,
    headers: List[str],
    value_patterns: ValuePatterns
) -> RecordMapping:
    """Map a single record's values to user intent."""
    mapped_fields = {}
    confidence_scores = {}
    unmatched_values = []
    field_mappings = []

    # Get all unique values from the record (skip metadata keys)
    metadata_keys = {"record_score", "_field_confidences", "source_url", "source_type", "source_trust_score"}
    seen = set()
    all_values = []
    for k, v in record.items():
        if k in metadata_keys:
            continue
        v_str = str(v) if v is not None else ""
        if v_str and v_str not in seen:
            seen.add(v_str)
            all_values.append(v_str)

    # For each semantic need the user has, try to find a matching value
    used_values = set()
    for semantic_need in intent.semantic_needs.keys():
        best_mapping = _find_best_value_for_need(
            all_values,
            semantic_need,
            headers,
            value_patterns,
            used_values
        )

        if best_mapping:
            mapped_fields[best_mapping.field_name] = best_mapping.mapped_value
            confidence_scores[best_mapping.field_name] = best_mapping.confidence
            field_mappings.append(best_mapping)
            # After mapping a value to one need, mark it as used
            # so it won't satisfy ALL needs (prevents blob duplication)
            used_values.add(best_mapping.original_value)
        else:
            # Could not find a value for this need
            unmatched_values.append(semantic_need)

    # Also track any values we couldn't map to a need
    mapped_values = set(m.mapped_value for m in field_mappings)
    for value in all_values:
        if value and value not in mapped_values:
            if not _is_noise_value(value):
                unmatched_values.append(value)

    return RecordMapping(
        original_data=record,
        mapped_fields=mapped_fields,
        confidence_scores=confidence_scores,
        unmatched_values=unmatched_values[:10]  # Limit
    )


def _find_best_value_for_need(
    values: List[str],
    semantic_need: str,
    headers: List[str],
    value_patterns: ValuePatterns,
    used_values: set = None
) -> Optional[FieldMapping]:
    """
    Find the best value that matches a semantic need.

    Strategy:
    1. Pattern match: does value match expected pattern for this need?
    2. Header match: does associated header suggest this need?
    3. Position match: is value in expected position?
    4. Fallback: return first non-empty value
    """
    if not values:
        return None

    used_values = used_values or set()

    candidates = []

    # Strategy 1: Pattern matching
    patterns = SEMANTIC_PATTERNS.get(semantic_need, [])
    if patterns:
        for value in values:
            if not value or _is_noise_value(value):
                continue
            # Skip values already used for another need
            if value in used_values:
                continue

            for pattern in patterns:
                if re.search(pattern, str(value), re.IGNORECASE):
                    candidates.append(FieldMapping(
                        field_name=semantic_need,
                        semantic_need=semantic_need,
                        original_value=value,
                        mapped_value=value.strip(),
                        confidence=0.95,
                        matched_by="pattern",
                        evidence=f"Matched pattern {pattern[:30]}...",
                        signals=[f"pattern_match:{pattern[:40]}", "high_confidence"]
                    ))
                    break

    if candidates:
        # Return highest confidence
        return max(candidates, key=lambda x: x.confidence)

    # Strategy 2: Header-based matching
    if headers:
        need_keywords = SEMANTIC_NEED_KEYWORDS.get(semantic_need, [])
        for i, header in enumerate(headers):
            header_lower = header.lower()
            for keyword in need_keywords:
                if keyword in header_lower:
                    # Try to get corresponding value from record
                    if i < len(values) and values[i]:
                        return FieldMapping(
                            field_name=semantic_need,
                            semantic_need=semantic_need,
                            original_value=values[i],
                            mapped_value=values[i].strip(),
                            confidence=0.8,
                            matched_by="header",
                            evidence=f"Header '{header}' matches '{keyword}'",
                            signals=[f"header_match:{header}", "keyword_matched"]
                        )

    # Strategy 3: Value pattern detection from page
    value_type = _detect_value_type(values, value_patterns)
    if value_type == semantic_need:
        for value in values:
            if value and not _is_noise_value(value):
                return FieldMapping(
                    field_name=semantic_need,
                    semantic_need=semantic_need,
                    original_value=value,
                    mapped_value=value.strip(),
                    confidence=0.7,
                    matched_by="page_pattern",
                    evidence=f"Page has {semantic_need} values",
                    signals=[f"page_detected:{semantic_need}", "positional_inference"]
                )

    # Strategy 4: Fallback - return first non-empty value
    for value in values:
        if value and not _is_noise_value(value) and len(value.strip()) > 1:
            return FieldMapping(
                field_name=semantic_need,
                semantic_need=semantic_need,
                original_value=value,
                mapped_value=value.strip(),
                confidence=0.3,
                matched_by="fallback",
                evidence="No better match found",
                signals=["low_confidence_fallback", "no_signal_matched"]
            )

    return None


def _detect_value_type(values: List[str], value_patterns: ValuePatterns) -> Optional[str]:
    """Detect what type most values in the list are."""
    if not values:
        return None

    # Check against detected page patterns
    sample = values[0] if values else ""

    # Currency check
    if value_patterns.currencies:
        for pattern in SEMANTIC_PATTERNS["price"]:
            if re.search(pattern, sample, re.IGNORECASE):
                return "price"

    # Date check
    if value_patterns.dates:
        for pattern in SEMANTIC_PATTERNS["date"]:
            if re.search(pattern, sample, re.IGNORECASE):
                return "date"

    # Rating check
    if value_patterns.ratings:
        for pattern in SEMANTIC_PATTERNS["rating"]:
            if re.search(pattern, sample, re.IGNORECASE):
                return "rating"

    return None


def _is_noise_value(value: str) -> bool:
    """Check if a value is likely noise (navigation, UI elements, etc.)."""
    if value is None:
        return True

    value_str = str(value).strip()
    if not value_str:
        return True

    value_lower = value_str.lower()

    # Common noise patterns (domain-agnostic)
    noise_patterns = [
        "about us", "contact us", "privacy policy", "terms", "conditions",
        "home", "menu", "search", "filter", "sort", "show all", "view all",
        "login", "sign up", "register", "signup", "signin",
        "facebook", "twitter", "instagram", "linkedin", "youtube",
        "copyright", "all rights", "powered by",
        "click here", "read more", "learn more", "view more",
        "call now", "book now", "buy now", "add to cart",
        "next", "previous", "back", "continue",
    ]

    # Single word noise
    if len(value_lower.split()) == 1 and value_lower in noise_patterns:
        return True

    # Full match with noise phrase
    if value_lower in noise_patterns:
        return True

    # Too short to be meaningful data
    if len(value_lower) < 2:
        return True

    # Too long (likely not a data value)
    if len(value_lower) > 300:
        return True

    return False


def resolve_conflicts(mappings: List[FieldMapping]) -> List[FieldMapping]:
    """
    When multiple values could map to the same field, choose the best one.

    For example, if we have both "£238" and "£248" that could map to "price",
    we need to pick the one with higher confidence.
    """
    if not mappings:
        return []

    # Group by semantic need
    by_need = {}
    for mapping in mappings:
        need = mapping.semantic_need
        if need not in by_need:
            by_need[need] = []
        by_need[need].append(mapping)

    # For each need, keep only the best mapping
    resolved = []
    for need, need_mappings in by_need.items():
        if len(need_mappings) == 1:
            resolved.append(need_mappings[0])
        else:
            # Multiple candidates - pick highest confidence
            best = max(need_mappings, key=lambda x: x.confidence)
            resolved.append(best)

    return resolved


def map_to_schema_fields(
    mapped_records: List[RecordMapping],
    schema_fields: List,
    intent: IntentSchema
) -> List[Dict]:
    """
    Convert RecordMapping objects to final schema format.

    Map semantic need names to actual schema field names.
    """

    results = []

    for record_mapping in mapped_records:
        result = {}

        for schema_field in schema_fields:
            field_name = schema_field.name

            # Check if we have a mapped value for this field
            if field_name in record_mapping.mapped_fields:
                result[field_name] = record_mapping.mapped_fields[field_name]
            else:
                result[field_name] = None

        # Add confidence score
        result["_field_confidences"] = record_mapping.confidence_scores
        result["record_score"] = _compute_record_score(record_mapping.confidence_scores, schema_fields)

        results.append(result)

    return results


def _compute_record_score(confidences: Dict[str, float], schema_fields: List) -> float:
    """Compute overall record score from per-field confidences."""
    if not confidences:
        return 0.0

    required_fields = [f for f in schema_fields if f.required]
    optional_fields = [f for f in schema_fields if not f.required]

    if not required_fields:
        # No required fields - average of all
        return sum(confidences.values()) / len(confidences) if confidences else 0.0

    # Check required fields
    required_confidences = [confidences.get(f.name, 0.0) for f in required_fields]
    required_avg = sum(required_confidences) / len(required_confidences) if required_confidences else 0.0

    # If any required field has 0 confidence (missing), heavily penalize
    if 0.0 in required_confidences:
        required_avg *= 0.5

    # Optional fields contribute less
    optional_confidences = [confidences.get(f.name, 0.0) for f in optional_fields]
    optional_avg = sum(optional_confidences) / len(optional_confidences) if optional_confidences else 0.0

    # Weighted score: 70% required, 30% optional
    score = (0.7 * required_avg) + (0.3 * optional_avg)

    return round(min(max(score, 0.0), 1.0), 3)


def ai_repair_mapping(
    unmapped_values: List[str],
    intent: IntentSchema,
    schema_fields: List,
    fallback_data: Dict[str, str]
) -> Dict[str, str]:
    """
    Use AI to repair mappings when pattern-based matching fails.

    This is the fallback when we can't confidently map values to fields.
    """
    from app.scraper import _llm_json

    schema_desc = [{"name": f.name, "type": f.field_type.value} for f in schema_fields]

    prompt = f"""Map these extracted values to the appropriate schema fields.

USER INTENT: {intent.raw_query}
NEEDS: {list(intent.semantic_needs.keys())}

SCHEMA FIELDS:
{schema_desc}

EXTRACTED VALUES (some could not be mapped):
{fallback_data}

UNMAPPED VALUES THAT NEED PLACEMENT:
{unmapped_values}

Return ONLY JSON with field_name: value pairs for fields that can be filled.
If a value cannot be confidently mapped, do not include it.
"""

    try:
        messages = [
            {"role": "system", "content": "You map extracted values to schema fields intelligently."},
            {"role": "user", "content": prompt}
        ]
        result = _llm_json(messages, temperature=0.1)

        if isinstance(result, dict):
            return result
    except Exception:
        pass

    return {}