import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
from app.models import SchemaField, FieldType
from app.html_utils import (
    _compact_text, _is_empty_value, _is_likely_noise_row,
    _extract_contacts_from_node, _sanitize_field_value,
    _enrich_record_contacts, _apply_page_level_contact_fallback
)
from app.config import settings

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
        if text and len(text) < settings.SELECTOR_HEADING_FALLBACK_LEN:
            headers_info.append({
                "text": text,
                "is_heading": True,
            })

    return headers_info


def apply_selectors(html: str, selectors_map: dict, schema_fields: list[SchemaField], base_url: str = "") -> list[dict]:
    """Execute generated CSS selectors on full HTML and score extracted records."""
    container_sel = selectors_map.get("item_container")
    field_sels = selectors_map.get("fields", {}) or {}

    if not container_sel:
        return []

    soup = BeautifulSoup(html, "html.parser")
    page_email, page_phone = _extract_contacts_from_node(soup)
    containers = soup.select(container_sel)
    
    results = []
    for node in containers:
        record: dict = {}
        for field in schema_fields:
            sel = field_sels.get(field.name)
            val = None
            if sel:
                try:
                    target = node.select_one(sel)
                    if target:
                        if field.field_type == FieldType.URL:
                            val = target.get("href")
                        else:
                            val = target.get_text(separator=" ", strip=True)
                except Exception as e:
                    logger.debug("[SelectorEngine] Invalid selector '%s': %s", sel, e)
                    val = None

            record[field.name] = _sanitize_field_value(field, val, base_url=base_url)

        # Post-extraction enrichment
        record = _enrich_record_contacts(
            record, schema_fields, node, 
            page_email=page_email, page_phone=page_phone,
            allow_page_fallback=False,
        )

        from app.utils.quality import score_record_quality
        record["record_score"] = score_record_quality(record, schema_fields)
        results.append(record)

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
    for container in containers[:settings.REGEX_MAX_CONTAINERS]:
        text = _compact_text(container.get_text(separator=" ", strip=True))
        if len(text) < settings.SELECTOR_MIN_TEXT_LEN:
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
                candidate = heading.get_text(" ", strip=True) if heading else text[:settings.SELECTOR_HEADING_FALLBACK_LEN]
                record[field.name] = _sanitize_field_value(field, candidate)
            elif field.name == text_field:
                # First non-special field gets full composite text for segmentation
                record[field.name] = _sanitize_field_value(field, text)
            else:
                record[field.name] = None

        record = _enrich_record_contacts(
            record, schema_fields, container,
            page_email=page_email, page_phone=page_phone,
            allow_page_fallback=True,
        )
        
        from app.utils.quality import score_record_quality
        record["record_score"] = score_record_quality(record, schema_fields)
        results.append(record)

    return _apply_page_level_contact_fallback(results, schema_fields, page_email, page_phone)


def _get_field_keywords(field_name: str) -> list[str]:
    """Get common alternative names for a field to help header matching."""
    name = field_name.lower()
    if any(k in name for k in ["company", "name", "title"]):
        return ["name", "company", "title", "business", "firm"]
    if any(k in name for k in ["price", "cost", "amt"]):
        return ["price", "cost", "amount", "total", "fare"]
    if any(k in name for k in ["date", "time"]):
        return ["date", "time", "when", "departure", "arrival"]
    if any(k in name for k in ["location", "address", "city"]):
        return ["location", "address", "city", "destination", "origin"]
    return [name]
