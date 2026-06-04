"""Page analysis and DOM-based CSS selector discovery.

Extracted from selector_discovery.py for modularity.

Ownership boundary: these functions handle HTML / DOM parsing, structure
analysis, and programmatic CSS selector discovery. LLM-based orchestration
and URL-level concerns (redirects, recovery) live in sibling modules.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup

from app.config import settings
from app.page_profiler import detect_page_structure, detect_value_patterns

if TYPE_CHECKING:
    from app.models import SchemaField

logger = logging.getLogger(__name__)


def _get_feedback_engine():
    """Lazy import to respect test mocking at app.selector_discovery.MotifFeedbackEngine."""
    from app.selector_discovery import MotifFeedbackEngine as _MotifFeedbackEngine

    return _MotifFeedbackEngine()


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
        },
    }


def build_selector_prompt(
    html_snippet: str,
    schema_fields: list[SchemaField],
    page_analysis: dict | None = None,
    solidified_motifs: list | None = None,
) -> str:
    """Construct the prompt for selector discovery via LLM.

    Args:
        html_snippet: The HTML to extract from
        schema_fields: Target schema fields
        page_analysis: Optional page structure analysis
        solidified_motifs: Optional learned structural patterns for adaptive hints

    """
    page_analysis = page_analysis or {}

    structure_type = page_analysis.get("structure_type", "unknown")
    structure_confidence = page_analysis.get("structure_confidence", 0.0)
    headers = page_analysis.get("headers", [])
    patterns = page_analysis.get("patterns_detected", {})

    # Generate motif feedback context if available
    motif_context = ""
    if solidified_motifs:
        feedback_engine = _get_feedback_engine()
        motif_hint = feedback_engine.build_motif_context(solidified_motifs, schema_fields)
        if motif_hint:
            motif_context = "\n" + motif_hint + "\n"

    structure_context = f"""
PAGE STRUCTURE DETECTED: {structure_type.upper()} (confidence: {structure_confidence:.2f})
- This could be a table, card layout, list, or mixed structure
- Target the DATA CONTAINER, not header / footer / navigation
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
        hint += f" (type: {f.field_type.value})"
        if f.description:
            hint += f": {f.description}"
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
- Filter / sort options, sidebar content
- Login / signup forms, social media links
- Copyright / terms / privacy pages

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
        solidified_motifs: Optional learned structural patterns for adaptive hints

    """
    # Lazy imports to respect test patching at app.selector_discovery.*
    from app.selector_discovery import clean_html_for_selectors as _clean_html
    from app.selector_discovery import llm_json as _llm_json

    # 1. Analyze page structure
    page_analysis = _analyze_page_data_type(html, schema_fields)

    # 2. Map schema to CSS selectors via LLM
    html_snippet = _clean_html(html)
    prompt = build_selector_prompt(html_snippet, schema_fields, page_analysis, solidified_motifs)

    selectors = {}
    try:
        selectors = await _llm_json(
            messages=[
                {
                    "role": "system",
                    "content": ("You output valid JSON objects for CSS selector extraction. No markdown, no commentary."),
                },
                {"role": "user", "content": prompt},
            ],
            timeout=settings.LLM_SELECTOR_TIMEOUT,
        )
    except Exception:
        logger.exception("[SelectorDiscovery] LLM extraction failed: %s")

    if not isinstance(selectors, dict):
        selectors = {}

    container_sel = selectors.get("item_container")
    if container_sel and str(container_sel).strip():
        return selectors

    logger.info("[SelectorDiscovery] LLM returned no item_container, falling back to DOM discovery")
    dom_selectors = _discover_selectors_from_dom(html, schema_fields)
    if dom_selectors and dom_selectors.get("item_container"):
        logger.info("[SelectorDiscovery] DOM discovery found container: %s", dom_selectors["item_container"])
        return dom_selectors

    return selectors or {}


def _discover_selectors_from_dom(html: str, schema_fields: list[SchemaField]) -> dict | None:
    """Discover container and field selectors by analyzing repeating DOM patterns.

    Falls back to structural DOM analysis when the LLM cannot produce CSS selectors.
    Uses ONLY general heuristics — no domain-specific selectors or class names.
    """
    soup = BeautifulSoup(html, "html.parser")
    if not soup:
        return None

    body = soup.find("body") or soup
    if not hasattr(body, "find_all"):
        return None
    import re as _re

    element_classes: list[tuple[Any, str, str]] = []
    for el in body.find_all(True):
        classes = el.get("class")
        if not classes:
            continue
        css = _build_css_for_element(el)
        if not css:
            continue
        text = el.get_text(separator=" ", strip=True)
        if len(text) < 20:
            continue
        element_classes.append((el, css, text))

    css_counts = Counter(css for _, css, _ in element_classes)
    repeating_css = {css for css, count in css_counts.items() if count >= 3}

    candidates: list[dict] = []
    for el, css, text in element_classes:
        if css not in repeating_css:
            continue
        parent = el.parent
        if not parent:
            continue
        siblings = [
            c
            for c in parent.find_all(True, recursive=False)
            if c.name
            not in (
                "script",
                "style",
                "noscript",
                "select",
                "option",
                "input",
                "button",
                "textarea",
                "form",
                "nav",
                "header",
                "footer",
            )
        ]
        same_class_count = sum(1 for c in siblings if " ".join(c.get("class", [])) == " ".join(el.get("class", [])))
        if same_class_count < 2:
            continue
        parent_css = _build_css_for_element(parent)
        if not parent_css:
            continue
        if len(parent.find_all(True)) > 0:
            parent_page_matches = len(soup.select(parent_css))
            if parent_page_matches < 2:
                continue
        data_signal_count = sum(
            1
            for c in siblings
            for t in [c.get_text(separator=" ", strip=True)]
            if _re.search(r"[\$£€¥₹]\s*\d+|\d{2,4}[-/]\d{2,4}[-/]\d{2,4}", t)
        )
        if data_signal_count < 2:
            continue
        candidates.append(
            {
                "selector": parent_css,
                "item_selector": css,
                "count": same_class_count,
                "score": same_class_count * 3 + data_signal_count * 2,
                "sample_text": text[:80],
            },
        )

    if not candidates:
        candidates = _discover_direct_repeating_elements(soup)
    else:
        candidates.extend(_discover_direct_repeating_elements(soup))
    if not candidates:
        candidates = _fallback_parent_child_discovery(soup)
    else:
        candidates.extend(_fallback_parent_child_discovery(soup))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    field_selectors = _infer_field_selectors_from_container(best["selector"], html, schema_fields)

    return {
        "item_container": best["selector"],
        "fields": field_selectors,
        "_discovery_method": "dom_fallback",
    }


def _compute_ui_noise_score(elements: list, texts: list[str]) -> float:
    """Score how likely a container candidate is to be UI chrome vs data.

    Uses structural signals — no domain-specific phrases:
    - High link / button ratio → likely nav / sidebar
    - Short average text length → likely menu / filter labels
    - Low percent of elements with price / date signals → likely non-data
    - High ratio of elements near nav / header / footer tags → likely chrome

    Returns 0.0 (definitely data) to 1.0 (definitely UI chrome).
    """
    if not elements or not texts:
        return 1.0
    import re as _re

    n = len(texts)
    link_ratio = sum(1 for el in elements if el.name == "a") / max(n, 1)
    form_ratio = sum(1 for el in elements if el.name in ("input", "select", "button", "textarea")) / max(n, 1)
    short_text_ratio = sum(1 for t in texts if len(t) < 15) / max(n, 1)
    price_or_date_ratio = sum(1 for t in texts if _re.search(r"[\$£€¥₹]\s*\d+|\d{2,4}[-/]\d{2,4}[-/]\d{2,4}", t)) / max(n, 1)
    low_diversity = 1.0 if len({t[:20] for t in texts}) < max(n * 0.3, 2) else 0.0
    near_chrome = 0
    for el in elements:
        p = el.parent
        for _ in range(3):
            if not p or not hasattr(p, "name"):
                break
            if p.name in ("nav", "header", "footer", "aside"):
                near_chrome += 1
                break
            p = p.parent if hasattr(p, "parent") else None
    near_chrome_ratio = near_chrome / max(n, 1)
    score = (
        link_ratio * 0.3
        + form_ratio * 0.2
        + short_text_ratio * 0.3
        + (1.0 - price_or_date_ratio) * 0.4
        + low_diversity * 0.2
        + near_chrome_ratio * 0.3
    )
    return min(max(score, 0.0), 1.0)


def _discover_direct_repeating_elements(soup) -> list[dict]:
    """Find elements that repeat with the same class across the page.

    When multiple elements share the same class and have meaningful data,
    use that class directly as the item_container selector.
    """
    import re as _re

    candidates: list[dict] = []
    class_el_map: dict[str, list] = {}

    for el in soup.find_all(True):
        if el.name in (
            "script",
            "style",
            "noscript",
            "svg",
            "meta",
            "link",
            "select",
            "option",
            "input",
            "button",
            "textarea",
            "form",
            "nav",
            "header",
            "footer",
        ):
            continue
        css = _build_css_for_element(el)
        if not css:
            continue
        if el.name in ("script", "style", "noscript", "svg", "meta", "link"):
            continue
        if css not in class_el_map:
            class_el_map[css] = []
        class_el_map[css].append(el)

    for css, elements in class_el_map.items():
        if len(elements) < 3:
            continue
        texts = [el.get_text(separator=" ", strip=True) for el in elements]
        non_empty = [t for t in texts if len(t) > 20]
        if len(non_empty) < 3:
            continue
        empty_ratio = (len(texts) - len(non_empty)) / max(len(texts), 1)
        if empty_ratio > 0.3:
            continue
        avg_text_len = sum(len(t) for t in texts) / max(len(texts), 1)
        data_signals = sum(1 for t in non_empty if _re.search(r"[\$£€¥₹]\s*\d+", t))
        date_signals = sum(1 for t in non_empty if _re.search(r"\d{2,4}[-/]\d{2,4}[-/]\d{2,4}", t))
        text_diversity = len({t[:40] for t in non_empty})
        ui_noise_score = _compute_ui_noise_score(elements, non_empty)
        if ui_noise_score > 0.6:
            continue
        if data_signals + date_signals < 2:
            continue
        score = len(elements) * 0.5 + data_signals * 2 + date_signals * 2 + avg_text_len * 0.05 + text_diversity * 2
        if avg_text_len < 50:
            continue
        candidates.append(
            {
                "selector": css,
                "item_selector": css,
                "count": len(elements),
                "score": score,
                "sample_text": non_empty[0][:80],
            },
        )

    return candidates


def _fallback_parent_child_discovery(soup) -> list[dict]:
    """Fallback: find repeating child structures in parent elements."""
    candidates: list[dict] = []
    body = soup.find("body") or soup
    if not hasattr(body, "find_all"):
        return candidates
    import re as _re

    for parent in body.find_all(True):
        children = [
            c
            for c in parent.find_all(True, recursive=False)
            if c.name
            not in (
                "script",
                "style",
                "noscript",
                "svg",
                "select",
                "option",
                "input",
                "button",
                "textarea",
                "form",
                "nav",
                "header",
                "footer",
            )
        ]
        if len(children) < 2:
            continue

        child_tags = [c.name for c in children]
        if len(set(child_tags)) > 3:
            continue

        child_classes = [" ".join(c.get("class", [])) for c in children]
        if len(set(child_classes)) > max(3, len(children) * 0.7):
            continue

        child_texts = [c.get_text(separator=" ", strip=True) for c in children]
        non_empty = [t for t in child_texts if len(t) > 20]
        if len(non_empty) < 2:
            continue

        data_signals = sum(
            1 for t in non_empty if _re.search(r"[\$£€¥₹]\s*\d", t) or _re.search(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", t)
        )
        if data_signals < 2:
            continue
        diversity = len({t[:30] for t in non_empty})
        score = len(children) + (data_signals * 2) + diversity
        if parent.name == "tr" and parent.parent and parent.parent.name == "tbody":
            score += 5

        css = _build_css_for_element(parent)
        if css:
            candidates.append(
                {
                    "selector": css,
                    "item_selector": "",
                    "count": len(children),
                    "score": score,
                    "sample_text": non_empty[0][:80] if non_empty else "",
                },
            )
    return candidates


def _build_css_for_element(el) -> str | None:
    """Build a CSS selector for a BeautifulSoup element using class or id."""
    if el.get("id"):
        return f"#{el['id']}"
    classes = el.get("class")
    if classes:
        cls_sel = "".join(f".{c}" for c in classes[:2])
        if el.name not in ("div", "span", "html", "body"):
            return f"{el.name}{cls_sel}"
        return cls_sel
    if el.name not in (
        "div",
        "span",
        "html",
        "body",
        "main",
        "section",
        "article",
        "a",
        "p",
        "li",
        "ul",
        "ol",
        "img",
        "br",
        "i",
        "b",
        "strong",
        "em",
        "small",
        "label",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "tr",
        "td",
        "th",
        "tbody",
        "thead",
    ):
        return el.name  # type: ignore[no-any-return]
    return None


def _infer_field_selectors_from_container(container_sel: str, html: str, schema_fields: list[SchemaField]) -> dict:
    """Infer field-level selectors by scanning container items for type-matching text.

    Returns a dict mapping field_name to selector (string). Empty string means
    the field was identified but no CSS selector could be generated — the fallback
    in selector_engine.py will use type patterns to extract values.
    """
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select(container_sel)
    if not containers:
        return {}

    field_map: dict = {}
    first_item = containers[0]

    for field in schema_fields:
        fname = field.name
        ftype = field.field_type.value if hasattr(field.field_type, "value") else str(field.field_type)

        if ftype in ("currency", "number", "date", "email", "phone", "url", "code", "rating"):
            field_map[fname] = ""
            continue

        elements = first_item.find_all(True)
        for el in elements:
            txt = el.get_text(separator=" ", strip=True)
            if not txt:
                continue
            name_lower = fname.lower().replace("_", " ")
            if name_lower in txt.lower()[:40]:
                css = _build_css_for_element(el)
                if css:
                    field_map[fname] = css
                    break

        if fname not in field_map:
            field_map[fname] = ""

    return field_map
