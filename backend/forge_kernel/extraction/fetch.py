"""Fetch abstraction — HTTP fetch and Playwright browser-assisted fetch.

Ported from the existing async_utils, html_utils, and browser_pool.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from enum import StrEnum

from forge_kernel.config import settings

logger = logging.getLogger(__name__)


class FetchStrategy(StrEnum):
    HTTP = "http"
    BROWSER = "browser"
    BROWSER_FALLBACK = "browser_fallback"


@dataclass
class FetchResult:
    """Result of a page fetch attempt."""

    html: str
    url: str
    final_url: str = ""
    status_code: int = 0
    strategy: FetchStrategy = FetchStrategy.HTTP
    headers: dict[str, str] = field(default_factory=dict)
    duration_ms: float = 0.0
    error: str | None = None
    anti_bot_score: float = 0.0


async def fetch_page_content(url: str, use_browser: bool = False) -> FetchResult:  # noqa: FBT001, FBT002
    """Fetch page content via HTTP or Playwright browser.

    Args:
        url: The URL to fetch.
        use_browser: If True, use Playwright browser for JS rendering.

    Returns:
        FetchResult with HTML content and metadata.

    """
    if use_browser:
        return await _fetch_with_browser(url)
    return await _fetch_with_httpx(url)


async def _fetch_with_httpx(url: str) -> FetchResult:
    """Fetch via plain HTTP with httpx."""
    import time

    try:
        import httpx
    except ImportError:
        return FetchResult(html="", url=url, error="httpx not installed", status_code=0)

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=settings.http.REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": settings.http.USER_AGENT},
        ) as client:
            resp = await client.get(url)
            duration = (time.monotonic() - start) * 1000
            return FetchResult(
                html=resp.text,
                url=url,
                final_url=str(resp.url),
                status_code=resp.status_code,
                strategy=FetchStrategy.HTTP,
                headers=dict(resp.headers),
                duration_ms=duration,
            )
    except Exception as e:
        duration = (time.monotonic() - start) * 1000
        return FetchResult(html="", url=url, error=str(e), status_code=0, duration_ms=duration)


async def _fetch_with_browser(url: str) -> FetchResult:
    """Fetch via Playwright browser for JS-rendered content."""
    import time

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed, falling back to HTTP fetch")
        return await _fetch_with_httpx(url)

    start = time.monotonic()
    browser = None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=settings.browser.PLAYWRIGHT_HEADLESS)
            ctx = await browser.new_context(
                viewport={"width": settings.browser.BROWSER_VIEWPORT_WIDTH, "height": settings.browser.BROWSER_VIEWPORT_HEIGHT},
                user_agent=settings.http.USER_AGENT,
            )
            try:
                page = await ctx.new_page()
                resp = await page.goto(url, wait_until="networkidle", timeout=settings.browser.PLAYWRIGHT_TIMEOUT)
                html = await page.content()
                final_url = page.url

                duration = (time.monotonic() - start) * 1000
                return FetchResult(
                    html=html,
                    url=url,
                    final_url=final_url,
                    status_code=resp.status if resp else 0,
                    strategy=FetchStrategy.BROWSER,
                    duration_ms=duration,
                )
            finally:
                await ctx.close()
    except Exception as e:
        duration = (time.monotonic() - start) * 1000
        logger.warning("Browser fetch failed for %s: %s", url, e)
        return FetchResult(html="", url=url, error=str(e), status_code=0, duration_ms=duration, strategy=FetchStrategy.BROWSER)
    finally:
        if browser:
            with contextlib.suppress(Exception):
                await browser.close()
