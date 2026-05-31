"""URL analysis, redirect detection, search form recovery, and value classification.

Extracted from selector_discovery.py for modularity.

Ownership boundary: these functions handle URL-level concerns — redirect
detection, search form recovery, value type classification, and field naming.
Page-level DOM analysis lives in the sibling selector_discovery_analysis module.
"""

from __future__ import annotations

import re
import logging
from bs4 import BeautifulSoup
from app.acquisition_state import AcquisitionLineage

logger = logging.getLogger(__name__)


# ─── Redirect Detection ────────────────────────────────────────────────


def _detect_redirect(original_url: str, final_url: str) -> dict:
    """Detect and classify URL redirects by comparing original vs final URL.

    Compares the originally requested URL against the final URL after
    browser navigation to detect redirects and classify them.
    Works with ANY domain — no hardcoded values.

    Classification logic:
    - Same URL (or trailing-slash difference only) → no redirect
    - Different domain / scheme → cross-domain (not flagged as redirect)
    - Final URL is homepage (/) and original had a deep path → homepage redirect
    - Path shortened significantly (deep → shallow) → session / expired token redirect
    - Path changed → generic path_changed redirect

    Args:
        original_url: The URL that was requested
        final_url: The URL after browser navigation (after all redirects)

    Returns:
        dict with:
        - redirected: bool
        - redirect_type: str (none|homepage_redirect|session_expired|path_changed)
        - message: str
        - original_url: str
        - final_url: str
    """
    from urllib.parse import urlparse

    # Normalize trailing slash
    orig_norm = original_url.rstrip("/")
    final_norm = final_url.rstrip("/")

    # Same URL → no redirect
    if orig_norm == final_norm:
        return {
            "redirected": False,
            "redirect_type": "none",
            "message": "No redirect detected — URLs match after normalization",
            "original_url": original_url,
            "final_url": final_url,
        }

    parsed_orig = urlparse(original_url)
    parsed_final = urlparse(final_url)

    # Different domain / scheme — cross-domain navigation, not a site redirect
    if parsed_orig.netloc != parsed_final.netloc:
        return {
            "redirected": False,
            "redirect_type": "none",
            "message": f"Different domain: {
                parsed_orig.netloc} → {
                parsed_final.netloc}",
            "original_url": original_url,
            "final_url": final_url,
        }

    orig_path = parsed_orig.path.rstrip("/")
    final_path = parsed_final.path.rstrip("/")

    orig_segments = [s for s in orig_path.split("/") if s]
    final_segments = [s for s in final_path.split("/") if s]

    # Redirect to homepage (final is "/" or empty)
    if not final_path or final_path == "/":
        # Deep path (3+ segments) redirected to homepage → likely expired
        # session / token
        if len(orig_segments) >= 3:
            return {
                "redirected": True,
                "redirect_type": "session_expired",
                "message": (
                    f"URL redirected to homepage — the search session, token, "
                    f"or page identifier has likely expired. Original path had "
                    f"{len(orig_segments)} segments (/{'/'.join(orig_segments)}), "
                    f"final is the root homepage."
                ),
                "original_url": original_url,
                "final_url": final_url,
            }
        return {
            "redirected": True,
            "redirect_type": "homepage_redirect",
            "message": "URL redirected to the site homepage",
            "original_url": original_url,
            "final_url": final_url,
        }

    # Path changed
    if orig_path != final_path:
        # Deep path → shallow path: likely expired session / token
        if len(orig_segments) >= 3 and len(final_segments) <= 2:
            return {
                "redirected": True,
                "redirect_type": "session_expired",
                "message": (
                    f"URL redirected from a deep path (/{'/'.join(orig_segments)}) "
                    f"to a shallower path (/{'/'.join(final_segments)}) — "
                    f"the session, token, or identifier likely expired."
                ),
                "original_url": original_url,
                "final_url": final_url,
            }
        return {
            "redirected": True,
            "redirect_type": "path_changed",
            "message": f"URL path changed: {orig_path} → {final_path}",
            "original_url": original_url,
            "final_url": final_url,
        }

    return {
        "redirected": False,
        "redirect_type": "none",
        "message": "No redirect detected",
        "original_url": original_url,
        "final_url": final_url,
    }


def build_redirect_info(
    original_url: str,
    final_url: str,
    search_recovery: dict | None = None,
    search_form: dict | None = None,
    search_params: dict[str, str] | None = None,
    fetch_method: str = "",
    existing_redirect_info: dict | None = None,
) -> dict:
    """Build redirect_info dict from an AcquisitionLineage.

    Uses the typed AcquisitionLineage model to determine the correct
    acquisition state, then converts back to the legacy dict format
    for backward compatibility with the API response.

    Args:
        original_url: The URL as originally provided
        final_url: The URL after redirects and recovery
        search_recovery: Result from _try_form_search_recovery (if attempted)
        search_form: Result from _detect_search_form (if detected)
        search_params: User-provided search parameters
        fetch_method: How the page was fetched
        existing_redirect_info: Pre-computed redirect_info dict (if available).
            If provided, uses this instead of re-running _detect_redirect.

    Returns:
        dict with redirected, redirect_type, message, original_url, final_url
    """
    redirect_info = existing_redirect_info or _detect_redirect(original_url, final_url)

    lineage = AcquisitionLineage.from_redirect_info(
        redirect_info=redirect_info,
        original_url=original_url,
        final_url=final_url,
        fetch_method=fetch_method,
        search_recovery=search_recovery,
        search_form=search_form,
        search_params=search_params,
    )

    return lineage.to_dict()


# ─── Content Quality Assessment ────────────────────────────────────────


def _assess_content_quality(html: str, profile) -> dict:
    """Assess whether the fetched page contains meaningful data containers.

    Detects landing pages (hero banners, search forms, welcome text),
    empty / poor pages (no repeating data containers), and pages with real
    extractable data.

    Works with ANY StructureProfile — no domain-specific assumptions.
    When the profile's container selector doesn't find enough data, falls
    back to scanning the page for repeating element patterns generically.

    Args:
        html: The page HTML content
        profile: A StructureProfile object (from page_profiler.detect_page_structure)

    Returns:
        dict with:
        - quality: str (good|low|landing_page)
        - has_data_containers: bool
        - is_landing_page: bool
        - data_container_count: int
        - landing_signals: list of detected landing page indicators
        - message: str
    """
    soup = BeautifulSoup(html, "html.parser")

    # ── Landing Page Detection ──────────────────────────────────────
    landing_signals: list[str] = []

    # Hero / banner sections (generic selectors, no hardcoded domain)
    hero_selectors = [
        ".hero",
        ".banner",
        ".jumbotron",
        ".landing",
        ".cover",
        "[class*='hero']",
        "[class*='banner']",
        "[class*='landing']",
        "[class*='jumbotron']",
    ]
    for sel in hero_selectors:
        try:
            if soup.select(sel):
                landing_signals.append("hero_banner")
                break
        except Exception:
            continue

    # Search forms (generic — any form with text / search input)
    forms = soup.find_all("form")
    search_form_found = False
    for form in forms:
        inputs = form.find_all("input")
        for inp in inputs:
            input_type = inp.get("type", "").lower()
            if input_type in ("", "text", "search"):
                search_form_found = True
                break
        if search_form_found:
            break
    if search_form_found:
        landing_signals.append("search_form")

    # Welcome / landing page text patterns (generic, domain-agnostic)
    body_text = soup.get_text().lower()[:2000]
    welcome_patterns = [
        "welcome",
        "find your",
        "search for",
        "get started",
        "start your",
        "explore",
        "discover",
        "find the best",
        "looking for",
    ]
    for pattern in welcome_patterns:
        if pattern in body_text:
            landing_signals.append(f"landing_text:{pattern}")
            break  # One landing text signal is enough

    # ── Data Container Detection ────────────────────────────────────
    data_container_count = 0
    has_profile_selector = profile is not None and hasattr(profile, "container_selector")
    container_selector = profile.container_selector if has_profile_selector else None

    if container_selector and container_selector != "body":
        try:
            containers = soup.select(container_selector)
            data_container_count = sum(1 for c in containers if len(c.get_text(strip=True)) > 20)
        except Exception:
            pass

    # ── Generic Data Container Discovery (fallback) ─────────────────
    # When profile's container selector finds little, scan for repeating
    # element patterns across the full DOM (no hardcoded selectors).
    if data_container_count < 3:
        from collections import Counter as _Counter

        tag_class_counts: _Counter = _Counter()
        for tag in soup.find_all(True):
            if tag.name in ("script", "style", "noscript", "svg", "form", "nav", "footer", "header"):
                continue
            classes = " ".join(tag.get("class", []) or [])
            if classes:
                key = f"{tag.name}.{'.'.join(classes.split()[:2])}"
                tag_class_counts[key] += 1

        # Find patterns with many repetitions (3+) — likely data containers
        for pattern, count in tag_class_counts.most_common(20):
            if count < 3:
                continue
            try:
                # Build a rough CSS selector from the pattern
                css_sel = pattern.replace(".", ".")
                matching = soup.select(css_sel)
                content_count = sum(1 for m in matching if len(m.get_text(strip=True)) > 20)
                if content_count > data_container_count:
                    data_container_count = content_count
            except Exception:
                continue

        # Also scan for repeating direct children of common containers
        for container_tag in ["div", "li", "article", "section", "tr"]:
            parents = soup.find_all(container_tag, limit=10)
            for parent in parents:
                children = parent.find_all(recursive=False)
                if len(children) >= 3:
                    # Check if children share the same structure
                    child_classes = [" ".join(c.get("class", []) or []) for c in children]
                    unique_classes = len(set(child_classes))
                    if unique_classes <= 2:
                        # Likely repeating items
                        data_container_count = max(data_container_count, len(children))

    # ── Classification ──────────────────────────────────────────────
    is_landing_page = len(landing_signals) >= 2 or (len(landing_signals) >= 1 and data_container_count < 3)

    if is_landing_page:
        return {
            "quality": "landing_page",
            "has_data_containers": data_container_count >= 3,
            "is_landing_page": True,
            "data_container_count": data_container_count,
            "landing_signals": landing_signals,
            "message": (
                f"This appears to be a landing or homepage (signals: "
                f"{', '.join(landing_signals)}), not a data results page "
                f"with extractable records."
            ),
        }

    if data_container_count >= 3:
        return {
            "quality": "good",
            "has_data_containers": True,
            "is_landing_page": False,
            "data_container_count": data_container_count,
            "landing_signals": landing_signals,
            "message": f"Found {data_container_count} data containers on the page with good extraction potential.",
        }

    return {
        "quality": "low",
        "has_data_containers": False,
        "is_landing_page": False,
        "data_container_count": data_container_count,
        "landing_signals": landing_signals,
        "message": "No repeating data containers detected on this page — content may be too sparse for extraction.",
    }


def _extract_container_text_values(html: str, container_selector: str) -> list[str]:
    """Extract meaningful, distinct text values from the first data container.

    Walks the container's DOM tree collecting leaf-level text values
    (short, individual text nodes) rather than concatenated full text.
    Also collects img alt texts.
    """
    soup = BeautifulSoup(html, "html.parser")
    containers: list = soup.select(container_selector)

    # Fallback: scan all visible elements
    if not containers:
        containers = [soup]

    container = containers[0]
    values = []
    seen = set()

    for tag in container.find_all(True):
        if tag.name in ("script", "style", "noscript", "svg", "form", "nav", "footer", "header"):
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
    for img in container.find_all("img"):
        alt = img.get("alt", "").strip()
        if alt and len(alt) > 2 and alt.lower() not in seen:
            seen.add(alt.lower())
            values.append(alt)

    return values


# ─── Value Classification ────────────────────────────────────────────


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
    # like "30 - 05 - 2026" (digits + dashes).
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
        suggestions.append(
            {
                "type": "currency",
                "confidence": 0.9,
                "example": patterns.currencies[0],
                "description": "Monetary values detected on page",
            }
        )
    if patterns.dates:
        suggestions.append(
            {
                "type": "date",
                "confidence": 0.9,
                "example": patterns.dates[0],
                "description": "Date values detected on page",
            }
        )
    if patterns.times:
        suggestions.append(
            {
                "type": "time",
                "confidence": 0.75,
                "example": patterns.times[0],
                "description": "Time values detected on page",
            }
        )
    if patterns.ratings:
        suggestions.append(
            {
                "type": "rating",
                "confidence": 0.85,
                "example": patterns.ratings[0],
                "description": "Rating or score values detected on page",
            }
        )
    if patterns.emails:
        suggestions.append(
            {
                "type": "email",
                "confidence": 0.95,
                "example": patterns.emails[0],
                "description": "Email addresses detected on page",
            }
        )
    if patterns.phones:
        suggestions.append(
            {
                "type": "phone",
                "confidence": 0.9,
                "example": patterns.phones[0],
                "description": "Phone numbers detected on page",
            }
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
            }
        )
    if patterns.durations:
        suggestions.append(
            {
                "type": "string",
                "confidence": 0.8,
                "example": patterns.durations[0],
                "description": "Duration values detected on page",
            }
        )
    if patterns.urls:
        suggestions.append(
            {
                "type": "url",
                "confidence": 0.85,
                "example": patterns.urls[0],
                "description": "URL / website values detected on page",
            }
        )
    if patterns.weights:
        suggestions.append(
            {
                "type": "string",
                "confidence": 0.8,
                "example": patterns.weights[0],
                "description": "Weight values detected on page",
            }
        )
    if patterns.percentages:
        suggestions.append(
            {
                "type": "percentage",
                "confidence": 0.8,
                "example": patterns.percentages[0],
                "description": "Percentage values detected on page",
            }
        )
    if patterns.booleans:
        suggestions.append(
            {
                "type": "boolean",
                "confidence": 0.85,
                "example": patterns.booleans[0],
                "description": "Boolean / status values detected on page",
            }
        )
    if patterns.dimensions:
        suggestions.append(
            {
                "type": "string",
                "confidence": 0.75,
                "example": patterns.dimensions[0],
                "description": "Dimension / size values detected on page",
            }
        )
    if patterns.quantities:
        suggestions.append(
            {
                "type": "string",
                "confidence": 0.75,
                "example": patterns.quantities[0],
                "description": "Quantity / pack size values detected on page",
            }
        )
    if patterns.product_codes:
        suggestions.append(
            {
                "type": "code",
                "confidence": 0.8,
                "example": patterns.product_codes[0],
                "description": "Product / SKU codes detected on page",
            }
        )
    if patterns.units:
        suggestions.append(
            {
                "type": "string",
                "confidence": 0.75,
                "example": patterns.units[0],
                "description": "Unit type indicators detected on page",
            }
        )
    if patterns.address_fragments:
        suggestions.append(
            {
                "type": "location",
                "confidence": 0.8,
                "example": patterns.address_fragments[0],
                "description": "Address / location values detected on page",
            }
        )
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
  {"name": "product_name", "type": "string", "example_value": "Ergonomic Office Chair", "confidence": 0.95, "description": "Product name"},  # noqa: E501
  {"name": "sku", "type": "code", "example_value": "FURN-4032", "confidence": 0.95, "description": "Product SKU or item code"},  # noqa: E501
  {"name": "price", "type": "currency", "example_value": "$299.99", "confidence": 0.95, "description": "Product price"},
  {"name": "rating", "type": "rating", "example_value": "4.5 / 5", "confidence": 0.90, "description": "Customer rating"},  # noqa: E501
  {"name": "delivery_info", "type": "string", "example_value": "Free shipping", "confidence": 0.80, "description": "Shipping or delivery information"},  # noqa: E501
  {"name": "delivery_time", "type": "string", "example_value": "2 - 3 business days", "confidence": 0.80, "description": "Estimated delivery time"},  # noqa: E501
  {"name": "availability", "type": "boolean", "example_value": "In Stock", "confidence": 0.90, "description": "Stock availability status"},  # noqa: E501
  {"name": "brand", "type": "string", "example_value": "SteelFrame Co.", "confidence": 0.95, "description": "Brand or manufacturer"},  # noqa: E501
  {"name": "materials", "type": "string", "example_value": "Leather, Aluminum", "confidence": 0.85, "description": "Product materials or features"},  # noqa: E501
  {"name": "weight_lbs", "type": "number", "example_value": "450", "confidence": 0.75, "description": "Product weight"},
  {"name": "color", "type": "string", "example_value": "Black, White", "confidence": 0.90, "description": "Available colors"}
]}
=== END EXAMPLE ===
"""

    return f"""You are a data schema designer. Name each data field found on this webpage.

I extracted these values from ONE data row on this {structure_type.upper()} page (confidence: {structure_confidence:.0%}):

{value_block}

{few_shot}

For EACH value, assign a descriptive snake_case field name.
Determine its data type from: string, number, currency, email, phone, url, date, time, rating, boolean, percentage, location, code.  # noqa: E501

CRITICAL: NEVER use type names as field names.
  ✖ BAD: {{"name": "string"}}  or {{"name": "code"}}  or {{"name": "time"}}  or {{"name": "text"}}  or {{"name": "number"}}  or {{"name": "date"}}  or {{"name": "currency"}}
  ✔ GOOD: {{"name": "airline_name"}}  or {{"name": "flight_number"}}  or {{"name": "departure_airport"}}  or {{"name": "departure_time"}}  or {{"name": "price"}}

Differentiate duplicate types — if two values share the same type, give them distinct context-specific names (e.g. "origin_airport_code" vs "destination_airport_code" instead of "code" and "code").  # noqa: E501

Look at each value carefully and infer its contextual meaning. For example:
- A 3-letter uppercase word like "LHR" or "JFK" is likely an airport code, name it "origin_airport_code" or "destination_airport_code"  # noqa: E501
- A city name like "London" or "New York" is a location, name it "origin_city" or "destination_city"
- A monetary value like "$450" or "£450" is a price, name it "price", "total_price", or "fee"
- A short time like "08:30" or "14:00" is a time, name it "departure_time" or "arrival_time"
- A date like "30 / 05 / 2026" is a date, name it "departure_date", "travel_date", or "return_date"

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


# ─── Search Form Detection ──────────────────────────────────────────────


def _detect_search_form(html: str) -> dict:
    """Detect search forms on a page and extract their field structure.

    Scans the page HTML for forms that look like search / query forms
    (text inputs with location, date, or search-related names / placeholders),
    and returns a structured description of the form fields, action URL,
    and method. Fully generic — works with any site, no hardcoded values.

    Args:
        html: The page HTML content

    Returns:
        dict with:
        - detected: bool — whether a search form was found
        - action: str — the form's action URL (relative or absolute)
        - method: str — GET or POST
        - fields: list of dicts with {id, name, type, placeholder, required_indicator}
        - search_fields: list of field dicts identified as search-relevant
        (city / date / airport related names and placeholders)
    """
    soup = BeautifulSoup(html, "html.parser")
    forms = soup.find_all("form")

    # Keywords that suggest a field is a search / query parameter
    SEARCH_FIELD_NAMES: set[str] = {
        "from",
        "to",
        "source",
        "target",
        "location",
        "place",
        "city",
        "date",
        "query",
        "search",
        "q",
        "keyword",
    }
    SEARCH_PLACEHOLDER_PATTERNS: list[str] = [
        r"from|to",
        r"location|place",
        r"date|when",
        r"search|find",
        r"keyword|query",
    ]

    best_form = None
    best_fields: list[dict] = []
    best_form_score = 0

    for form in forms:
        inputs = form.find_all("input")
        selects = form.find_all("select")
        all_inputs = list(inputs) + list(selects)

        if not all_inputs:
            continue

        fields: list[dict] = []
        search_inputs: list[dict] = []
        form_score = 0

        for inp in all_inputs:
            tag_name = inp.name  # 'input' or 'select'
            field_id = inp.get("id", "") or ""
            field_name = inp.get("name", "") or ""
            field_type = inp.get("type", "text") if tag_name == "input" else "select"
            placeholder = inp.get("placeholder", "") or ""

            input_type_lower = field_type.lower()
            # Skip hidden, submit, button, file, checkbox, radio, etc.
            # Only keep text-like and date-like inputs
            if input_type_lower not in ("", "text", "search", "date", "datetime-local", "tel", "number"):
                continue

            field_entry = {
                "id": field_id,
                "name": field_name or field_id,
                "type": field_type,
                "placeholder": placeholder,
            }
            fields.append(field_entry)

            # Score this field for search relevance
            name_lower = field_name.lower()
            id_lower = field_id.lower()
            placeholder_lower = placeholder.lower()

            # Check field name
            for keyword in SEARCH_FIELD_NAMES:
                if keyword in name_lower or keyword in id_lower:
                    form_score += 2
                    break

            # Check placeholder text against patterns
            for pattern in SEARCH_PLACEHOLDER_PATTERNS:
                if re.search(pattern, placeholder_lower, re.IGNORECASE):
                    form_score += 2
                    break

            # If field is relevant, add to search_inputs
            is_search_relevant = False
            for keyword in SEARCH_FIELD_NAMES:
                if keyword in name_lower or keyword in id_lower or keyword in placeholder_lower:
                    is_search_relevant = True
                    break
            if is_search_relevant:
                search_inputs.append(field_entry)

        # Boost score for forms with search inputs
        if search_inputs:
            form_score += len(search_inputs) * 3

        if form_score > best_form_score:
            best_form_score = form_score
            best_form = form
            best_fields = fields

    if best_form is None or best_form_score < 3:
        return {
            "detected": False,
            "action": "",
            "method": "",
            "fields": [],
            "search_fields": [],
        }

    action = best_form.get("action", "") or ""
    method = (best_form.get("method", "post") or "post").upper()

    return {
        "detected": True,
        "action": action.strip(),
        "method": method,
        "fields": best_fields,
        "search_fields": search_inputs,
    }


# ─── Search Form POST Recovery ─────────────────────────────────────────


def _build_absolute_url(base_url: str, action: str) -> str:
    """Build an absolute URL from a base URL and potentially relative action."""
    from urllib.parse import urljoin, urlparse

    if action.startswith("http://") or action.startswith("https://"):
        return action
    if action.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{action}"
    return urljoin(base_url.rstrip("/") + "/", action.lstrip("/"))


def _map_search_params_to_fields(
    search_params: dict[str, str],
    form_fields: list[dict],
) -> dict[str, str]:
    """Map user-provided search parameters to form field names.

    Uses fuzzy matching of field names, IDs, and placeholders to find
    the best field for each search parameter. No hardcoded field names.

    Args:
        search_params: User-provided params like {"origin": "NYC", "destination": "LHR"}
        form_fields: Detected form fields from _detect_search_form()

    Returns:
        dict mapping form field names → values
    """
    mapped: dict[str, str] = {}

    # Build a list of (field_entry, match_keywords) for fuzzy matching
    param_variants: dict[str, list[str]] = {
        "query": ["query", "search", "q", "keyword"],
        "location": ["location", "place", "city"],
        "origin": ["origin", "from", "source", "departure", "depart", "start"],
        "destination": ["destination", "to", "target", "arrival", "arrive", "end"],
        "from": ["from", "origin", "source", "departure", "depart", "start"],
        "to": ["to", "destination", "target", "arrival", "arrive", "end"],
        "date": ["date", "when"],
        "departure_date": ["departure_date", "departuredate", "departdate", "depart", "startdate", "date"],
        "depart_date": ["depart_date", "departuredate", "departdate", "depart", "startdate", "date"],
        "return_date": ["return_date", "returndate", "return", "enddate", "date"],
        "arrival_date": ["arrival_date", "arrivaldate", "arrivedate", "arrival", "enddate", "date"],
    }

    used_fields: set[str] = set()

    for param_key, value in search_params.items():
        if not value:
            continue
        param_lower = param_key.lower().replace("_", "").replace("-", "")

        # Find the matching param variants or use the param key directly
        # Use the original key (with underscores) for dict lookup since
        # param_variants keys use underscores (e.g. "departure_date")
        variant_keywords = param_variants.get(param_key.lower(), [param_lower])

        best_match = None
        best_score = 0

        for field in form_fields:
            field_name = field.get("name", "").lower().replace("_", "").replace("-", "")
            field_id = field.get("id", "").lower().replace("_", "").replace("-", "")
            placeholder = field.get("placeholder", "").lower().replace("_", "").replace("-", "")

            # Skip already-mapped fields
            if field_name in used_fields or field_id in used_fields:
                continue

            for kw in variant_keywords:
                score = 0
                kw_norm = kw.lower().replace("_", "").replace("-", "")
                if kw_norm == field_name or kw_norm == field_id:
                    score = 10  # Exact match
                elif kw_norm in field_name or kw_norm in field_id:
                    score = 5  # Substring match on name / id
                elif kw_norm in placeholder:
                    score = 3  # Placeholder match

                if score > best_score:
                    best_score = score
                    best_match = field

        if best_match:
            form_field_name = best_match.get("name", "") or best_match.get("id", "")
            if form_field_name:
                mapped[form_field_name] = value
                used_fields.add(form_field_name)
                used_fields.add(best_match.get("id", ""))

    return mapped


async def _try_form_search_recovery(
    landing_page_html: str,
    landing_page_url: str,
    search_params: dict[str, str],
) -> dict:
    """Try to recover from an expired session URL by submitting the site's
    search form programmatically.

    Detects the search form on the landing page, maps user-provided
    search parameters to form fields, POSTs to the form action, and
    follows redirects to the fresh session results page.

    Fully generic — works with any site that has a search form, no
    hardcoded domains or field names.

    Args:
        landing_page_html: HTML of the landing / homepage (after redirect)
        landing_page_url: URL of the landing page (for resolving relative actions)
        search_params: Dict of search parameters
            (e.g. {"origin": "NYC", "destination": "LHR", "departure_date": "05 / 15 / 2026"})

    Returns:
        dict with:
        - success: bool — whether recovery succeeded
        - fresh_url: str — the URL of the fresh session results page
        - fresh_html: str — HTML of the fresh session results page
        - form_detected: bool
        - form_info: dict — the detected form structure
        - error: str | None — error message if recovery failed
    """
    import httpx
    from app.url_safety import validate_public_http_url

    # Step 1: Detect the search form
    form_info = _detect_search_form(landing_page_html)
    if not form_info["detected"]:
        return {
            "success": False,
            "fresh_url": landing_page_url,
            "fresh_html": "",
            "form_detected": False,
            "form_info": form_info,
            "error": "No search form detected on the landing page — cannot recover expired session",
        }

    # Step 2: Map user search params to form field names
    form_action = form_info["action"]
    form_method = form_info["method"]
    form_fields = form_info["fields"]

    mapped_params = _map_search_params_to_fields(search_params, form_fields)

    if not mapped_params:
        # Could not map any params — return the form structure so the user can
        # see what's needed
        return {
            "success": False,
            "fresh_url": landing_page_url,
            "fresh_html": "",
            "form_detected": True,
            "form_info": form_info,
            "error": (
                f"Found a search form at '{form_action}' but could not map your "
                f"search parameters to form fields. Detected form fields: "
                f"{[f['name'] or f['id'] for f in form_fields]}. "
                f"Try using field names like: origin, destination, departure_date."
            ),
        }

    # Build absolute form action URL
    absolute_action = _build_absolute_url(landing_page_url, form_action)

    # SSRF: Validate absolute form action URL before submission
    try:
        validate_public_http_url(absolute_action)
    except ValueError as e:
        return {
            "success": False,
            "fresh_url": landing_page_url,
            "fresh_html": "",
            "form_detected": True,
            "form_info": form_info,
            "error": f"Search form action URL '{absolute_action}' failed security check: {e}",
        }

    logger.info(
        "[SearchRecovery] POSTing to %s with params: %s",
        absolute_action,
        mapped_params,
    )

    # Step 3: Submit the form
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(30.0),
        ) as client:
            if form_method == "GET":
                resp = await client.get(absolute_action, params=mapped_params)
            else:
                resp = await client.post(absolute_action, data=mapped_params)

            max_redirects = 10
            redirects_followed = 0
            while resp.is_redirect:
                redirects_followed += 1
                if redirects_followed > max_redirects:
                    raise ValueError(f"Too many redirects (max {max_redirects})")

                redirect_target = resp.headers.get("location", "")
                if not redirect_target:
                    break

                from urllib.parse import urljoin

                redirect_url = urljoin(str(resp.url), redirect_target)

                # SSRF: Validate each redirect hop target URL
                validate_public_http_url(redirect_url)

                resp = await client.get(redirect_url)

            fresh_url = str(resp.url)
            # SSRF: Validate final resolved URL
            validate_public_http_url(fresh_url)

            fresh_html = resp.text

            if resp.status_code >= 400:
                return {
                    "success": False,
                    "fresh_url": fresh_url,
                    "fresh_html": fresh_html,
                    "form_detected": True,
                    "form_info": form_info,
                    "error": f"Search form submission returned HTTP {
                        resp.status_code}",
                }

            logger.info(
                "[SearchRecovery] Form submitted successfully → %s (status %d)",
                fresh_url,
                resp.status_code,
            )

            return {
                "success": True,
                "fresh_url": fresh_url,
                "fresh_html": fresh_html,
                "form_detected": True,
                "form_info": form_info,
                "error": None,
            }

    except httpx.TimeoutException:
        return {
            "success": False,
            "fresh_url": landing_page_url,
            "fresh_html": "",
            "form_detected": True,
            "form_info": form_info,
            "error": "Search form submission timed out after 30 seconds",
        }
    except Exception as e:
        return {
            "success": False,
            "fresh_url": landing_page_url,
            "fresh_html": "",
            "form_detected": True,
            "form_info": form_info,
            "error": f"Search form submission failed: {str(e)}",
        }


# ─── Generic field name post-processing ───────────────────────────────────

_GENERIC_NAMES: set[str] = {
    # Pure type names that should never be field identifiers
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
    # 3-letter uppercase codes
    ("code", r"^[A-Z]{3}$", "three_letter_code"),
    # 2-letter uppercase codes
    ("code", r"^[A-Z]{2}$", "code_abbreviation"),
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
    # Location / city names (capitalized proper nouns like "London")
    ("location", r"[A-Z][a-z]+", "city_name"),
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
