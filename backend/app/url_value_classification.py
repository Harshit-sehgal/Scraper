"""Value classification, field type suggestion, and field name inference.

Extracted from the legacy selector_discovery_url module for modularity.

Ownership boundary: classifies extracted text values by type, maps value
patterns to field type suggestions, builds LLM prompts for field naming,
and post-processes generic field names. Content quality lives in
content_quality.py; search form detection in search_form_recovery.py.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ─── Value Classification ───────────────────────────────────────────


def _classify_value(value: str) -> str:
    """Classify a single text value using VALUE_PATTERNS.

    Prioritizes specific types (currency, date, email, etc.) over generic
    ones like "number" which can match numeric substrings within any value.

    Returns: One of: string, number, currency, email, phone, url, date,
    time, rating, boolean, percentage, location, code.
    """
    from app.page_profiler import VALUE_PATTERNS

    value = value.strip()
    if not value:
        return "string"

    # Priority order: check specific types first, generic "number" last
    type_priority = [
        ("email", ["email"]),
        ("currency", ["currency"]),
        ("url", ["url"]),
        ("time", ["time"]),
        ("date", ["date"]),
        ("percentage", ["percentage"]),
        ("rating", ["rating"]),
        ("boolean", ["boolean"]),
        ("product_code", ["product_code"]),
        ("airport_code", ["airport_code"]),
        ("code_3letter", ["code_3letter"]),
        ("phone", ["phone"]),
        ("address", ["address"]),
        ("number", ["number"]),  # Generic — checked last
    ]

    matched_type = None
    for output_type, pattern_names in type_priority:
        for pname in pattern_names:
            for pattern in VALUE_PATTERNS.get(pname, []):
                try:
                    if output_type == "number":
                        if re.fullmatch(pattern, value, re.IGNORECASE):
                            matched_type = output_type
                            break
                    elif re.search(pattern, value, re.IGNORECASE):
                        matched_type = output_type
                        break
                except re.error:
                    logger.debug("Invalid regex pattern in VALUE_PATTERNS[%s]: %s", pname, pattern)
                    continue
            if matched_type:
                break
        if matched_type:
            break

    type_map = {
        "currency": "currency",
        "date": "date",
        "rating": "rating",
        "code_3letter": "code",
        "phone": "phone",
        "email": "email",
        "number": "number",
        "duration": "string",
        "url": "url",
        "weight": "string",
        "percentage": "percentage",
        "time": "time",
        "boolean": "boolean",
        "dimension": "string",
        "quantity": "string",
        "product_code": "code",
        "unit_type": "string",
        "airport_code": "code",
        "address": "location",
    }

    if matched_type and matched_type in type_map:
        return type_map[matched_type]

    return "string"


def _value_patterns_to_field_types(patterns) -> list[dict]:
    """Map detected value patterns to generic field type suggestions.

    Returns a list of {type, confidence, example, description} dicts without
    assuming specific field names — the LLM will determine field names from context.
    """
    suggestions = []
    if patterns.currencies:
        suggestions.append(
            {
                "type": "currency",
                "confidence": 0.9,
                "example": patterns.currencies[0],
                "description": "Monetary values detected on page",
            },
        )
    if patterns.dates:
        suggestions.append(
            {
                "type": "date",
                "confidence": 0.9,
                "example": patterns.dates[0],
                "description": "Date values detected on page",
            },
        )
    if patterns.times:
        suggestions.append(
            {
                "type": "time",
                "confidence": 0.75,
                "example": patterns.times[0],
                "description": "Time values detected on page",
            },
        )
    if patterns.ratings:
        suggestions.append(
            {
                "type": "rating",
                "confidence": 0.85,
                "example": patterns.ratings[0],
                "description": "Rating or score values detected on page",
            },
        )
    if patterns.emails:
        suggestions.append(
            {
                "type": "email",
                "confidence": 0.95,
                "example": patterns.emails[0],
                "description": "Email addresses detected on page",
            },
        )
    if patterns.phones:
        suggestions.append(
            {
                "type": "phone",
                "confidence": 0.9,
                "example": patterns.phones[0],
                "description": "Phone numbers detected on page",
            },
        )
    codes_3letter = getattr(patterns, "codes_3letter", []) or []
    airport_codes = getattr(patterns, "airport_codes", []) or []
    if codes_3letter or airport_codes:
        suggestions.append(
            {
                "type": "code",
                "confidence": 0.75,
                "example": (airport_codes or codes_3letter)[0],
                "description": "Short codes (3-letter) detected on page",
            },
        )
    if patterns.durations:
        suggestions.append(
            {
                "type": "string",
                "confidence": 0.8,
                "example": patterns.durations[0],
                "description": "Duration values detected on page",
            },
        )
    if patterns.urls:
        suggestions.append(
            {
                "type": "url",
                "confidence": 0.85,
                "example": patterns.urls[0],
                "description": "URL / website values detected on page",
            },
        )
    if patterns.weights:
        suggestions.append(
            {
                "type": "string",
                "confidence": 0.8,
                "example": patterns.weights[0],
                "description": "Weight values detected on page",
            },
        )
    if patterns.percentages:
        suggestions.append(
            {
                "type": "percentage",
                "confidence": 0.8,
                "example": patterns.percentages[0],
                "description": "Percentage values detected on page",
            },
        )
    if patterns.booleans:
        suggestions.append(
            {
                "type": "boolean",
                "confidence": 0.85,
                "example": patterns.booleans[0],
                "description": "Boolean / status values detected on page",
            },
        )
    if patterns.dimensions:
        suggestions.append(
            {
                "type": "string",
                "confidence": 0.75,
                "example": patterns.dimensions[0],
                "description": "Dimension / size values detected on page",
            },
        )
    if patterns.quantities:
        suggestions.append(
            {
                "type": "string",
                "confidence": 0.75,
                "example": patterns.quantities[0],
                "description": "Quantity / pack size values detected on page",
            },
        )
    if patterns.product_codes:
        suggestions.append(
            {
                "type": "code",
                "confidence": 0.8,
                "example": patterns.product_codes[0],
                "description": "Product / SKU codes detected on page",
            },
        )
    if patterns.units:
        suggestions.append(
            {
                "type": "string",
                "confidence": 0.75,
                "example": patterns.units[0],
                "description": "Unit type indicators detected on page",
            },
        )
    if patterns.address_fragments:
        suggestions.append(
            {
                "type": "location",
                "confidence": 0.8,
                "example": patterns.address_fragments[0],
                "description": "Address / location values detected on page",
            },
        )
    return suggestions


def build_url_analysis_prompt(values: list[str], page_analysis: dict[str, Any]) -> str:
    """Build a prompt using structured container values instead of raw HTML.

    Rather than sending raw HTML to the LLM and asking it to both parse AND
    name fields (which causes it to default to generic type names), we:
    1. Pre-extract text values from the data container (programmatically)
    2. Classify each value by type using pattern detection
    3. Send the LLM ONLY the structured value+type pairs for naming

    This drastically reduces the LLM's cognitive load — it only needs to
    assign descriptive field names based on the data context.
    """
    structure_type = page_analysis.get("structure_type", "unknown")
    structure_confidence = page_analysis.get("structure_confidence", 0.0)

    # Build a clean table of values with their types
    rows = []
    for i, val in enumerate(values, 1):
        vtype = _classify_value(val)
        rows.append(f'  #{i:<3} "{val}"  type: {vtype}')

    value_block = "\n".join(rows)

    few_shot = """
=== EXAMPLE ===
Input values from a product listing page:
  #1   "Ergonomic Office Chair"           type: string
  #2   "FURN-4032"                        type: code
  #3   "$299.99"                          type: currency
  #4   "4.5 / 5"                            type: rating
  #5   "Free shipping"                    type: string
  #6   "2 - 3 business days"                type: string
  #7   "In Stock"                         type: boolean
  #8   "SteelFrame Co."                   type: string
  #9   "Leather, Aluminum"                type: string
  #10  "450"                              type: number
  #11  "Black, White"                     type: string

Expected output:
{"page_type": "cards", "estimated_record_count": 36, "fields": [
  {"name": "product_name", "type": "string", "example_value": "Ergonomic Office Chair",
  "confidence": 0.95, "description": "Product name"},
  {"name": "sku", "type": "code", "example_value": "FURN-4032",
  "confidence": 0.95, "description": "Product SKU or item code"},
  {"name": "price", "type": "currency", "example_value": "$299.99",
  "confidence": 0.95, "description": "Product price"},
  {"name": "rating", "type": "rating", "example_value": "4.5 / 5",
  "confidence": 0.90, "description": "Customer rating"},
  {"name": "delivery_info", "type": "string", "example_value": "Free shipping",
  "confidence": 0.80, "description": "Shipping or delivery information"},
  {"name": "delivery_time", "type": "string", "example_value": "2 - 3 business days",
  "confidence": 0.80, "description": "Estimated delivery time"},
  {"name": "availability", "type": "boolean", "example_value": "In Stock",
  "confidence": 0.90, "description": "Stock availability status"},
  {"name": "brand", "type": "string", "example_value": "SteelFrame Co.",
  "confidence": 0.95, "description": "Brand or manufacturer"},
  {"name": "materials", "type": "string", "example_value": "Leather, Aluminum",
  "confidence": 0.85, "description": "Product materials or features"},
  {"name": "weight_lbs", "type": "number", "example_value": "450",
  "confidence": 0.75, "description": "Product weight"},
  {"name": "color", "type": "string", "example_value": "Black, White",
  "confidence": 0.90, "description": "Available colors"}
]}
=== END EXAMPLE ===
"""

    return f"""You are a data schema designer. Name each data field found on this webpage.

I extracted these values from ONE data row on this {structure_type.upper()} page
(confidence: {structure_confidence:.0%}):

{value_block}

{few_shot}

For EACH value, assign a descriptive snake_case field name.
Determine its data type from: string, number, currency, email, phone, url,
date, time, rating, boolean, percentage, location, code.

CRITICAL: NEVER use type names as field names.
  BAD: {{"name": "string"}}  or {{"name": "code"}}  or {{"name": "time"}}
  or {{"name": "text"}}  or {{"name": "number"}}  or {{"name": "date"}}
  or {{"name": "currency"}}
  GOOD: {{"name": "airline_name"}}  or {{"name": "flight_number"}}
  or {{"name": "departure_airport"}}  or {{"name": "departure_time"}}
  or {{"name": "price"}}

Differentiate duplicate types — if two values share the same type,
give them distinct context-specific names
(e.g. "origin_airport_code" vs "destination_airport_code"
instead of "code" and "code").

Look at each value carefully and infer its contextual meaning. For example:
- A 3-letter uppercase word like "LHR" or "JFK" is likely an airport code,
  name it "origin_airport_code" or "destination_airport_code"
- A city name like "London" or "New York" is a location,
  name it "origin_city" or "destination_city"
- A monetary value like "$450" or "Â£450" is a price,
  name it "price", "total_price", or "fee"
- A short time like "08:30" or "14:00" is a time,
  name it "departure_time" or "arrival_time"
- A date like "30 / 05 / 2026" is a date,
  name it "departure_date", "travel_date", or "return_date"

Return ONLY JSON — NO markdown, NO commentary:
{{"page_type": "{structure_type}",
  "estimated_record_count": 24,
  "fields": [
    {{"name": "descriptive_field_name",
      "type": "string",
      "example_value": "actual value from HTML",
      "confidence": 0.95,
      "description": "What this field represents"}}
  ]
}} """


# ─── Generic field name post-processing ────────────────────────────────

_GENERIC_NAMES: set[str] = {
    "string",
    "text",
    "number",
    "integer",
    "float",
    "boolean",
    "bool",
    "code",
    "date",
    "time",
    "currency",
    "email",
    "phone",
    "url",
    "website",
    "rating",
    "location",
    "address",
    "percentage",
    "list",
    "object",
    "field",
}


def _rename_generic_fields(fields: list[dict]) -> list[dict]:
    """Post-process field list to replace generic type-name fields.

    If an LLM returns a field named "string", "code", "time", etc.
    (a type name used as a field identifier), try to infer a better
    name from the example value and the field's data type.
    """
    renamed: list[dict] = []
    seen_names: dict[str, int] = {}

    for f in fields:
        name: str = f.get("name", "")
        example: str = str(f.get("example_value", ""))
        ftype: str = f.get("type", "string")

        if name.lower() in _GENERIC_NAMES:
            better = _infer_field_name(example, ftype)
            if better:
                name = better
                f["name"] = better
                f["description"] = f.get("description", "") or better.replace("_", " ").title()

        # Deduplicate names
        lower = name.lower()
        if lower in seen_names:
            seen_names[lower] += 1
            name = f"{name}_{seen_names[lower]}"
            f["name"] = name
        else:
            seen_names[lower] = 1

        renamed.append(f)

    return renamed


# Simple type-aware naming hints for generic fields
_FIELD_NAME_HINTS: list[tuple[str, str, str]] = [
    ("currency", "", "price"),
    ("code", r"^[A-Z]{3}$", "three_letter_code"),
    ("code", r"^[A-Z]{2}$", "code_abbreviation"),
    ("code", "", "reference_code"),
    ("date", "", "date"),
    ("time", "", "time"),
    ("email", "", "email"),
    ("phone", "", "phone_number"),
    ("location", r"[A-Z][a-z]+", "city_name"),
    ("url", "", "website_url"),
    ("rating", "", "rating"),
    ("percentage", "", "percentage"),
    ("boolean", "", "flag"),
    ("number", "", "value"),
]


def _infer_field_name(example_value: str, field_type: str) -> str:
    """Try to infer a descriptive field name from an example value and type.

    Returns an empty string if no good inference is possible.
    """
    if not example_value:
        return ""

    val = example_value.strip()

    for pattern_type, pattern, suggestion in _FIELD_NAME_HINTS:
        if field_type != pattern_type:
            continue
        if pattern and not re.fullmatch(pattern, val, re.IGNORECASE):
            continue
        return suggestion

    return ""
