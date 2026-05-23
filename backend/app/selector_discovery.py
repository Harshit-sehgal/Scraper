"""
Selector Discovery — LLM-guided CSS selector generation.

Extracted from scraper.py to isolate LLM-related orchestration.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from collections import Counter
from app.config import settings
from app.html_utils import clean_html_for_selectors
from app.llm_bridge import llm_json, reset_llm_call_count
from app.models import SchemaField
from app.page_profiler import detect_page_structure, detect_value_patterns
from app.motif_feedback import MotifFeedbackEngine
from app.strategy_evolution import FetchStrategy
from app.acquisition_state import AcquisitionLineage, AcquisitionState
from app.session_url_detector import detect_session_params
from app.acquisition_telemetry import get_acquisition_telemetry
from app.empty_response_detector import detect_empty_response, EmptyResponseCheck
from app.acquisition_mode import AcquisitionMode, AcquisitionConfig, should_escalate, escalate_mode

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

    selectors = {}
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
    except Exception as e:
        logger.exception("[SelectorDiscovery] LLM extraction failed: %s", e)

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
        siblings = [c for c in parent.find_all(True, recursive=False) if c.name not in ("script", "style", "noscript", "select", "option", "input", "button", "textarea", "form", "nav", "header", "footer")]
        same_class_count = sum(1 for c in siblings if " ".join(c.get("class", [])) == " ".join(el.get("class", [])))
        if same_class_count < 2:
            continue
        parent_css = _build_css_for_element(parent)
        if not parent_css:
            continue
        data_signal_count = sum(
            1 for c in siblings
            for t in [c.get_text(separator=" ", strip=True)]
            if _re.search(r"[\$£€¥₹]\s*\d+|\d{2,4}[-/]\d{2,4}[-/]\d{2,4}", t)
        )
        if data_signal_count < 2:
            continue
        candidates.append({
            "selector": parent_css,
            "item_selector": css,
            "count": same_class_count,
            "score": same_class_count * 3 + data_signal_count * 2,
            "sample_text": text[:80],
        })

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


def _discover_direct_repeating_elements(soup) -> list[dict]:
    """Find elements that repeat with the same class across the page.
    
    When multiple elements share the same class and have meaningful data,
    use that class directly as the item_container selector.
    """
    import re as _re
    candidates: list[dict] = []
    class_el_map: dict[str, list] = {}

    for el in soup.find_all(True):
        if el.name in ("script", "style", "noscript", "svg", "meta", "link", "select", "option", "input", "button", "textarea", "form", "nav", "header", "footer"):
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
        data_signals = sum(
            1 for t in non_empty
            if _re.search(r"[\$£€¥₹]\s*\d+", t)
        )
        date_signals = sum(
            1 for t in non_empty
            if _re.search(r"\d{2,4}[-/]\d{2,4}[-/]\d{2,4}", t)
        )
        text_diversity = len(set(t[:40] for t in non_empty))
        if data_signals + date_signals < 2:
            continue
        score = len(elements) * 0.5 + data_signals * 2 + date_signals * 2 + avg_text_len * 0.05 + text_diversity * 2
        if avg_text_len < 50:
            continue
        candidates.append({
            "selector": css,
            "item_selector": css,
            "count": len(elements),
            "score": score,
            "sample_text": non_empty[0][:80],
        })

    return candidates


def _fallback_parent_child_discovery(soup) -> list[dict]:
    """Fallback: find repeating child structures in parent elements."""
    candidates: list[dict] = []
    body = soup.find("body") or soup
    if not hasattr(body, "find_all"):
        return candidates
    import re as _re

    for parent in body.find_all(True):
        children = [c for c in parent.find_all(True, recursive=False) if c.name not in ("script", "style", "noscript", "svg", "select", "option", "input", "button", "textarea", "form", "nav", "header", "footer")]
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
            1 for t in non_empty
            if _re.search(r"[\$£€¥₹]\s*\d", t)
            or _re.search(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", t)
        )
        if data_signals < 2:
            continue
        diversity = len(set(t[:30] for t in non_empty))
        score = len(children) + (data_signals * 2) + diversity
        if parent.name == "tr" and parent.parent and parent.parent.name == "tbody":
            score += 5

        css = _build_css_for_element(parent)
        if css:
            candidates.append({
                "selector": css,
                "item_selector": "",
                "count": len(children),
                "score": score,
                "sample_text": non_empty[0][:80] if non_empty else "",
            })
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
    if el.name not in ("div", "span", "html", "body", "main", "section", "article", "a", "p", "li", "ul", "ol", "img", "br", "i", "b", "strong", "em", "small", "label", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th", "tbody", "thead"):
        return el.name
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


# ─── URL Analyzer — Auto-Detect Fields from a URL ────────────────────────

import re
from bs4 import BeautifulSoup


# ─── Redirect Detection ────────────────────────────────────────────────

def _detect_redirect(original_url: str, final_url: str) -> dict:
    """Detect and classify URL redirects by comparing original vs final URL.

    Compares the originally requested URL against the final URL after
    browser navigation to detect redirects and classify them.
    Works with ANY domain — no hardcoded values.

    Classification logic:
    - Same URL (or trailing-slash difference only) → no redirect
    - Different domain/scheme → cross-domain (not flagged as redirect)
    - Final URL is homepage (/) and original had a deep path → homepage redirect
    - Path shortened significantly (deep → shallow) → session/expired token redirect
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

    # Different domain/scheme — cross-domain navigation, not a site redirect
    if parsed_orig.netloc != parsed_final.netloc:
        return {
            "redirected": False,
            "redirect_type": "none",
            "message": f"Different domain: {parsed_orig.netloc} → {parsed_final.netloc}",
            "original_url": original_url,
            "final_url": final_url,
        }

    orig_path = parsed_orig.path.rstrip("/")
    final_path = parsed_final.path.rstrip("/")

    orig_segments = [s for s in orig_path.split("/") if s]
    final_segments = [s for s in final_path.split("/") if s]

    # Redirect to homepage (final is "/" or empty)
    if not final_path or final_path == "/":
        # Deep path (3+ segments) redirected to homepage → likely expired session/token
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
        # Deep path → shallow path: likely expired session/token
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
    empty/poor pages (no repeating data containers), and pages with real
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

    # Hero/banner sections (generic selectors, no hardcoded domain)
    hero_selectors = [
        ".hero", ".banner", ".jumbotron", ".landing", ".cover",
        "[class*='hero']", "[class*='banner']", "[class*='landing']",
        "[class*='jumbotron']",
    ]
    for sel in hero_selectors:
        try:
            if soup.select(sel):
                landing_signals.append("hero_banner")
                break
        except Exception:
            continue

    # Search forms (generic — any form with text/search input)
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

    # Welcome/landing page text patterns (generic, domain-agnostic)
    body_text = soup.get_text().lower()[:2000]
    welcome_patterns = [
        "welcome", "find your", "search for", "book now", "get started",
        "start your", "explore", "discover", "find the best",
        "looking for", "where are you going", "destination",
    ]
    for pattern in welcome_patterns:
        if pattern in body_text:
            landing_signals.append(f"landing_text:{pattern}")
            break  # One landing text signal is enough

    # ── Data Container Detection ────────────────────────────────────
    data_container_count = 0
    has_profile_selector = profile is not None and hasattr(profile, 'container_selector')
    container_selector = profile.container_selector if has_profile_selector else None

    if container_selector and container_selector != "body":
        try:
            containers = soup.select(container_selector)
            data_container_count = sum(
                1 for c in containers
                if len(c.get_text(strip=True)) > 20
            )
        except Exception:
            pass

    # ── Generic Data Container Discovery (fallback) ─────────────────
    # When profile's container selector finds little, scan for repeating
    # element patterns across the full DOM (no hardcoded selectors).
    if data_container_count < 3:
        tag_class_counts: Counter = Counter()
        for tag in soup.find_all(True):
            if tag.name in ('script', 'style', 'noscript', 'svg', 'form', 'nav', 'footer', 'header'):
                continue
            classes = ' '.join(tag.get('class', []) or [])
            if classes:
                key = f"{tag.name}.{'.'.join(classes.split()[:2])}"
                tag_class_counts[key] += 1

        # Find patterns with many repetitions (3+) — likely data containers
        for pattern, count in tag_class_counts.most_common(20):
            if count < 3:
                continue
            try:
                # Build a rough CSS selector from the pattern
                css_sel = pattern.replace('.', '.')
                matching = soup.select(css_sel)
                content_count = sum(
                    1 for m in matching
                    if len(m.get_text(strip=True)) > 20
                )
                if content_count > data_container_count:
                    data_container_count = content_count
            except Exception:
                continue

        # Also scan for repeating direct children of common containers
        for container_tag in ['div', 'li', 'article', 'section', 'tr']:
            parents = soup.find_all(container_tag, limit=10)
            for parent in parents:
                children = parent.find_all(recursive=False)
                if len(children) >= 3:
                    # Check if children share the same structure
                    child_classes = [
                        ' '.join(c.get('class', []) or []) for c in children
                    ]
                    unique_classes = len(set(child_classes))
                    if unique_classes <= 2:
                        # Likely repeating items
                        data_container_count = max(
                            data_container_count, len(children)
                        )

    # ── Classification ──────────────────────────────────────────────
    is_landing_page = (
        len(landing_signals) >= 2
        or (len(landing_signals) >= 1 and data_container_count < 3)
    )

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


# ─── Search Form Detection ──────────────────────────────────────────────

def _detect_search_form(html: str) -> dict:
    """Detect search forms on a page and extract their field structure.

    Scans the page HTML for forms that look like search/query forms
    (text inputs with location, date, or search-related names/placeholders),
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
        (city/date/airport related names and placeholders)
    """
    soup = BeautifulSoup(html, "html.parser")
    forms = soup.find_all("form")

    # Keywords that suggest a field is a search/query parameter
    SEARCH_FIELD_NAMES: set[str] = {
        "fro", "from", "to", "destination", "origin", "source", "target",
        "depart", "arrive", "arrival", "return",
        "city", "airport", "location", "place",
        "date", "checkin", "checkout", "check_in", "check_out",
        "departure_date", "return_date", "travel_date",
        "adult", "child", "infant", "passenger", "guest",
        "cabin", "class", "cabinclass", "cabin_class",
        "query", "search", "q", "keyword",
    }
    SEARCH_PLACEHOLDER_PATTERNS: list[str] = [
        r"from|to", r"destination|origin", r"city|airport|location",
        r"depart|arrive|return",
        r"date|when|check.?in|check.?out",
        r"search|find|fly|flight|book",
        r"adult|child|infant|passenger|guest",
        r"leaving|going|where",
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
        "origin": ["origin", "from", "fro", "frocity", "departure", "depart", "leaving"],
        "destination": ["destination", "dest", "to", "tocity", "arrival", "arrive", "going"],
        "departure_date": ["departure_date", "departdate", "frodate", "depart", "checkin", "check_in"],
        "return_date": ["return_date", "returndate", "todate", "return", "checkout", "check_out"],
        "date": ["date", "travel_date", "traveldate"],
        "adults": ["adult", "adults", "passenger", "passengers"],
        "children": ["child", "children", "kid", "kids"],
        "infants": ["infant", "infants"],
        "cabin_class": ["cabin", "cabinclass", "cabin_class", "class"],
        "query": ["query", "search", "q", "keyword"],
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
                    score = 5   # Substring match on name/id
                elif kw_norm in placeholder:
                    score = 3   # Placeholder match

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
        landing_page_html: HTML of the landing/homepage (after redirect)
        landing_page_url: URL of the landing page (for resolving relative actions)
        search_params: Dict of search parameters
            (e.g. {"origin": "NYC", "destination": "LHR", "departure_date": "05/15/2026"})

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
        # Could not map any params — return the form structure so the user can see what's needed
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

    logger.info(
        "[SearchRecovery] POSTing to %s with params: %s",
        absolute_action, mapped_params,
    )

    # Step 3: Submit the form
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
        ) as client:
            if form_method == "GET":
                resp = await client.get(absolute_action, params=mapped_params)
            else:
                resp = await client.post(absolute_action, data=mapped_params)

            fresh_url = str(resp.url)
            fresh_html = resp.text

            if resp.status_code >= 400:
                return {
                    "success": False,
                    "fresh_url": fresh_url,
                    "fresh_html": fresh_html,
                    "form_detected": True,
                    "form_info": form_info,
                    "error": f"Search form submission returned HTTP {resp.status_code}",
                }

            logger.info(
                "[SearchRecovery] Form submitted successfully → %s (status %d)",
                fresh_url, resp.status_code,
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


async def analyze_url_for_fields(url: str, search_params: dict[str, str] | None = None, acquisition_mode: str = "standard", _escalation_depth: int = 0) -> dict:
    """Analyze a URL and auto-detect what data fields can be extracted.

    This is the core of the "preview URL → suggest fields" workflow.

    1. Fetches the URL using anti-bot stealth headers
    2. Detects redirects by comparing original vs final URL
    3. If redirected (session_expired) AND search_params provided, attempts
       recovery by POSTing to the site's search form to generate a fresh session
    4. Assesses content quality (landing page vs data page)
    5. Analyzes page structure (table/cards/list/mixed)
    6. Detects value patterns (currencies, dates, ratings, etc.)
    7. Uses LLM to discover all data fields and their selectors
    8. Returns suggested fields with types, confidence, and example values

    Every step is fully generic — no hardcoded domains, paths, or selectors.

    Args:
        url: The URL to analyze
        search_params: Optional dict of search parameters to POST to the
            site's search form if the URL has expired. Keys are semantic
            (e.g. origin, destination, departure_date, return_date, adults).
            Values are the search values (e.g. "NYC", "LHR", "05/15/2026").

    Returns:
        dict with:
        - url: str
        - redirect_info: dict (redirect detection result or None)
        - content_quality: dict (content quality assessment or None)
        - search_form: dict (detected search form structure or None)
        - search_recovery: dict (recovery attempt result or None)
        - page_structure: str (table|cards|list|mixed)
        - structure_confidence: float
        - estimated_record_count: int
        - item_container: str (CSS selector)
        - suggested_fields: list of field suggestions
        - anti_bot_score: float
    """
    from app.html_utils import fetch_page_content as _fetch_page_content
    from app.scrape_telemetry import detect_anti_bot
    import httpx

    reset_llm_call_count()
    start_time = time.time()

    # Build acquisition config from the requested mode
    try:
        mode_enum = AcquisitionMode(acquisition_mode)
    except ValueError:
        mode_enum = AcquisitionMode.STANDARD
    config = AcquisitionConfig.from_mode(mode_enum)

    logger.info("[URLAnalyzer] Fetching and analyzing: %s", url)

    # ── Step 1: Determine final URL (lightweight check) ──────────────
    # Use a quick httpx request to determine where the URL ultimately
    # resolves to, without the overhead of a full Playwright session.
    final_url = url
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(10.0),
        ) as client:
            resp = await client.get(url)
            if str(resp.url) != url:
                final_url = str(resp.url)
                logger.info(
                    "[URLAnalyzer] URL redirected: %s → %s", url, final_url
                )
    except Exception:
        logger.debug("[URLAnalyzer] Could not determine final URL via httpx for %s", url)
        pass

    # Run redirect detection immediately (before full fetch)
    redirect_info = _detect_redirect(url, final_url)

    # Detect session-bound URL parameters
    session_detection = detect_session_params(url) if config.detect_session_params else {
        "is_session_bound": False, "ephemeral_params": [], "canonical_url": url, "confidence": 0.0, "details": []
    }

    # ── Step 2: Fetch the URL with anti-bot stealth ──────────────────
    try:
        html, js_render_delay, fetch_method, retry_count = await _fetch_page_content(
            url, preferred_method=FetchStrategy.PLAYWRIGHT_FULL
        )
    except Exception as e:
        logger.error("[URLAnalyzer] Failed to fetch %s: %s", url, e)
        return {
            "url": url,
            "redirect_info": redirect_info,
            "acquisition_lineage": AcquisitionLineage(
                original_url=url, final_url=final_url,
                state=AcquisitionState.DIRECT,
                message=f"Failed to fetch URL: {str(e)}",
            ).model_dump(mode="json"),
            "user_message": f"Failed to fetch the URL: {str(e)}",
            "session_detection": session_detection,
            "canonical_url": session_detection.get("canonical_url", url),
            "content_quality": None,
            "empty_check": {"is_empty": True, "empty_type": "blank", "confidence": 1.0, "message": "Failed to fetch", "suggestions": []},
            "search_form": None,
            "search_recovery": None,
            "error": f"Failed to fetch URL: {str(e)}",
            "page_structure": "unknown",
            "structure_confidence": 0.0,
            "estimated_record_count": 0,
            "item_container": None,
            "suggested_fields": [],
            "anti_bot_score": 0.0,
            "acquisition_mode": acquisition_mode,
        }

    if not html or len(html.strip()) < 100:
        return {
            "url": url,
            "redirect_info": redirect_info,
            "acquisition_lineage": AcquisitionLineage(
                original_url=url, final_url=final_url,
                state=AcquisitionState.DIRECT,
                message="Fetched page appears empty",
            ).model_dump(mode="json"),
            "user_message": "The fetched page appears to be empty.",
            "session_detection": session_detection,
            "canonical_url": session_detection.get("canonical_url", url),
            "content_quality": None,
            "empty_check": {"is_empty": True, "empty_type": "blank", "confidence": 1.0, "message": "Fetched page appears empty", "suggestions": ["The URL may be incorrect or the server returned an empty page"]},
            "search_form": None,
            "search_recovery": None,
            "error": "Fetched page appears empty",
            "page_structure": "unknown",
            "structure_confidence": 0.0,
            "estimated_record_count": 0,
            "item_container": None,
            "suggested_fields": [],
            "anti_bot_score": 0.0,
            "acquisition_mode": acquisition_mode,
        }

    # ── Step 3: Search Form Recovery (for expired session URLs) ──────
    # If the URL redirected (e.g. session token expired) and the user
    # provided search params, attempt to POST to the site's search form
    # to generate a fresh search session.
    search_form = _detect_search_form(html) if config.attempt_search_form else {"detected": False, "form_fields": [], "action": ""}
    search_recovery = None

    if (
        config.attempt_recovery
        and redirect_info.get("redirected")
        and search_params
        and search_form.get("detected")
    ):
        logger.info(
            "[URLAnalyzer] Redirected URL with search params — attempting recovery via %s",
            search_form.get("action", "/search"),
        )
        search_recovery = await _try_form_search_recovery(
            landing_page_html=html,
            landing_page_url=final_url,
            search_params=search_params,
        )

        # If recovery succeeded, analyze the fresh session page
        if search_recovery.get("success") and search_recovery.get("fresh_html"):
            logger.info(
                "[URLAnalyzer] Recovery succeeded → %s, re-analyzing fresh page",
                search_recovery.get("fresh_url", ""),
            )
            # Re-analyze the fresh session results page
            html = search_recovery["fresh_html"]
            fetch_method = "search_form_post"
            # Update final URL for the fresh session
            if search_recovery.get("fresh_url"):
                final_url = search_recovery["fresh_url"]
            # Update redirect_info to reflect successful recovery
            redirect_info = build_redirect_info(
                original_url=url,
                final_url=final_url,
                search_recovery=search_recovery,
                search_form=search_form,
                search_params=search_params,
                fetch_method=fetch_method,
                existing_redirect_info=redirect_info,
            )
    else:
        # If redirected but no search params provided, still detect the form
        # to guide the user on what params are available
        if redirect_info.get("redirected") and search_form.get("detected"):
            logger.info(
                "[URLAnalyzer] Redirected URL with search form detected — "
                "provide search_params to attempt recovery. Fields: %s",
                [f["name"] or f["id"] for f in (search_form.get("search_fields") or []) if isinstance(f, dict)],  # type: ignore[union-attr]
            )

    # ── Step 4: Check anti-bot score ─────────────────────────────────
    anti_bot_score = detect_anti_bot(html)

    # ── Step 5: Analyze page structure and value patterns ─────────────
    profile = detect_page_structure(html)
    patterns = detect_value_patterns(html)

    page_analysis = {
        "structure_type": profile.structure_type,
        "structure_confidence": profile.structure_confidence,
        "headers": profile.headers,
    }

    # ── Step 6: Content Quality Gate ─────────────────────────────────
    content_quality = _assess_content_quality(html, profile)

    # ── Step 6b: Empty Response Check ─────────────────────────────────
    # Detect pages that return 200 but have no useful data
    empty_check = detect_empty_response(html) if config.detect_empty_responses else EmptyResponseCheck(
        is_empty=False, empty_type="", confidence=0.0, message="Empty response detection disabled"
    )

    # ── Step 7: Extract container values and build structured prompt ─
    container_values = _extract_container_text_values(html, profile.container_selector)

    # If we got very few values from the container, fall back to scanning
    # visible page text for individual values
    if len(container_values) < 3:
        soup = BeautifulSoup(html, "html.parser")
        for noise in soup(['script', 'style', 'nav', 'footer', 'header', 'noscript', 'svg', 'form']):
            noise.decompose()
        visible_text = soup.get_text(separator=" ", strip=True)
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

    # ── Step 8: Build structured response ────────────────────────────
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
                    "selector": "",
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

    # Log with redirect/quality/recovery context
    quality_warning = ""
    if redirect_info.get("redirected"):
        quality_warning = f" [REDIRECTED: {redirect_info.get('redirect_type', 'unknown')}]"
    if content_quality.get("quality") != "good":
        quality_warning += f" [QUALITY: {content_quality.get('quality', 'unknown')}]"
    if search_recovery and search_recovery.get("success"):
        quality_warning += " [RECOVERED via search form]"
    logger.info(
        "[URLAnalyzer] Analyzed %s: %s structure, %d fields suggested, %.1fs%s",
        url if not search_recovery else search_recovery.get("fresh_url", url),
        profile.structure_type, len(suggested_fields), elapsed, quality_warning,
    )

    # Build acquisition lineage from the final state
    acquisition_lineage = AcquisitionLineage.from_redirect_info(
        redirect_info=redirect_info,
        original_url=url,
        final_url=final_url,
        fetch_method=fetch_method,
        search_recovery=search_recovery,
        search_form=search_form if search_form else None,
        search_params=search_params,
    )
    # Enrich lineage with session detection results
    acquisition_lineage.session_bound = bool(session_detection.get("is_session_bound", False))  # type: ignore[assignment]
    acquisition_lineage.ephemeral_params = list(session_detection.get("ephemeral_params") or [])  # type: ignore[assignment,arg-type]

    # If the page is effectively empty, update the acquisition state
    if empty_check.is_empty and acquisition_lineage.state == AcquisitionState.DIRECT:
        acquisition_lineage.state = AcquisitionState.EMPTY_RESPONSE
        acquisition_lineage.message = empty_check.message

    # Determine the canonical URL: the stable, bookmarkable URL
    # If recovery succeeded, use the recovered URL; otherwise use the
    # session-stripped version of the original URL
    canonical_url = session_detection["canonical_url"]
    if acquisition_lineage.state == AcquisitionState.RECOVERED and acquisition_lineage.recovered_url:
        canonical_url = acquisition_lineage.recovered_url

    # Record acquisition telemetry
    try:
        get_acquisition_telemetry().record(
            url=url,
            state=acquisition_lineage.state,
            original_url=acquisition_lineage.original_url,
            final_url=acquisition_lineage.final_url,
            canonical_url=canonical_url,  # type: ignore[arg-type]
            fetch_method=fetch_method,
            session_bound=bool(session_detection.get("is_session_bound", False)),  # type: ignore[arg-type]
            ephemeral_params=list(session_detection.get("ephemeral_params") or []),  # type: ignore[arg-type,arg-type]
            recovery_method=acquisition_lineage.recovery_method,
            recovered_url=acquisition_lineage.recovered_url,
            fetch_time_ms=round((time.time() - start_time) * 1000, 1),
        )
    except Exception:
        logger.debug("[URLAnalyzer] Failed to record acquisition telemetry", exc_info=True)

    # ── Escalation Check ─────────────────────────────────────────────
    # If the acquisition failed or was degraded, check whether we should
    # escalate to a more aggressive mode and retry.
    escalated_mode = None
    max_depth = config.max_retries
    if (_escalation_depth < max_depth
            and should_escalate(mode_enum, acquisition_lineage.state.value, empty_check.is_empty)):
        escalated_mode = escalate_mode(mode_enum)
        if escalated_mode != mode_enum:
            logger.info(
                "[URLAnalyzer] Escalating from %s → %s (depth %d) due to state=%s",
                mode_enum.value, escalated_mode.value, _escalation_depth + 1, acquisition_lineage.state.value,
            )
            return await analyze_url_for_fields(
                url=url,
                search_params=search_params,
                acquisition_mode=escalated_mode.value,
                _escalation_depth=_escalation_depth + 1,
            )

    return {
        "url": url,
        "redirect_info": redirect_info,
        "acquisition_lineage": acquisition_lineage.model_dump(mode="json"),
        "user_message": acquisition_lineage.get_user_message(),
        "session_detection": session_detection,
        "canonical_url": canonical_url,
        "acquisition_mode": acquisition_mode,
        "acquisition_config": {
            "mode": config.mode.value,
            "attempt_recovery": config.attempt_recovery,
            "attempt_search_form": config.attempt_search_form,
            "use_playwright": config.use_playwright,
            "detect_empty_responses": config.detect_empty_responses,
            "detect_session_params": config.detect_session_params,
            "max_retries": config.max_retries,
            "escalated": escalated_mode is not None,
        },
        "content_quality": content_quality,
        "empty_check": {
            "is_empty": empty_check.is_empty,
            "empty_type": empty_check.empty_type,
            "confidence": empty_check.confidence,
            "message": empty_check.message,
            "suggestions": empty_check.suggestions,
        },
        "search_form": search_form if search_form.get("detected") else None,
        "search_recovery": search_recovery,
        "page_structure": profile.structure_type,
        "structure_confidence": profile.structure_confidence,
        "estimated_record_count": estimated_records,
        "item_container": item_container,
        "fetch_method": fetch_method,
        "fetch_time_ms": round((time.time() - start_time) * 1000, 1),
        "anti_bot_score": round(anti_bot_score, 3),
        "suggested_fields": suggested_fields,
    }
