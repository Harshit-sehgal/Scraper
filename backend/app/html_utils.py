import re
import logging
import asyncio
import time
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import httpx

from app.config import settings
from app.models import SchemaField, FieldType
from app.semantic_segmentation import segment_single_text, is_likely_noise_field
from app.browser_pool import get_browser_pool

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
    if not key or len(key) < settings.SELECTOR_MIN_TEXT_LEN:
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
    if len(all_values) >= settings.NOISE_MIN_VALUES_FOR_REPETITION_CHECK and len(set(all_values)) == 1:
        return True

    combined = " ".join(all_values)

    # Structural: if no entity field defined, check via semantic density
    entity_fields = [f.name for f in schema_fields if _is_entity_name_field(f.name)]
    if not entity_fields:
        seg = segment_single_text(combined)
        if not seg.structural_pattern and seg.overall_cohesion < settings.NOISE_COHESION_THRESHOLD:
            return True

    # Privacy/legal/navigation: these are structurally distinct
    nav_indicators = ["privacy policy", "terms of", "cookie", "about us"]
    if any(v in combined for v in nav_indicators):
        return True

    # Social media links: structural noise on listing pages
    # Only flag if multiple platforms appear (single mention is likely legitimate)
    social = ["facebook", "instagram", "twitter", "linkedin", "youtube"]
    if sum(v in combined for v in social) >= settings.NOISE_SOCIAL_PLATFORM_THRESHOLD:
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

async def fetch_page_content(url: str) -> tuple[str, float, str, int]:
    """Load a URL in a pooled headless browser context and fallback to plain HTTP when needed.

    Returns:
        tuple of (html_content, js_render_delay_ms, method_used, retry_count)
    """
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower() or "default"
    
    page = None
    js_render_delay_ms = 0.0
    retry_count = 0
    method_used = "playwright"
    
    try:
        pool = get_browser_pool()
        context = await pool.get_context(domain)
        page = await context.new_page()

        async def _route_filter(route):
            if route.request.resource_type in {"image", "media", "font"}:
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", _route_filter)

        # Phase 1: Try networkidle
        try:
            await page.goto(url, wait_until="networkidle", timeout=settings.PLAYWRIGHT_TIMEOUT)
            
            # Wait for common loading indicators to disappear
            loading_selectors = [
                ".loading", ".spinner", ".loader", "#loading", "#spinner",
                "[class*='Loading']", "[class*='Spinner']", "[class*='Loader']",
                ".sk-cube-grid", ".lds-ripple", ".bouncing-loader"
            ]
            for sel in loading_selectors:
                try:
                    # Wait for it to be hidden, but don't block if it never appears
                    await page.wait_for_selector(sel, state="hidden", timeout=settings.PAGE_LOADING_INDICATOR_TIMEOUT)
                except Exception:
                    pass

            # Adaptive post-network buffer: check DOM stabilization
            stabilization_start = time.time()
            try:
                await page.wait_for_function(
                    f"""() => {{
                        const body = document.body;
                        if (!body) return true;
                        const html = body.innerHTML;
                        return new Promise(resolve => {{
                            let lastHtml = html;
                            let stableChecks = 0;
                            let totalChecks = 0;
                            const interval = setInterval(() => {{
                                const current = document.body ? document.body.innerHTML : lastHtml;
                                if (current === lastHtml) {{
                                    stableChecks++;
                                }} else {{
                                    stableChecks = 0;
                                }}
                                
                                // Resolve if stable for N checks AND we've waited at least M checks
                                // or if we hit the absolute check limit.
                                if ((stableChecks >= {settings.DOM_STABILIZATION_MIN_STABLE_CHECKS} && totalChecks > {settings.DOM_STABILIZATION_MIN_TOTAL_CHECKS}) || totalChecks > {settings.DOM_STABILIZATION_MAX_CHECKS}) {{
                                    clearInterval(interval);
                                    resolve(true);
                                }}
                                lastHtml = current;
                                totalChecks++;
                            }}, {settings.DOM_STABILIZATION_INTERVAL});
                        }});
                    }}""",
                    timeout=settings.PAGE_SETTLE_DELAY * 1000,
                )
            except Exception:
                pass
            js_render_delay_ms = (time.time() - stabilization_start) * 1000

            # Optional: Auto-scroll to trigger lazy-loaders
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await asyncio.sleep(settings.PAGE_SCROLL_DELAY)
            await page.evaluate("window.scrollTo(0, 0)")

        except Exception as e:
            logging.warning(
                "[Scraper] networkidle timeout for %s: %s. Waiting longer with domcontentloaded",
                url, e,
            )
            await page.wait_for_load_state("domcontentloaded")
            fallback_start = time.time()
            await asyncio.sleep(settings.PAGE_FALLBACK_EXTRA_WAIT)
            js_render_delay_ms = (time.time() - fallback_start) * 1000

        html = await page.content()
        return html, js_render_delay_ms, method_used, 0
    except Exception as e:
        logging.error(f"[Scraper] Playwright failed for {url}: {e}. Falling back to httpx")
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass

    # httpx fallback
    method_used = "httpx"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.REQUEST_TIMEOUT),
        headers={"User-Agent": settings.USER_AGENT},
    ) as client:
        for attempt in range(max(1, settings.MAX_RETRIES)):
            retry_count = attempt
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text, 0.0, method_used, retry_count
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                if attempt < settings.MAX_RETRIES - 1:
                    wait = settings.HTTP_BACKOFF_FACTOR * (attempt + 1)
                    logging.warning(
                        "[Scraper] httpx attempt %d/%d failed for %s: %s. Retrying in %.1fs",
                        attempt + 1, settings.MAX_RETRIES, url, e, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logging.error(
                        "[Scraper_diagnostics] httpx failed after %d attempts for %s: %s",
                        settings.MAX_RETRIES, url, e,
                    )
                    raise
    return "", 0.0, method_used, retry_count

def clean_html_for_selectors(html: str, max_chars: int | None = None) -> str:
    """Remove known-noise tags while preserving structure useful for selector discovery."""
    if max_chars is None:
        max_chars = settings.SELECTOR_SNIPPET_MAX_CHARS
        
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
        if len(digits) < settings.CONTACT_VALID_PHONE_MIN_DIGITS or len(digits) > settings.CONTACT_VALID_PHONE_MAX_DIGITS:
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
    if field.field_type == FieldType.CURRENCY:
        # Extract amount and optional symbol
        match = re.search(r"([$£€¥₹]\s*\d+[\d,.]*|\d+[\d,.]*\s*[$£€¥₹])", text)
        if match:
            return match.group(1).replace(" ", "")
        # Fallback to finding just the number if no symbol found
        match_num = re.search(r"\d+[\d,.]*", text)
        return match_num.group(0) if match_num else None
    if field.field_type == FieldType.URL:
        if not text.startswith("http"):
            from urllib.parse import urljoin
            text = urljoin(base_url, text)
        return text if text.startswith("http") else None
    
    if _is_noise_name_value(text) and _is_entity_name_field(field.name):
        return None

    return text
