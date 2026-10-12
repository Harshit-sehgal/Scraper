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
                    flags = 0 if pname == "code_3letter" else re.IGNORECASE
                    if output_type == "number":
                        if re.fullmatch(pattern, value, re.IGNORECASE):
                            matched_type = output_type
                            break
                    elif re.search(pattern, value, flags):
                        matched_type = output_type
                        break
                except re.error as exc:
                    logger.debug("Skipping invalid regex pattern %r: %s", pattern, exc)
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
        flags = 0 if "[A-Z]" in pattern else re.IGNORECASE
        if pattern and not re.fullmatch(pattern, val, flags):
            continue
        return suggestion

    return ""


_DOM_FIELD_STOPWORDS = {
    "aria",
    "card",
    "content",
    "container",
    "data",
    "div",
    "field",
    "group",
    "item",
    "list",
    "md",
    "record",
    "row",
    "sm",
    "span",
    "text",
    "value",
    "xs",
}

_DOM_FIELD_SYNONYMS = {
    "amount": "price",
    "area": "area",
    "arr": "arrival_time",
    "arrival": "arrival_time",
    "author": "author",
    "capital": "capital",
    "cost": "price",
    "currency": "price",
    "dep": "departure_time",
    "departure": "departure_time",
    "description": "description",
    "fee": "price",
    "image": "image_url",
    "img": "image_url",
    "in-stock": "availability",
    "instock": "availability",
    "label": "name",
    "latitude": "latitude",
    "link": "url",
    "longitude": "longitude",
    "population": "population",
    "product": "name",
    "region": "region",
    "reputation": "reputation",
    "score": "rating",
    "sku": "sku",
    "star": "rating",
    "stars": "rating",
    "status": "availability",
    "summary": "description",
    "tag": "tag",
    "tags": "tag",
    "title": "name",
    "username": "username",
}

_DOM_LIST_FIELD_NAMES = {
    "amenity",
    "category",
    "feature",
    "keyword",
    "label",
    "skill",
    "tag",
}

_DOM_NUMERIC_LABELS = {
    "area",
    "capacity",
    "count",
    "distance",
    "height",
    "length",
    "population",
    "size",
    "volume",
    "weight",
    "width",
}


def _dom_tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", value.lower()) if token]


def _dom_field_name(element: Any, value: str) -> str:
    """Infer a stable field name from DOM semantics, not page-specific values."""
    # Structured-data annotations are stronger than presentation classes.
    # Keep ``text`` valid here even though it is a class stopword: the
    # stopword only prevents generic class names from becoming fields.
    for token in _dom_tokens(str(element.get("itemprop", ""))):
        if token in _DOM_FIELD_SYNONYMS:
            return _DOM_FIELD_SYNONYMS[token]
        if token in {"availability", "description", "email", "location", "name", "phone", "price", "rating", "text", "url"}:
            return token

    semantic_values = [element.get(attr, "") for attr in ("aria-label", "data-label", "data-name", "name", "id", "class")]
    for token in (token for raw in semantic_values for token in _dom_tokens(str(raw))):
        if token in _DOM_FIELD_SYNONYMS:
            return _DOM_FIELD_SYNONYMS[token]
        if token in _DOM_FIELD_STOPWORDS or token.isdigit():
            continue
        if token in {"availability", "description", "email", "location", "name", "phone", "price", "rating", "url"}:
            return token

    if element.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return "name"
    if element.name == "img":
        return "image_url"
    if element.name == "a" and element.get("href"):
        return "url"

    value_type = _classify_value(value)
    return {
        "currency": "price",
        "date": "date",
        "email": "email",
        "location": "location",
        "phone": "phone_number",
        "rating": "rating",
        "url": "url",
    }.get(value_type, "")


def _dom_relative_selector(element: Any, container: Any | None = None, *, allow_multiple: bool = False) -> str:
    """Build a selector scoped to the repeating item container."""
    tag = element.name or "*"
    classes = [cls for cls in element.get("class", []) if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", str(cls))]
    if classes:
        base_selector = f"{tag}.{'.'.join(classes[:3])}"
    elif element.get("id") and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", str(element["id"])):
        base_selector = f"{tag}#{element['id']}"
    else:
        base_selector = tag

    # A repeated semantic class can occur more than once in one record (for
    # example a rank cell and a title cell). Build a relative path only when
    # the simple selector is ambiguous, preserving readable selectors for the
    # common one-match case.
    if container is not None:
        try:
            if len(container.select(base_selector)) > 1 and not allow_multiple:
                parts: list[str] = []
                current = element
                while current is not None and current is not container:
                    current_tag = current.name or "*"
                    current_classes = [
                        cls for cls in current.get("class", []) if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", str(cls))
                    ]
                    current_selector = f"{current_tag}.{'.'.join(current_classes[:3])}" if current_classes else current_tag
                    parent = getattr(current, "parent", None)
                    if parent is not None:
                        siblings = parent.find_all(current_tag, recursive=False)
                        if len(siblings) > 1:
                            current_selector += f":nth-of-type({siblings.index(current) + 1})"
                    parts.append(current_selector)
                    current = parent
                if parts:
                    return " > ".join(reversed(parts))
        except (AttributeError, IndexError, TypeError, ValueError):
            pass

    return base_selector


def _dom_label_name(label: str, fallback: str) -> str:
    """Turn a visible key/value label into a stable, descriptive field name."""
    tokens = _dom_tokens(label)
    return "_".join(tokens[:12]) or fallback


def _direct_list_item_text(container: Any) -> str:
    """Read a list item's own text without nested list records."""
    parts: list[str] = []
    for child in container.children:
        child_name = getattr(child, "name", None)
        if child_name in {"ul", "ol"}:
            continue
        text = child if child_name is None else child.get_text(" ", strip=True)
        if text and str(text).strip():
            parts.append(str(text).strip())
    return " ".join(parts)


def _classify_labeled_value(label: str, value: str) -> str:
    """Use an explicit numeric label to preserve numeric measurements with units."""
    value_type = _classify_value(value)
    if (
        value_type == "string"
        and _DOM_NUMERIC_LABELS.intersection(_dom_tokens(label))
        and re.match(
            r"^\s*[\d,.]+(?:\s|$)",
            value,
        )
    ):
        return "number"
    return value_type


def _key_value_field(
    label: str,
    value: str,
    selector: str,
    *,
    seen_names: dict[str, int],
) -> dict[str, Any]:
    """Build one labeled field without guessing from page-wide patterns."""
    base_name = _dom_label_name(label, "field")
    name_count = seen_names.get(base_name, 0) + 1
    seen_names[base_name] = name_count
    name = base_name if name_count == 1 else f"{base_name}_{name_count}"
    return {
        "name": name,
        "type": _classify_labeled_value(label, value),
        "selector": selector,
        "example_value": value,
        "confidence": 0.95,
        "description": f"Value for {label.strip() or name.replace('_', ' ')}",
    }


def _infer_key_value_fields(
    soup: Any,
    container_selector: str,
    max_fields: int,
) -> list[dict[str, Any]]:
    """Infer fields from explicit definition-list or two-column labels."""
    fields: list[dict[str, Any]] = []
    seen_names: dict[str, int] = {}

    if container_selector == "dl":
        for container in soup.select("dl"):
            direct_terms = container.find_all(["dt", "dd"], recursive=False)
            dd_index = 0
            for index, term in enumerate(direct_terms):
                if term.name != "dt":
                    continue
                value_node = next((candidate for candidate in direct_terms[index + 1 :] if candidate.name == "dd"), None)
                if value_node is None:
                    continue
                label = term.get_text(" ", strip=True)
                value = value_node.get_text(" ", strip=True)
                if not label or not value:
                    continue
                dd_index += 1
                fields.append(
                    _key_value_field(
                        label,
                        value,
                        f"dd:nth-of-type({dd_index})",
                        seen_names=seen_names,
                    ),
                )
                if len(fields) >= max_fields:
                    return fields
        return fields

    if container_selector in {"table", "table tr"}:
        rows = soup.select("table tr")
        for row_index, row in enumerate(rows):
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) != 2 or any(cell.name == "th" for cell in cells):
                continue
            label = cells[0].get_text(" ", strip=True)
            value = cells[1].get_text(" ", strip=True)
            if not label or not value:
                continue
            if container_selector == "table":
                parent = getattr(row, "parent", None)
                sibling_rows = parent.find_all("tr", recursive=False) if parent is not None else []
                sibling_index = sibling_rows.index(row) + 1 if row in sibling_rows else row_index + 1
                parent_name = parent.name if parent is not None else ""
                parent_selector = f"{parent_name} > " if parent_name in {"tbody", "thead", "tfoot"} else ""
                selector = f"{parent_selector}tr:nth-of-type({sibling_index}) > td:nth-of-type(2)"
            else:
                selector = "td:nth-of-type(2)"
            fields.append(
                _key_value_field(label, value, selector, seen_names=seen_names),
            )
            if len(fields) >= max_fields:
                return fields

    return fields


def _select_dom_field_element(name: str, elements: list[Any]) -> Any:
    """Choose the least noisy representative element for one field.

    A semantic wrapper often contains both the requested value and display
    metadata (for example a headline link plus its source label). Name fields
    should use the entity link or heading rather than the wrapper's aggregate
    text. This remains DOM-driven and does not depend on a particular site.
    """
    if name == "name":
        linked_elements = []
        for element in elements:
            if element.name == "a" and element.get("href") and element.get_text(" ", strip=True):
                linked_elements.append(element)
            linked_elements.extend(link for link in element.find_all("a", href=True) if link.get_text(" ", strip=True))
        if linked_elements:
            return max(linked_elements, key=lambda item: len(item.get_text(" ", strip=True)))

        headings = [element for element in elements if element.name in {"h1", "h2", "h3", "h4", "h5", "h6"}]
        if headings:
            return max(headings, key=lambda item: len(item.get_text(" ", strip=True)))

    leaf_elements = [
        element
        for element in elements
        if not any(child.get_text(" ", strip=True) for child in element.find_all(True, recursive=False))
    ]
    return max(leaf_elements or elements, key=lambda item: len(item.get_text(" ", strip=True)))


def infer_dom_field_suggestions(html: str, container_selector: str, max_fields: int = 20) -> list[dict[str, Any]]:
    """Infer extractable fields from repeated DOM semantics.

    The analyzer uses this deterministic pass as the safety floor for its
    field inventory. It only considers values repeated inside the detected
    data container, so navigation, footer text, and page-wide pattern noise
    cannot become suggested result columns merely because they match a regex.
    """
    if not html or not container_selector:
        return []

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select(container_selector)
    if not containers:
        return []

    if "tr" in container_selector.lower():
        header_row = next((row for row in soup.find_all("tr") if row.find_all("th")), None)
        if header_row is not None:
            headers = [cell.get_text(" ", strip=True) for cell in header_row.find_all("th")]
            data_rows = [row for row in soup.find_all("tr") if not row.find_all("th") and row.find_all("td")]
            table_fields: list[dict[str, Any]] = []
            for index, header in enumerate(headers):
                tokens = _dom_tokens(header)
                name = "_".join(tokens) or f"column_{index + 1}"
                values = []
                for row in data_rows:
                    cells = row.find_all("td", recursive=False) or row.find_all("td")
                    if index < len(cells):
                        value = cells[index].get_text(" ", strip=True)
                        if value:
                            values.append(value)
                if not values:
                    continue
                coverage = len(values) / max(len(data_rows), 1)
                if coverage < 0.5:
                    continue
                table_fields.append(
                    {
                        "name": name,
                        "type": _classify_value(values[0]),
                        "selector": f"td:nth-of-type({index + 1})",
                        "example_value": values[0],
                        "confidence": round(min(0.98, 0.75 + 0.2 * coverage), 2),
                        "description": f"Table column {header or index + 1}",
                    },
                )
            return table_fields[:max_fields]

        key_value_fields = _infer_key_value_fields(soup, container_selector, max_fields)
        if key_value_fields:
            return key_value_fields

    if container_selector == "dl":
        key_value_fields = _infer_key_value_fields(soup, container_selector, max_fields)
        if key_value_fields:
            return key_value_fields

    if container_selector == "table":
        key_value_fields = _infer_key_value_fields(soup, container_selector, max_fields)
        if key_value_fields:
            return key_value_fields

    candidates: dict[str, dict[str, Any]] = {}
    sampled_containers = containers[:100]
    required_coverage = 1 if len(sampled_containers) == 1 else max(2, (len(sampled_containers) + 1) // 2)
    ignored_tags = {"button", "form", "img", "input", "meta", "option", "script", "select", "style", "svg"}

    for container in sampled_containers:
        per_container: dict[str, tuple[int, list[Any]]] = {}
        for element in container.find_all(True):
            value = element.get_text(" ", strip=True)
            if not value or len(value) > 240:
                continue
            name = _dom_field_name(element, value)
            if not name or element.name in ignored_tags:
                continue
            direct_children = element.find_all(True, recursive=False)
            has_child_values = bool(direct_children and any(child.get_text(" ", strip=True) for child in direct_children))
            # A semantically named leaf (including anchors such as tags) is
            # more useful than its aggregate parent. Unnamed layout parents
            # remain excluded so wrappers do not become result fields.
            priority = 1 if not has_child_values else 0
            existing = per_container.get(name)
            if existing and priority < existing[0]:
                continue
            if existing and priority == existing[0]:
                existing[1].append(element)
            else:
                per_container[name] = (priority, [element])

        # A plain list item is itself the record. Expose its visible text only
        # when no stronger semantic field exists, keeping the fallback scoped
        # to the item and away from page-wide prose or regex matches.
        if getattr(container, "name", "") == "li" and (not per_container or set(per_container).issubset({"url"})):
            item_text = _direct_list_item_text(container)
            if item_text:
                text_field = candidates.setdefault(
                    "text",
                    {
                        "name": "text",
                        "type": "string",
                        "selector": ":scope",
                        "example_value": item_text,
                        "_values": [],
                        "_is_list": False,
                    },
                )
                text_field["_values"].append(item_text)

        for name, (_priority, elements) in per_container.items():
            is_list = name in _DOM_LIST_FIELD_NAMES and len(elements) > 1
            element = elements[0] if is_list else _select_dom_field_element(name, elements)
            value = element.get_text(" ", strip=True)
            selector = _dom_relative_selector(element, container, allow_multiple=is_list)
            field = candidates.setdefault(
                name,
                {
                    "name": name,
                    "type": _classify_value(value),
                    "selector": selector,
                    "example_value": value,
                    "_values": [],
                    "_is_list": False,
                },
            )
            field["_values"].append(value)
            field["_is_list"] = field["_is_list"] or is_list

    # Article/main prose is an explicitly scoped content region. Expose all
    # paragraphs as one list-valued field, while leaving nav/footer prose out
    # of the analyzer inventory and the eventual result projection.
    if container_selector == "body" and "description" not in candidates:
        content_roots = [("article", node) for node in soup.find_all("article") if node.find("p") is not None]
        if len(content_roots) != 1:
            content_roots = [
                ("main", node) for node in soup.find_all("main") if node.find("h1") is not None and node.find("p") is not None
            ]
        if len(content_roots) == 1:
            root_selector, content_root = content_roots[0]
            paragraphs = [node.get_text(" ", strip=True) for node in content_root.find_all("p")]
            paragraphs = [value for value in paragraphs if value]
            if paragraphs:
                candidates["description"] = {
                    "name": "description",
                    "type": "list_string",
                    "selector": f"{root_selector} p",
                    "example_value": paragraphs[0],
                    "_values": [paragraphs[0]],
                    "_is_list": True,
                }

    suggestions: list[dict[str, Any]] = []
    for field in candidates.values():
        values = field.pop("_values")
        is_list = field.pop("_is_list", False)
        if len(values) < required_coverage:
            continue
        field_type = field["type"]
        if field["name"] in {"availability", "rating", "price", "image_url", "name", "url"}:
            field_type = {
                "availability": "boolean",
                "image_url": "url",
                "name": "string",
                "price": "currency",
                "rating": "rating",
                "url": "url",
            }.get(field["name"], field_type)
            field["type"] = field_type
        elif is_list:
            field["type"] = "list_string"
        field["confidence"] = round(min(0.98, 0.75 + 0.2 * len(values) / max(len(containers), 1)), 2)
        field["description"] = f"Repeated {field['name'].replace('_', ' ')} value in the data container"
        suggestions.append(field)

    suggestions.sort(key=lambda field: (-field["confidence"], field["name"]))
    return suggestions[:max_fields]
