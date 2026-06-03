from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse

if TYPE_CHECKING:
    from app.strategy_evolution import FetchStrategy

import httpx
from bs4 import BeautifulSoup

from app.browser_network_capture import (
    build_cookie_header,
    collect_browser_state,
    setup_network_capture,
    store_browser_state,
    store_captures,
)
from app.browser_pool import get_browser_pool
from app.config import settings
from app.domain_intelligence import get_domain_intelligence
from app.models import FieldType, SchemaField

# Research-shell boundary:
# `app.semantic_segmentation` and `app.strategy_evolution` are research
# modules (see backend/app/research/__init__.py). They are imported
# lazily inside the functions that use them so that `import app.html_utils`
# does not pull the research shell into the product kernel at startup.
# ─── SSRF / private-network IP validation ──────────────────────────────
from app.url_safety import validate_public_http_url as _validate_url_safe

logger = logging.getLogger(__name__)


EMPTY_TOKENS = {"-", "n / a", "na", "null", "none", "", "not available", "empty", "0", "false", "undefined"}
PLACEHOLDER_PHRASES = {"no data", "not specified", "coming soon", "tbd", "unknown"}
LIKELY_LOCATION_WORDS = {"city", "country", "state"}
NAME_FIELD_NOISE_PREFIXES = {
    "privacy policy",
    "terms of",
    "cookie",
    "copyright",
    "all rights",
    "contact us",
    "about us",
    "home",
    "search",
    "menu",
    "login",
    "sign up",
    "subscribe",
    "newsletter",
    "follow us",
    "read more",
    "learn more",
    "view details",
    "quick links",
    "useful links",
    "selling tools",
    "starting from",
    "years of experience",
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
    if len(key) < settings.SELECTOR_MIN_TEXT_LEN:
        # If extremely short but contains alphanumeric characters (e.g. "LON", "PAR", "238", "1"), it is valid.
        # Only treat as placeholder if it is purely symbols (e.g. "--", "...")
        if not re.search(r"[a-zA-Z0-9]", key):
            return True
        return False
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
    from app.semantic_segmentation import is_likely_noise_field  # research-shell, lazy

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
    from app.semantic_segmentation import is_likely_noise_field, segment_single_text  # research-shell, lazy

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

    # Privacy / legal / navigation: these are structurally distinct
    nav_indicators = ["privacy policy", "terms of", "cookie", "about us"]
    if any(v in combined for v in nav_indicators):
        return True

    # Social media links: structural noise on listing pages
    # Only flag if multiple platforms appear (single mention is likely
    # legitimate)
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
                    record.get(f.name)
                    for f in schema_fields
                    if f.field_type == FieldType.EMAIL and not _is_empty_value(record.get(f.name))
                )
                phone_present = any(
                    record.get(f.name)
                    for f in schema_fields
                    if f.field_type == FieldType.PHONE and not _is_empty_value(record.get(f.name))
                )
                url_field = next((f.name for f in schema_fields if f.field_type == FieldType.URL), "")
                website_present = bool(record.get(url_field)) if url_field else False

                if not (email_present or phone_present or website_present):
                    return True

        address_field = next(
            (
                f.name
                for f in schema_fields
                if f.field_type == FieldType.LOCATION or any(x in f.name.lower() for x in ["address", "location"])
            ),
            "",
        )
        address_text = _compact_text(str(record.get(address_field) or "")) if address_field else ""
        if address_text and name_text and address_text.startswith(name_text[:40]):
            email_present = any(
                record.get(f.name)
                for f in schema_fields
                if f.field_type == FieldType.EMAIL and not _is_empty_value(record.get(f.name))
            )
            phone_present = any(
                record.get(f.name)
                for f in schema_fields
                if f.field_type == FieldType.PHONE and not _is_empty_value(record.get(f.name))
            )
            url_field = next((f.name for f in schema_fields if f.field_type == FieldType.URL), "")
            website_present = bool(record.get(url_field)) if url_field else False
            if not (email_present or phone_present or website_present):
                return True

    return False


def _extract_contacts_from_node(node) -> tuple[str | None, str | None]:
    """Search a BeautifulSoup node for email and phone numbers, including href attributes."""
    text = node.get_text(separator=" ", strip=True)

    # Check hrefs in this node and its descendants
    hrefs = []
    if node.name == "a":
        hrefs.append(node.get("href") or "")
    for a in node.find_all("a"):
        hrefs.append(a.get("href") or "")

    for href in hrefs:
        if href.lower().startswith("mailto:"):
            parts = href.split("mailto:", 1)
            if len(parts) > 1:
                email = parts[1].split("?")[0]
                if _valid_email(email):
                    text += f" {email}"
        elif href.lower().startswith("tel:"):
            parts = href.split("tel:", 1)
            if len(parts) > 1:
                phone = parts[1].split("?")[0]
                if _valid_phone(phone):
                    text += f" {phone}"

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


async def fetch_page_content(
    url: str,
    preferred_method: str | None = None,
    timeout_ms: int | None = None,
    hydration_wait_ms: int | None = None,
    skip_networkidle: bool = False,
    scroll_attempts: int | None = None,
    anti_bot_stealth: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> tuple[str, float, str, int]:
    """Load a URL in a pooled headless browser context or via plain HTTP.

    Args:
        url: The URL to fetch.
        preferred_method: The preferred fetch strategy as a string key
            (e.g. "playwright_full", "httpx_basic"). Defaults to
            "playwright_full" if None.
        timeout_ms: Override the Playwright navigation timeout (ms).
        hydration_wait_ms: Override the hydration wait / delay after load (ms).
        skip_networkidle: If True, use domcontentloaded instead of networkidle.
        scroll_attempts: Override the number of scroll attempts.
        anti_bot_stealth: If True, enable extra stealth measures.
        extra_headers: Extra HTTP headers to inject.

    Returns:
        tuple of (html_content, js_render_delay_ms, method_used, retry_count)
    """
    from app.strategy_evolution import FetchStrategy  # research-shell, lazy

    domain = urlparse(url).netloc.lower() or "default"

    # Normalize method to Enum
    if preferred_method is None or preferred_method == "":
        strategy = FetchStrategy.PLAYWRIGHT_FULL
    elif isinstance(preferred_method, str):
        try:
            strategy = FetchStrategy(preferred_method)
        except ValueError:
            strategy = FetchStrategy.PLAYWRIGHT_FULL
    else:
        strategy = preferred_method

    if anti_bot_stealth and strategy in (FetchStrategy.PLAYWRIGHT_FULL, FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT):
        strategy = FetchStrategy.PLAYWRIGHT_STEALTH

    # ── Phase 80: Granular Strategy Execution ──

    # 1. HTTPX-based strategies
    if strategy in [
        FetchStrategy.HTTPX_BASIC,
        FetchStrategy.HTTPX_WITH_UA,
        FetchStrategy.HTTPX_SMART,
        FetchStrategy.HYBRID,
    ]:
        try:
            html, delay, method, retries = await _fetch_with_httpx(
                url,
                strategy=strategy,
                extra_headers=extra_headers,
                timeout_ms=timeout_ms,
            )
            if html:
                # Basic anti-bot check on httpx result
                from app.scrape_telemetry import detect_anti_bot

                if detect_anti_bot(html) < 0.7:
                    return html, delay, method, retries
                logger.info("[Scraper] HTTPX result looks like a block, falling through")
        except Exception as e:
            if strategy != FetchStrategy.HYBRID:
                logger.warning("[Scraper] %s failed for %s: %s. Falling back to Playwright", strategy.value, url, e)
            # HYBRID continues to Playwright anyway if it fails

    # 2. Playwright-based strategies
    page = None
    network_payloads = []  # Pre-initialize for safety
    js_render_delay_ms = 0.0
    method_used = strategy.value

    try:
        pool = get_browser_pool()
        # Pass strategy to get_context for specialized setup
        context = await pool.get_context(domain, strategy=strategy)
        page = await context.new_page()
        if extra_headers:
            await page.set_extra_http_headers(extra_headers)

        # Phase 80: Lightweight mode filters more resources
        async def _route_filter(route):
            req_url = route.request.url
            try:
                _validate_url_safe(req_url)
            except ValueError as e:
                logger.warning("[SSRF] Playwright request to %s rejected: %s", req_url, e)
                await route.abort()
                return

            abort_types = {"image", "media", "font"}
            if strategy == FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT:
                abort_types.update({"stylesheet", "other"})

            if route.request.resource_type in abort_types:
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", _route_filter)

        # Set up network response interception for API / XHR JSON capture
        network_payloads = await setup_network_capture(page)

        # Phase 1: Try networkidle with quick timeout for faster failure
        # detection
        try:
            wait_until: Literal["domcontentloaded", "networkidle"]
            if skip_networkidle:
                wait_until = "domcontentloaded"
            elif strategy != FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT:
                wait_until = "networkidle"
            else:
                wait_until = "domcontentloaded"
            # Use recovery timeout if provided, otherwise use a short initial
            # timeout (15s) for networkidle
            if timeout_ms is not None:
                initial_timeout = timeout_ms
            else:
                initial_timeout = min(settings.PLAYWRIGHT_TIMEOUT, 15000)
            await page.goto(url, wait_until=wait_until, timeout=initial_timeout)

            # SSRF: validate the final page URL is not private / internal after
            # Playwright navigation
            try:
                final_url = page.url
                _validate_url_safe(final_url)
            except ValueError:
                logger.warning(
                    "[SSRF] Playwright navigated to blocked target %s from %s — aborting",
                    page.url,
                    url,
                )
                await page.close()
                raise

            # Phase 79: Adaptive hydration and scroll from domain intelligence
            intel = get_domain_intelligence().get_intelligence(url)

            # Wait for common loading indicators
            if strategy != FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT:
                loading_selectors = [".loading", ".spinner", ".loader", "[class*='Loading']", "[class*='Spinner']"]
                for sel in loading_selectors:
                    try:
                        await page.wait_for_selector(sel, state="hidden", timeout=2000)
                    except Exception:  # nosec B110
                        pass

            # Adaptive post-network buffer: check DOM stabilization
            from app.telemetry_state import get_telemetry_state

            telemetry = get_telemetry_state()
            avg_stabilization = telemetry.get_avg_stabilization(domain)
            stabilization_start = time.time()
            # Use recovery hydration wait if provided, otherwise domain
            # intelligence or default
            if hydration_wait_ms is not None:
                settle_timeout = hydration_wait_ms / 1000.0
            else:
                settle_timeout = intel.hydration_delay_ms / 1000.0 if intel.hydration_delay_ms > 0 else settings.PAGE_SETTLE_DELAY
            settle_timeout = max(settle_timeout, 3.0)

            min_wait_ms = 2500
            try:
                await page.wait_for_function(
                    f"""() => {{
                         const body = document.body;
                         if (!body) return true;
                         const start = Date.now();
                         let lastHtml = body.innerHTML;
                         let stableSince = Date.now();

                         return new Promise(resolve => {{
                             const interval = setInterval(() => {{
                                 const currentHtml = document.body ? document.body.innerHTML : lastHtml;
                                 const now = Date.now();
                                 if (currentHtml !== lastHtml) {{
                                     lastHtml = currentHtml;
                                     stableSince = now;
                                 }}
                                 const stableFor = now - stableSince;
                                 const totalWait = now - start;
                                 if (stableFor >= {avg_stabilization} && totalWait >= {min_wait_ms}) {{
                                     clearInterval(interval);
                                     resolve(true);
                                 }}
                             }}, {settings.DOM_STABILIZATION_INTERVAL});
                         }});
                     }}""",
                    timeout=settle_timeout * 1000,
                )
            except Exception:  # nosec B110
                pass
            js_render_delay_ms = (time.time() - stabilization_start) * 1000
            telemetry.record_stabilization(domain, js_render_delay_ms)

            # Scroll handling — use recovery scroll_attempts if provided
            if strategy != FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT:
                _scroll_attempts = 0
                max_scrolls = scroll_attempts if scroll_attempts is not None else getattr(settings, "MAX_SCROLL_ATTEMPTS", 3)
                last_height = await page.evaluate("document.body.scrollHeight")
                while _scroll_attempts < max_scrolls:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(settings.PAGE_SCROLL_DELAY)
                    new_height = await page.evaluate("document.body.scrollHeight")
                    if new_height == last_height:
                        break
                    last_height = new_height
                    _scroll_attempts += 1
                if _scroll_attempts > 0:
                    intel.infinite_scroll_required = True
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(settings.POST_SCROLL_RESET_DELAY)

        except Exception as e:
            # Before falling back, check partial HTML for anti-bot signals
            try:
                partial_html = await page.content()
                from app.scrape_telemetry import detect_anti_bot

                if detect_anti_bot(partial_html) > 0.5:
                    logger.warning(
                        "[Scraper] Anti-bot detected during initial %s for %s — aborting early",
                        wait_until,
                        url,
                    )
                    raise ValueError(f"Anti-bot challenge detected during {wait_until}: {e}")
            except ValueError:
                raise  # Re-raise anti-bot detection so scraper records the proper failure reason
            except Exception:  # nosec B110
                pass

            logger.warning(
                "[Scraper] %s slow load for %s: %s. Falling to domcontentloaded",
                strategy.value,
                url,
                e,
            )
            await page.wait_for_load_state("domcontentloaded")
            # Reduced fallback wait: 2s instead of 5s — JS has already had time
            # to start
            await asyncio.sleep(min(settings.PAGE_FALLBACK_EXTRA_WAIT, 2.0))

        browser_state = await collect_browser_state(page)
        if browser_state:
            store_browser_state(url, browser_state)
            logger.info(
                "[BrowserState] Captured %d session candidate(s) from browser storage for %s",
                browser_state.get("session_candidate_count", 0),
                url,
            )

        try:
            raw_cookies = await context.cookies()
            cookie_header = build_cookie_header(raw_cookies)
            if cookie_header:
                from app.anti_bot_engine import get_anti_bot_engine

                get_anti_bot_engine().update_cookies(domain, cookie_header)
        except Exception as cookie_err:
            logger.debug("[BrowserState] Cookie persistence skipped for %s: %s", url, cookie_err)

        html = await page.content()

        # Store captured network payloads for later extraction
        if network_payloads:
            store_captures(url, network_payloads)
            logger.info(
                "[BrowserNetwork] Captured %d network payloads from %s",
                len(network_payloads),
                url,
            )

        return html, js_render_delay_ms, method_used, 0
    except Exception as e:
        html_content = ""
        if page:
            try:
                html_content = await page.content()
            except Exception:  # nosec B110
                pass

        err_msg = str(e).lower()
        is_antibot = False
        from app.scrape_telemetry import detect_anti_bot

        if html_content and detect_anti_bot(html_content) > 0.5:
            is_antibot = True
        elif any(
            marker in err_msg
            for marker in ["captcha", "cloudflare", "access denied", "denied", "forbidden", "challenge", "blocked"]
        ):
            is_antibot = True

        if is_antibot:
            logger.error(
                "[Scraper] Anti-bot challenge detected during %s for %s. Refusing naive HTTP fallback to prevent IP ban.",
                strategy.value,
                url,
            )
            raise ValueError(f"Anti-bot challenge detected: {e}")

        logger.error("[Scraper] %s failed for %s: %s. Final fallback to httpx_basic", strategy.value, url, e)
        return await _fetch_with_httpx(
            url,
            strategy=FetchStrategy.HTTPX_BASIC,
            extra_headers=extra_headers,
            timeout_ms=timeout_ms,
        )
    finally:
        if page:
            try:
                await page.close()
            except Exception:  # nosec B110
                pass


async def _fetch_with_httpx(
    url: str,
    strategy: FetchStrategy | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout_ms: int | None = None,
) -> tuple[str, float, str, int]:
    """Internal helper for httpx fetching with retries."""
    from app.strategy_evolution import FetchStrategy  # research-shell, lazy

    if strategy is None:
        strategy = FetchStrategy.HTTPX_BASIC
    elif isinstance(strategy, str):
        try:
            strategy = FetchStrategy(strategy)
        except ValueError:
            strategy = FetchStrategy.HTTPX_BASIC
    method_used = strategy.value

    # Use anti-bot stealth headers for smart / stealth strategies
    from app.anti_bot_engine import get_anti_bot_engine

    domain = urlparse(url).netloc.lower() or "default"
    anti_bot = get_anti_bot_engine()

    if strategy in [FetchStrategy.HTTPX_SMART, FetchStrategy.HTTPX_WITH_UA]:
        stealth = anti_bot.get_stealth_profile(domain)
        headers = dict(stealth.get("extra_headers", {}))
        headers["User-Agent"] = stealth["user_agent"]
    else:
        headers = {"User-Agent": settings.USER_AGENT}
        if strategy == FetchStrategy.HTTPX_BASIC:
            # Minimal headers for basic fetch
            headers = {"User-Agent": settings.HTTPX_BASIC_USER_AGENT}

    if extra_headers:
        headers.update(extra_headers)
    cookie_string = anti_bot.get_cookies(domain)
    if cookie_string and "Cookie" not in headers and "cookie" not in {k.lower() for k in headers}:
        headers["Cookie"] = cookie_string

    timeout_seconds = (timeout_ms / 1000.0) if timeout_ms is not None else settings.REQUEST_TIMEOUT
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        headers=headers,
        follow_redirects=False,
    ) as client:
        for attempt in range(max(1, settings.MAX_RETRIES)):
            retry_count = attempt
            try:
                # Validate the initial URL before fetching
                _validate_url_safe(url)

                # Phase 80: Smart mode simulates basic session
                if strategy == FetchStrategy.HTTPX_SMART:
                    initial_host = urlparse(url).scheme + "://" + urlparse(url).netloc
                    _validate_url_safe(initial_host)
                    await client.get(initial_host)

                current_url = url
                max_redirects = 10
                redirects_followed = 0

                while True:
                    resp = await client.get(current_url)
                    if resp.is_redirect:
                        redirects_followed += 1
                        if redirects_followed > max_redirects:
                            raise ValueError(f"Too many redirects (max {max_redirects})")

                        redirect_target = resp.headers.get("location", "")
                        if not redirect_target:
                            break

                        from urllib.parse import urljoin

                        redirect_url = urljoin(str(resp.url), redirect_target)

                        # Validate the target redirect URL before fetching it!
                        _validate_url_safe(redirect_url)
                        current_url = redirect_url
                    else:
                        break

                resp.raise_for_status()

                # SSRF: validate the final resolved URL is not private /
                # internal
                final_url = str(resp.url)
                _validate_url_safe(final_url)

                # Persist cookies from response for future requests
                set_cookie = resp.headers.get("set-cookie", "")
                if set_cookie:
                    anti_bot.update_cookies(domain, set_cookie)

                return resp.text, 0.0, method_used, retry_count
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                if attempt < settings.MAX_RETRIES - 1:
                    wait = settings.HTTP_BACKOFF_FACTOR * (attempt + 1)
                    logger.warning(
                        "[Scraper] %s attempt %d/%d failed for %s: %s. Retrying in %.1fs",
                        strategy.value,
                        attempt + 1,
                        settings.MAX_RETRIES,
                        url,
                        e,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "[Scraper_diagnostics] %s failed after %d attempts for %s: %s",
                        strategy.value,
                        settings.MAX_RETRIES,
                        url,
                        e,
                    )
                    raise
    return "", 0.0, method_used, 0


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
    blocked = {d.strip() for d in settings.EMAIL_BLOCKED_DOMAINS.split(",")}
    if domain in blocked:
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
