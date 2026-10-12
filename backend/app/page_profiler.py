"""Layer 2: Page Profiler.
======================

Universal page structure detection that works for ANY data type.

Core principle: Detect structure and value patterns, not domain-specific features.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, Tag


@dataclass
class StructureProfile:
    """Represents how the page organizes data, regardless of domain."""

    structure_type: str  # table, cards, list, key_value, mixed
    container_selector: str  # CSS selector for data rows / cards
    # Table headers or field labels
    headers: list[str] = field(default_factory=list)
    structure_confidence: float = 0.0  # How confident we are in detection
    sample_containers: list[str] = field(default_factory=list)  # Sample container HTML


@dataclass
class ValuePatterns:
    """Represents what types of values the page contains, detected by pattern."""

    currencies: list[str] = field(default_factory=list)  # ["£", "$", "€", "₹"]
    dates: list[str] = field(default_factory=list)  # date format samples
    # ["4.5 / 5", "★★★", "8.5"]  # noqa: ERA001, RUF100
    ratings: list[str] = field(default_factory=list)
    codes_3letter: list[str] = field(default_factory=list)  # ["LON", "PAR", "BOM"]
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)
    durations: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    # ["250g", "1kg", "500 g", "2lb"]  # noqa: ERA001, RUF100
    weights: list[str] = field(default_factory=list)
    percentages: list[str] = field(default_factory=list)  # ["8%", "20% off", "0.5%"]
    # ["14:30", "2:30 PM", "08:00"]  # noqa: ERA001, RUF100
    times: list[str] = field(default_factory=list)
    # ["Available", "In Stock", "Yes", "No"]  # noqa: ERA001, RUF100
    booleans: list[str] = field(default_factory=list)
    # ["10x15cm", "5\"x7\"", "A4"]  # noqa: ERA001, RUF100
    dimensions: list[str] = field(default_factory=list)
    # ["Pack of 6", "12 pieces", "500ml"]  # noqa: ERA001, RUF100
    quantities: list[str] = field(default_factory=list)
    # ["SKU-12345", "#ABC123", "EAN 123456789"]  # noqa: ERA001, RUF100
    product_codes: list[str] = field(default_factory=list)
    # ["per kg", "per item", "each", "dozen"]  # noqa: ERA001, RUF100
    units: list[str] = field(default_factory=list)
    address_fragments: list[str] = field(default_factory=list)  # ["123 Main St", "New York, NY"]


# Universal patterns for value type detection (NOT domain-specific)
VALUE_PATTERNS = {
    "currency": [
        r"[\$\u20a8\u20ac\u00a3\u00a5\u20b9]\s*\d+[\d,]*\.?\d*",  # 238, $450, 5,200
        r"\d+[\d,]*\s*(inr|usd|eur|gbp|aud|cad)",  # 5000 INR, 100 USD
        r"(rs\.?|rupees?)\s*\d+",  # Rs 500, Rupees 1000
        # 25L, 1.2Cr, 50K
        r"\d+\.?\d*\s*(cr|crore|l|lakh|k|m|mn|million|thousand)\b",
    ],
    "date": [
        r"\d{1,2}[-\/]\d{1,2}[-\/]\d{2,4}",  # 22 - 05 - 2026, 05 / 22 / 2026
        r"\d{4}[-\/]\d{2}[-\/]\d{1,2}",  # 2026 - 05 - 22
        # May 22
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}",
        # 22 May
        r"\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
        r"\d{1,2}:\d{2}",  # 14:30, 2:30 PM
    ],
    "rating": [
        r"\d+\.?\d*/\d+",  # 4.5 / 5, 8.5 / 10
        r"[★☆]{1,5}",  # ★★★, ☆☆☆
        r"\d+\.?\d*\s*(star|rating)",  # 4.5 stars
        r"\[\d+\/5\]",  # [4 / 5]
    ],
    "code_3letter": [
        r"\b[A-Z]{3}\b",  # LON, PAR, BOM, DEL
    ],
    "duration": [
        r"\d+h\s*\d+m",  # 2h 30m
        r"\d+h$",  # 2h
        r"\d+:\d{2}",  # 02:30
        r"\d+\s*hours?",  # 3 hours
    ],
    "phone": [
        r"\+?\d[\d\s\-\(\)]{8,}",  # +91 9876543210, (555) 123 - 4567
    ],
    "email": [
        r"[\w.+-]+@[\w-]+\.[\w.-]+",
    ],
    "number": [
        r"\d+[\d,]*\.?\d*",  # 123, 1,234, 123.45
    ],
    "url": [
        r"https?://[^\s]+",
        r"www\.[^\s]+",
    ],
    "weight": [
        # 250g, 1kg, 500 g, 2lb
        r"\d+[\.\,]?\d*\s*(?:g|kg|lb|lbs|ounce|oz|gram|kilo|kilogram)",
        r"(?:g|kg|lb|lbs|ounce|oz|gram|kilo|kilograms?)\s*\d+",  # kg 1, g 500
    ],
    "percentage": [
        r"\d+[\.\,]?\d*%",  # 8%, 20%, 0.5%
        r"\d+[\.\,]?\d*\s*per\s*cent",  # 8 per cent
    ],
    "time": [
        r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?",  # 14:30, 2:30 PM, 08:00
        r"\d{1,2}\s*(?:AM|PM|am|pm)",  # 2 PM, 11 AM
    ],
    "boolean": [
        r"\b(?:Yes|No|True|False|Available|Unavailable|In\s+Stock|Out\s+of\s+Stock|Sold\s+Out|Inactive|Active|Enabled|Disabled)\b",
    ],
    "dimension": [
        # 10x15cm, 5x7
        r"\d+[\.\,]?\d*\s*(?:x|\*)\s*\d+[\.\,]?\d*\s*(?:cm|mm|m|in|inches|ft|feet)?",
        r"(?:A[0-5]|Letter|Legal|Tabloid)",  # Paper sizes
    ],
    "quantity": [
        r"(?:Pack|pack)\s*(?:of|/)?\s*\d+",  # Pack of 6, Pack / 12
        r"\d+\s*(?:pieces?|units?|items?|count|pcs|qty)",  # 12 pieces, 6 units
        # 500ml, 1L, 2 litres
        r"\d+[\.\,]?\d*\s*(?:ml|l|L|litre|liter|gallon|fl oz)",
        r"(?:each|per\s*dozen|per\s*piece|per\s*unit)",  # each, per dozen
    ],
    "product_code": [
        r"\bSKU[-:\s]*[A-Za-z0-9-]+\b",  # SKU-12345, SKU: ABC123
        r"\b(?:EAN|UPC|ISBN|ASIN)[-:\s]*[0-9]+\b",  # EAN 1234567890123
        r"\b[0-9]{12,13}\b",
        # EAN-13 / UPC-A barcode numbers only (12 - 13 digits)
    ],
    "unit_type": [
        # per kg, per piece
        r"per\s*(?:kg|g|lb|piece|item|unit|dozen|litre|ml|pack|box|serving)",
        # each, /kg
        r"(?:each|per\s*kg|per\s*g|per\s*lb|/\s*kg|/\s*piece|/\s*item)",
        r"\b(?:dozen|pack|box|carton|case|bundle|pair|set)\b",
    ],
    "address": [
        # 123 Main St
        r"\d+\s+[A-Za-z]+\s+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Boulevard|Blvd|Way|Circle|Cir|Court|Ct|Plaza|Square)",
        r"[A-Za-z ,]+\s+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln)\s+\d+",
        r"\b(?:P\.?\s*O\.?\s*Box)\s+\d+",
        r"\b[\w\s]+,\s*(?:NY|CA|TX|FL|IL|OH|PA|GA|NC|MI|NJ|VA|WA|AZ|MA|TN|IN|MO|MD|WI|CO|MN|AL|SC|LA|KY|OR|OK|CT|UT|IA|NV|AR|MS|KS|NM|NE|WV|ID|HI|NH|ME|RI|MT|DE|SD|ND|AK|VT|WY|DC)\b",
    ],
}


def detect_page_structure(html: str) -> StructureProfile:
    """Detect the page structure type: table, cards, list, key_value, or mixed.

    This is domain-agnostic - a flight page and a product page might both
    use "cards" structure, and the system should handle both the same way.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise elements
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Try each structure type in order of specificity
    structure = _detect_table_structure(soup)
    if structure and structure.structure_confidence > 0.8:
        return structure

    structure = _detect_cards_structure(soup)
    if structure and structure.structure_confidence > 0.7:
        return structure

    structure = _detect_list_structure(soup)
    if structure and structure.structure_confidence >= 0.6:
        return structure

    structure = _detect_key_value_structure(soup)
    if structure and structure.structure_confidence >= 0.6:
        return structure

    # Default to mixed
    return StructureProfile(structure_type="mixed", container_selector="body", headers=[], structure_confidence=0.3)


def _detect_table_structure(soup: BeautifulSoup) -> StructureProfile | None:
    """Detect if page uses table structure."""
    tables = soup.find_all("table")
    if not tables:
        return None

    # Find the most likely data table (not layout table)
    best_table = None
    best_headers = []

    for table in tables:
        headers = table.find_all("th")
        if headers:
            best_headers = [h.get_text(strip=True) for h in headers[:10]]
            # Check if table has rows with data
            rows = table.find_all("tr")
            if len(rows) > 2:
                best_table = table
                break

    if not best_table:
        return None

    # Calculate confidence based on header quality and row count
    rows = best_table.find_all("tr")
    confidence = min(0.5 + (len(best_headers) / 10) + (len(rows) / 100), 1.0)

    # Get sample row for container selector
    container_sel = "table tr"

    return StructureProfile(
        structure_type="table",
        container_selector=container_sel,
        headers=best_headers,
        structure_confidence=confidence,
        sample_containers=[str(rows[0]) if rows else ""],
    )


def _detect_cards_structure(soup: BeautifulSoup) -> StructureProfile | None:
    """Detect if page uses card / listings structure."""
    # Group every classed element, not only classes named ``card`` or
    # ``product``. Real pages commonly use semantic names such as ``quote``
    # or opaque component names. Layout classes are excluded so a repeated
    # row/column wrapper cannot outrank the records nested inside it.
    groups: dict[str, list[Any]] = {}
    seen_by_selector: dict[str, set[int]] = {}
    for element in soup.find_all(True):
        if isinstance(element, str):
            continue
        classes = [str(cls) for cls in element.get("class", [])]
        selectors = [f"{element.name}.{cls}" for cls in classes if _is_layout_neutral_class(cls)]
        if not selectors and element.name == "article" and not classes:
            selectors = ["article"]
        for selector in selectors:
            seen = seen_by_selector.setdefault(selector, set())
            if id(element) in seen:
                continue
            seen.add(id(element))
            groups.setdefault(selector, []).append(element)

    best_selector = ""
    best_container = None
    best_headers: list[str] = []
    best_sample_texts: list[str] = []
    best_rank: tuple[int, float, int, float] = (0, 0.0, 0, 0.0)
    confidence = 0.0

    for selector, group in groups.items():
        if len(group) < 2:
            continue
        texts = [item.get_text(" ", strip=True) for item in group[:20] if item.get_text(" ", strip=True)]
        if len(texts) < 2:
            continue
        nested_value_count = sum(len(item.find_all(True, recursive=False)) >= 2 for item in group[:20])
        if not any(len(text) > 20 for text in texts) and nested_value_count < 2:
            continue
        item_count = len(group)
        descendant_avg = sum(len(item.find_all(True)) for item in group[:20]) / max(len(group[:20]), 1)
        avg_length = sum(len(text) for text in texts) / max(len(texts), 1)
        # Prefer repeated, data-bearing records; for equal counts, nested
        # child values distinguish a record from a repeated leaf field.
        # Structural richness comes first because a field such as a title can
        # occur more than once per record, while the record itself carries the
        # complete set of sibling values.
        rank = (nested_value_count, descendant_avg, item_count, avg_length)
        candidate_confidence = min(0.5 + (min(item_count, 3) / 10) + (avg_length / 1000), 0.9)

        if rank > best_rank:
            best_rank = rank
            best_selector = selector
            best_container = group[0]
            confidence = candidate_confidence
            best_sample_texts = [text[:200] for text in texts[:3]]
            best_headers = [
                heading.get_text(strip=True) for heading in best_container.find_all(["h1", "h2", "h3", "h4", "strong", "b"])[:5]
            ]

    if not best_selector:
        return None

    # Generate CSS selector
    container_sel = best_selector or "div[class*='card'], div[class*='item'], article"
    if best_container is not None and not best_selector:
        container_sel = _generate_container_selector(best_container)

    return StructureProfile(
        structure_type="cards",
        container_selector=container_sel,
        headers=best_headers,
        structure_confidence=confidence,
        sample_containers=best_sample_texts[:3],
    )


_LAYOUT_CLASS_TOKENS = {
    "body",
    "container",
    "content",
    "footer",
    "grid",
    "header",
    "layout",
    "list",
    "main",
    "nav",
    "page",
    "row",
    "section",
    "shell",
    "sidebar",
    "wrapper",
}


def _is_layout_neutral_class(value: str) -> bool:
    """Return whether a class token is safe to consider as a record candidate."""
    tokens = [token for token in re.split(r"[^a-z0-9]+", value.lower()) if token]
    if not tokens:
        return False
    if any(token in _LAYOUT_CLASS_TOKENS for token in tokens):
        return False
    return not any(token.startswith(("col", "offset", "row", "span")) for token in tokens)


def _detect_list_structure(soup: BeautifulSoup) -> StructureProfile | None:
    """Detect if page uses list structure."""
    # Check for ul / ol lists
    lists = soup.find_all(["ul", "ol"])
    best_list = None
    max_items = 0

    for lst in lists:
        direct_items = lst.find_all("li", recursive=False)
        all_items = lst.find_all("li")
        items = direct_items if len(direct_items) > 5 else all_items
        if len(items) > 5 and len(items) > max_items:
            max_items = len(items)
            best_list = lst

    if not best_list or max_items < 5:
        return None

    container_sel = _scoped_list_selector(best_list)
    confidence = min(0.5 + (max_items / 50), 0.8)

    return StructureProfile(
        structure_type="list",
        container_selector=container_sel,
        headers=[],
        structure_confidence=confidence,
        sample_containers=[str(best_list.find("li"))] if best_list.find("li") else [],
    )


def _detect_key_value_structure(soup: BeautifulSoup) -> StructureProfile | None:
    """Detect if page uses key-value or definition list structure."""
    # Check for definition lists
    dl = soup.find("dl")
    if dl and isinstance(dl, Tag):
        dts = dl.find_all("dt")
        if len(dts) > 3:
            headers = [dt.get_text(strip=True) for dt in dts[:10]]
            return StructureProfile(
                structure_type="key_value",
                container_selector="dl",
                headers=headers,
                structure_confidence=0.7,
                sample_containers=[str(dl)],
            )

    # Check for 2-column tables
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) > 2:
            first_row = rows[0].find_all(["td", "th"])
            if len(first_row) == 2:  # Two columns
                headers = [
                    cells[0].get_text(strip=True)
                    for row in rows[:10]
                    if (cells := row.find_all(["td", "th"], recursive=False)) and len(cells) == 2
                ]
                return StructureProfile(
                    structure_type="key_value",
                    container_selector="table",
                    headers=headers,
                    structure_confidence=0.6,
                    sample_containers=[str(rows[0])],
                )

    return None


def _generate_container_selector(element) -> str:
    """Generate a reasonable CSS selector for a container element."""
    if hasattr(element, "name"):
        tag = element.name
        classes = element.get("class", [])
        if classes:
            class_sel = ".".join(classes[:2])
            return f"{tag}.{class_sel}"
        return tag  # type: ignore[no-any-return]
    return "div"


def _unique_ancestor_selector(element: Tag) -> str:
    """Build a tag path that remains unique when wrappers repeat."""
    segments: list[str] = []
    current: Tag | None = element
    while isinstance(current, Tag) and current.name not in {None, "[document]", "body", "html"}:
        parent = getattr(current, "parent", None)
        if not isinstance(parent, Tag) or parent.name in {None, "[document]"}:
            segments.append(f"{current.name}:nth-of-type(1):not({current.name} {current.name})")
            break

        siblings = parent.find_all(current.name, recursive=False)
        sibling_index = siblings.index(current) + 1 if current in siblings else 1
        segment = current.name
        if len(siblings) > 1:
            segment = f"{segment}:nth-of-type({sibling_index})"
        segments.append(segment)
        current = parent

    return " > ".join(reversed(segments))


def _scoped_list_selector(list_element: Tag) -> str:
    """Build a selector for one list while excluding nested list records."""
    list_tag = list_element.name or "ul"
    parent = getattr(list_element, "parent", None)
    if not isinstance(parent, Tag) or getattr(parent, "name", None) in {None, "[document]"}:
        return f"{list_tag}:nth-of-type(1):not({list_tag} {list_tag}) > li"

    sibling_lists = parent.find_all(list_tag, recursive=False)
    list_index = sibling_lists.index(list_element) + 1 if list_element in sibling_lists else 1
    list_selector = list_tag if len(sibling_lists) <= 1 else f"{list_tag}:nth-of-type({list_index})"

    if parent.name in {"body", "html"}:
        return f"{parent.name} > {list_selector} > li"

    parent_selector = _unique_ancestor_selector(parent)
    return f"{parent_selector} > {list_selector} > li"


def detect_value_patterns(html: str) -> ValuePatterns:
    """Detect what types of values the page contains using broad patterns.

    This is domain-agnostic - it just looks for patterns like currency symbols,
    date formats, weights, times, etc., regardless of whether it's a flight,
    product, or directory page.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()

    patterns = ValuePatterns()

    # Common English words to exclude from 3-letter code detection
    COMMON_3LETTER_WORDS = {
        "THE",
        "AND",
        "FOR",
        "ARE",
        "NOT",
        "YOU",
        "ALL",
        "CAN",
        "HAS",
        "WAS",
        "BUT",
        "ITS",
        "OUT",
        "NEW",
        "NOW",
        "HOW",
        "GET",
        "SEE",
        "USE",
        "MAY",
        "LET",
        "MAN",
        "WAY",
        "DAY",
        "OLD",
        "BIG",
        "FEW",
        "HOT",
        "TOP",
        "BAD",
        "RUN",
        "SIT",
        "DID",
        "LOT",
        "ASK",
        "TRY",
        "TOO",
        "OWN",
        "CUT",
        "HIM",
        "HER",
        "ONE",
        "TWO",
        "SIX",
        "TEN",
        "ANY",
        "EACH",
        "OUR",
    }

    # Map pattern_type to ValuePatterns attribute
    pattern_map = {
        "currency": "currencies",
        "date": "dates",
        "rating": "ratings",
        "code_3letter": "codes_3letter",
        "phone": "phones",
        "email": "emails",
        "number": "numbers",
        "duration": "durations",
        "url": "urls",
        "weight": "weights",
        "percentage": "percentages",
        "time": "times",
        "boolean": "booleans",
        "dimension": "dimensions",
        "quantity": "quantities",
        "product_code": "product_codes",
        "unit_type": "units",
        "address": "address_fragments",
    }

    for pattern_type, regexes in VALUE_PATTERNS.items():
        samples = []
        for regex in regexes:
            # Three-letter codes are conventionally uppercase. Applying a
            # case-insensitive flag here turns ordinary prose (for example
            # "far") into a false code candidate and later a fake field.
            flags = 0 if pattern_type == "code_3letter" else re.IGNORECASE
            matches = re.findall(regex, text, flags)
            samples.extend(matches[:10])

        attr_name = pattern_map.get(pattern_type)
        if not attr_name:
            continue

        unique = list(set(samples))

        # Special handling for 3-letter codes (filter common words)
        if pattern_type == "code_3letter":
            unique = [s for s in unique if s.upper() not in COMMON_3LETTER_WORDS]

        setattr(patterns, attr_name, unique[:10])

    return patterns
