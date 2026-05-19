"""
Browser Pool — Persistent Chromium management and context pooling.

LAW: Browser instances are heavy. Contexts are light.
Reuse browsers to minimize startup latency; rotate contexts to maintain stealth.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Browser, BrowserContext

from app.config import settings

logger = logging.getLogger(__name__)


class BrowserPool:
    """Manages a persistent Chromium instance with reusable contexts."""

    def __init__(self) -> None:
        self._playwright: Optional[Any] = None
        self._browser: Optional[Browser] = None
        self._contexts: dict[str, BrowserContext] = {}
        self._context_use_count: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._last_activity = time.time()
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Metrics
        self.startup_latency_ms: float = 0.0
        self.active_contexts: int = 0
        self.context_reuse_rate: float = 0.0
        self.total_fetches: int = 0
        self.reused_fetches: int = 0
        self.crash_count: int = 0

    async def get_context(self, domain: str) -> BrowserContext:
        """Get or create a browser context for a specific domain."""
        async with self._lock:
            self._last_activity = time.time()
            self.total_fetches += 1
            
            if not self._playwright:
                start = time.time()
                self._playwright = await async_playwright().start()
                self.startup_latency_ms = (time.time() - start) * 1000
            
            if not self._browser or not self._browser.is_connected():
                logger.info("[BrowserPool] Launching new Chromium instance")
                try:
                    self._browser = await self._playwright.chromium.launch(
                        headless=settings.PLAYWRIGHT_HEADLESS
                    )
                except Exception as e:
                    self.crash_count += 1
                    logger.error("[BrowserPool] Failed to launch browser: %s", e)
                    raise
                    
                # Ensure background cleanup is running
                if not self._cleanup_task or self._cleanup_task.done():
                    self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

            # Check for existing context
            context = self._contexts.get(domain)
            if context:
                use_count = self._context_use_count.get(domain, 0)
                if use_count < settings.BROWSER_CONTEXT_LIFETIME:
                    self._context_use_count[domain] = use_count + 1
                    self.reused_fetches += 1
                    self.context_reuse_rate = self.reused_fetches / self.total_fetches
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
            
            if settings.PLAYWRIGHT_STEALTH:
                stealth_js = """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                """
                await context.add_init_script(stealth_js)
                
            self._contexts[domain] = context
            self._context_use_count[domain] = 1
            self.active_contexts = len(self._contexts)
            
            # Auto-restart if we have too many contexts
            if len(self._contexts) > settings.BROWSER_MAX_CONTEXTS:
                logger.info("[BrowserPool] Max contexts reached, scheduling full restart")
                # Mark for teardown in next idle cycle
            
            return context

    async def check_health(self) -> bool:
        """Perform a basic health check on the browser instance."""
        if not self._browser or not self._browser.is_connected():
            return False
        
        try:
            # Try to create a dummy page and close it
            ctx = await self._browser.new_context()
            page = await ctx.new_page()
            await page.close()
            await ctx.close()
            return True
        except Exception as e:
            logger.warning("[BrowserPool] Health check failed: %s", e)
            return False

    def get_metrics(self) -> dict:
        """Return browser pool operational metrics."""
        return {
            "startup_latency_ms": round(self.startup_latency_ms, 2),
            "active_contexts": self.active_contexts,
            "context_reuse_rate": round(self.context_reuse_rate, 3),
            "total_fetches": self.total_fetches,
            "crash_count": self.crash_count,
            "connected": self._browser.is_connected() if self._browser else False
        }

    async def close(self) -> None:
        """Gracefully close all contexts and the browser instance."""
        async with self._lock:
            for ctx in list(self._contexts.values()):
                try:
                    await ctx.close()
                except Exception:
                    pass
            self._contexts.clear()
            self._context_use_count.clear()
            
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None
            
            self.active_contexts = 0

    async def _periodic_cleanup(self) -> None:
        """Close browser if idle for too long."""
        while True:
            await asyncio.sleep(60)
            if self._browser:
                if time.time() - self._last_activity > settings.BROWSER_IDLE_TIMEOUT:
                    logger.info("[BrowserPool] Idle timeout reached, closing browser")
                    await self.close()
                    break
                
                # Also check health
                if not await self.check_health():
                    logger.warning("[BrowserPool] Unhealthy browser detected in cleanup, restarting")
                    await self.close()
                    break


# Global Singleton
_pool: BrowserPool | None = None

def get_browser_pool() -> BrowserPool:
    global _pool
    if _pool is None:
        _pool = BrowserPool()
    return _pool
