from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse

if TYPE_CHECKING:
    from app.strategy_evolution import FetchStrategy

from contextlib import suppress

import httpx

try:
    from playwright.async_api import Error as PlaywrightError
except ImportError:
    PlaywrightError = RuntimeError  # type: ignore[misc,assignment]
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


def _record_browser_minutes(
    *,
    usage_context: dict[str, Any] | None,
    url: str,
    method: str,
    quantity: int,
    phase: str,
    duration_ms: float | None = None,
) -> bool:
    """Record billable Playwright browser minutes when caller attribution exists."""
    if quantity <= 0:
        return True
    context = usage_context or {}
    user_id = str(context.get("user_id") or "")
    if not user_id:
        return True

    metadata: dict[str, Any] = {
        "url": url,
        "method": method,
        "job_id": str(context.get("job_id") or ""),
        "phase": phase,
    }
    if duration_ms is not None:
        metadata["duration_ms"] = round(duration_ms, 3)
    try:
        from app.utils.usage_ledger import UsageType, get_usage_ledger

        get_usage_ledger().record_usage(
            user_id,
            UsageType.BROWSER_MINUTE,
            quantity=quantity,
            metadata=metadata,
            org_id=str(context.get("org_id") or ""),
            project_id=str(context.get("project_id") or ""),
        )
        return True
    except ValueError:
        logger.warning("Browser-minute quota exceeded for job %s URL %s", metadata["job_id"], url)
        return False
    except (AttributeError, TypeError, RuntimeError) as exc:
        logger.debug("Browser-minute metering skipped: %s", exc)
        return True


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
        return bool(not re.search(r"[a-zA-Z0-9]", key))
    if key.endswith(" page") and key.split()[0] in EMPTY_TOKENS:
        return True
    if key.startswith(("click ", "read ", "view ")):
        return True
    return bool(re.fullmatch(r"\d+\s+more", key))


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
    return bool(any(token in val for token in ["show all", "nearby locations", "use my current location"]))


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


def _is_likely_noise_row(record: dict[str, Any], schema_fields: list[SchemaField]) -> bool:
    """Determine if a record is noise using semantic density and structural analysis."""
    from app.semantic_segmentation import (  # research-shell, lazy
        is_likely_noise_field,
        segment_single_text,
    )

    all_values = []
    for value in record.values():
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
    record: dict[str, Any],
    schema_fields: list[SchemaField],
    node,
    page_email: str | None = None,
    page_phone: str | None = None,
    allow_page_fallback: bool = False,
) -> dict[str, Any]:
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


def _normalize_fetch_strategy(
    preferred_method: str | None,
    anti_bot_stealth: bool,
) -> FetchStrategy:
    """Convert preferred_method string to a FetchStrategy enum."""
    from app.strategy_evolution import FetchStrategy

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
    return strategy


async def _try_httpx_strategies(
    url: str,
    strategy: FetchStrategy,
    extra_headers: dict[str, str] | None = None,
    timeout_ms: int | None = None,
    cookies: dict[str, str] | None = None,
) -> tuple[str, float, str, int] | None:
    """Try HTTPX-based strategies; return result tuple or None to fall through."""
    from app.scrape_telemetry import detect_anti_bot
    from app.strategy_evolution import FetchStrategy

    if strategy not in [
        FetchStrategy.HTTPX_BASIC,
        FetchStrategy.HTTPX_WITH_UA,
        FetchStrategy.HTTPX_SMART,
        FetchStrategy.HYBRID,
    ]:
        return None

    try:
        html, delay, method, retries = await _fetch_with_httpx(
            url,
            strategy=strategy,
            extra_headers=extra_headers,
            timeout_ms=timeout_ms,
            cookies=cookies,
        )
        if html and detect_anti_bot(html) < 0.7:
            return html, delay, method, retries
        logger.info("[Scraper] HTTPX result looks like a block, falling through")
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as e:
        if strategy != FetchStrategy.HYBRID:
            logger.warning("[Scraper] %s failed for %s: %s. Falling back to Playwright", strategy.value, url, e)
    return None


async def _setup_playwright_page(
    pool: Any,
    domain: str,
    strategy: FetchStrategy,
    url: str,
    cookies: dict[str, str] | None,
    extra_headers: dict[str, str] | None,
) -> tuple[Any, Any, list]:
    """Set up Playwright browser context and page with route filtering and network capture."""
    from app.strategy_evolution import FetchStrategy

    context = await pool.get_context(domain, strategy=strategy)
    if cookies:
        cookie_list = [{"name": name, "value": value, "url": url} for name, value in cookies.items()]
        await context.add_cookies(list(cookie_list))
    page = await context.new_page()
    if extra_headers:
        await page.set_extra_http_headers(extra_headers)

    async def _route_filter(route) -> None:
        req_url = route.request.url
        if isinstance(req_url, str):
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
    network_payloads, _console_logs = await setup_network_capture(page)
    return context, page, network_payloads


async def _playwright_navigate_and_stabilize(
    page: Any,
    url: str,
    strategy: FetchStrategy,
    timeout_ms: int | None,
    skip_networkidle: bool,
    hydration_wait_ms: int | None,
    scroll_attempts: int | None,
    domain: str,
    *,
    wait_for_selector: str | None = None,
    wait_for_function: str | None = None,
    wait_for_timeout: int | None = None,
    wait_for_navigation: bool | None = None,
) -> float:
    """Navigate, wait for stabilization, and scroll; returns js_render_delay_ms.

    User-supplied wait-condition overrides (Roadmap Wave 5, Item 3) take
    precedence over the platform-default ``networkidle``-based settle
    logic so a caller can wait on a specific selector, a JS function, or
    a fixed timeout when handling SPAs / lazy content.
    """
    from app.scrape_telemetry import detect_anti_bot
    from app.strategy_evolution import FetchStrategy
    from app.telemetry_state import get_telemetry_state

    try:
        wait_until: Literal["domcontentloaded", "networkidle"] = (
            "domcontentloaded" if skip_networkidle or strategy == FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT else "networkidle"
        )
        initial_timeout = timeout_ms if timeout_ms is not None else min(settings.PLAYWRIGHT_TIMEOUT, 15000)
        await page.goto(url, wait_until=wait_until, timeout=initial_timeout)

        try:
            final_url = page.url
            _validate_url_safe(final_url)
        except ValueError:
            logger.warning("[SSRF] Playwright navigated to blocked target %s from %s — aborting", page.url, url)
            with suppress(RuntimeError, OSError, PlaywrightError):
                await page.close()
            raise

        # Custom navigation wait (Roadmap Wave 5 Item 3)
        if wait_for_navigation:
            with suppress(asyncio.TimeoutError, RuntimeError, OSError, PlaywrightError):
                await page.wait_for_event("framenavigated", timeout=initial_timeout)

        # Custom selector wait (Roadmap Wave 5 Item 3)
        if wait_for_selector:
            with suppress(asyncio.TimeoutError, RuntimeError, OSError, PlaywrightError):
                selector_timeout = wait_for_timeout if wait_for_timeout is not None else min(settings.PLAYWRIGHT_TIMEOUT, 15000)
                await page.wait_for_selector(wait_for_selector, timeout=selector_timeout)

        # Custom function wait (Roadmap Wave 5 Item 3)
        if wait_for_function:
            with suppress(asyncio.TimeoutError, RuntimeError, OSError, PlaywrightError):
                function_timeout = wait_for_timeout if wait_for_timeout is not None else min(settings.PLAYWRIGHT_TIMEOUT, 15000)
                await page.wait_for_function(wait_for_function, timeout=function_timeout)

        # Fixed-timeout wait (Roadmap Wave 5 Item 3)
        if wait_for_timeout is not None and wait_for_selector is None and wait_for_function is None:
            with suppress(asyncio.TimeoutError, RuntimeError, OSError, PlaywrightError):
                await page.wait_for_timeout(int(wait_for_timeout))

        intel = get_domain_intelligence().get_intelligence(url)

        if strategy != FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT:
            loading_selectors = [".loading", ".spinner", ".loader", "[class*='Loading']", "[class*='Spinner']"]
            for sel in loading_selectors:
                with suppress(asyncio.TimeoutError, RuntimeError, OSError, PlaywrightError):
                    await page.wait_for_selector(sel, state="hidden", timeout=2000)

        telemetry = get_telemetry_state()
        avg_stabilization = telemetry.get_avg_stabilization(domain)
        stabilization_start = time.time()
        if hydration_wait_ms is not None:
            settle_timeout = hydration_wait_ms / 1000.0
        else:
            settle_timeout = intel.hydration_delay_ms / 1000.0 if intel.hydration_delay_ms > 0 else settings.PAGE_SETTLE_DELAY
        settle_timeout = max(settle_timeout, 3.0)

        min_wait_ms = 2500
        with suppress(asyncio.TimeoutError, RuntimeError, OSError, ValueError, PlaywrightError):
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
        js_render_delay_ms = (time.time() - stabilization_start) * 1000
        telemetry.record_stabilization(domain, js_render_delay_ms)

        if strategy != FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT:
            _scroll_attempts_val = 0
            max_scrolls = scroll_attempts if scroll_attempts is not None else 3
            last_height = await page.evaluate("document.body.scrollHeight")
            while _scroll_attempts_val < max_scrolls:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(settings.PAGE_SCROLL_DELAY)
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                _scroll_attempts_val += 1
            if _scroll_attempts_val > 0:
                intel.infinite_scroll_required = True
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(settings.POST_SCROLL_RESET_DELAY)

        return js_render_delay_ms
    except (RuntimeError, OSError, AttributeError, ValueError, TimeoutError, PlaywrightError) as e:
        try:
            partial_html = await page.content()
            if detect_anti_bot(partial_html) > 0.5:
                logger.warning("[Scraper] Anti-bot detected during initial %s for %s — aborting early", e, url)
                _ab_msg = f"Anti-bot challenge detected: {e}"
                raise ValueError(_ab_msg)
        except ValueError:
            raise
        except (TimeoutError, RuntimeError, OSError, PlaywrightError):
            logger.debug("Secondary load state wait failed for %s", url, exc_info=True)

        logger.warning("[Scraper] %s slow load for %s: %s. Falling to domcontentloaded", strategy.value, url, e)
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(min(settings.PAGE_FALLBACK_EXTRA_WAIT, 2.0))
        return 0.0


async def _collect_playwright_results(
    page: Any,
    context: Any,
    url: str,
    domain: str,
    network_payloads: list,
) -> str:
    """Collect browser state, cookies, and HTML after navigation."""
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
    except (RuntimeError, OSError, AttributeError, ValueError, TimeoutError, PlaywrightError) as cookie_err:
        logger.debug("[BrowserState] Cookie persistence skipped for %s: %s", url, cookie_err)

    html = await page.content()
    if network_payloads:
        store_captures(url, network_payloads)
        logger.info("[BrowserNetwork] Captured %d network payloads from %s", len(network_payloads), url)
    return html


async def _detect_anti_bot_and_fallback(
    page: Any,
    e: Exception,
    url: str,
    extra_headers: dict[str, str] | None = None,
    timeout_ms: int | None = None,
) -> tuple[str, float, str, int]:
    """Check if an error is anti-bot related; if so raise ValueError, otherwise fallback to httpx."""
    from app.scrape_telemetry import detect_anti_bot
    from app.strategy_evolution import FetchStrategy

    html_content = ""
    if page:
        with suppress(RuntimeError, OSError, PlaywrightError):
            html_content = await page.content()

    err_msg = str(e).lower()
    anti_bot_keywords = {"captcha", "cloudflare", "access denied", "denied", "forbidden", "challenge", "blocked"}
    is_antibot = False
    try:
        if (html_content and detect_anti_bot(html_content) > 0.5) or any(marker in err_msg for marker in anti_bot_keywords):
            is_antibot = True
    except (TypeError, ValueError, AttributeError):
        is_antibot = any(marker in err_msg for marker in anti_bot_keywords)

    if is_antibot:
        logger.error(
            "[Scraper] Anti-bot challenge detected for %s. Refusing naive HTTP fallback to prevent IP ban.",
            url,
            exc_info=e,
        )
        _ab_msg = f"Anti-bot challenge detected: {e}"
        raise ValueError(_ab_msg) from e

    logger.error("[Scraper] Playwright failed for %s. Final fallback to httpx_basic", url, exc_info=e)
    return await _fetch_with_httpx(
        url,
        strategy=FetchStrategy.HTTPX_BASIC,
        extra_headers=extra_headers,
        timeout_ms=timeout_ms,
    )


async def fetch_page_content(
    url: str,
    preferred_method: str | None = None,
    timeout_ms: int | None = None,
    hydration_wait_ms: int | None = None,
    skip_networkidle: bool = False,
    scroll_attempts: int | None = None,
    anti_bot_stealth: bool = False,
    extra_headers: dict[str, str] | None = None,
    usage_context: dict[str, Any] | None = None,
    cookies: dict[str, str] | None = None,
    wait_for_selector: str | None = None,
    wait_for_function: str | None = None,
    wait_for_timeout: int | None = None,
    wait_for_navigation: bool | None = None,
) -> tuple[str, float, str, int]:
    """Load a URL in a pooled headless browser context or via plain HTTP.

    Wait-condition overrides (Roadmap Wave 5, Item 3):

    * ``wait_for_selector``: a CSS selector to wait for before extraction.
    * ``wait_for_function``: a JS expression that must evaluate truthy.
    * ``wait_for_timeout``: explicit timeout (ms) post-navigation.
    * ``wait_for_navigation``: if True, wait for a navigation event after
      the initial load (useful for JS-only redirects).
    """
    from app.strategy_evolution import FetchStrategy

    domain = urlparse(url).netloc.lower() or "default"
    strategy = _normalize_fetch_strategy(preferred_method, anti_bot_stealth)

    httpx_result = await _try_httpx_strategies(url, strategy, extra_headers, timeout_ms, cookies)
    if httpx_result is not None:
        return httpx_result

    page: Any = None
    context: Any = None
    network_payloads: list = []
    js_render_delay_ms = 0.0
    method_used = strategy.value
    browser_meter_started_at: float | None = None
    browser_metered_initial = False

    try:
        browser_meter_started_at = time.monotonic()
        if not _record_browser_minutes(usage_context=usage_context, url=url, method=method_used, quantity=1, phase="initial"):
            logger.warning("[Scraper] Browser-minute quota exhausted for %s. Falling back to httpx_basic", url)
            return await _fetch_with_httpx(
                url, strategy=FetchStrategy.HTTPX_BASIC, extra_headers=extra_headers, timeout_ms=timeout_ms
            )
        browser_metered_initial = True

        pool = get_browser_pool()
        context, page, network_payloads = await _setup_playwright_page(pool, domain, strategy, url, cookies, extra_headers)

        js_render_delay_ms = await _playwright_navigate_and_stabilize(
            page,
            url,
            strategy,
            timeout_ms,
            skip_networkidle,
            hydration_wait_ms,
            scroll_attempts,
            domain,
            wait_for_selector=wait_for_selector,
            wait_for_function=wait_for_function,
            wait_for_timeout=wait_for_timeout,
            wait_for_navigation=wait_for_navigation,
        )

        html = await _collect_playwright_results(page, context, url, domain, network_payloads)
        return html, js_render_delay_ms, method_used, 0

    except ValueError:
        raise
    except (RuntimeError, OSError, AttributeError, TimeoutError, PlaywrightError) as e:
        return await _detect_anti_bot_and_fallback(page, e, url, extra_headers, timeout_ms)
    finally:
        if browser_metered_initial and browser_meter_started_at is not None:
            elapsed_seconds = max(0.0, time.monotonic() - browser_meter_started_at)
            billable_minutes = max(1, math.ceil(elapsed_seconds / 60.0))
            extra_minutes = billable_minutes - 1
            if extra_minutes > 0:
                _record_browser_minutes(
                    usage_context=usage_context,
                    url=url,
                    method=method_used,
                    quantity=extra_minutes,
                    phase="additional",
                    duration_ms=elapsed_seconds * 1000,
                )
        if page:
            with suppress(RuntimeError, OSError, PlaywrightError):
                await page.close()


def _build_httpx_headers(strategy: FetchStrategy, domain: str, extra_headers: dict[str, str] | None) -> dict[str, str]:
    """Build HTTP headers for the given fetch strategy and domain."""
    from app.anti_bot_engine import get_anti_bot_engine
    from app.strategy_evolution import FetchStrategy

    anti_bot = get_anti_bot_engine()
    if strategy in [FetchStrategy.HTTPX_SMART, FetchStrategy.HTTPX_WITH_UA]:
        stealth = anti_bot.get_stealth_profile(domain)
        headers = dict(stealth.get("extra_headers", {}))
        headers["User-Agent"] = stealth["user_agent"]
    else:
        headers = {"User-Agent": settings.USER_AGENT}
        if strategy == FetchStrategy.HTTPX_BASIC:
            headers = {"User-Agent": settings.HTTPX_BASIC_USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)
    cookie_string = anti_bot.get_cookies(domain)
    if cookie_string and "Cookie" not in headers and "cookie" not in {k.lower() for k in headers}:
        headers["Cookie"] = cookie_string
    return headers


async def _follow_httpx_redirects(client: httpx.AsyncClient, url: str, strategy: FetchStrategy) -> httpx.Response:
    """Follow HTTP redirects with SSRF validation at each hop."""
    from app.strategy_evolution import FetchStrategy

    current_url = url
    max_redirects = 10
    redirects_followed = 0

    if strategy == FetchStrategy.HTTPX_SMART:
        initial_host = urlparse(url).scheme + "://" + urlparse(url).netloc
        _validate_url_safe(initial_host)
        warmup_resp = await client.get(initial_host)
        await warmup_resp.aclose()

    while True:
        next_resp = await client.get(current_url)
        if next_resp.is_redirect:
            redirects_followed += 1
            if redirects_followed > max_redirects:
                await next_resp.aclose()
                msg = f"Too many redirects (max {max_redirects})"
                raise ValueError(msg)

            redirect_target = next_resp.headers.get("location", "")
            if not redirect_target:
                return next_resp

            from urllib.parse import urljoin

            redirect_url = urljoin(str(next_resp.url), redirect_target)
            _validate_url_safe(redirect_url)
            await next_resp.aclose()
            current_url = redirect_url
        else:
            return next_resp


async def _extract_httpx_body(resp: httpx.Response, domain: str, anti_bot: Any) -> str:
    """Extract body from HTTP response with SSRF validation and cookie persistence.

    FU-2026-07-04 (M2): refuse responses whose ``Content-Length`` exceeds the
    configured MAX_HTML_FETCH_BYTES cap (default 25 MB). A single hostile page
    with gigabytes of HTML would otherwise OOM the worker. The cap is a
    last-resort defence — legitimate pages above 25 MB are vanishingly rare.
    """
    from app.config import settings

    max_html_bytes = int(getattr(settings, "MAX_HTML_FETCH_BYTES", 25 * 1024 * 1024))
    try:
        resp.raise_for_status()
        final_url = str(resp.url)
        _validate_url_safe(final_url)
        set_cookie = resp.headers.get("set-cookie", "")
        if set_cookie:
            anti_bot.update_cookies(domain, set_cookie)

        # Pre-check Content-Length before materializing the full body
        cl_header = resp.headers.get("content-length")
        if cl_header:
            try:
                declared = int(cl_header)
            except ValueError:
                declared = -1
            if declared > max_html_bytes:
                msg = (
                    f"Content-Length {declared} exceeds "
                    f"MAX_HTML_FETCH_BYTES ({max_html_bytes}); refusing "
                    f"to buffer body for {resp.url}"
                )
                raise ValueError(msg)

        return resp.text
    finally:
        await resp.aclose()


async def _fetch_with_httpx(
    url: str,
    strategy: FetchStrategy | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout_ms: int | None = None,
    cookies: dict[str, str] | None = None,
) -> tuple[str, float, str, int]:
    """Internal helper for httpx fetching with retries."""
    from app.anti_bot_engine import get_anti_bot_engine
    from app.strategy_evolution import FetchStrategy
    from app.url_safety import get_safe_async_client

    if strategy is None:
        strategy = FetchStrategy.HTTPX_BASIC
    elif isinstance(strategy, str):
        try:
            strategy = FetchStrategy(strategy)
        except ValueError:
            strategy = FetchStrategy.HTTPX_BASIC
    method_used = strategy.value

    domain = urlparse(url).netloc.lower() or "default"
    anti_bot = get_anti_bot_engine()
    headers = _build_httpx_headers(strategy, domain, extra_headers)

    timeout_seconds = (timeout_ms / 1000.0) if timeout_ms is not None else settings.REQUEST_TIMEOUT

    async with get_safe_async_client(
        timeout=httpx.Timeout(timeout_seconds),
        headers=headers,
        follow_redirects=False,
        cookies=cookies,
    ) as client:
        for attempt in range(max(1, settings.MAX_RETRIES)):
            retry_count = attempt
            try:
                _validate_url_safe(url)
                resp = await _follow_httpx_redirects(client, url, strategy)
                body = await _extract_httpx_body(resp, domain, anti_bot)
                return body, 0.0, method_used, retry_count
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
                    logger.exception(
                        "[Scraper] %s failed after %d attempts for %s. Final fallback to httpx_basic",
                        strategy.value,
                        settings.MAX_RETRIES,
                        url,
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
    if isinstance(cleaned, bytes):
        from app.encoding_detection import decode_content

        text: str = decode_content(cleaned)
    else:
        text = cleaned
    return text[:max_chars]


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
        return cleaned or None

    text = _compact_text(str(value))
    if _is_empty_value(text):
        return None

    if field.field_type == FieldType.BOOLEAN:
        if isinstance(value, bool):
            return value

        normalized = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
        if normalized in {
            "true",
            "yes",
            "y",
            "1",
            "on",
            "active",
            "available",
            "in stock",
            "enabled",
            "present",
        }:
            return True
        if normalized in {
            "false",
            "no",
            "n",
            "0",
            "off",
            "inactive",
            "unavailable",
            "out of stock",
            "sold out",
            "disabled",
            "missing",
            "not available",
        }:
            return False
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
