
"""
Layer 2: Page Profiler
======================
Universal page structure detection that works for ANY data type.

Core principle: Detect structure and value patterns, not domain-specific features.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

from bs4 import BeautifulSoup, Tag


@dataclass
class StructureProfile:
    """Represents how the page organizes data, regardless of domain."""
    structure_type: str  # table, cards, list, key_value, mixed
    container_selector: str  # CSS selector for data rows/cards
    headers: List[str] = field(default_factory=list)  # Table headers or field labels
    structure_confidence: float = 0.0  # How confident we are in detection
    sample_containers: List[str] = field(default_factory=list)  # Sample container HTML


@dataclass
class ValuePatterns:
    """Represents what types of values the page contains, detected by pattern."""
    currencies: List[str] = field(default_factory=list)  # ["£", "$", "€", "₹"]
    dates: List[str] = field(default_factory=list)  # date format samples
    ratings: List[str] = field(default_factory=list)  # ["4.5/5", "★★★", "8.5"]
    codes_3letter: List[str] = field(default_factory=list)  # ["LON", "PAR", "BOM"]
    phones: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    numbers: List[str] = field(default_factory=list)
    durations: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)


# Universal patterns for value type detection (NOT domain-specific)
VALUE_PATTERNS = {
    "currency": [
        r"[\$\u20a8\u20ac\u00a3\u00a5\u20b9]\s*\d+[\d,]*\.?\d*",  # 238, $450, 5,200
        r"\d+[\d,]*\s*(inr|usd|eur|gbp|aud|cad)",  # 5000 INR, 100 USD
        r"(rs\.?|rupees?)\s*\d+",  # Rs 500, Rupees 1000
        r"\d+\.?\d*\s*(cr|crore|l|lakh|k|m|mn|million|thousand)",  # 25L, 1.2Cr, 50K
    ],
    "date": [
        r"\d{1,2}[-\/]\d{1,2}[-\/]\d{2,4}",  # 22-05-2026, 05/22/2026
        r"\d{4}[-\/]\d{2}[-\/]\d{1,2}",  # 2026-05-22
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}",  # May 22
        r"\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",  # 22 May
        r"\d{1,2}:\d{2}",  # 14:30, 2:30 PM
    ],
    "rating": [
        r"\d+\.?\d*/\d+",  # 4.5/5, 8.5/10
        r"[★☆]{1,5}",  # ★★★, ☆☆☆
        r"\d+\.?\d*\s*(star|rating)",  # 4.5 stars
        r"\[\d+\/5\]",  # [4/5]
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
        r"\+?\d[\d\s\-\(\)]{8,}",  # +91 9876543210, (555) 123-4567
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
}


def detect_page_structure(html: str) -> StructureProfile:
    """
    Detect the page structure type: table, cards, list, key_value, or mixed.

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
    if structure and structure.structure_confidence > 0.7:
        return structure

    structure = _detect_key_value_structure(soup)
    if structure and structure.structure_confidence > 0.6:
        return structure

    # Default to mixed
    return StructureProfile(
        structure_type="mixed",
        container_selector="body",
        headers=[],
        structure_confidence=0.3
    )


def _detect_table_structure(soup: BeautifulSoup) -> Optional[StructureProfile]:
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
        sample_containers=[str(rows[0]) if rows else ""]
    )


def _detect_cards_structure(soup: BeautifulSoup) -> Optional[StructureProfile]:
    """Detect if page uses card/listings structure."""
    # Card indicators (generic, not domain-specific)
    card_selectors = [
        ("div", {"class": re.compile(r"(card|item|result|listing|product|hotel|flight|job|property)", re.I)}),
        ("article", {}),
        ("li", {"class": re.compile(r"(item|result)", re.I)}),
        ("div", {"class": re.compile(r"(grid|grid-item|col)", re.I)}),
    ]

    best_container = None
    best_headers = []
    max_items = 0
    confidence = 0.0

    for tag, attrs in card_selectors:
        containers = soup.find_all(tag, attrs)
        if not containers:
            continue

        # Check if these are actual data cards (not just styled divs)
        item_count = 0
        sample_texts: list[str] = []

        for container in containers[:20]:
            if isinstance(container, str):
                continue
            text = container.get_text(strip=True)
            if len(text) > 50:  # Has substantial content
                item_count += 1
                if len(sample_texts) < 3:
                    sample_texts.append(text[:200])

        if item_count > 2:
            # Calculate confidence based on consistency
            avg_length = sum(len(t) for t in sample_texts) / max(len(sample_texts), 1)
            confidence = min(0.4 + (item_count / 10) + (avg_length / 500), 0.9)

            if item_count > max_items:
                max_items = item_count
                best_container = containers[0].parent if containers[0].parent else containers[0]
                # Try to extract headers from first card
                headers = []
                for h in container.find_all(["h1", "h2", "h3", "h4", "strong", "b"])[:5]:
                    headers.append(h.get_text(strip=True))
                best_headers = headers

    if max_items < 3:
        return None

    # Generate CSS selector
    if best_container:
        container_sel = _generate_container_selector(best_container)
    else:
        container_sel = "div[class*='card'], div[class*='item'], article"

    return StructureProfile(
        structure_type="cards",
        container_selector=container_sel,
        headers=best_headers,
        structure_confidence=confidence,
        sample_containers=sample_texts[:3]
    )


def _detect_list_structure(soup: BeautifulSoup) -> Optional[StructureProfile]:
    """Detect if page uses list structure."""
    # Check for ul/ol lists
    lists = soup.find_all(["ul", "ol"])
    best_list = None
    max_items = 0

    for lst in lists:
        items = lst.find_all("li")
        if len(items) > 5:
            if len(items) > max_items:
                max_items = len(items)
                best_list = lst

    if not best_list or max_items < 5:
        return None

    container_sel = f"{best_list.name} li"
    confidence = min(0.5 + (max_items / 50), 0.8)

    return StructureProfile(
        structure_type="list",
        container_selector=container_sel,
        headers=[],
        structure_confidence=confidence,
        sample_containers=[str(best_list.find("li"))] if best_list.find("li") else []
    )


def _detect_key_value_structure(soup: BeautifulSoup) -> Optional[StructureProfile]:
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
                sample_containers=[str(dl)]
            )

    # Check for 2-column tables
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) > 2:
            first_row = rows[0].find_all(["td", "th"])
            if len(first_row) == 2:  # Two columns
                headers = [cell.get_text(strip=True) for cell in first_row]
                return StructureProfile(
                    structure_type="key_value",
                    container_selector="table tr",
                    headers=headers,
                    structure_confidence=0.6,
                    sample_containers=[str(rows[0])]
                )

    return None


def _generate_container_selector(element) -> str:
    """Generate a reasonable CSS selector for a container element."""
    if hasattr(element, 'name'):
        tag = element.name
        classes = element.get('class', [])
        if classes:
            class_sel = ".".join(classes[:2])
            return f"{tag}.{class_sel}"
        return tag
    return "div"


def detect_value_patterns(html: str) -> ValuePatterns:
    """
    Detect what types of values the page contains using universal patterns.

    This is domain-agnostic - it just looks for patterns like currency symbols,
    date formats, etc., regardless of whether it's a flight, hotel, or product page.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()

    patterns = ValuePatterns()

    # Extract samples for each pattern type
    for pattern_type, regexes in VALUE_PATTERNS.items():
        samples = []
        for regex in regexes:
            matches = re.findall(regex, text, re.IGNORECASE)
            samples.extend(matches[:10])  # Limit samples

        # Store unique samples
        if pattern_type == "currency":
            patterns.currencies = list(set(samples))[:10]
        elif pattern_type == "date":
            patterns.dates = list(set(samples))[:10]
        elif pattern_type == "rating":
            patterns.ratings = list(set(samples))[:10]
        elif pattern_type == "code_3letter":
            # Accept all 3-letter codes; filter out common English words
            common_words = {"THE", "AND", "FOR", "ARE", "NOT", "YOU", "ALL", "CAN", "HAS", "WAS", "BUT", "ITS", "OUT", "NEW", "NOW", "HOW"}
            codes = [s for s in set(samples) if s.upper() not in common_words]
            patterns.codes_3letter = codes[:10]
        elif pattern_type == "phone":
            patterns.phones = list(set(samples))[:10]
        elif pattern_type == "email":
            patterns.emails = list(set(samples))[:10]
        elif pattern_type == "number":
            patterns.numbers = list(set(samples))[:20]
        elif pattern_type == "duration":
            patterns.durations = list(set(samples))[:10]
        elif pattern_type == "url":
            patterns.urls = list(set(samples))[:10]

    return patterns


