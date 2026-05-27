"""
Page Evidence Collector — Gathers all useful evidence from a rendered page.

Before any extraction, this module collects raw evidence from the page:
  1. Visible text blocks with positional context
  2. Repeated sibling/card structures (candidate containers)
  3. Tables, rows, and list structures
  4. Links and buttons
  5. Pattern matches (price, date, currency, email, phone, etc.)
  6. Form fields
  7. Network/XHR JSON responses (when available)
  8. Hydration data from <script> tags (Next.js, JSON-LD, window.__INITIAL_STATE__)
  9. Page metadata (title, URL, canonical URL, description)

This evidence is used by container_discovery and downstream extractors
to make field- and record-level decisions without relying on hardcoded
selectors or domain-specific rules.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any

from bs4 import BeautifulSoup, Tag

from app.browser_network_capture import get_captures

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class VisibleTextBlock:
    """A single visible text node with positional and container context."""
    text: str
    tag: str
    parent_path: str
    visible: bool = True
    x_position: float = 0.0
    y_position: float = 0.0
    width: float = 0.0
    height: float = 0.0
    container_id: str = ""
    nearby_text: list[str] = field(default_factory=list)
    pattern_type: str = ""  # "price", "date", "email", "phone", "currency", "url", "time", "location", "organization", "name", "code", etc.

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CandidateContainer:
    """A candidate result container discovered from DOM structure."""
    selector: str
    tag: str
    text_density: float = 0.0
    child_count: int = 0
    descendant_count: int = 0
    depth: int = 0
    has_price: bool = False
    has_date: bool = False
    has_time: bool = False
    has_currency: bool = False
    has_location: bool = False
    has_organization: bool = False
    has_contact: bool = False
    has_link: bool = False
    has_button: bool = False
    has_image: bool = False
    has_label_value_pairs: bool = False
    combined_text: str = ""
    all_texts: list[str] = field(default_factory=list)
    sub_containers: list[str] = field(default_factory=list)
    internal_segment_count: int = 0
    repeated_structure_score: float = 0.0
    sibling_similarity: float = 0.0
    record_score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PageEvidence:
    """All evidence collected from a single page."""
    url: str
    title: str = ""
    canonical_url: str = ""
    meta_description: str = ""
    text_blocks: list[VisibleTextBlock] = field(default_factory=list)
    candidate_containers: list[CandidateContainer] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    buttons: list[dict] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    patterns: dict[str, list[str]] = field(default_factory=dict)
    network_json: list[dict] = field(default_factory=list)
    hydration_data: dict[str, Any] = field(default_factory=dict)
    page_structure: str = ""  # "listing", "table", "cards", "list", "search_results", "detail", "single_item", "unknown"
    estimated_record_count: int = 0
    html_length: int = 0
    visible_text_length: int = 0
    dom_node_count: int = 0
    bounding_boxes: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = asdict(self)
        # Keep it serializable
        return result


# ---------------------------------------------------------------------------
# Pattern definitions (generic, no domain-specific entries)
# ---------------------------------------------------------------------------

PATTERN_DEFINITIONS: list[tuple[str, re.Pattern]] = [
    ("currency", re.compile(r'[\$\€\£\¥\₹]\s*\d+[\d,.]*')),
    ("price", re.compile(r'(?:price|total|amount|cost|fare)\s*:?\s*[\$\€\£\¥\₹]?\s*\d+[\d,.]*', re.I)),
    ("date_iso", re.compile(r'\d{4}-\d{2}-\d{2}')),
    ("date_slash", re.compile(r'\d{1,2}/\d{1,2}/\d{2,4}')),
    ("date_text", re.compile(r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}', re.I)),
    ("time", re.compile(r'\d{1,2}:\d{2}\s*(?:am|pm)?', re.I)),
    ("email", re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')),
    ("phone", re.compile(r'\+?\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}')),
    ("percentage", re.compile(r'\d+[\.,]?\d*%')),
    ("url", re.compile(r'https?://[^\s<>"\'\]\)]+')),
    ("rating", re.compile(r'(?:rating|score|stars?)\s*:?\s*\d+(?:\.\d+)?(?:\s*\/\s*\d+)?', re.I)),
    ("location_code", re.compile(r'\b[A-Z]{3}\b')),  # 3-letter codes like MIA, JFK
]

# Repeated structure detection
STRUCTURAL_SEPARATORS = ["hr", "br", "---", "___", "···"]


# ---------------------------------------------------------------------------
# Evidence collection
# ---------------------------------------------------------------------------

def collect_page_evidence(
    html: str,
    url: str = "",
    network_json: list[dict] | None = None,
    bounding_boxes: list[dict] | None = None,
) -> PageEvidence:
    """Collect all useful evidence from a page's HTML.

    Args:
        html: Raw HTML of the page (post-render).
        url: The page URL.
        network_json: Optional network/XHR JSON responses captured during rendering.

    Returns:
        PageEvidence with all collected evidence.
    """
    evidence = PageEvidence(url=url, html_length=len(html))

    if not html or len(html.strip()) < 50:
        return evidence

    soup = BeautifulSoup(html, "html.parser")

    # ── Page metadata ────────────────────────────────────────────────
    title_tag = soup.find("title")
    if title_tag:
        evidence.title = title_tag.get_text(strip=True)
    canonical = soup.find("link", rel="canonical")
    if canonical and hasattr(canonical, 'get'):
        evidence.canonical_url = str(canonical.get("href", ""))
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and hasattr(meta_desc, 'get'):
        evidence.meta_description = str(meta_desc.get("content", ""))

    # ── DOM node count ───────────────────────────────────────────────
    evidence.dom_node_count = len(soup.find_all(True))

    # ── Collect visible text blocks ──────────────────────────────────
    text_blocks = _collect_visible_text_blocks(soup)
    evidence.text_blocks = text_blocks

    # ── Extract visible text for analysis ────────────────────────────
    for tag in soup(["script", "style", "noscript", "svg", "link"]):
        tag.decompose()
    visible_text = soup.get_text(separator=" ", strip=True)
    evidence.visible_text_length = len(visible_text)

    # ── Pattern matching ─────────────────────────────────────────────
    patterns: dict[str, list[str]] = {}
    for pattern_name, pattern in PATTERN_DEFINITIONS:
        matches = pattern.findall(visible_text)
        if matches:
            # Deduplicate and limit
            unique = list(dict.fromkeys(m.strip() for m in matches))[:20]
            patterns[pattern_name] = unique
    evidence.patterns = patterns

    # ── Links ────────────────────────────────────────────────────────
    links = []
    seen_hrefs = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        text = a_tag.get_text(strip=True)
        if href and href not in seen_hrefs and not href.startswith("#"):
            seen_hrefs.add(href)
            links.append({"href": href, "text": text[:100]})
    evidence.links = links[:50]

    # ── Buttons ──────────────────────────────────────────────────────
    buttons = []
    seen_btn_text = set()
    for btn in soup.find_all(["button", "input"]):
        if btn.name == "input" and btn.get("type") not in (None, "submit", "button"):
            continue
        text = (btn.get_text(strip=True) or btn.get("value", "") or "").strip()
        if text and text not in seen_btn_text:
            seen_btn_text.add(text)
            buttons.append({"text": text[:80], "tag": btn.name})
    evidence.buttons = buttons[:20]

    # ── Forms ────────────────────────────────────────────────────────
    forms = []
    for form in soup.find_all("form"):
        action = form.get("action", "") or ""
        method = (form.get("method", "get") or "get").upper()
        inputs = []
        for inp in form.find_all(["input", "select", "textarea"]):
            inp_name = inp.get("name", "") or ""
            inp_type = inp.get("type", "text") if inp.name == "input" else inp.name
            placeholder = inp.get("placeholder", "") or ""
            if inp_name:
                inputs.append({"name": inp_name, "type": inp_type, "placeholder": placeholder})
        if inputs or action:
            forms.append({"action": action, "method": method, "inputs": inputs})
    evidence.forms = forms[:10]

    # ── Images ───────────────────────────────────────────────────────
    images = []
    for img in soup.find_all("img"):
        src = img.get("src", "") or ""
        alt = img.get("alt", "") or ""
        if src:
            images.append({"src": src[:200], "alt": alt[:100]})
    evidence.images = images[:30]

    # ── Tables ────────────────────────────────────────────────────────
    tables = _collect_tables(soup)
    evidence.tables = tables[:10]

    # ── Hydration data from scripts ─────────────────────────────────
    evidence.hydration_data = _extract_hydration_data(soup)

    # ── Network JSON ─────────────────────────────────────────────────
    if network_json:
        evidence.network_json = network_json[:20]
    elif url:
        captured = get_captures(url)
        if captured:
            evidence.network_json = captured[:20]
            logger.debug("[PageEvidence] Found %d captured network payloads for %s", len(captured[:20]), url)

    if bounding_boxes:
        evidence.bounding_boxes = bounding_boxes[:500]

    # ── Candidate containers ─────────────────────────────────────────
    containers = _discover_candidate_containers(soup)
    evidence.candidate_containers = containers[:30]

    # ── Page structure classification ────────────────────────────────
    evidence.page_structure = _classify_page_structure(evidence)
    evidence.estimated_record_count = _estimate_record_count(evidence)

    return evidence


def _collect_visible_text_blocks(soup: BeautifulSoup) -> list[VisibleTextBlock]:
    """Collect visible text nodes with their tag and parent path."""
    blocks: list[VisibleTextBlock] = []
    processed_paths: set[str] = set()

    # Walk leaf text nodes
    for element in soup.find_all(True):
        # Skip non-content tags
        if element.name in ("script", "style", "noscript", "svg", "link", "meta", "head"):
            continue

        text = element.get_text(separator=" ", strip=True)
        if not text or len(text) < 3:
            continue

        # Build parent path
        path_parts = []
        parent = element
        while parent and parent.name:
            path_parts.append(parent.name)
            if len(path_parts) >= 6:
                break
            parent = parent.parent
        parent_path = "/".join(reversed(path_parts))

        # Deduplicate by parent_path + text prefix
        key = f"{parent_path}|{text[:50]}"
        if key in processed_paths:
            continue
        processed_paths.add(key)

        # Detect pattern type
        pattern_type = _detect_pattern_type(text)

        block = VisibleTextBlock(
            text=text[:500],
            tag=element.name,
            parent_path=parent_path,
            visible=True,
            pattern_type=pattern_type,
        )
        blocks.append(block)

    return blocks


def _detect_pattern_type(text: str) -> str:
    """Detect the pattern type of a text block."""
    for pattern_name, pattern in PATTERN_DEFINITIONS:
        if pattern.search(text):
            return pattern_name
    return ""


def _collect_tables(soup: BeautifulSoup) -> list[dict]:
    """Extract structured table data."""
    tables = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = []
            for cell in tr.find_all(["td", "th"]):
                cells.append(cell.get_text(separator=" ", strip=True)[:200])
            if cells:
                rows.append(cells)
        if len(rows) >= 2:  # At least a header + one data row
            tables.append({
                "row_count": len(rows),
                "col_count": max(len(r) for r in rows),
                "rows": rows[:20],
                "headers": rows[0] if rows else [],
            })
    return tables


def _extract_hydration_data(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract JSON data from script tags (hydration, state, LD+JSON)."""
    hydration: dict[str, Any] = {}

    # JSON-LD structured data
    jsonld_scripts = soup.find_all("script", type="application/ld+json")
    jsonld_data = []
    for script in jsonld_scripts:
        try:
            data = json.loads(script.string)
            jsonld_data.append(data)
        except (json.JSONDecodeError, TypeError):
            pass
    if jsonld_data:
        hydration["jsonld"] = jsonld_data[:10]

    # Next.js __NEXT_DATA__
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data and hasattr(next_data, 'string') and next_data.string:
        try:
            data = json.loads(str(next_data.string))
            # Extract props and state
            props = data.get("props", {})
            page_props = props.get("pageProps", {})
            if page_props:
                hydration["nextjs_page_props"] = _truncate_large_values(page_props)
            if "initialState" in data:
                hydration["nextjs_initial_state"] = _truncate_large_values(data["initialState"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Window __INITIAL_STATE__
    for script in soup.find_all("script"):
        if not script.string:
            continue
        text = script.string.strip()
        for var_name in ["__INITIAL_STATE__", "__PRELOADED_STATE__", "window.__INITIAL_STATE__"]:
            if var_name in text:
                # Try to extract JSON after assignment (depth-aware brace matching)
                match = re.search(rf'{re.escape(var_name)}\s*=\s*(\{{)', text)
                if match:
                    # Count braces to extract the full JSON object
                    start = match.start(1)
                    brace_count = 0
                    end = start
                    for i in range(start, len(text)):
                        if text[i] == '{':
                            brace_count += 1
                        elif text[i] == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end = i + 1
                                break
                    if end > start:
                        try:
                            data = json.loads(text[start:end])
                            hydration[var_name] = _truncate_large_values(data)
                        except (json.JSONDecodeError, TypeError):
                            pass

    # Apollo/Relay state
    for script in soup.find_all("script"):
        if not script.string:
            continue
        text = script.string.strip()
        if "apolloState" in text or "ROOT_QUERY" in text:
            match = re.search(r'window\.__APOLLO_STATE__\s*=\s*(\{.+?\});', text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    hydration["apollo_state"] = _truncate_large_values(data)
                except (json.JSONDecodeError, TypeError):
                    pass

    return hydration


def _truncate_large_values(obj: Any, max_depth: int = 4, max_str_len: int = 500) -> Any:
    """Recursively truncate large values for serialization."""
    if isinstance(obj, dict):
        if max_depth <= 0:
            return {"__truncated__": True}
        return {k: _truncate_large_values(v, max_depth - 1, max_str_len) for k, v in obj.items()}
    if isinstance(obj, list):
        if max_depth <= 0:
            return ["__truncated__"]
        return [_truncate_large_values(v, max_depth - 1, max_str_len) for v in obj[:50]]
    if isinstance(obj, str) and len(obj) > max_str_len:
        return obj[:max_str_len] + "..."
    return obj


def _discover_candidate_containers(soup: BeautifulSoup) -> list[CandidateContainer]:
    """Discover candidate result containers from DOM structure.

    Looks for repeated sibling structures that might represent result cards,
    list items, table rows, or other repeated data containers.
    """
    containers: list[CandidateContainer] = []
    seen_selectors: set[str] = set()

    # Strategy 1: Find repeated direct children of common container parents
    for parent_tag in ["div", "li", "tr", "section", "article", "ul", "ol", "tbody"]:
        for parent in soup.find_all(parent_tag):
            children = [c for c in parent.children if isinstance(c, Tag)]
            if len(children) < 2:
                continue

            # Check if children have similar structure
            child_tags = [c.name for c in children]
            unique_tags = set(child_tags)
            if len(unique_tags) == 1 and len(children) >= 2:
                # Same tag repeated — likely a container
                for child in children[:10]:
                    sel = _build_container_selector(child)
                    if sel and sel not in seen_selectors:
                        seen_selectors.add(sel)
                        container = _score_container(child, sel, children)
                        containers.append(container)

            # Also check for mixed tags but similar class patterns
            if len(unique_tags) <= 2 and len(children) >= 3:
                class_sets = []
                for c in children:
                    cls = " ".join(c.get("class", []))
                    class_sets.append(cls)
                unique_classes = set(class_sets)
                if len(unique_classes) <= 2 and len(unique_classes) < len(children):
                    # Same classes repeated — likely cards
                    for child in children[:10]:
                        sel = _build_container_selector(child)
                        if sel and sel not in seen_selectors:
                            seen_selectors.add(sel)
                            container = _score_container(child, sel, children)
                            containers.append(container)

    # Strategy 2: Table rows
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) >= 3:
            sel = _build_container_selector(rows[1]) if len(rows) > 1 else ""
            if sel and sel not in seen_selectors:
                seen_selectors.add(sel)
                container = _score_container(rows[1], sel, rows[1:])
                containers.append(container)

    # Strategy 3: List items
    for list_tag in soup.find_all(["ul", "ol"]):
        items = list_tag.find_all("li", recursive=False)
        if len(items) >= 3:
            sel = _build_container_selector(items[0])
            if sel and sel not in seen_selectors:
                seen_selectors.add(sel)
                container = _score_container(items[0], sel, items)
                containers.append(container)

    # Score and sort containers
    for container in containers:
        if isinstance(container, CandidateContainer):
            container.record_score = _compute_container_score(container)

    containers.sort(key=lambda c: c.record_score if isinstance(c, CandidateContainer) else 0.0, reverse=True)
    return containers


def _build_container_selector(element: Tag) -> str:
    """Build a minimal CSS selector for an element."""
    tag = element.name
    classes = element.get("class", [])
    if classes:
        # Use up to 2 most specific classes
        cls_part = ".".join(c for c in classes if c)[:2]
        return f"{tag}.{cls_part}" if cls_part else tag
    return tag


def _score_container(element: Tag, selector: str, siblings: list[Tag]) -> CandidateContainer:
    """Score a candidate container based on its content and structure."""
    text = element.get_text(separator=" ", strip=True)
    text_len = len(text)

    # Get all text snippets within
    all_texts = []
    for t in element.find_all(string=True):
        t = t.strip()
        if t and len(t) > 1:
            all_texts.append(t)

    # Count descendants
    descendants = element.find_all(True)
    children = [c for c in element.children if isinstance(c, Tag)]

    # Detect features
    has_price = bool(re.search(r'[\$\€\£\¥\₹]\s*\d+', text))
    has_date = bool(re.search(r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}', text))
    has_time = bool(re.search(r'\d{1,2}:\d{2}\s*(?:am|pm)?', text, re.I))
    has_currency = bool(re.search(r'[\$\€\£\¥\₹]', text))
    has_location = bool(re.search(r'\b[A-Z]{3}\b', text) and len(text) > 20)  # 3-letter codes with enough context
    has_organization = bool(re.search(r'(?:inc\.?|llc|ltd\.?|corp\.?|co\.?|hospital|university|school)\b', text, re.I))
    has_contact = bool(re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+|\+?\d{7,}', text))
    has_link = bool(element.find("a"))
    has_button = bool(element.find(["button", "input[type=submit]"]))
    has_image = bool(element.find("img"))
    has_label_value = bool(re.search(r'(?:price|name|date|time|location|phone|email|address)\s*:|\|\s*(?:price|name|date)', text, re.I))

    # Text density (chars per descendant)
    text_density = text_len / max(1, len(descendants))

    # Detect internal segments (compound records with sub-sections)
    internal_segments = 0
    for sep in ["Segment", "Section", "Part", "Item"]:
        if sep.lower() in text.lower():
            internal_segments += 1

    # Sibling similarity: how similar is this to its siblings
    sibling_similarity = 0.0
    if len(siblings) >= 2:
        child_tags = sorted(c.name for c in element.find_all(True))
        similar_count = 0
        for sibling in siblings[1:6]:
            sib_tags = sorted(s.name for s in sibling.find_all(True))
            if child_tags == sib_tags:
                similar_count += 1
        sibling_similarity = similar_count / max(1, len(siblings) - 1)

    # Repeated structure score
    repeated_structure = sibling_similarity * 0.7 + (1.0 if len(children) >= 2 else 0.0) * 0.3

    return CandidateContainer(
        selector=selector,
        tag=element.name,
        text_density=round(text_density, 4),
        child_count=len(children),
        descendant_count=len(descendants),
        depth=_get_depth(element),
        has_price=has_price,
        has_date=has_date,
        has_time=has_time,
        has_currency=has_currency,
        has_location=has_location,
        has_organization=has_organization,
        has_contact=has_contact,
        has_link=has_link,
        has_button=has_button,
        has_image=has_image,
        has_label_value_pairs=has_label_value,
        combined_text=text[:1000],
        all_texts=all_texts,
        internal_segment_count=internal_segments,
        repeated_structure_score=round(repeated_structure, 4),
        sibling_similarity=round(sibling_similarity, 4),
    )


def _get_depth(element: Tag) -> int:
    """Get the DOM depth of an element."""
    depth = 0
    parent = element.parent
    while parent and parent.name:
        depth += 1
        parent = parent.parent
    return depth


def _compute_container_score(container: CandidateContainer) -> float:
    """Compute a universal container quality score.

    A good result container has:
    - Rich text (descriptive + values)
    - Pattern matches (price, date, etc.)
    - Repeated structure
    - Labels and values
    - Links/buttons for interaction
    - Not too deep in the DOM
    """
    score = 0.0

    # Text density: too low = empty, too high = prose
    if 2.0 <= container.text_density <= 150.0:
        score += 0.15
    elif container.text_density > 0 and container.text_density < 2.0:
        score += 0.05  # sparse but has content

    # Has meaningful content (not just a single word)
    combined_len = len(container.combined_text)
    if combined_len > 50:
        score += 0.10
    elif combined_len > 20:
        score += 0.05

    # Pattern presence
    pattern_count = sum([
        container.has_price, container.has_date, container.has_time,
        container.has_currency, container.has_location, container.has_organization,
        container.has_contact,
    ])
    score += min(pattern_count * 0.08, 0.30)

    # Label-value pairs
    if container.has_label_value_pairs:
        score += 0.10

    # Repeated structure (strong signal)
    score += container.repeated_structure_score * 0.15

    # Sibling similarity (strong signal for listing pages)
    score += container.sibling_similarity * 0.10

    # Has action elements
    if container.has_link:
        score += 0.05
    if container.has_button:
        score += 0.05
    if container.has_image:
        score += 0.03

    # Internal segments (compound records)
    score += min(container.internal_segment_count * 0.10, 0.20)

    # Depth penalty (too deep = unlikely container)
    if container.depth > 15:
        score *= 0.8
    elif container.depth < 3:
        score *= 0.6  # too shallow = likely not a real container

    # Child count: too few = no structure, too many = too broad
    if 2 <= container.child_count <= 15:
        score += 0.05

    # Penalty for being a pure price/button container (no descriptive text)
    if (container.has_price or container.has_button) and not container.has_organization and not container.has_date and not container.has_location:
        if combined_len < 80:
            score *= 0.5  # Significant penalty for narrow containers

    return round(min(score, 1.0), 4)


def _classify_page_structure(evidence: PageEvidence) -> str:
    """Classify the overall page structure type."""
    containers = evidence.candidate_containers
    patterns = evidence.patterns
    tables = evidence.tables

    # Table-based
    if tables and tables[0].get("row_count", 0) >= 3:
        return "table"

    # Card-based (repeated containers with rich content)
    good_containers = [c for c in containers if c.record_score > 0.3]
    if len(good_containers) >= 3:
        return "cards"

    # Search results
    if "location_code" in patterns and ("date_slash" in patterns or "date_iso" in patterns or "time" in patterns):
        return "search_results"

    # List
    list_containers = [c for c in containers if c.tag in ("li", "item")]
    if len(list_containers) >= 3:
        return "list"

    # Detail page
    if len(containers) <= 2 and evidence.visible_text_length > 1000:
        return "detail"

    # Single item
    if len(containers) <= 2 and evidence.visible_text_length < 1000:
        return "single_item"

    return "unknown"


def _estimate_record_count(evidence: PageEvidence) -> int:
    """Estimate how many records this page likely contains."""
    if evidence.page_structure == "cards":
        return len([c for c in evidence.candidate_containers if c.record_score > 0.3])
    if evidence.page_structure == "table":
        if evidence.tables:
            return max(t.get("row_count", 0) - 1 for t in evidence.tables)
        return 0
    if evidence.page_structure == "list":
        return len([c for c in evidence.candidate_containers if c.tag == "li"])
    return 0
