"""
Selector Discovery — LLM-guided CSS selector generation.

Extracted from scraper.py to isolate LLM-related orchestration.
"""

from __future__ import annotations

import logging
from typing import List

from app.async_utils import run_sync_in_thread
from app.config import settings
from app.html_utils import clean_html_for_selectors
from app.llm_bridge import llm_json
from app.models import SchemaField
from app.page_profiler import detect_page_structure, detect_value_patterns

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
        }
    }


def build_selector_prompt(html_snippet: str, schema_fields: list[SchemaField], page_analysis: dict | None = None) -> str:
    """Construct the prompt for selector discovery via LLM."""
    page_analysis = page_analysis or {}
    
    structure_type = page_analysis.get("structure_type", "unknown")
    structure_confidence = page_analysis.get("structure_confidence", 0.0)
    headers = page_analysis.get("headers", [])
    patterns = page_analysis.get("patterns_detected", {})
    
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
{header_context}

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
4. VERIFY FIELD SEMANTICS: Ensure the selector for "price" actually points to a price value, "title" to a title, etc.
5. If multiple elements could match, choose the most specific one.
6. Use null for fields that cannot be found.

HTML SNIPPET:
```html
{html_snippet}
```"""


async def discover_selectors(
    html: str,
    schema_fields: list[SchemaField],
) -> dict:
    """Analyze page structure and map schema to CSS selectors via LLM."""
    # 1. Analyze page structure
    page_analysis = _analyze_page_data_type(html, schema_fields)

    # 2. Map schema to CSS selectors via LLM
    html_snippet = clean_html_for_selectors(html)
    prompt = build_selector_prompt(html_snippet, schema_fields, page_analysis)

    def _sync_call():
        return llm_json(messages=[
            {
                "role": "system",
                "content": (
                    "You output valid JSON objects for CSS selector extraction. "
                    "No markdown, no commentary."
                ),
            },
            {"role": "user", "content": prompt}
        ], timeout=settings.LLM_SELECTOR_TIMEOUT)

    try:
        selectors = await run_sync_in_thread(_sync_call)
        
        if not isinstance(selectors, dict):
            logger.warning("[SelectorDiscovery] LLM returned non-dict response")
            return {}
            
        return selectors
    except Exception as e:
        logger.exception("[SelectorDiscovery] LLM extraction failed: %s", e)
        return {}
