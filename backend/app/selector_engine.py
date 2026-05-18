import re
import logging
from bs4 import BeautifulSoup
from app.models import SchemaField, FieldType
from app.page_profiler import detect_page_structure, detect_value_patterns
from app.html_utils import (
    _compact_text, _is_empty_value, _is_likely_noise_row,
    _extract_contacts_from_node, _sanitize_field_value,
    _enrich_record_contacts, _apply_page_level_contact_fallback
)
from app.llm_bridge import llm_json
from app.async_utils import run_sync_in_thread
from app.utils.quality import score_record_quality
from app.data_utils import normalize_scraped_record

def _detect_table_headers(html: str) -> list[dict]:
    """Detect table/grid headers from HTML to understand column semantics."""
    soup = BeautifulSoup(html, "html.parser")
    headers_info = []

    for th in soup.find_all(["th", "thead"]):
        text = _compact_text(th.get_text())
        if text:
            headers_info.append({
                "text": text,
                "class": " ".join(th.get("class", [])),
                "id": th.get("id", ""),
            })

    for header in soup.find_all(["h1", "h2", "h3", "h4"])[:5]:
        text = _compact_text(header.get_text())
        if text and len(text) < 50:
            headers_info.append({
                "text": text,
                "is_heading": True,
            })

    return headers_info

def _analyze_page_data_type(html: str, schema_fields: list[SchemaField]) -> dict:
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

def _intelligent_column_mapping(html: str, schema_fields: list[SchemaField]) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    mapping_hints: dict = {}

    table = soup.find("table") or soup.find("div", class_=lambda x: x and ("table" in x or "grid" in x))
    if not table:
        return mapping_hints

    headers = []
    for th in table.find_all(["th", "thead"]):
        headers.append(_compact_text(th.get_text()).lower())

    for field in schema_fields:
        field_keywords = _get_field_keywords(field.name)
        for i, header in enumerate(headers):
            for keyword in field_keywords:
                if keyword in header:
                    mapping_hints[field.name] = {"column_index": i, "matched_header": header}
                    break

    return mapping_hints

def _get_field_keywords(field_name: str) -> list[str]:
    name_lower = field_name.lower().replace("_", " ")
    base = [name_lower]

    keywords_map = {
        "price": ["price", "cost", "amount", "rate", "fee", "fare"],
        "date": ["date", "day", "time", "start", "end", "begin", "schedule"],
        "time": ["time", "duration", "start", "end", "schedule"],
        "name": ["name", "title", "title", "company"],
        "phone": ["phone", "contact", "mobile", "call"],
        "email": ["email", "mail", "contact"],
        "address": ["address", "location", "place"],
        "rating": ["rating", "review", "star", "score"],
        "description": ["description", "about", "detail", "info"],
    }

    for key, synonyms in keywords_map.items():
        if key in name_lower:
            base.extend(synonyms)

    return base

def _infer_field_type_from_examples(examples: list[str], field_name: str) -> str:
    if not examples:
        return "string"

    name_lower = field_name.lower()

    if any(k in name_lower for k in ["price", "cost", "amount"]):
        return "currency"
    if any(k in name_lower for k in ["date", "time", "start", "end", "schedule"]):
        return "date"
    if any(k in name_lower for k in ["duration", "hours"]):
        return "duration"
    if any(k in name_lower for k in ["from", "origin", "source"]):
        return "location"
    if any(k in name_lower for k in ["to", "destination", "dst"]):
        return "location"

    sample = examples[0].lower().strip()

    if re.search(r"^\d+h\s*\d+m$", sample):
        return "duration"
    if re.search(r"\d+h$", sample):
        return "duration"
    if re.search(r"^\d+:\d{2}$", sample):
        return "duration"
    if re.search(r"\d+\s*hours?", sample):
        return "duration"

    if re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", sample, re.IGNORECASE):
        return "date"
    if re.search(r"\d{1,2}[/-]\d{1,2}[/-](\d{2}|\d{4})", sample):
        return "date"
    if re.search(r"\d{4}[-]\d{2}[-]\d{2}", sample):
        return "date"

    if re.search(r"^[\$\u20a8\u20ac\u00a3\u00a5]\s*\d+[\d,]*\.?\d*$", sample):
        return "currency"
    if re.search(r"\d+[\d,]*\s*(inr|usd|eur|gbp)$", sample, re.IGNORECASE):
        return "currency"

    return "string"

def build_selector_prompt(html_snippet: str, schema_fields: list[SchemaField], page_analysis: dict | None = None) -> str:
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
2. Target the repeating DATA CONTAINER (rows, cards, items) - NOT navigation
3. Use relative selectors (descendant or child)
4. Each schema field needs a selector or null

HTML SNIPPET:
```html
{html_snippet}
```"""

async def extract_css_selectors(prompt: str) -> dict:
    def _sync_call():
        messages = [
            {
                "role": "system",
                "content": (
                    "You output valid JSON objects for CSS selector extraction. "
                    "No markdown, no commentary."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        response = llm_json(messages, temperature=0.1)
        return response if isinstance(response, dict) else {}

    return await run_sync_in_thread(_sync_call)


def apply_selectors(html: str, selectors_map: dict, schema_fields: list[SchemaField], base_url: str = "") -> list[dict]:
    """Execute generated CSS selectors on full HTML and score extracted records."""
    container_sel = selectors_map.get("item_container")
    field_sels = selectors_map.get("fields", {}) or {}

    if not container_sel:
        logging.warning("No item_container selector generated")
        return []

    soup = BeautifulSoup(html, "html.parser")
    if str(container_sel).lower() in ("body", "html", "main"):
        containers = [soup]
    else:
        try:
            containers = soup.select(container_sel)
        except Exception as e:
            logging.error(f"[Scraper] Invalid container selector '{container_sel}': {e}")
            return []

    logging.info("Containers found with '%s': %d", container_sel, len(containers))
    page_email, page_phone = _extract_contacts_from_node(soup)
    allow_page_contact_fallback = len(containers) == 1
    results = []

    for container in containers:
        record: dict = {}
        for field in schema_fields:
            selector = field_sels.get(field.name)
            if not selector:
                record[field.name] = None
                continue

            try:
                nodes = container.select(selector)
            except Exception as e:
                logging.debug(f"[Scraper] Invalid field selector '{selector}' for {field.name}: {e}")
                record[field.name] = None
                continue

            if not nodes:
                record[field.name] = None
                continue

            if field.field_type == FieldType.LIST_STRING:
                values = [_sanitize_field_value(field, n.get_text(" ", strip=True), base_url=base_url) for n in nodes]
                values = [v for v in values if v is not None]
                record[field.name] = values or None
                continue

            node = nodes[0]
            raw_text = node.get_text(separator=" ", strip=True)

            if field.field_type == FieldType.URL:
                href = None
                if node.name == "a":
                    href = node.get("href")
                else:
                    link = node.find("a")
                    href = link.get("href") if link else None
                record[field.name] = _sanitize_field_value(field, href, base_url=base_url)
                continue
            
            # Special handling for contacts in links
            if field.field_type in (FieldType.EMAIL, FieldType.PHONE):
                href = node.get("href") if node.name == "a" else (node.find("a").get("href") if node.find("a") else None)
                if href:
                    if field.field_type == FieldType.EMAIL and "mailto:" in href.lower():
                        raw_text = href.split("mailto:", 1)[1].split("?")[0]
                    elif field.field_type == FieldType.PHONE and "tel:" in href.lower():
                        raw_text = href.split("tel:", 1)[1].split("?")[0]

            if "rating" in field.name.lower() or "star" in field.name.lower():
                classes = node.get("class", [])
                rating_words = [c for c in classes if c in ["One", "Two", "Three", "Four", "Five"]]
                if rating_words:
                    raw_text = rating_words[0]

            record[field.name] = _sanitize_field_value(field, raw_text, base_url=base_url)

        normalized = normalize_scraped_record(record, schema_fields)
        if not any(not _is_empty_value(normalized.get(f.name)) for f in schema_fields):
            continue

        normalized = _enrich_record_contacts(
            normalized,
            schema_fields=schema_fields,
            node=container,
            page_email=page_email,
            page_phone=page_phone,
            allow_page_fallback=allow_page_contact_fallback,
        )

        normalized["record_score"] = score_record_quality(normalized, schema_fields)
        results.append(normalized)

    return _apply_page_level_contact_fallback(results, schema_fields, page_email, page_phone)


def extract_with_regex(html: str, schema_fields: list[SchemaField], base_url: str = "") -> list[dict]:
    """Fallback extraction path when selector generation fails."""
    soup = BeautifulSoup(html, "html.parser")
    page_email, page_phone = _extract_contacts_from_node(soup)
    containers = list(soup.find_all(["article", "li", "tr", "div"], class_=re.compile(r"product|item|card|listing|row|flight-result|result-item|search-result|itinerary", re.I)))
    if not containers:
        headers = soup.find_all(["h2", "h3", "h4"])
        containers = [h.parent for h in headers if h.parent]
    if not containers:
        containers = list(soup.find_all("tr")[1:])
        
    if soup.body:
        containers.append(soup.body)

    results = []
    for container in containers[:300]:
        text = _compact_text(container.get_text(separator=" ", strip=True))
        if len(text) < 5:
            continue

        record: dict = {}
        text_field = schema_fields[0].name if schema_fields else "text"
        for field in schema_fields:
            field_name = field.name.lower()

            if field.field_type == FieldType.URL:
                link = container.find("a")
                record[field.name] = _sanitize_field_value(field, link.get("href") if link else None, base_url=base_url)
            elif field.field_type == FieldType.EMAIL:
                link = container.find("a", href=re.compile(r"mailto:", re.I))
                href = link.get("href") if link else None
                val = href.split("mailto:", 1)[1].split("?")[0] if href else text
                record[field.name] = _sanitize_field_value(field, val)
            elif field.field_type == FieldType.PHONE:
                link = container.find("a", href=re.compile(r"tel:", re.I))
                href = link.get("href") if link else None
                val = href.split("tel:", 1)[1].split("?")[0] if href else text
                record[field.name] = _sanitize_field_value(field, val)
            elif any(k in field_name for k in ["title", "name", "company"]):
                heading = container.find(["h1", "h2", "h3", "h4", "a", "strong"])
                candidate = heading.get_text(" ", strip=True) if heading else text[:70]
                record[field.name] = _sanitize_field_value(field, candidate)
            elif field.name == text_field:
                # First non-special field gets full composite text for segmentation
                record[field.name] = _sanitize_field_value(field, text)
            else:
                # Extra fields left empty; mapper fills from segmented candidates
                record[field.name] = None

        normalized = normalize_scraped_record(record, schema_fields)
        if not any(not _is_empty_value(normalized.get(f.name)) for f in schema_fields):
            continue

        if _is_likely_noise_row(normalized, schema_fields):
            continue

        normalized = _enrich_record_contacts(
            normalized,
            schema_fields=schema_fields,
            node=container,
            page_email=page_email,
            page_phone=page_phone,
            allow_page_fallback=False,
        )

        normalized["record_score"] = score_record_quality(normalized, schema_fields)
        results.append(normalized)

    return _apply_page_level_contact_fallback(results, schema_fields, page_email, page_phone)
