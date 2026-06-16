import contextlib
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from app.config import settings
from app.html_utils import (
    _apply_page_level_contact_fallback,
    _compact_text,
    _enrich_record_contacts,
    _extract_contacts_from_node,
    _sanitize_field_value,
)
from app.models import FieldType, SchemaField

logger = logging.getLogger(__name__)


def _detect_table_headers(html: str) -> list[dict]:
    """Detect table / grid headers from HTML to understand column semantics."""
    soup = BeautifulSoup(html, "html.parser")
    headers_info: list[dict[str, Any]] = []

    for th in soup.find_all(["th", "thead"]):
        text = _compact_text(th.get_text())
        if text:
            cls_val = th.get("class")
            cls_str = " ".join(cls_val) if isinstance(cls_val, list) else (str(cls_val) if cls_val else "")
            id_val = th.get("id", "") or ""
            id_str = id_val[0] if isinstance(id_val, list) else str(id_val)
            headers_info.append(
                {
                    "text": text,
                    "class": cls_str,
                    "id": id_str,
                },
            )

    for header in soup.find_all(["h1", "h2", "h3", "h4"])[:5]:
        text = _compact_text(header.get_text())
        if text and len(text) < settings.SELECTOR_HEADING_FALLBACK_LEN:
            headers_info.append(
                {
                    "text": text,
                    "is_heading": True,
                },
            )

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
    field_sels: dict[str, Any],
    schema_fields: list[SchemaField],
) -> dict[str, Any]:
    """Build type-hint metadata for alignment from selector map + schema."""
    schema_by_name = {f.name: f for f in schema_fields}
    meta: dict[str, Any] = {}
    for key, entry in (field_sels or {}).items():
        if isinstance(entry, dict):
            meta[key] = dict(entry)
            if key in schema_by_name and "type" not in meta[key]:
                meta[key]["type"] = schema_by_name[key].field_type.value
        elif key in schema_by_name:
            meta[key] = {"selector": str(entry), "type": schema_by_name[key].field_type.value}
    return meta


def _collect_child_text_nodes(node) -> list[str]:
    """Extract individual text chunks from all leaf-level descendant elements.

    Also extracts direct text content (text nodes not inside child elements).
    """
    texts: list[str] = []
    for el in node.find_all(True):
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
            "nav",
            "header",
            "footer",
        ):
            continue
        children = [
            c
            for c in el.find_all(True, recursive=False)
            if c.name
            not in (
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
                "nav",
                "header",
                "footer",
            )
        ]
        if not children:
            t = el.get_text(separator=" ", strip=True)
            if t:
                texts.append(t)
    if len(texts) < 8:
        full = node.get_text(separator="|", strip=True)
        if full:
            parts = [p.strip() for p in full.split("|") if p.strip() and len(p.strip()) > 1]
            seen = set(texts)
            for p in parts:
                if p not in seen:
                    texts.append(p)
                    seen.add(p)
    if not texts:
        full = node.get_text(separator=" ", strip=True)
        if full:
            texts = [full]
    return texts


def _find_text_at_position(full_text: str, start: int, end: int) -> bool:
    """Check if a character range overlaps with text content."""
    return start >= 0 and end <= len(full_text)


def _infer_field_type_from_name(field_name: str) -> FieldType | None:
    """Infer a FieldType from a field key name using general heuristics.

    Uses general heuristics rather than site-specific mappings.
    """
    n = (field_name or "").lower()
    if not n:
        return None
    type_keywords = {
        FieldType.CURRENCY: ("price", "cost", "amount", "fee", "total", "rate", "value", "sum", "charge", "payment"),
        FieldType.EMAIL: ("email", "mail", "e-mail", "contact", "e_mail"),
        FieldType.PHONE: ("phone", "tel", "mobile", "cell", "contact_no", "telephone", "contact_number"),
        FieldType.URL: ("url", "link", "href", "website", "profile_url", "source"),
        FieldType.DATE: ("_date", "date_", " day ", "_day", "created_", "updated_", "published_", "due_date"),
        FieldType.NUMBER: ("count", "quantity", "qty", "stock", "rank", "position", "index", "num"),
        FieldType.RATING: ("rating", "score", "stars", "review_score", "grade", "review"),
        FieldType.LOCATION: ("location", "address", "city", "country", "region", "state", "place", "area"),
        FieldType.CODE: ("code", "id", "ref", "sku", "isbn", "upc", "identifier", "ref_no"),
    }
    for ftype, keywords in type_keywords.items():
        if any(kw in n for kw in keywords):
            return ftype
    return None


def _infer_string_field_semantic_type(field_name: str, description: str = "") -> FieldType | None:
    """Infer narrow semantic types for string fields when the label is explicit."""
    inferred = _infer_field_type_from_name(field_name)
    if inferred == FieldType.RATING:
        return FieldType.RATING

    desc = (description or "").lower()
    if re.search(r"\b(rating|rated|score|stars?|grade)\b", desc):
        return FieldType.RATING
    return None


def _find_field_named_node(container, field_name: str):
    variants = {
        field_name,
        field_name.replace("_", "-"),
        field_name.replace("_", " "),
    }
    if "_" in field_name:
        variants.add(field_name.rsplit("_", 1)[-1])
    pattern = re.compile(rf"(^|[^a-z0-9])(?:{'|'.join(re.escape(v) for v in variants)})(?:$|[^a-z0-9])", re.IGNORECASE)
    return container.find(True, class_=pattern)


def _sanitize_regex_string_value(field: SchemaField, value: Any, base_url: str = ""):
    clean = _sanitize_field_value(field, value, base_url=base_url)
    if not isinstance(clean, str) or field.field_type != FieldType.STRING:
        return clean

    field_hint = f"{field.name} {field.description}".lower()
    if "quote" not in field_hint:
        return clean

    quote_pairs = {('"', '"'), ("\u201c", "\u201d"), ("\u2018", "\u2019")}
    while len(clean) >= 2 and (clean[0], clean[-1]) in quote_pairs:
        clean = clean[1:-1].strip()
    return clean or None


def _extract_field_by_pattern(
    node,
    sel_entry,
    field_name: str = "",
    used_spans: list[tuple[int, int]] | None = None,
    used_child_indices: set | None = None,
) -> str | None:
    """Fallback: extract field value from a container node when CSS selector is missing.

    Args:
        node: BeautifulSoup node (container element)
        sel_entry: Field selector entry (dict or string)
        field_name: Name of the field being extracted
        used_spans: List of (start, end) character ranges already consumed
        used_child_indices: Set of child text node indices already consumed

    """
    import re as re_mod

    if used_spans is None:
        used_spans = []
    if used_child_indices is None:
        used_child_indices = set()
    full_text = node.get_text(separator=" ", strip=True)
    if not full_text:
        return None

    example = (sel_entry.get("example_value") or "").strip() if isinstance(sel_entry, dict) else ""

    ftype = None
    if isinstance(sel_entry, dict) and sel_entry.get("type"):
        with contextlib.suppress(ValueError):
            ftype = FieldType(sel_entry["type"])

    if ftype is None:
        ftype = _infer_field_type_from_name(field_name)
    elif ftype == FieldType.STRING:
        ftype = _infer_string_field_semantic_type(field_name)

    def _is_span_used(match_start: int, match_end: int) -> bool:
        return any(match_start < ue and match_end > us for us, ue in used_spans)

    # Strategy 1: Type-based regex extraction with uniqueness
    if ftype is not None:
        patterns: list[str] = []
        if ftype == FieldType.CURRENCY:
            patterns = [r"(?:[$£€¥₹]|USD\s*|EUR\s*)\s*\d[\d,.]*"]
        elif ftype == FieldType.EMAIL:
            patterns = [r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"]
        elif ftype == FieldType.PHONE:
            patterns = [r"[\d\s\-()+]{7,20}"]
        elif ftype == FieldType.URL:
            patterns = [r"https?://[^\s]+"]
        elif ftype == FieldType.DATE:
            patterns = [
                r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}",
                r"\d{4}-\d{2}-\d{2}",
                r"\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}",
                r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}",
                r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}\s*[-]\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}",
            ]
        elif ftype == FieldType.NUMBER:
            patterns = [r"-?\d+(?:\.\d+)?"]
        elif ftype == FieldType.RATING:
            patterns = [
                r"(?:\d+(?:\.\d+)?)\s*(?:[/|]?\s*\d+)?\s*(?:stars?|rating)?",
                r"\b(?:one|two|three|four|five)\b",
            ]

        if patterns:
            n_lower = field_name.lower()
            use_last = any(w in n_lower for w in ("return", "arrival", "arrive", "end", "to_", "dest"))
            all_matches = []
            for pat in patterns:
                for match in re_mod.finditer(pat, full_text, re_mod.IGNORECASE):
                    if not _is_span_used(match.start(), match.end()):
                        all_matches.append(match)
            if not all_matches:
                ancestor = node.parent
                for _ in range(3):
                    if not ancestor or not hasattr(ancestor, "get_text"):
                        break
                    anc_text = ancestor.get_text(separator=" ", strip=True)
                    if anc_text and anc_text != full_text:
                        for pat in patterns:
                            for match in re_mod.finditer(pat, anc_text, re_mod.IGNORECASE):
                                if not _is_span_used(match.start(), match.end()):
                                    all_matches.append(match)
                    if all_matches:
                        break
                    ancestor = ancestor.parent if hasattr(ancestor, "parent") else None
            if all_matches:
                chosen = all_matches[-1] if use_last else all_matches[0]
                used_spans.append((chosen.start(), chosen.end()))
                return chosen.group(0).strip()
            return None

    # Strategy 2: For untyped string fields, try child-text-node matching
    child_texts = _collect_child_text_nodes(node)
    if child_texts and field_name:
        name_lower = field_name.lower().replace("_", " ")
        name_parts = name_lower.split()
        for idx, ct in enumerate(child_texts):
            if idx in used_child_indices:
                continue
            ct_lower = ct.lower()
            if name_lower in ct_lower:
                used_child_indices.add(idx)
                return ct.strip()
            for part in name_parts:
                if len(part) > 2 and part in ct_lower:
                    used_child_indices.add(idx)
                    return ct.strip()
            singular = name_lower.rstrip("s")
            if len(singular) > 2 and singular in ct_lower:
                used_child_indices.add(idx)
                return ct.strip()

    # Strategy 3: Search for the example value literally
    if example and len(example) > 2 and example.lower() in full_text.lower():
        return example.strip()

    # Strategy 4: Fuzzy example match
    if example and len(example) > 2:
        example_words = example.lower().split()
        if settings.SELECTOR_FUZZY_MIN_WORDS <= len(example_words) <= settings.SELECTOR_FUZZY_MAX_WORDS:
            text_lower = full_text.lower()
            matches = sum(1 for w in example_words if w in text_lower)
            if matches / len(example_words) >= settings.SELECTOR_FUZZY_MATCH_RATIO:
                window = _extract_context_window(full_text, example_words)
                if window:
                    return window

    # Strategy 5: Classify each unused child text and match to field by type
    if ftype is not None and ftype not in (FieldType.STRING, FieldType.LOCATION, FieldType.CODE):
        return None
    n_lower = field_name.lower()
    use_last = any(w in n_lower for w in ("return", "arrival", "arrive", "end", "to_", "dest"))
    name_entity_fields = ("operator", "provider", "company", "brand")
    if not use_last:
        use_last = any(w in n_lower for w in name_entity_fields)
    best_match = None
    for idx, ct in enumerate(child_texts):
        if idx in used_child_indices:
            continue
        classification = _classify_text_value(ct)
        if _field_matches_classification(field_name, classification):
            if use_last:
                best_match = (idx, ct)
            else:
                used_child_indices.add(idx)
                return ct.strip()
    if use_last and best_match:
        idx, ct = best_match
        used_child_indices.add(idx)
        return ct.strip()

    return None


def _classify_text_value(text: str) -> str:
    """Classify a text value into a semantic category."""
    import re as _re

    t = text.strip()
    if not t:
        return "empty"
    lower = t.lower()
    if _re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$", t):
        return "date"
    if _re.match(r"^\d{4}-\d{2}-\d{2}$", t):
        return "date"
    if _re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}", t):
        return "date"
    if _re.match(r"^[\$£€¥₹]\s*\d[\d,.]*$", t):
        return "currency"
    if _re.match(r"^[A-Z]{3,4}$", t):
        return "code"
    if _re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){2,}$", t):
        return "location"
    label_patterns = ("starting from", "call now", "learn more", "select", "age")
    if any(w in lower for w in label_patterns):
        return "label"
    if _re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$", t) and len(t) > 1:
        return "name"
    return "text"


def _field_matches_classification(field_name: str, classification: str) -> bool:
    """Check if a field name is compatible with a text classification."""
    n = field_name.lower()
    mapping = {
        "date": ("date", "day"),
        "currency": ("price", "cost", "amount", "fee", "total"),
        "name": ("name", "title", "operator", "provider", "company"),
        "location": ("city", "location", "place", "area"),
        "code": ("code", "identifier", "ref", "sku"),
        "text": (),  # matched via field ordering priority — STRING fields can match text
    }
    keywords = mapping.get(classification, ())
    if classification == "code":
        keywords = (*keywords, "id", "ref")
    if not keywords and classification == "text":
        return True
    return any(kw in n for kw in keywords)


def _extract_context_window(text: str, keywords: list[str], max_len: int | None = None) -> str | None:
    """Extract a focused text window around keyword matches for a field value."""
    max_len = max_len if max_len is not None else settings.SELECTOR_CONTEXT_WINDOW_MAX_LEN
    text_lower = text.lower()
    first_pos = -1
    for kw in keywords:
        idx = text_lower.find(kw)
        if idx != -1:
            first_pos = idx
            break
    if first_pos == -1:
        return None
    start = max(0, first_pos - max_len // 4)
    end = min(len(text), first_pos + max_len)
    segment = text[start:end].strip()
    if len(segment) < settings.SELECTOR_MIN_SEGMENT_LEN:
        return None
    return segment


def _read_node_value(target, field_type: FieldType | None = None, field_name: str = "") -> str | None:
    if field_type == FieldType.URL:
        return target.get("href")  # type: ignore[no-any-return]
    text_val = target.get_text(separator=" ", strip=True)
    title_val = target.get("title")
    alt_val = target.get("alt")
    use_title = False
    if title_val:
        title_clean = title_val.strip()
        if title_clean:
            if text_val.endswith(("...", "…")):
                use_title = True
            elif (
                field_type in (None, FieldType.STRING)
                or any(k in field_name.lower() for k in ["title", "name", "company", "product"])
            ) and len(title_clean) > len(text_val):
                # Prefer title attribute if it's longer
                use_title = True
    if use_title and title_val:
        return title_val.strip()  # type: ignore[no-any-return]
    if alt_val and not text_val:
        return alt_val.strip()  # type: ignore[no-any-return]
    return text_val  # type: ignore[no-any-return]


def extract_raw_from_selectors(
    html: str,
    selectors_map: dict[str, Any],
    base_url: str = "",  # noqa: ARG001, RUF100
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
        record: dict[str, Any] = {}
        used_spans: list[tuple[int, int]] = []
        used_child_indices: set[Any] = set()
        # Sort fields: typed fields with regex patterns first, then LOCATION / CODE, then STRING / None last.
        # This prevents STRING fields from greedily consuming children that
        # typed fields should match.
        _TYPED_ORDER: dict[Any, int] = {}
        for ftype in (
            FieldType.CURRENCY,
            FieldType.EMAIL,
            FieldType.PHONE,
            FieldType.URL,
            FieldType.DATE,
            FieldType.NUMBER,
            FieldType.RATING,
        ):
            _TYPED_ORDER[ftype] = 0
        _TYPED_ORDER[FieldType.LOCATION] = 1
        _TYPED_ORDER[FieldType.CODE] = 1
        _TYPED_ORDER[FieldType.STRING] = 2
        _TYPED_ORDER[None] = 2

        _typed_order = dict(_TYPED_ORDER)

        def _field_sort_key(item, _order=_typed_order):
            key, sel_entry = item
            ftype = None
            if isinstance(sel_entry, dict) and sel_entry.get("type"):
                with contextlib.suppress(ValueError):
                    ftype = FieldType(sel_entry["type"])
            if ftype is None:
                ftype = _infer_field_type_from_name(key)
            return _order.get(ftype, 2)

        sorted_fields = sorted(field_sels.items(), key=_field_sort_key)
        for key, sel_entry in sorted_fields:
            sel = _selector_css(sel_entry)
            val = None
            if sel:
                try:
                    target = node.select_one(sel)
                    if target:
                        node_ftype: FieldType | None = None
                        if isinstance(sel_entry, dict) and sel_entry.get("type"):
                            try:
                                node_ftype = FieldType(sel_entry["type"])
                            except ValueError:
                                node_ftype = None
                        val = _read_node_value(target, node_ftype, key)
                except Exception as e:
                    logger.debug("[SelectorEngine] Invalid selector '%s' for %s: %s", sel, key, e)
            else:
                val = _extract_field_by_pattern(node, sel_entry, key, used_spans, used_child_indices)
            if isinstance(sel_entry, dict) and sel_entry.get("type") == "currency" and val:
                from app.selector_profiles.loader import _postprocess_field

                val = _postprocess_field(val, sel_entry)
            record[key] = val
        if any(v not in (None, "") for v in record.values()):
            raw_records.append(record)
    return raw_records


def apply_selectors(
    html: str,
    selectors_map: dict[str, Any],
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
        record: dict[str, Any] = {}
        for field in schema_fields:
            val = aligned.get(field.name)
            record[field.name] = _sanitize_field_value(field, val, base_url=base_url)
            if return_field_quality:
                from app.utils.quality import _value_quality

                field_quality_map[field.name].append(_value_quality(field, record[field.name]))

        if node is not None:
            record = _enrich_record_contacts(
                record,
                schema_fields,
                node,
                page_email=page_email,
                page_phone=page_phone,
                allow_page_fallback=False,
            )

        from app.utils.quality import score_record_quality

        record["record_score"] = score_record_quality(record, schema_fields)
        if record["record_score"] > 0:
            results.append(record)

    if return_field_quality:
        avg_field_quality = {name: (sum(scores) / len(scores)) if scores else 0.0 for name, scores in field_quality_map.items()}
        return results, avg_field_quality

    return results


def extract_with_regex(html: str, schema_fields: list[SchemaField], base_url: str = "") -> list[dict]:
    """Fallback extraction path when selector generation fails.

    Dispatches extraction logic primarily by FieldType, with narrow semantic
    inference for string fields whose name or description explicitly describes
    ratings.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove obvious noise before searching for containers
    for noise in soup.select("header, footer, nav, aside, .ads, .sidebar"):
        noise.decompose()

    page_email, page_phone = _extract_contacts_from_node(soup)

    # Priority 1: Common data container classes
    containers = list(
        soup.find_all(
            ["article", "li", "tr", "div"],
            class_=re.compile(r"item|card|listing|row|result|entry|quote", re.IGNORECASE),
        ),
    )

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
    seen_texts = set()

    # Use the first schema field as the primary entity field (user-defined
    # ordering)
    desc_field = schema_fields[0].name if schema_fields else "text"

    for container in containers[: settings.REGEX_MAX_CONTAINERS]:
        text = _compact_text(container.get_text(separator=" ", strip=True))
        if len(text) < settings.SELECTOR_MIN_TEXT_LEN or text in seen_texts:
            continue
        # Skip containers that look like noise: ads, newsletters, signup forms,
        # sidebars
        cls_val = container.get("class")
        classes = " ".join(cls_val) if isinstance(cls_val, list) else (str(cls_val) if cls_val else "")
        id_val = container.get("id", "") or ""
        id_attr = id_val[0] if isinstance(id_val, list) else str(id_val)
        noise_text = text.lower()
        if re.search(
            r"subscribe|newsletter|sign.?up|advertisement|ad[-_]?banner|sidebar|sponsored|cookie",
            f"{classes} {id_attr} {noise_text}",
            re.IGNORECASE,
        ):
            continue
        seen_texts.add(text)

        record: dict[str, Any] = {}

        for field in schema_fields:
            ft = field.field_type
            if ft == FieldType.STRING:
                ft = _infer_string_field_semantic_type(field.name, field.description) or ft
            val = None

            if ft == FieldType.URL:
                link = container.find("a")
                val = _sanitize_field_value(field, link.get("href") if link else None, base_url=base_url)

            elif ft == FieldType.EMAIL:
                link = container.find("a", href=re.compile(r"mailto:", re.IGNORECASE))
                href_val = link.get("href") if link else None
                href = href_val[0] if isinstance(href_val, list) else str(href_val) if href_val else None
                val = href.split("mailto:", 1)[1].split("?")[0] if href else text
                val = _sanitize_field_value(field, val)

            elif ft == FieldType.PHONE:
                link = container.find("a", href=re.compile(r"tel:", re.IGNORECASE))
                href_val = link.get("href") if link else None
                href = href_val[0] if isinstance(href_val, list) else str(href_val) if href_val else None
                val = href.split("tel:", 1)[1].split("?")[0] if href else text
                val = _sanitize_field_value(field, val)

            elif ft == FieldType.CURRENCY:
                price_node = container.find(
                    True,
                    class_=re.compile(r"price|amount|cost|amt|fare|mrp|discount|total|sale|offer", re.IGNORECASE),
                )
                if price_node:
                    val = price_node.get_text()
                else:
                    match = re.search(r"([$£€¥₹]\s*\d+[\d,.]*|\d+[\d,.]*\s*[$£€¥₹]|Rs\.?\s*\d+)", text)
                    val = match.group(1) if match else None
                val = _sanitize_field_value(field, val)

            elif ft == FieldType.PERCENTAGE:
                pct_node = container.find(True, class_=re.compile(r"percent|discount|saving|off|tax|vat", re.IGNORECASE))
                if pct_node:
                    val = pct_node.get_text()
                else:
                    match = re.search(r"(\d+[\.\,]?\d*%)", text)
                    val = match.group(1) if match else None
                val = _sanitize_field_value(field, val)

            elif ft == FieldType.RATING:
                rating_node = container.find(True, class_=re.compile(r"rating|stars|score|review", re.IGNORECASE))
                if rating_node:
                    val = rating_node.get_text()
                else:
                    match = re.search(r"(\d+\.?\d*/\d+|\d+\.?\d*\s*stars?|★+)", text, re.IGNORECASE)
                    val = match.group(1) if match else None
                val = _sanitize_field_value(field, val)

            elif ft == FieldType.BOOLEAN:
                bool_node = container.find(True, class_=re.compile(r"stock|available|status|active", re.IGNORECASE))
                if bool_node:
                    val = bool_node.get_text()
                else:
                    match = re.search(r"\b(In Stock|Out of Stock|Available|Unavailable|Sold Out|Yes|No)\b", text, re.IGNORECASE)
                    val = match.group(1) if match else None
                val = _sanitize_field_value(field, val)

            elif ft == FieldType.CODE:
                code_node = container.find(
                    True,
                    class_=re.compile(r"sku|product-code|barcode|isbn|model-number|part", re.IGNORECASE),
                )
                if code_node:
                    val = code_node.get_text()
                else:
                    match = re.search(r"(SKU[-:\s]*[A-Za-z0-9-]+|\b[0-9]{12,13}\b)", text, re.IGNORECASE)
                    val = match.group(1) if match else None
                val = _sanitize_field_value(field, val)

            elif ft == FieldType.LOCATION:
                loc_node = container.find(
                    True,
                    class_=re.compile(r"origin|destination|city|location|airport|from|to|station", re.IGNORECASE),
                )
                if loc_node:
                    val = loc_node.get_text()
                else:
                    match = re.search(r"\b[A-Z]{3}\b", text)
                    val = match.group(0) if match else None
                val = _sanitize_field_value(field, val)

            elif ft in (FieldType.NUMBER, FieldType.INTEGER, FieldType.FLOAT):
                num_node = container.find(True, class_=re.compile(r"number|count|amount|value|qty|quantity", re.IGNORECASE))
                if num_node:
                    val = num_node.get_text()
                else:
                    match = re.search(r"(\d+[\d,]*\.?\d*)", text)
                    val = match.group(1) if match else None
                val = _sanitize_field_value(field, val)

            elif ft == FieldType.STRING:
                named_node = _find_field_named_node(container, field.name)
                if named_node:
                    val = _sanitize_regex_string_value(field, named_node.get_text(" ", strip=True), base_url=base_url)
                elif field.name == desc_field:
                    # Primary entity: get the most specific identifying text
                    # Strategy 1: Look for heading / link elements
                    heading = container.find(["h1", "h2", "h3", "h4", "strong"])
                    if not heading:
                        link = container.find("a")
                        if link and not re.search(r"visit|click|more|details|select|here|book", link.get_text(), re.IGNORECASE):
                            heading = link
                    if not heading and container.name == "tr":
                        heading = container.find("td")

                    # Strategy 2: Look for img alt text (e.g. company logo)
                    if not heading:
                        img = container.find("img", alt=True)
                        if img:
                            alt_val = img.get("alt")
                            alt_str = alt_val[0] if isinstance(alt_val, list) else str(alt_val) if alt_val else ""
                            if alt_str.strip() and len(alt_str.strip()) > 2:
                                heading = img

                    # Strategy 3: Look for elements with identifying class
                    # patterns
                    if not heading:
                        named_el = container.find(class_=re.compile(r"name|title|brand|company|org", re.IGNORECASE))
                        if named_el:
                            heading = named_el

                    # Strategy 4: First element with short, meaningful text
                    # (not a full sentence)
                    if not heading:
                        for child in container.find_all(["span", "div", "p", "b", "i"], recursive=True, limit=10):
                            child_text = child.get_text(strip=True)
                            if (
                                child_text
                                and len(child_text) < 60
                                and child_text != text
                                and re.match(r"^[A-Za-z]\w+(\s+[A-Za-z]\w+){0,4}$", child_text)
                            ):
                                heading = child
                                break

                    candidate = (
                        heading.get("alt")
                        if heading and heading.name == "img"
                        else (heading.get_text(" ", strip=True) if heading else text[: settings.SELECTOR_HEADING_FALLBACK_LEN])
                    )
                    val = _sanitize_regex_string_value(field, candidate, base_url=base_url)
                else:
                    # Secondary string fields: prefer a field-specific child,
                    # otherwise fall back to compact container text.
                    val = _sanitize_regex_string_value(field, text[:200], base_url=base_url) if text else None

            # DATE or unknown — extract the most prominent text
            elif field.name == desc_field:
                # Primary entity: get the most specific identifying text
                # Strategy 1: Look for heading / link elements
                heading = container.find(["h1", "h2", "h3", "h4", "strong"])
                if not heading:
                    link = container.find("a")
                    if link and not re.search(r"visit|click|more|details|select|here|book", link.get_text(), re.IGNORECASE):
                        heading = link
                if not heading and container.name == "tr":
                    heading = container.find("td")

                # Strategy 2: Look for img alt text (e.g. company logo)
                if not heading:
                    img = container.find("img", alt=True)
                    if img:
                        alt_val = img.get("alt")
                        alt_str = alt_val[0] if isinstance(alt_val, list) else str(alt_val) if alt_val else ""
                        if alt_str.strip() and len(alt_str.strip()) > 2:
                            heading = img

                # Strategy 3: Look for elements with identifying class
                # patterns
                if not heading:
                    named_el = container.find(class_=re.compile(r"name|title|brand|company|org", re.IGNORECASE))
                    if named_el:
                        heading = named_el

                # Strategy 4: First element with short, meaningful text
                # (not a full sentence)
                if not heading:
                    for child in container.find_all(["span", "div", "p", "b", "i"], recursive=True, limit=10):
                        child_text = child.get_text(strip=True)
                        if (
                            child_text
                            and len(child_text) < 60
                            and child_text != text
                            and re.match(r"^[A-Za-z]\w+(\s+[A-Za-z]\w+){0,4}$", child_text)
                        ):
                            heading = child
                            break

                candidate = (
                    heading.get("alt")
                    if heading and heading.name == "img"
                    else (heading.get_text(" ", strip=True) if heading else text[: settings.SELECTOR_HEADING_FALLBACK_LEN])
                )
                val = _sanitize_field_value(field, candidate)
            else:
                # Secondary fields: use container text or None
                val = _sanitize_field_value(field, text[:200]) if text else None

            record[field.name] = val

        record = _enrich_record_contacts(
            record,
            schema_fields,
            container,
            page_email=page_email,
            page_phone=page_phone,
            allow_page_fallback=True,
        )

        from app.utils.quality import score_record_quality

        record["record_score"] = score_record_quality(record, schema_fields)
        if record["record_score"] > 0:
            results.append(record)

    return _apply_page_level_contact_fallback(results, schema_fields, page_email, page_phone)
