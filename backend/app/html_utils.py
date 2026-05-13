import re
import logging
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import requests

from app.models import SchemaField, FieldType
from app.semantic_segmentation import segment_single_text, is_likely_noise_field

EMPTY_TOKENS = {"-", "n/a", "na", "null", "none", "", "not available", "empty", "0", "false", "undefined"}
PLACEHOLDER_PHRASES = {"no data", "not specified", "coming soon", "tbd", "unknown"}
LIKELY_LOCATION_WORDS = {"india", "usa", "uk", "chennai", "bangalore", "delhi", "mumbai", "london", "new york", "city", "country", "state"}
NAME_FIELD_NOISE_PREFIXES = {
    "privacy policy", "terms of", "cookie", "copyright", "all rights",
    "contact us", "about us", "home", "search", "menu", "login", "sign up",
    "subscribe", "newsletter", "follow us", "read more", "learn more",
    "view details", "quick links", "useful links", "selling tools",
    "starting from", "years of experience",
}

def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def _normalized_text_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").strip().lower()).strip()

def _is_placeholder_value(text: str) -> bool:
    key = _normalized_text_key(text)
    if not key:
        return True
    if key in EMPTY_TOKENS or key in PLACEHOLDER_PHRASES:
        return True
    if key.endswith(" page") and key.split()[0] in EMPTY_TOKENS:
        return True
    if key.startswith(("click ", "read ", "view ")):
        return True
    if re.fullmatch(r"\d+\s+more", key):
        return True
    return False

def _is_entity_name_field(field_name: str) -> bool:
    name = (field_name or "").lower()
    return any(token in name for token in ["company", "name", "title", "entity"])

def _is_noise_name_value(text: str) -> bool:
    val = _compact_text(text).lower()
    if not val:
        return True
    if _is_placeholder_value(val):
        return True
    if val in LIKELY_LOCATION_WORDS:
        return True
    if any(val.startswith(prefix) for prefix in NAME_FIELD_NOISE_PREFIXES):
        return True
    if re.search(r"\(\d+\)$", val):
        return True
    if any(token in val for token in ["show all", "nearby locations", "use my current location"]):
        return True
    return False

def _is_likely_noise_entity(text: str) -> bool:
    """Check if text is noise using semantic density analysis."""
    is_noise, _conf, _evidence = is_likely_noise_field("name", text)
    return is_noise

def _is_empty_value(value) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        meaningful = []
        for item in value:
            if item is None:
                continue
            text = _compact_text(str(item))
            if not text or _is_placeholder_value(text):
                continue
            meaningful.append(text)
        return len(meaningful) == 0
    if isinstance(value, str):
        text = _compact_text(value)
        return text == "" or _is_placeholder_value(text)
    return False

def _is_likely_noise_row(record: dict, schema_fields: list[SchemaField]) -> bool:
    """Determine if a record is noise using semantic density and structural analysis."""
    all_values = []
    for _key, value in record.items():
        if value and not _is_empty_value(value):
            text = _compact_text(str(value)).lower()
            all_values.append(text)

    if not all_values:
        return True

    # Structural: all values identical (likely template noise)
    if len(all_values) >= 3 and len(set(all_values)) == 1:
        return True

    combined = " ".join(all_values)

    # Structural: if no entity field defined, check via semantic density
    entity_fields = [f.name for f in schema_fields if _is_entity_name_field(f.name)]
    if not entity_fields:
        seg = segment_single_text(combined)
        if not seg.structural_pattern and seg.overall_cohesion < 0.2:
            return True

    # Privacy/legal/navigation: these are structurally distinct
    nav_indicators = ["privacy policy", "terms of", "cookie", "about us"]
    if any(v in combined for v in nav_indicators):
        return True

    # Social media links: structural noise on listing pages
    social = ["facebook", "instagram", "twitter", "linkedin", "youtube"]
    if any(v in combined for v in social):
        return True

    # Entity field check: use semantic density on the name field
    entity_fields = [f.name for f in schema_fields if _is_entity_name_field(f.name)]
    name_text = None
    if entity_fields:
        name_field = entity_fields[0]
        name_text = _compact_text(str(record.get(name_field) or ""))
        if name_text:
            is_noise, _conf, _evidence = is_likely_noise_field(name_field, name_text)
            if is_noise:
                email_present = any(
                    record.get(f.name) for f in schema_fields
                    if f.field_type == FieldType.EMAIL and not _is_empty_value(record.get(f.name))
                )
                phone_present = any(
                    record.get(f.name) for f in schema_fields
                    if f.field_type == FieldType.PHONE and not _is_empty_value(record.get(f.name))
                )
                url_field = next((f.name for f in schema_fields if f.field_type == FieldType.URL), "")
                website_present = bool(record.get(url_field)) if url_field else False

                if not (email_present or phone_present or website_present):
                    return True

        address_field = next(
            (f.name for f in schema_fields
             if f.field_type == FieldType.LOCATION or any(x in f.name.lower() for x in ["address", "location"])),
            ""
        )
        address_text = _compact_text(str(record.get(address_field) or "")) if address_field else ""
        if address_text and name_text and address_text.startswith(name_text[:40]):
             email_present = any(
                    record.get(f.name) for f in schema_fields
                    if f.field_type == FieldType.EMAIL and not _is_empty_value(record.get(f.name))
                )
             phone_present = any(
                    record.get(f.name) for f in schema_fields
                    if f.field_type == FieldType.PHONE and not _is_empty_value(record.get(f.name))
                )
             url_field = next((f.name for f in schema_fields if f.field_type == FieldType.URL), "")
             website_present = bool(record.get(url_field)) if url_field else False
             if not (email_present or phone_present or website_present):
                return True

    return False

def _extract_contacts_from_node(node) -> tuple[str | None, str | None]:
    """Search a BeautifulSoup node for email and phone numbers."""
    text = node.get_text(separator=" ", strip=True)
    return _valid_email(text), _valid_phone(text)

def _enrich_record_contacts(
    record: dict,
    schema_fields: list[SchemaField],
    node,
    page_email: str | None = None,
    page_phone: str | None = None,
    allow_page_fallback: bool = False,
) -> dict:
    """Try to find missing contact info within a specific DOM node or page context."""
    email_field = next((f for f in schema_fields if f.field_type == FieldType.EMAIL), None)
    phone_field = next((f for f in schema_fields if f.field_type == FieldType.PHONE), None)

    if email_field and _is_empty_value(record.get(email_field.name)):
        e, _p = _extract_contacts_from_node(node)
        if e:
            record[email_field.name] = e
        elif allow_page_fallback and page_email:
            record[email_field.name] = page_email

    if phone_field and _is_empty_value(record.get(phone_field.name)):
        _e, p = _extract_contacts_from_node(node)
        if p:
            record[phone_field.name] = p
        elif allow_page_fallback and page_phone:
            record[phone_field.name] = page_phone

    return record


def _apply_page_level_contact_fallback(
    results: list[dict],
    schema_fields: list[SchemaField],
    page_email: str | None,
    page_phone: str | None,
) -> list[dict]:
    """If specific records are missing contacts, apply the global page-level ones."""
    if not page_email and not page_phone:
        return results

    email_field_name = next((f.name for f in schema_fields if f.field_type == FieldType.EMAIL), None)
    phone_field_name = next((f.name for f in schema_fields if f.field_type == FieldType.PHONE), None)

    for record in results:
        if email_field_name and _is_empty_value(record.get(email_field_name)) and page_email:
            record[email_field_name] = page_email
        if phone_field_name and _is_empty_value(record.get(phone_field_name)) and page_phone:
            record[phone_field_name] = page_phone
    return results


def _extract_page_contacts(html: str) -> tuple[str | None, str | None]:
    """Convenience to get contacts from full HTML."""
    soup = BeautifulSoup(html, "html.parser")
    return _extract_contacts_from_node(soup)


def _boost_contacts_with_page_html(
    results: list[dict],
    html: str,
    schema_fields: list[SchemaField],
) -> list[dict]:
    """Aggressively search the page if records are mostly empty of contacts."""
    e, p = _extract_page_contacts(html)
    return _apply_page_level_contact_fallback(results, schema_fields, e, p)

async def fetch_page_content(url: str) -> str:
    """Load a URL in a headless browser and fallback to plain HTTP when needed."""
    browser = None
    context = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            async def _route_filter(route):
                if route.request.resource_type in {"image", "media", "font"}:
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", _route_filter)
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)
            await asyncio.sleep(1.5)
            html = await page.content()
            return html
    except Exception as e:
        logging.error(f"[Scraper] Playwright failed for {url}: {e}. Falling back to requests")
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception as e:
                logging.error(f"[Scraper] Error closing playwright context: {e}")
        if browser is not None:
            try:
                await browser.close()
            except Exception as e:
                logging.error(f"[Scraper] Error closing playwright browser: {e}")

    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    return resp.text

def clean_html_for_selectors(html: str, max_chars: int = 16000) -> str:
    """Remove known-noise tags while preserving structure useful for selector discovery."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
        tag.decompose()

    for tag in soup.find_all(True):
        attrs_to_keep = ["class", "id", "href", "itemprop"]
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in attrs_to_keep}

    cleaned = soup.prettify()
    return cleaned[:max_chars]

def _valid_email(text: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    if not match:
        return None

    email = match.group(0).lower().strip(" .,;:")
    local_part, _, domain = email.partition("@")
    if local_part in {"noreply", "no-reply", "donotreply", "do-not-reply", "test"}:
        return None
    if domain in {"example.com", "test.com", "localhost"}:
        return None
    if "invalid" in domain or "placeholder" in domain:
        return None
    return email

def _valid_phone(text: str) -> str | None:
    candidates = re.findall(r"(?:\+?\d[\d\s()\-]{6,}\d)", text)
    cleaned = []
    seen = set()
    for c in candidates:
        c_norm = _compact_text(c).strip("- ,")
        digits = re.sub(r"\D", "", c_norm)
        if len(digits) < 7 or len(digits) > 15:
            continue
        if c_norm not in seen:
            seen.add(c_norm)
            cleaned.append(c_norm)
    return cleaned[0] if cleaned else None

def _sanitize_field_value(field: SchemaField, value, base_url: str = ""):
    """Apply type-specific sanitization to extracted values."""
    if value is None:
        return None

    if field.field_type == FieldType.LIST_STRING:
        if not isinstance(value, list):
            value = [value]
        cleaned = [_compact_text(str(v)) for v in value if not _is_empty_value(v)]
        return cleaned if cleaned else None

    text = _compact_text(str(value))
    if _is_empty_value(text):
        return None

    if field.field_type == FieldType.EMAIL:
        return _valid_email(text)
    if field.field_type == FieldType.PHONE:
        return _valid_phone(text)
    if field.field_type == FieldType.URL:
        if not text.startswith("http"):
            from urllib.parse import urljoin
            text = urljoin(base_url, text)
        return text if text.startswith("http") else None
    
    if _is_noise_name_value(text) and _is_entity_name_field(field.name):
        return None

    return text
