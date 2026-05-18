"""
Selector Profile Loader — domain-specific extraction via JSON configs.

Design:
  Instead of hardcoding CSS selectors in Python for each site, store them
  as JSON profiles. The loader matches the URL domain to a profile,
  then uses Playwright's page.evaluate() to run the selectors directly
  in the browser context — producing clean, structured records.

  Adding a new site = create a JSON file in profiles/. No code changes.

Profile schema:
  {
    "domain": "example.com",          // Domain to match (substring match)
    "description": "...",             // Human-readable description
    "wait_for": "div.card",           // CSS selector to wait for before extracting
    "item_container": "div.card",     // CSS selector for each repeating item
    "fields": {
      "field_name": {
        "selector": ".class span",    // CSS selector relative to item_container
        "type": "string|currency|number",  // Field type hint for post-processing
        "attribute": "text"           // "text" (default), "href", or a data attribute
      }
    }
  }

  The "type" field supports post-processing:
    - "currency": extracts numeric value from strings like "£238" or "$500"
    - "number": converts extracted text to float
    - "text" (default): returns raw text content
    - "href": extracts the href attribute from an <a> tag
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# Path to the profiles directory
_PROFILES_DIR = Path(__file__).resolve().parent / "profiles"

# Cache loaded profiles to avoid repeated disk I/O
_profile_cache: dict[str, dict] | None = None

from app.config import settings

USER_AGENT = settings.USER_AGENT


# ── Profile Loading ──────────────────────────────────────────────────────


def _load_all_profiles() -> dict[str, dict]:
    """Load all JSON profiles from the profiles/ directory.
    
    Returns a dict mapping domain → profile config.
    """
    global _profile_cache
    if _profile_cache is not None:
        return _profile_cache

    _profile_cache = {}
    profiles_dir = _PROFILES_DIR

    if not profiles_dir.exists():
        logger.debug("Selector profiles directory not found: %s", profiles_dir)
        return _profile_cache

    for fpath in sorted(profiles_dir.glob("*.json")):
        try:
            with open(fpath, "r") as f:
                profile = json.load(f)
            domain = profile.get("domain", "").strip().lower()
            if not domain:
                logger.warning("Profile %s has no 'domain' field, skipping", fpath.name)
                continue
            _profile_cache[domain] = profile
            logger.debug("Loaded selector profile: %s → %s", domain, fpath.name)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load profile %s: %s", fpath.name, e)

    logger.info("Loaded %d selector profiles", len(_profile_cache))
    return _profile_cache


def _match_domain(url: str) -> Optional[dict]:
    """Find a profile that matches the URL's domain.
    
    Uses substring matching so 'flightsnholidays.co.uk' matches
    'www.flightsnholidays.co.uk' and 'flightsnholidays.co.uk'.
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    profiles = _load_all_profiles()
    for domain, profile in profiles.items():
        if domain in hostname:
            return profile
    return None


def reload_profiles():
    """Force reload profiles from disk. Call when profiles are added/updated at runtime."""
    global _profile_cache
    _profile_cache = None
    _load_all_profiles()


# ── Field Value Post-Processing ──────────────────────────────────────────


def _parse_currency(text: Optional[str]) -> Optional[str]:
    """Extract numeric price from a string like '£238', 'AED 500', or '$1,234.56'."""
    if not text:
        return None
    cleaned = text.replace(",", "")
    match = re.search(r"[\d]+(?:\.[\d]+)?", cleaned)
    if match:
        return match.group(0)
    return None


def _postprocess_field(value, field_config: dict) -> str | None:
    """Apply type-specific post-processing to an extracted field value."""
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    field_type = field_config.get("type", "text")

    if field_type == "currency":
        parsed = _parse_currency(text)
        return parsed if parsed else text
    elif field_type == "number":
        try:
            cleaned = text.replace(",", "").replace("£", "").replace("$", "").replace("€", "")
            return str(float(cleaned))
        except (ValueError, TypeError):
            return text

    return text


# ── Playwright Extraction ────────────────────────────────────────────────


async def extract_with_profile(
    url: str,
    profile: dict,
    max_wait: int = 30,
) -> list[dict]:
    """Extract structured data from a URL using a selector profile.
    
    Uses Playwright to render the page, waits for the target container,
    then extracts field values from each matching item using page.evaluate().
    
    Args:
        url: Target URL to scrape.
        profile: Profile dict loaded from JSON config.
        max_wait: Max seconds to wait for the wait_for selector.
    
    Returns:
        List of dicts with keys matching the profile's field definitions.
    """
    container_sel = profile.get("item_container")
    wait_for_sel = profile.get("wait_for", container_sel)
    field_defs = profile.get("fields", {})

    if not container_sel or not field_defs:
        logger.warning("Profile missing 'item_container' or 'fields'")
        return []

    logger.info(
        "[ProfileExtractor] Fetching %s with profile (container=%s, %d fields)",
        url, container_sel, len(field_defs),
    )

    browser = None
    context = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            # Block images/media/fonts for speed
            async def _route_filter(route):
                if route.request.resource_type in {"image", "media", "font"}:
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", _route_filter)

            try:
                await page.goto(url, wait_until="networkidle", timeout=settings.PLAYWRIGHT_TIMEOUT)
            except Exception:
                logger.warning("[ProfileExtractor] networkidle timeout, trying domcontentloaded")
                await page.goto(url, wait_until="domcontentloaded", timeout=settings.PLAYWRIGHT_TIMEOUT - 10000)

            # Wait for the target container to appear
            if wait_for_sel:
                try:
                    await page.wait_for_selector(wait_for_sel, timeout=max_wait * 1000)
                    await asyncio.sleep(settings.PAGE_SETTLE_DELAY)  # buffer for remaining JS rendering
                except Exception:
                    logger.warning(
                        "[ProfileExtractor] Selector '%s' not found within %ds",
                        wait_for_sel, max_wait,
                    )
                    return []

            # Build the evaluate JS string from the profile config
            field_extractors = {}
            for field_name, field_cfg in field_defs.items():
                sel = field_cfg.get("selector", "")
                attr = field_cfg.get("attribute", "text")
                field_extractors[field_name] = {"selector": sel, "attribute": attr}

            # Serialize for embedding in JS
            import json as _json
            field_json = _json.dumps(field_extractors)

            records = await page.evaluate(f"""
                () => {{
                    const fieldDefs = {field_json};
                    const cards = document.querySelectorAll('{container_sel}');
                    return Array.from(cards).map(card => {{
                        const record = {{}};
                        for (const [name, cfg] of Object.entries(fieldDefs)) {{
                            const el = card.querySelector(cfg.selector);
                            if (!el) {{
                                record[name] = null;
                                continue;
                            }}
                            if (cfg.attribute === 'href') {{
                                record[name] = el.getAttribute('href') || null;
                            }} else if (cfg.attribute === 'text') {{
                                record[name] = (el.textContent || '').trim() || null;
                            }} else {{
                                record[name] = el.getAttribute(cfg.attribute) || null;
                            }}
                        }}
                        return record;
                    }});
                }}
            """)

            # Post-process field values
            for record in records:
                for field_name, field_cfg in field_defs.items():
                    if field_name in record:
                        record[field_name] = _postprocess_field(
                            record[field_name], field_cfg
                        )

            logger.info("[ProfileExtractor] Extracted %d records", len(records))
            return records

    except Exception as e:
        logger.exception("[ProfileExtractor] Fatal error for %s: %s", url, e)
        return []
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass


async def try_profile_extraction(url: str, max_wait: int = 30) -> Optional[list[dict]]:
    """Try to extract data from a URL using a matching selector profile.
    
    Returns extracted records if a matching profile is found, or None if no
    profile matches (caller should fall back to the generic extraction pipeline).
    
    Args:
        url: Target URL to scrape.
        max_wait: Max seconds to wait for content to render.
    
    Returns:
        List of records if a profile matched and extraction succeeded.
        None if no profile matches the URL domain.
    """
    profile = _match_domain(url)
    if profile is None:
        logger.debug("No selector profile found for URL: %s", url)
        return None

    logger.info("Found selector profile for %s: %s", url, profile.get("domain"))
    return await extract_with_profile(url, profile, max_wait=max_wait)
