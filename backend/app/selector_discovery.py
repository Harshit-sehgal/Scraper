"""
Selector Discovery — LLM-guided CSS selector generation.

Extracted from scraper.py to isolate LLM-related orchestration.
"""

from __future__ import annotations

import logging
import time
from app.config import settings
from app.html_utils import clean_html_for_selectors
from app.llm_bridge import llm_json, reset_llm_call_count
from app.models import SchemaField
from app.page_profiler import detect_page_structure, detect_value_patterns
from app.motif_feedback import MotifFeedbackEngine
from app.strategy_evolution import FetchStrategy

logger = logging.getLogger(__name__)


def _analyze_page_data_type(html: str, schema_fields: list[SchemaField]) -> dict:
    """Analyze high-level page structure and value patterns to guide LLM discovery."""
    profile = detect_page_structure(html)
    patterns = detect_value_patterns(html)

    return {
        "structure_type": profile.structure_type,
        "structure_confidence": profile.structure_confidence,
        "headers": profile.headers,
        "patterns_detected": {
            "currencies": bool(patterns.currencies),
            "dates": bool(patterns.dates),
            "ratings": bool(patterns.ratings),
            "codes": bool(patterns.codes_3letter),
            "phones": bool(patterns.phones),
            "emails": bool(patterns.emails),
            "numbers": bool(patterns.numbers),
            "durations": bool(patterns.durations),
            "urls": bool(patterns.urls),
            "weights": bool(patterns.weights),
            "percentages": bool(patterns.percentages),
            "times": bool(patterns.times),
            "booleans": bool(patterns.booleans),
            "dimensions": bool(patterns.dimensions),
            "quantities": bool(patterns.quantities),
            "product_codes": bool(patterns.product_codes),
            "units": bool(patterns.units),
            "addresses": bool(patterns.address_fragments),
        }
    }


def build_selector_prompt(html_snippet: str, schema_fields: list[SchemaField], page_analysis: dict | None = None, solidified_motifs: list | None = None) -> str:
    """Construct the prompt for selector discovery via LLM.
    
    Args:
        html_snippet: The HTML to extract from
        schema_fields: Target schema fields
        page_analysis: Optional page structure analysis
        solidified_motifs: Optional learned structural patterns for autonomous adaptation
    """
    page_analysis = page_analysis or {}
    
    structure_type = page_analysis.get("structure_type", "unknown")
    structure_confidence = page_analysis.get("structure_confidence", 0.0)
    headers = page_analysis.get("headers", [])
    patterns = page_analysis.get("patterns_detected", {})
    
    # Generate motif feedback context if available
    motif_context = ""
    if solidified_motifs:
        feedback_engine = MotifFeedbackEngine()
        motif_hint = feedback_engine.build_motif_context(solidified_motifs, schema_fields)
        if motif_hint:
            motif_context = "\n" + motif_hint + "\n"
    
    structure_context = f"""
PAGE STRUCTURE DETECTED: {structure_type.upper()} (confidence: {structure_confidence:.2f})
- This could be a table, card layout, list, or mixed structure
- Target the DATA CONTAINER, not header/footer/navigation
- For card-based layouts: look for repeating divs with classes like card, item, result, flight-result, product, listing
- For tables: target <tr> rows inside <tbody>, skip the <thead> header rows
- The data container should contain MULTIPLE repeating items, each with the same structure
"""
    
    if patterns:
        detected = [k for k, v in patterns.items() if v]
        if detected:
            structure_context += f"\nVALUE PATTERNS DETECTED: {', '.join(detected)}"
    
    header_context = ""
    if headers:
        header_context = f"\nDETECTED HEADERS: {headers[:8]}"
    
    field_hints = []
    for f in schema_fields:
        hint = f'  - "{f.name}"'
        hint += f' (type: {f.field_type.value})'
        if f.description:
            hint += f': {f.description}'
        field_hints.append(hint)

    schema_str = "\n".join(field_hints)

    return f"""You are an expert data extraction engineer.
Extract structured data from this HTML snippet.

{structure_context}
{motif_context}{header_context}

USER SCHEMA:
{schema_str}

CRITICAL EXCLUSIONS (apply to ANY page type):
- Navigation menus, header, footer
- Filter/sort options, sidebar content
- Login/signup forms, social media links
- Copyright/terms/privacy pages

EXTRACTION RULES:
1. Return ONLY JSON: {{"item_container": "selector", "fields": {{"field_name": "selector"}}}}
2. Target the repeating DATA CONTAINER (rows, cards, items) - NOT navigation.
3. Use relative selectors (descendant or child) that work INSIDE the item_container.
4. Include EVERY distinct data column visible in each item (descriptive snake_case keys).
   Map user schema fields when possible, AND add any extra columns found (e.g. stops, return_date, rating).
5. VERIFY FIELD SEMANTICS: Ensure each selector points at the correct value type for its key name.
6. If multiple elements could match, choose the most specific one.
7. Use null only for fields that cannot be found.

HTML SNIPPET:
```html
{html_snippet}
```"""


async def discover_selectors(
    html: str,
    schema_fields: list[SchemaField],
    solidified_motifs: list | None = None,
) -> dict:
    """Analyze page structure and map schema to CSS selectors via LLM.
    
    Args:
        html: Page HTML content
        schema_fields: Target schema fields to extract
        solidified_motifs: Optional learned structural patterns for autonomous adaptation
    """
    # 1. Analyze page structure
    page_analysis = _analyze_page_data_type(html, schema_fields)

    # 2. Map schema to CSS selectors via LLM
    html_snippet = clean_html_for_selectors(html)
    prompt = build_selector_prompt(html_snippet, schema_fields, page_analysis, solidified_motifs)

    try:
        selectors = await llm_json(messages=[
            {
                "role": "system",
                "content": (
                    "You output valid JSON objects for CSS selector extraction. "
                    "No markdown, no commentary."
                ),
            },
            {"role": "user", "content": prompt}
        ], timeout=settings.LLM_SELECTOR_TIMEOUT)
        
        if not isinstance(selectors, dict):
            logger.warning("[SelectorDiscovery] LLM returned non-dict response")
            return {}
            
        return selectors
    except Exception as e:
        logger.exception("[SelectorDiscovery] LLM extraction failed: %s", e)
        return {}


# ─── URL Analyzer — Auto-Detect Fields from a URL ────────────────────────

import re
from bs4 import BeautifulSoup


def _extract_container_text_values(html: str, container_selector: str) -> list[str]:
    """Extract meaningful, distinct text values from the first data container.
    
    Walks the container's DOM tree collecting leaf-level text values
    (short, individual text nodes) rather than concatenated full text.
    Also collects img alt texts.
    """
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select(container_selector)
    
    # Fallback: scan all visible elements
    if not containers:
        containers = [soup]
    
    container = containers[0]
    values = []
    seen = set()
    
    for tag in container.find_all(True):
        if tag.name in ('script', 'style', 'noscript', 'svg', 'form', 'nav', 'footer', 'header'):
            continue
        
        text = tag.get_text(strip=True)
        if not text or len(text) < 2:
            continue
        
        norm = text.lower()
        if norm in seen:
            continue
        seen.add(norm)
        
        # Skip if this tag's text is entirely from a single child (not a leaf)
        children = tag.find_all(True, recursive=False)
        if len(children) == 1:
            child_text = children[0].get_text(strip=True)
            if child_text and child_text == text:
                continue
        
        # Skip very long text (likely descriptions, not field values)
        if len(text) > 100:
            continue
        
        values.append(text)
    
    # Add alt texts from images
    for img in container.find_all('img'):
        alt = img.get('alt', '').strip()
        if alt and len(alt) > 2 and alt.lower() not in seen:
            seen.add(alt.lower())
            values.append(alt)
    
    return values


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
    # This prevents "£450" from being classified as "number" because
    # the number regex matches the "450" substring.
    # Also date before phone because phone patterns can match date strings
    # like "30-05-2026" (digits + dashes).
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
                    # For generic "number" pattern, use fullmatch to avoid
                    # matching numeric substrings in mixed values like "BA123".
                    # For all other patterns, search is fine.
                    if output_type == "number":
                        if re.fullmatch(pattern, value, re.IGNORECASE):
                            matched_type = output_type
                            break
                    else:
                        if re.search(pattern, value, re.IGNORECASE):
                            matched_type = output_type
                            break
                except re.error:
                    continue
            if matched_type:
                break
        if matched_type:
            break
    
    # Map internal type names → standard types
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
    
    # No specific pattern matched
    return "string"


def _value_patterns_to_field_types(patterns) -> list[dict]:
    """Map detected value patterns to generic field type suggestions.
    
    Returns a list of {type, confidence, example, description} dicts without
    assuming specific field names — the LLM will determine field names from context.
    """
    suggestions = []
    if patterns.currencies:
        suggestions.append({
            "type": "currency", "confidence": 0.9,
            "example": patterns.currencies[0],
            "description": "Monetary values detected on page",
        })
    if patterns.dates:
        suggestions.append({
            "type": "date", "confidence": 0.9,
            "example": patterns.dates[0],
            "description": "Date values detected on page",
        })
    if patterns.times:
        suggestions.append({
            "type": "time", "confidence": 0.75,
            "example": patterns.times[0],
            "description": "Time values detected on page",
        })
    if patterns.ratings:
        suggestions.append({
            "type": "rating", "confidence": 0.85,
            "example": patterns.ratings[0],
            "description": "Rating or score values detected on page",
        })
    if patterns.emails:
        suggestions.append({
            "type": "email", "confidence": 0.95,
            "example": patterns.emails[0],
            "description": "Email addresses detected on page",
        })
    if patterns.phones:
        suggestions.append({
            "type": "phone", "confidence": 0.9,
            "example": patterns.phones[0],
            "description": "Phone numbers detected on page",
        })
    if patterns.codes_3letter or patterns.airport_codes:
        suggestions.append({
            "type": "code", "confidence": 0.75,
            "example": (patterns.airport_codes or patterns.codes_3letter)[0],
            "description": "Short codes (3-letter) detected on page",
        })
    if patterns.durations:
        suggestions.append({
            "type": "string", "confidence": 0.8,
            "example": patterns.durations[0],
            "description": "Duration values detected on page",
        })
    if patterns.urls:
        suggestions.append({
            "type": "url", "confidence": 0.85,
            "example": patterns.urls[0],
            "description": "URL/website values detected on page",
        })
    if patterns.weights:
        suggestions.append({
            "type": "string", "confidence": 0.8,
            "example": patterns.weights[0],
            "description": "Weight values detected on page",
        })
    if patterns.percentages:
        suggestions.append({
            "type": "percentage", "confidence": 0.8,
            "example": patterns.percentages[0],
            "description": "Percentage values detected on page",
        })
    if patterns.booleans:
        suggestions.append({
            "type": "boolean", "confidence": 0.85,
            "example": patterns.booleans[0],
            "description": "Boolean/status values detected on page",
        })
    if patterns.dimensions:
        suggestions.append({
            "type": "string", "confidence": 0.75,
            "example": patterns.dimensions[0],
            "description": "Dimension/size values detected on page",
        })
    if patterns.quantities:
        suggestions.append({
            "type": "string", "confidence": 0.75,
            "example": patterns.quantities[0],
            "description": "Quantity/pack size values detected on page",
        })
    if patterns.product_codes:
        suggestions.append({
            "type": "code", "confidence": 0.8,
            "example": patterns.product_codes[0],
            "description": "Product/SKU codes detected on page",
        })
    if patterns.units:
        suggestions.append({
            "type": "string", "confidence": 0.75,
            "example": patterns.units[0],
            "description": "Unit type indicators detected on page",
        })
    if patterns.address_fragments:
        suggestions.append({
            "type": "location", "confidence": 0.8,
            "example": patterns.address_fragments[0],
            "description": "Address/location values detected on page",
        })
    return suggestions


def build_url_analysis_prompt(values: list[str], page_analysis: dict) -> str:
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
        rows.append(f"  #{i:<3} \"{val}\"  type: {vtype}")
    
    value_block = "\n".join(rows)

    few_shot = """
=== EXAMPLE ===
Input values from a flight search page:
  #1   "New York"           type: location
  #2   "JFK"                type: code
  #3   "London-Stansted"    type: location
  #4   "STN"                type: code
  #5   "\u00a3450"          type: currency
  #6   "30/05/2026"         type: date
  #7   "2h 30m"             type: string
  #8   "British Airways"    type: string
  #9   "BA178"              type: code
  #10  "08:30"              type: time
  #11  "11:00"              type: time

Expected output:
{"page_type": "cards", "estimated_record_count": 24, "fields": [
  {"name": "origin_city", "type": "location", "example_value": "New York", "confidence": 0.95, "description": "Departure city"},
  {"name": "departure_airport", "type": "code", "example_value": "JFK", "confidence": 0.95, "description": "Departure airport code"},
  {"name": "destination_city", "type": "location", "example_value": "London-Stansted", "confidence": 0.95, "description": "Arrival city and airport"},
  {"name": "arrival_airport", "type": "code", "example_value": "STN", "confidence": 0.95, "description": "Arrival airport code"},
  {"name": "price", "type": "currency", "example_value": "\u00a3450", "confidence": 0.95, "description": "Ticket price"},
  {"name": "travel_date", "type": "date", "example_value": "30/05/2026", "confidence": 0.95, "description": "Date of travel"},
  {"name": "duration", "type": "string", "example_value": "2h 30m", "confidence": 0.85, "description": "Flight duration"},
  {"name": "airline_name", "type": "string", "example_value": "British Airways", "confidence": 0.95, "description": "Airline operating the flight"},
  {"name": "flight_number", "type": "code", "example_value": "BA178", "confidence": 0.95, "description": "Flight number"},
  {"name": "departure_time", "type": "time", "example_value": "08:30", "confidence": 0.95, "description": "Scheduled departure time"},
  {"name": "arrival_time", "type": "time", "example_value": "11:00", "confidence": 0.95, "description": "Scheduled arrival time"}
]}
=== END EXAMPLE ===
"""

    return f"""You are a data schema designer. Name each data field found on this webpage.

I extracted these values from ONE data row on this {structure_type.upper()} page (confidence: {structure_confidence:.0%}):

{value_block}

{few_shot}

For EACH value, assign a descriptive snake_case field name.
Determine its data type from: string, number, currency, email, phone, url, date, time, rating, boolean, percentage, location, code.

CRITICAL: NEVER use type names as field names.
  \u2716 BAD: {{"name": "string"}} or {{"name": "code"}} or {{"name": "time"}} or {{"name": "text"}} or {{"name": "number"}} or {{"name": "date"}} or {{"name": "currency"}}
  \u2714 GOOD: {{"name": "airline_name"}} or {{"name": "flight_number"}} or {{"name": "departure_time"}} or {{"name": "price"}}

Differentiate duplicate types — if two values share the same type, give them distinct context-specific names (e.g. "origin_airport_code" vs "destination_airport_code" instead of "code" and "code").

Look at each value carefully and infer its contextual meaning. For example:
- A 3-letter uppercase word like "LHR" or "JFK" is likely an airport code, name it "origin_airport_code" or "destination_airport_code"
- A city name like "London" or "New York" is a location, name it "origin_city" or "destination_city"
- A monetary value like "$450" or "\u00a3450" is a price, name it "price", "total_price", or "fee"
- A short time like "08:30" or "14:00" is a time, name it "departure_time" or "arrival_time"
- A date like "30/05/2026" is a date, name it "departure_date", "travel_date", or "return_date"

Return ONLY JSON — NO markdown, NO commentary:
{{
  "page_type": "{structure_type}",
  "estimated_record_count": 24,
  "fields": [
    {{
      "name": "descriptive_field_name",
      "type": "string",
      "example_value": "actual value from HTML",
      "confidence": 0.95,
      "description": "What this field represents"
    }}
  ]
}}"""


# ─── Generic field name post-processing ───────────────────────────────────

_GENERIC_NAMES: set[str] = {
    # Pure type names that should never be field identifiers
    "string", "text", "number", "integer", "float", "boolean", "bool",
    "code", "date", "time", "currency", "email", "phone", "url",
    "website", "rating", "location", "address", "percentage",
    "list", "object", "field",
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
            # Try to infer a better name from the example value
            better = _infer_field_name(example, ftype)
            if better:
                name = better
                f["name"] = better
                f["description"] = f.get("description", "") or better.replace("_", " ").title()
        
        # Deduplicate names (e.g. two "string" fields → "field_1", "field_2")
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
# Maps (type, example_value_pattern) → suggested field name
_FIELD_NAME_HINTS: list[tuple[str, str, str]] = [
    # Currency values
    ("currency", "", "price"),
    # 3-letter uppercase codes (airport codes)
    ("code", "^[A-Z]{3}$", "airport_code"),
    # 2-letter uppercase codes
    ("code", "^[A-Z]{2}$", "code_abbreviation"),
    # Mixed letter-digit codes (flight numbers, product codes)
    ("code", "", "reference_code"),
    # Date values
    ("date", "", "date"),
    # Time values
    ("time", "", "time"),
    # Email
    ("email", "", "email"),
    # Phone
    ("phone", "", "phone_number"),
    # Location/city names (capitalized proper nouns like "London")
    ("location", "[A-Z][a-z]+", "city_name"),
    # URLs
    ("url", "", "website_url"),
    # Ratings
    ("rating", "", "rating"),
    # Percentages
    ("percentage", "", "percentage"),
    # Booleans
    ("boolean", "", "flag"),
    # Numbers by themselves
    ("number", "", "value"),
]


def _infer_field_name(example_value: str, field_type: str) -> str:
    """Try to infer a descriptive field name from an example value and type.
    
    Returns an empty string if no good inference is possible.
    """
    if not example_value:
        return ""
    
    val = example_value.strip()
    
    # Check specific patterns first
    for pattern_type, pattern, suggestion in _FIELD_NAME_HINTS:
        if field_type != pattern_type:
            continue
        if pattern and not re.fullmatch(pattern, val, re.IGNORECASE):
            continue
        return suggestion
    
    return ""


async def analyze_url_for_fields(url: str) -> dict:
    """Analyze a URL and auto-detect what data fields can be extracted.
    
    This is the core of the "preview URL → suggest fields" workflow.
    
    1. Fetches the URL using anti-bot stealth headers
    2. Analyzes page structure (table/cards/list/mixed)
    3. Detects value patterns (currencies, dates, ratings, etc.)
    4. Uses LLM to discover all data fields and their selectors
    5. Returns suggested fields with types, confidence, and example values
    
    Args:
        url: The URL to analyze
        
    Returns:
        dict with:
        - url: str
        - page_structure: str (table|cards|list|mixed)
        - structure_confidence: float
        - estimated_record_count: int
        - item_container: str (CSS selector)
        - suggested_fields: list of field suggestions
        - anti_bot_score: float
    """
    from app.html_utils import fetch_page_content as _fetch_page_content
    from app.scrape_telemetry import detect_anti_bot
    
    reset_llm_call_count()
    start_time = time.time()
    
    logger.info("[URLAnalyzer] Fetching and analyzing: %s", url)
    
    # Step 1: Fetch the URL with anti-bot stealth
    try:
        html, js_render_delay, fetch_method, retry_count = await _fetch_page_content(
            url, preferred_method=FetchStrategy.PLAYWRIGHT_FULL
        )
    except Exception as e:
        logger.error("[URLAnalyzer] Failed to fetch %s: %s", url, e)
        return {
            "url": url,
            "error": f"Failed to fetch URL: {str(e)}",
            "page_structure": "unknown",
            "structure_confidence": 0.0,
            "estimated_record_count": 0,
            "item_container": None,
            "suggested_fields": [],
            "anti_bot_score": 0.0,
        }
    
    if not html or len(html.strip()) < 100:
        return {
            "url": url,
            "error": "Fetched page appears empty",
            "page_structure": "unknown",
            "structure_confidence": 0.0,
            "estimated_record_count": 0,
            "item_container": None,
            "suggested_fields": [],
            "anti_bot_score": 0.0,
        }
    
    # Step 2: Check anti-bot score
    anti_bot_score = detect_anti_bot(html)
    
    # Step 3: Analyze page structure and value patterns
    profile = detect_page_structure(html)
    patterns = detect_value_patterns(html)
    
    page_analysis = {
        "structure_type": profile.structure_type,
        "structure_confidence": profile.structure_confidence,
        "headers": profile.headers,
    }
    
    # Step 4: Extract container values and build structured prompt
    # Instead of sending raw HTML to the LLM (which overwhelms it and causes
    # generic type names), we pre-extract individual text values from the
    # data container, classify each by type, and send ONLY structured pairs.
    container_values = _extract_container_text_values(html, profile.container_selector)
    
    # If we got very few values from the container, fall back to scanning
    # visible page text for individual values
    if len(container_values) < 3:
        soup = BeautifulSoup(html, "html.parser")
        for noise in soup(['script', 'style', 'nav', 'footer', 'header', 'noscript', 'svg', 'form']):
            noise.decompose()
        visible_text = soup.get_text(separator=" ", strip=True)
        # Split into short meaningful chunks and classify each
        chunks = []
        for tok in visible_text.split():
            tok = tok.strip()
            if tok and len(tok) > 1 and len(tok) < 80 and tok not in chunks:
                chunks.append(tok)
        container_values = chunks[:40]
    
    prompt = build_url_analysis_prompt(container_values, page_analysis)
    
    try:
        result = await llm_json(messages=[
            {
                "role": "system",
                "content": (
                    "You output valid JSON objects for data schema design. "
                    "No markdown, no commentary. Return ONLY the JSON."
                ),
            },
            {"role": "user", "content": prompt}
        ], temperature=settings.URL_ANALYZER_TEMPERATURE, timeout=settings.LLM_SELECTOR_TIMEOUT)
    except Exception as e:
        logger.exception("[URLAnalyzer] LLM analysis failed for %s: %s", url, e)
        result = None
    
    # Step 5: Build structured response
    field_type_map = {
        "string": "string",
        "text": "string",
        "number": "number",
        "float": "float",
        "integer": "integer",
        "int": "integer",
        "boolean": "boolean",
        "bool": "boolean",
        "email": "email",
        "phone": "phone",
        "url": "url",
        "website": "url",
        "date": "date",
        "currency": "currency",
        "price": "currency",
        "rating": "rating",
        "location": "location",
        "address": "location",
        "percentage": "percentage",
        "list": "list_string",
        "code": "code",
        "time": "time",
    }
    
    suggested_fields = []
    if result and isinstance(result, dict):
        raw_fields = result.get("fields", [])
        if isinstance(raw_fields, dict):
            # Handle the case where fields come as {name: value} format
            raw_fields = [
                {"name": k, "example_value": v, "type": "string", "confidence": 0.5}
                for k, v in raw_fields.items()
                if isinstance(v, str)
            ]
        
        if isinstance(raw_fields, list):
            for f in raw_fields:
                if not isinstance(f, dict):
                    continue
                name = str(f.get("name", "")).strip()
                if not name:
                    continue
                
                raw_type = str(f.get("type", "string")).lower().strip()
                mapped_type = field_type_map.get(raw_type, "string")
                
                suggested_fields.append({
                    "name": name,
                    "type": mapped_type,
                    "selector": "",  # Selectors determined by scraper's selector discovery pipeline
                    "example_value": f.get("example_value", ""),
                    "confidence": min(float(f.get("confidence", 0.5)), 1.0),
                    "description": str(f.get("description", "")),
                })
    
    # If LLM returned no fields, use pattern analysis as fallback
    if not suggested_fields:
        for hint in _value_patterns_to_field_types(patterns):
            suggested_fields.append({
                "name": hint["type"],
                "type": hint["type"],
                "selector": "",
                "example_value": hint.get("example", ""),
                "confidence": hint["confidence"],
                "description": hint.get("description", ""),
            })
    
    # Post-processing: rename generic type-name fields to more descriptive names
    suggested_fields = _rename_generic_fields(suggested_fields)
    
    # Sort by confidence descending
    suggested_fields.sort(key=lambda f: f["confidence"], reverse=True)
    
    # Use URL-analyzer-specific field limit
    suggested_fields = suggested_fields[:settings.URL_ANALYZER_MAX_FIELDS]
    
    item_container = profile.container_selector
    estimated_records = 0
    if result and isinstance(result, dict):
        estimated_records = int(result.get("estimated_record_count", 0))

    
    elapsed = time.time() - start_time
    logger.info(
        "[URLAnalyzer] Analyzed %s: %s structure, %d fields suggested, %.1fs",
        url, profile.structure_type, len(suggested_fields), elapsed,
    )
    
    return {
        "url": url,
        "page_structure": profile.structure_type,
        "structure_confidence": profile.structure_confidence,
        "estimated_record_count": estimated_records,
        "item_container": item_container,
        "fetch_method": fetch_method,
        "fetch_time_ms": round((time.time() - start_time) * 1000, 1),
        "anti_bot_score": round(anti_bot_score, 3),
        "suggested_fields": suggested_fields,
    }
