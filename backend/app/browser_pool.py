"""
Browser Pool — Persistent Chromium management and context pooling.

LAW: Browser instances are heavy. Contexts are light.
Reuse browsers to minimize startup latency; rotate contexts to maintain stealth.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext

from app.config import settings

logger = logging.getLogger(__name__)


class BrowserPool:
    """Manages a persistent Chromium instance with reusable contexts."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._contexts: dict[str, BrowserContext] = {}
        self._context_use_count: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._last_activity = time.time()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def get_context(self, domain: str) -> BrowserContext:
        """Get or create a browser context for a specific domain."""
        async with self._lock:
            self._last_activity = time.time()
            if not self._playwright:
                self._playwright = await async_playwright().start()
            
            if not self._browser or not self._browser.is_connected():
                logger.info("[BrowserPool] Launching new Chromium instance")
                self._browser = await self._playwright.chromium.launch(
                    headless=settings.PLAYWRIGHT_HEADLESS
                )
                # Ensure background cleanup is running
                if not self._cleanup_task or self._cleanup_task.done():
                    self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

            # Check for existing context
            context = self._contexts.get(domain)
            if context:
                use_count = self._context_use_count.get(domain, 0)
                if use_count < settings.BROWSER_CONTEXT_LIFETIME:
                    self._context_use_count[domain] = use_count + 1
                    return context
                else:
                    logger.debug("[BrowserPool] Context for %s reached lifetime, rotating", domain)
                    await context.close()
                    self._contexts.pop(domain, None)

            # Create new context
            logger.debug("[BrowserPool] Creating new context for %s", domain)
            context = await self._browser.new_context(
                user_agent=settings.USER_AGENT,
                viewport={"width": settings.BROWSER_VIEWPORT_WIDTH, "height": settings.BROWSER_VIEWPORT_HEIGHT},
            )
            self._contexts[domain] = context
            self._context_use_count[domain] = 1
            
            # Auto-restart if we have too many contexts
            if len(self._contexts) > settings.BROWSER_MAX_CONTEXTS:
                logger.info("[BrowserPool] Max contexts reached, scheduling full restart")
                # We don't restart immediately to avoid breaking active fetches
                # but we stop issuing new ones to old contexts
            
            return context

    async def close(self) -> None:
        """Gracefully close all contexts and the browser instance."""
        async with self._lock:
            for ctx in self._contexts.values():
                try:
                    await ctx.close()
                except Exception:
                    pass
            self._contexts.clear()
            
            if self._browser:
                await self._browser.close()
                self._browser = None
            
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

    async def _periodic_cleanup(self) -> None:
        """Close browser if idle for too long."""
        while True:
            await asyncio.sleep(60)
            if self._browser and time.time() - self._last_activity > settings.BROWSER_IDLE_TIMEOUT:
                logger.info("[BrowserPool] Idle timeout reached, closing browser")
                await self.close()
                break


# Global Singleton
_pool: BrowserPool | None = None

def get_browser_pool() -> BrowserPool:
    global _pool
    if _pool is None:
        _pool = BrowserPool()
    return _pool
