"""Browser Pool — Persistent Chromium management and context pooling.

LAW: Browser instances are heavy. Contexts are light.
Reuse browsers to minimize startup latency; rotate contexts to maintain stealth.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

from playwright.async_api import Browser, BrowserContext, async_playwright

from app.config import settings

if TYPE_CHECKING:
    from app.strategy_evolution import FetchStrategy

logger = logging.getLogger(__name__)


class BrowserPool:
    """Manages a persistent Chromium instance with reusable contexts."""

    def __init__(self) -> None:
        self._playwright: Any | None = None
        self._browser: Browser | None = None
        self._contexts: dict[str, BrowserContext] = {}
        self._context_use_count: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._last_activity = time.time()
        self._cleanup_task: asyncio.Task | None = None

        # Hard recycling states
        self._active_fetches = 0
        self._cumulative_fetches = 0
        self._recycling = False
        self._recycle_event = asyncio.Event()
        self._recycle_event.set()
        self._background_tasks: set[asyncio.Task] = set()

        # Metrics
        self.startup_latency_ms: float = 0.0
        self.active_contexts: int = 0
        self.context_reuse_rate: float = 0.0
        self.total_fetches: int = 0
        self.reused_fetches: int = 0
        self.crash_count: int = 0

    async def get_context(self, domain: str, strategy: FetchStrategy | None = None) -> BrowserContext:
        """Get or create a browser context for a specific domain."""
        await self._recycle_event.wait()

        # Check if we should recycle before proceeding
        if self._should_recycle():
            task = asyncio.create_task(self._check_and_trigger_recycle())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            await self._recycle_event.wait()

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
                    self._browser = await self._playwright.chromium.launch(headless=settings.PLAYWRIGHT_HEADLESS)
                except Exception:
                    self.crash_count += 1
                    logger.exception("[BrowserPool] Failed to launch browser")
                    try:
                        from app.metrics_collector import record_browser_launch

                        record_browser_launch(success=False)
                    except Exception:
                        logger.debug("[BrowserPool] Failed to record browser launch failure metric")
                    raise
                try:
                    from app.metrics_collector import record_browser_launch

                    record_browser_launch(success=True)
                except Exception:
                    logger.debug("[BrowserPool] Failed to record browser launch success metric")

                # Ensure background cleanup is running
                if not self._cleanup_task or self._cleanup_task.done():
                    self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

            # Check for existing context
            # We key by (domain, strategy) to allow different strategies for
            # same domain
            context_key = f"{domain}:{strategy.value if strategy else 'default'}"
            context = self._contexts.get(context_key)
            if context:
                use_count = self._context_use_count.get(context_key, 0)
                if use_count < settings.BROWSER_CONTEXT_LIFETIME:
                    self._context_use_count[context_key] = use_count + 1
                    self.reused_fetches += 1
                    self.context_reuse_rate = self.reused_fetches / self.total_fetches
                    return context
                logger.debug("[BrowserPool] Context for %s reached lifetime, rotating", context_key)
                await context.close()
                self._contexts.pop(context_key, None)

            # Create new context with optional proxy configuration
            from app.strategy_evolution import FetchStrategy

            is_stealth = strategy == FetchStrategy.PLAYWRIGHT_STEALTH

            # Use AntiBotEngine's stealth profile for enhanced fingerprint
            # randomization
            context_options: dict[str, Any]
            if is_stealth:
                from app.anti_bot_engine import get_anti_bot_engine

                stealth_profile = get_anti_bot_engine().get_stealth_profile(domain)
                context_options = {
                    "user_agent": stealth_profile["user_agent"],
                    "viewport": stealth_profile["viewport"],
                    "device_scale_factor": stealth_profile["device_scale_factor"],
                    "is_mobile": False,
                    "has_touch": False,
                    "locale": stealth_profile["locale"],
                    "timezone_id": stealth_profile["timezone"],
                }
            else:
                context_options = {
                    "user_agent": settings.USER_AGENT,
                    "viewport": {"width": settings.BROWSER_VIEWPORT_WIDTH, "height": settings.BROWSER_VIEWPORT_HEIGHT},
                    "device_scale_factor": 1.0 if not is_stealth else 2.0,
                    "is_mobile": False,
                    "has_touch": False,
                    "locale": settings.STEALTH_DEFAULT_LOCALE,
                    "timezone_id": settings.STEALTH_TIMEZONE_POOL.split(",")[0],
                }

            # Add proxy if enabled
            if settings.PROXY_ROTATION_ENABLED:
                from app.proxy_manager import get_proxy_manager

                proxy_mgr = get_proxy_manager()
                if proxy_mgr.enabled:
                    proxy_config = proxy_mgr.get_proxy_for_playwright()
                    if proxy_config:
                        context_options["proxy"] = proxy_config
                        logger.debug("[BrowserPool] Creating context for %s with proxy: %s", domain, proxy_config["server"])

            context = await self._browser.new_context(**context_options)

            # Register page tracking
            def register_page_tracking(ctx) -> None:
                def on_page(page) -> None:
                    self._active_fetches += 1
                    self._cumulative_fetches += 1
                    logger.debug(
                        "[BrowserPool] Page created. Active: %d, Cumulative: %d",
                        self._active_fetches,
                        self._cumulative_fetches,
                    )

                    def on_close(p) -> None:  # noqa: ARG001, RUF100
                        self._active_fetches = max(0, self._active_fetches - 1)
                        logger.debug("[BrowserPool] Page closed. Active: %d", self._active_fetches)
                        # Only schedule a recycle check if recycling might be
                        # needed — this avoids creating asyncio tasks (and
                        # unawaited-coroutine warnings in tests) when the
                        # pool is far from any recycling threshold.
                        if self._should_recycle():
                            task = asyncio.create_task(self._check_and_trigger_recycle())
                            self._background_tasks.add(task)
                            task.add_done_callback(self._background_tasks.discard)

                    page.on("close", on_close)

                ctx.on("page", on_page)

            register_page_tracking(context)

            # Phase 80: Advanced Stealth Evasion
            if settings.PLAYWRIGHT_STEALTH or is_stealth:
                # Basic stealth
                _nav_langs_raw = settings.STEALTH_NAVIGATOR_LANGUAGES.split(",")
                _nav_langs_js = "[" + ", ".join(f"'{lang.strip()}'" for lang in _nav_langs_raw) + "]"
                stealth_js = f"""
                Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
                window.chrome = {{ runtime: {{}} }};
                Object.defineProperty(navigator, 'plugins', {{get: () => [1, 2, 3, 4, 5]}});
                Object.defineProperty(navigator, 'languages', {{get: () => {_nav_langs_js}}});
                """
                await context.add_init_script(stealth_js)

                if is_stealth:
                    # Advanced fingerprint randomization
                    hw_concurrency = settings.STEALTH_HARDWARE_CONCURRENCY
                    advanced_stealth = f"""
                    // WebGL spoofing
                    const getParameter = WebGLRenderingContext.prototype.getParameter;
                    WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                        if (parameter === 37445) return 'Intel Open Source Technology Center';
                        if (parameter === 37446) return 'Mesa DRI Intel(R) Ivybridge Mobile ';
                        return getParameter.apply(this, arguments);
                    }};

                    // Hardware concurrency randomization
                    Object.defineProperty(navigator, 'hardwareConcurrency', {{
                        get: () => {hw_concurrency}
                    }});

                    // Battery status spoofing
                    if (navigator.getBattery) {{
                        navigator.getBattery = () => Promise.resolve({{
                            charging: true,
                            chargingTime: 0,
                            dischargingTime: Infinity,
                            level: 1
                        }});
                    }}
                    """
                    await context.add_init_script(advanced_stealth)

            self._contexts[context_key] = context
            self._context_use_count[context_key] = 1
            self.active_contexts = len(self._contexts)

            return context

    def _get_random_ua(self) -> str:
        """Return a randomized browser user agent."""
        import random

        return random.choice(settings.STEALTH_UA_POOL.split(","))  # nosec B311  # noqa: S311

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
            return True  # noqa: TRY300
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
            "connected": self._browser.is_connected() if self._browser else False,
        }

    async def close(self) -> None:
        """Gracefully close all contexts and the browser instance."""
        async with self._lock:
            for ctx in list(self._contexts.values()):
                try:
                    await ctx.close()
                except Exception as e:
                    logger.debug("[BrowserPool] Failed to close context during close(): %s", e)
            self._contexts.clear()
            self._context_use_count.clear()

            # Cancel any lingering background tasks to avoid RuntimeWarnings
            # about unawaited coroutines (AsyncMock in tests, or leaked tasks
            # in production).
            for task in list(self._background_tasks):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            self._background_tasks.clear()

            if self._browser:
                try:
                    await self._browser.close()
                except Exception as e:
                    logger.debug("[BrowserPool] Failed to close browser during close(): %s", e)
                self._browser = None

            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._cleanup_task
                self._cleanup_task = None

            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception as e:
                    logger.debug("[BrowserPool] Failed to stop playwright during close(): %s", e)
                self._playwright = None

            self.active_contexts = 0
            self._active_fetches = 0
            self._cumulative_fetches = 0

    def _get_rss_memory(self) -> int:
        import resource

        try:
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        except (AttributeError, OSError, ValueError):
            logger.debug("[BrowserPool] Failed to get RSS memory")
            return 0

    def _should_recycle(self) -> bool:
        if self._cumulative_fetches >= settings.BROWSER_MAX_CUMULATIVE_FETCHES:
            logger.info("[BrowserPool] Cumulative fetches (%d) reached limit. Recycling required.", self._cumulative_fetches)
            return True
        rss = self._get_rss_memory()
        if rss > settings.BROWSER_MAX_RSS_MEMORY_MB * 1024 * 1024:
            logger.info("[BrowserPool] Process RSS memory (%.2f MB) exceeded limit. Recycling required.", rss / (1024 * 1024))
            return True
        return False

    async def _check_and_trigger_recycle(self) -> None:
        if not self._should_recycle() or self._recycling:
            return

        self._recycling = True
        self._recycle_event.clear()

        while self._active_fetches > 0:
            logger.info("[BrowserPool] Waiting for %d active fetches to drain before recycling...", self._active_fetches)
            await asyncio.sleep(settings.BROWSER_DRAIN_POLL_INTERVAL)

        logger.info("[BrowserPool] Active fetches drained to 0. Performing hard browser process recycle.")
        try:
            await self._hard_recycle()
        except Exception:
            logger.exception("[BrowserPool] Hard recycle failed")
        finally:
            self._recycling = False
            self._recycle_event.set()

    async def _hard_recycle(self) -> None:
        for ctx in list(self._contexts.values()):
            try:
                await ctx.close()
            except Exception as e:
                logger.debug("[BrowserPool] Failed to close context during hard recycle: %s", e)
        self._contexts.clear()
        self._context_use_count.clear()

        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.debug("[BrowserPool] Failed to close browser during hard recycle: %s", e)
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug("[BrowserPool] Failed to stop playwright during hard recycle: %s", e)
            self._playwright = None

        self.active_contexts = 0
        self._active_fetches = 0
        self._cumulative_fetches = 0
        logger.info("[BrowserPool] Hard recycle completed successfully.")

    async def _periodic_cleanup(self) -> None:
        """Close browser if idle for too long."""
        while True:
            await asyncio.sleep(settings.BROWSER_CLEANUP_INTERVAL)
            try:
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
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Don't let a transient cleanup failure (e.g. ``check_health``
                # raising) kill the watchdog loop — log and try again on the
                # next tick.
                logger.warning("[BrowserPool] Periodic cleanup raised: %s", e)


# Global Singleton
_pool: BrowserPool | None = None
_pool_lock = __import__("threading").Lock()


def get_browser_pool() -> BrowserPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = BrowserPool()
    return _pool
