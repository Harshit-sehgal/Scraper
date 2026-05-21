import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
from app.models import SchemaField, FieldType
from app.html_utils import (
    _compact_text,
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


def _selector_css(sel_entry) -> str | None:
    if not sel_entry:
        return None
    if isinstance(sel_entry, str):
        return sel_entry.strip() or None
    if isinstance(sel_entry, dict):
        return (sel_entry.get("selector") or "").strip() or None
    return None


def build_selector_field_metadata(
    field_sels: dict,
    schema_fields: list[SchemaField],
) -> dict:
    """Build type-hint metadata for alignment from selector map + schema."""
    schema_by_name = {f.name: f for f in schema_fields}
    meta: dict = {}
    for key, entry in (field_sels or {}).items():
        if isinstance(entry, dict):
            meta[key] = dict(entry)
            if key in schema_by_name and "type" not in meta[key]:
                meta[key]["type"] = schema_by_name[key].field_type.value
        elif key in schema_by_name:
            meta[key] = {"selector": str(entry), "type": schema_by_name[key].field_type.value}
    return meta


def _read_node_value(target, field_type: FieldType | None = None, field_name: str = "") -> str | None:
    if field_type == FieldType.URL:
        return target.get("href")
    text_val = target.get_text(separator=" ", strip=True)
    title_val = target.get("title")
    alt_val = target.get("alt")
    use_title = False
    if title_val:
        title_clean = title_val.strip()
        if title_clean:
            if text_val.endswith("...") or text_val.endswith("…"):
                use_title = True
            elif any(k in field_name.lower() for k in ["title", "name", "company", "product"]):
                if len(title_clean) > len(text_val):
                    use_title = True
    if use_title and title_val:
        return title_val.strip()
    if alt_val and not text_val:
        return alt_val.strip()
    return text_val


def extract_raw_from_selectors(
    html: str,
    selectors_map: dict,
    base_url: str = "",
) -> list[dict]:
    """Extract every field in the selector map from each item container (unmapped keys)."""
    container_sel = selectors_map.get("item_container")
    field_sels = selectors_map.get("fields", {}) or {}
    if not container_sel or not field_sels:
        return []

    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select(container_sel)

    raw_records: list[dict] = []
    for node in containers:
        record: dict = {}
        for key, sel_entry in field_sels.items():
            sel = _selector_css(sel_entry)
            val = None
            if sel:
                try:
                    target = node.select_one(sel)
                    if target:
                        ftype = None
                        if isinstance(sel_entry, dict) and sel_entry.get("type"):
                            try:
                                ftype = FieldType(sel_entry["type"])
                            except ValueError:
                                ftype = None
                        val = _read_node_value(target, ftype, key)
                except Exception as e:
                    logger.debug("[SelectorEngine] Invalid selector '%s' for %s: %s", sel, key, e)
            if isinstance(sel_entry, dict) and sel_entry.get("type") == "currency" and val:
                from app.selector_profiles.loader import _postprocess_field
                val = _postprocess_field(val, sel_entry)
            record[key] = val
        if any(v not in (None, "") for v in record.values()):
            raw_records.append(record)
    return raw_records


def apply_selectors(
    html: str, 
    selectors_map: dict, 
    schema_fields: list[SchemaField], 
    base_url: str = "",
    return_field_quality: bool = False,
    user_intent: str = "",
) -> list[dict] | tuple[list[dict], dict]:
    """Extract all selector-map fields, align to user schema, then score records."""
    from app.data_utils import align_extracted_keys_to_schema

    container_sel = selectors_map.get("item_container")
    field_sels = selectors_map.get("fields", {}) or {}

    if not container_sel:
        return ([], {}) if return_field_quality else []

    soup = BeautifulSoup(html, "html.parser")
    page_email, page_phone = _extract_contacts_from_node(soup)
    containers = soup.select(container_sel)

    raw_records = extract_raw_from_selectors(html, selectors_map, base_url=base_url)
    if not raw_records:
        return ([], {}) if return_field_quality else []

    field_meta = build_selector_field_metadata(field_sels, schema_fields)
    aligned_records = align_extracted_keys_to_schema(
        raw_records,
        schema_fields,
        selector_field_defs=field_meta,
        user_intent=user_intent,
    )

    results = []
    field_quality_map: dict[str, list[float]] = {f.name: [] for f in schema_fields}

    for idx, aligned in enumerate(aligned_records):
        node = containers[idx] if idx < len(containers) else None
        record: dict = {}
        for field in schema_fields:
            val = aligned.get(field.name)
            record[field.name] = _sanitize_field_value(field, val, base_url=base_url)
            if return_field_quality:
                from app.utils.quality import _value_quality
                field_quality_map[field.name].append(_value_quality(field, record[field.name]))

        if node is not None:
            record = _enrich_record_contacts(
                record, schema_fields, node,
                page_email=page_email, page_phone=page_phone,
                allow_page_fallback=False,
            )

        from app.utils.quality import score_record_quality
        record["record_score"] = score_record_quality(record, schema_fields)
        if record["record_score"] > 0:
            results.append(record)

    if return_field_quality:
        avg_field_quality = {
            name: (sum(scores) / len(scores)) if scores else 0.0
            for name, scores in field_quality_map.items()
        }
        return results, avg_field_quality

    return results


def extract_with_regex(html: str, schema_fields: list[SchemaField], base_url: str = "") -> list[dict]:
    """Fallback extraction path when selector generation fails."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove obvious noise before searching for containers
    for noise in soup.select("header, footer, nav, aside, .ads, .sidebar"):
        noise.decompose()
        
    page_email, page_phone = _extract_contacts_from_node(soup)
    
    # Priority 1: Common data container classes
    containers = list(soup.find_all(["article", "li", "tr", "div"], class_=re.compile(r"product|item|card|listing|row|flight-result|result-item|search-result|itinerary", re.I)))
    
    # Priority 2: Headings and their parents
    if not containers:
        headers = soup.find_all(["h2", "h3", "h4"])
        containers = [h.parent for h in headers if h.parent]
        
    # Priority 3: All table rows (skipping header)
    if not containers:
        containers = list(soup.find_all("tr")[1:])
        
    # Priority 4: Final body fallback (ONLY if nothing else found)
    if not containers and soup.body:
        containers = [soup.body]

    results = []
    seen_texts = set() # Local dedup for regex path
    
    for container in containers[:settings.REGEX_MAX_CONTAINERS]:
        text = _compact_text(container.get_text(separator=" ", strip=True))
        if len(text) < settings.SELECTOR_MIN_TEXT_LEN or text in seen_texts:
            continue
        seen_texts.add(text)

        record: dict = {}
        # Identify the most "descriptive" field to hold full text if needed
        desc_field = next((f.name for f in schema_fields if any(k in f.name.lower() for k in ["title", "name", "company", "description"])), schema_fields[0].name if schema_fields else "text")
        
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
            elif field.field_type == FieldType.CURRENCY or "price" in field_name:
                # Find elements with price-like classes or text containing currency symbols
                price_node = container.find(True, class_=re.compile(r"price|amount|cost|amt|fare", re.I))
                if price_node:
                    val = price_node.get_text()
                else:
                    # Search text for currency-like pattern
                    match = re.search(r"([$£€¥₹]\s*\d+[\d,.]*|\d+[\d,.]*\s*[$£€¥₹])", text)
                    val = match.group(1) if match else None
                record[field.name] = _sanitize_field_value(field, val)
            elif any(k in field_name for k in ["title", "name", "company", "airline", "product"]):
                # Try to find a heading or a strong/a element with relevant class
                heading = container.find(["h1", "h2", "h3", "h4", "strong", "a", "span", "div"], class_=re.compile(r"title|name|company|heading|airline|product", re.I))
                if not heading and container.name == "tr":
                    # For table rows, try the first cell
                    heading = container.find("td")
                if not heading:
                    heading = container.find(["h1", "h2", "h3", "h4", "strong"])
                if not heading:
                    # If it's an <a> tag, make sure it doesn't just say 'Visit' or 'Click'
                    link = container.find("a")
                    if link and not re.search(r"visit|click|more|details|select", link.get_text(), re.I):
                        heading = link
                
                candidate = heading.get_text(" ", strip=True) if heading else text[:settings.SELECTOR_HEADING_FALLBACK_LEN]
                record[field.name] = _sanitize_field_value(field, candidate)
            elif field.name == desc_field:
                # descriptive field gets full composite text if nothing better was found
                record[field.name] = _sanitize_field_value(field, text[:200]) # Limit length for regex path
            else:
                record[field.name] = None

        record = _enrich_record_contacts(
            record, schema_fields, container,
            page_email=page_email, page_phone=page_phone,
            allow_page_fallback=True,
        )
        
        from app.utils.quality import score_record_quality
        record["record_score"] = score_record_quality(record, schema_fields)
        if record["record_score"] > 0:
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
