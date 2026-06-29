"""Browser Pool — Persistent Chromium management and context pooling.

LAW: Browser instances are heavy. Contexts are light.
Reuse browsers to minimize startup latency; rotate contexts to reduce fingerprint consistency.

Two acquisition patterns:
- ``get_context()`` — reusable, domain-keyed context (for scraping).
- ``acquire_context()`` — async context manager that yields an isolated,
  request-scoped context (for workflow replay, preview, etc.).  Each
  acquire creates a fresh browser context with clean cookies/storage but
  shares the underlying Chromium process.  Concurrent acquires are capped
  by ``settings.BROWSER_MAX_CONTEXTS`` (default 10).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from playwright.async_api import Browser, BrowserContext, Error, async_playwright

from app.config import settings
from app.utils.log_redaction import mask_proxy_url

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
        self._context_last_used: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._last_activity = time.time()
        self._cleanup_task: asyncio.Task | None = None

        # Process cap — at most BROWSER_MAX_PROCESSES Chromium instances
        # may be launched. Tracked atomically so concurrent callers
        # cannot race past the limit.
        self._process_count = 0
        self._process_lock = threading.Lock()

        # Hard recycling states
        self._active_fetches = 0
        self._cumulative_fetches = 0
        self._recycling = False
        self._recycle_event = asyncio.Event()
        self._recycle_event.set()
        self._background_tasks: set[asyncio.Task] = set()

        # Thread lock for synchronous callbacks (Playwright page events) that
        # need to update counters safely. asyncio.Lock cannot be used with
        # regular ``with`` — it requires ``async with``.
        self._counter_lock = threading.Lock()

        # ── Per-request isolated contexts ────────────────────────────────
        # Semaphore caps concurrent isolated context acquisitions.
        self._concurrency_semaphore = asyncio.Semaphore(settings.BROWSER_MAX_CONTEXTS)
        # Track isolated contexts separately so close() can clean them up.
        self._isolated_contexts: dict[str, BrowserContext] = {}
        self._active_acquires: int = 0

        # Metrics
        self.startup_latency_ms: float = 0.0
        self.active_contexts: int = 0
        self.context_reuse_rate: float = 0.0
        self.total_fetches: int = 0
        self.reused_fetches: int = 0
        self.crash_count: int = 0

    async def _ensure_browser_launched_locked(self) -> None:
        """Start Playwright + launch browser (caller must hold self._lock)."""
        if not self._playwright:
            start = time.time()
            self._playwright = await async_playwright().start()
            self.startup_latency_ms = (time.time() - start) * 1000

        if self._browser and self._browser.is_connected():
            return

        if not self._try_reserve_process_slot():
            msg = (
                f"[BrowserPool] Process cap reached "
                f"({settings.BROWSER_MAX_PROCESSES}). Refusing to launch a new Chromium process."
            )
            raise RuntimeError(msg)
        browser_args = []
        if settings.BROWSER_SECURITY_HARDENING:
            browser_args.extend(
                [
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--disable-gpu",
                    "--no-first-run",
                ],
            )
        try:
            self._browser = await self._playwright.chromium.launch(
                headless=settings.PLAYWRIGHT_HEADLESS,
                args=browser_args or None,
            )
        except (Error, OSError, RuntimeError):
            self.crash_count += 1
            logger.exception("[BrowserPool] Failed to launch browser")
            self._release_process_slot()
            try:
                from app.metrics_collector import record_browser_launch

                record_browser_launch(success=False)
            except (ImportError, RuntimeError, ValueError):
                logger.debug("[BrowserPool] Failed to record browser launch failure metric")
            raise
        try:
            from app.metrics_collector import record_browser_launch

            record_browser_launch(success=True)
        except (ImportError, RuntimeError, ValueError):
            logger.debug("[BrowserPool] Failed to record browser launch success metric")

        if not self._cleanup_task or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def _get_existing_context(self, context_key: str) -> BrowserContext | None:
        """Return a cached context if it hasn't exceeded its lifetime."""
        context = self._contexts.get(context_key)
        if context is None:
            return None
        use_count = self._context_use_count.get(context_key, 0)
        self._context_last_used[context_key] = time.time()
        if use_count < settings.BROWSER_CONTEXT_LIFETIME:
            self._context_use_count[context_key] = use_count + 1
            self.reused_fetches += 1
            self.context_reuse_rate = self.reused_fetches / self.total_fetches
            return context
        logger.debug("[BrowserPool] Context for %s reached lifetime, rotating", context_key)
        await context.close()
        self._contexts.pop(context_key, None)
        self._context_use_count.pop(context_key, None)
        self._context_last_used.pop(context_key, None)
        return None

    def _build_stealth_context_options(self, domain: str) -> dict[str, Any]:
        """Build context options from anti-bot stealth profile."""
        from app.anti_bot_engine import get_anti_bot_engine

        sp = get_anti_bot_engine().get_stealth_profile(domain)
        return {
            "user_agent": sp["user_agent"],
            "viewport": sp["viewport"],
            "device_scale_factor": sp["device_scale_factor"],
            "is_mobile": False,
            "has_touch": False,
            "locale": sp["locale"],
            "timezone_id": sp["timezone"],
        }

    def _build_default_context_options(self) -> dict[str, Any]:
        """Build context options from settings defaults."""
        return {
            "user_agent": settings.USER_AGENT,
            "viewport": {"width": settings.BROWSER_VIEWPORT_WIDTH, "height": settings.BROWSER_VIEWPORT_HEIGHT},
            "device_scale_factor": 1.0,
            "is_mobile": False,
            "has_touch": False,
            "locale": settings.STEALTH_DEFAULT_LOCALE,
            "timezone_id": settings.STEALTH_TIMEZONE_POOL.split(",")[0],
        }

    async def _create_browser_context(self, context_options: dict[str, Any]) -> BrowserContext:
        """Create a new browser context from options, recording metrics."""
        if self._browser is None:
            msg = "Browser not initialised before context creation"
            raise RuntimeError(msg)
        try:
            context = await self._browser.new_context(**context_options)
        except (Error, OSError, RuntimeError):
            try:
                from app.metrics_collector import record_browser_context_failed

                record_browser_context_failed()
            except (ImportError, RuntimeError, ValueError):
                logger.debug("[BrowserPool] Failed to record browser context failure metric")
            raise
        try:
            from app.metrics_collector import record_browser_context_created

            record_browser_context_created()
        except (ImportError, RuntimeError, ValueError):
            logger.debug("[BrowserPool] Failed to record browser context creation metric")
        return context

    async def _inject_persisted_cookies(self, context: BrowserContext, domain: str) -> None:
        """Inject anti-bot engine cookies into a Playwright context."""
        try:
            from app.anti_bot_engine import get_anti_bot_engine

            cookie_string = get_anti_bot_engine().get_cookies(domain)
            if cookie_string:
                parsed_cookies = _parse_cookie_string_for_playwright(cookie_string, domain)
                if parsed_cookies:
                    await context.add_cookies(parsed_cookies)  # type: ignore[arg-type]
                    logger.debug("[BrowserPool] Injected %d persisted cookies for %s", len(parsed_cookies), domain)
        except (ImportError, AttributeError, TypeError, RuntimeError, OSError):
            logger.debug("[BrowserPool] Failed to inject persisted cookies for %s", domain, exc_info=True)

    def _register_page_tracking(self, context: BrowserContext) -> None:
        """Register page creation/close event handlers for the context."""

        def on_page(page) -> None:
            with self._counter_lock:
                self._active_fetches += 1
                self._cumulative_fetches += 1

            def on_close(p) -> None:
                with self._counter_lock:
                    self._active_fetches = max(0, self._active_fetches - 1)
                if self._should_recycle():
                    task = asyncio.create_task(self._check_and_trigger_recycle())
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)

            page.on("close", on_close)

        context.on("page", on_page)

    async def _apply_stealth_evasion(self, context: BrowserContext, is_stealth: bool) -> None:
        """Inject stealth JS into the context to evade bot detection."""
        if not (settings.PLAYWRIGHT_STEALTH or is_stealth):
            return
        _nav_langs_raw = settings.STEALTH_NAVIGATOR_LANGUAGES.split(",")
        _nav_langs_js = "[" + ", ".join(f"'{lang.strip()}'" for lang in _nav_langs_raw) + "]"
        basic_js = f"""
        Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
        window.chrome = {{ runtime: {{}} }};
        (function() {{
            const pluginData = [
                {{name:'PDF Viewer',filename:'internal-pdf-viewer',description:'Portable Document Format'}},
                {{name:'Chrome PDF Viewer',filename:'internal-pdf-viewer',description:'Portable Document Format'}},
                {{name:'Chromium PDF Viewer',filename:'internal-pdf-viewer',description:'Portable Document Format'}},
                {{name:'Microsoft EDGE PDF Viewer',filename:'internal-pdf-viewer',description:'Portable Document Format'}},
                {{name:'WebKit built-in PDF',filename:'internal-pdf-viewer',description:'Portable Document Format'}},
            ];
            const pluginArray = [];
            pluginData.forEach(function(p) {{
                const plugin = {{name:p.name,filename:p.filename,description:p.description,length:1,
                    0:{{type:'application/pdf',suffixes:'pdf',description:p.description}}}};
                pluginArray.push(plugin);
            }});
            Object.defineProperty(pluginArray, 'length', {{get: () => pluginArray.length}});
            Object.defineProperty(navigator, 'plugins', {{get: () => pluginArray}});
        }})();
        Object.defineProperty(navigator, 'languages', {{get: () => {_nav_langs_js}}});
        """
        await context.add_init_script(basic_js)
        if not is_stealth:
            return

        import random

        _webgl_vendors = [
            ("Intel Open Source Technology Center", "Intel(R) HD Graphics 630"),
            ("Intel Open Source Technology Center", "Mesa DRI Intel(R) UHD Graphics 630"),
            ("NVIDIA Corporation", "GeForce GTX 1060/PCIe/SSE2"),
            ("NVIDIA Corporation", "GeForce GTX 1650/PCIe/SSE2"),
            ("NVIDIA Corporation", "GeForce RTX 3060/PCIe/SSE2"),
            ("AMD", "Radeon RX 580 Series"),
            ("AMD", "Radeon(TM) RX 470 Graphics"),
            ("Intel Open Source Technology Center", "Mesa Intel(R) UHD Graphics 770"),
        ]
        gl_vendor, gl_renderer = random.choice(_webgl_vendors)  # nosec B311 - fingerprint pool selection, not crypto
        hw_concurrency = settings.STEALTH_HARDWARE_CONCURRENCY
        advanced_js = f"""
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {{
            if (parameter === 37445) return '{gl_vendor.replace("'", "\\'")}';
            if (parameter === 37446) return '{gl_renderer.replace("'", "\\'")}';
            return getParameter.apply(this, arguments);
        }};
        if (typeof WebGL2RenderingContext !== 'undefined') {{
            const getParam2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(parameter) {{
                if (parameter === 37445) return '{gl_vendor.replace("'", "\\'")}';
                if (parameter === 37446) return '{gl_renderer.replace("'", "\\'")}';
                return getParam2.apply(this, arguments);
            }};
        }}
        Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {hw_concurrency}}});
        if (navigator.getBattery) {{
            navigator.getBattery = () => Promise.resolve({{charging:true,chargingTime:0,dischargingTime:Infinity,level:1}});
        }}
        """
        await context.add_init_script(advanced_js)

    async def _await_recycle_if_needed(self) -> None:
        """Check recycle condition and wait if recycling is in progress."""
        await self._recycle_event.wait()
        if self._should_recycle():
            task = asyncio.create_task(self._check_and_trigger_recycle())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            await self._recycle_event.wait()

    def _add_proxy_to_options(self, context_options: dict[str, Any], domain: str) -> None:
        """Add proxy configuration to context options if proxy rotation is enabled."""
        if not settings.PROXY_ROTATION_ENABLED:
            return
        from app.proxy_manager import get_proxy_manager

        proxy_mgr = get_proxy_manager()
        if not proxy_mgr.enabled:
            return
        proxy_config = proxy_mgr.get_proxy_for_playwright()
        if proxy_config:
            context_options["proxy"] = proxy_config
            logger.debug("[BrowserPool] Creating context for %s with proxy: %s", domain, mask_proxy_url(proxy_config["server"]))

    async def get_context(self, domain: str, strategy: FetchStrategy | None = None) -> BrowserContext:
        """Get or create a browser context for a specific domain."""
        from app.strategy_evolution import FetchStrategy

        await self._await_recycle_if_needed()
        async with self._lock:
            self._last_activity = time.time()
            self.total_fetches += 1
            await self._ensure_browser_launched_locked()

            context_key = f"{domain}:{strategy.value if strategy else 'default'}"
            cached = await self._get_existing_context(context_key)
            if cached is not None:
                return cached

            await self._evict_lru_if_needed()

            is_stealth = strategy == FetchStrategy.PLAYWRIGHT_STEALTH
            context_options = self._build_stealth_context_options(domain) if is_stealth else self._build_default_context_options()
            self._add_proxy_to_options(context_options, domain)

            context = await self._create_browser_context(context_options)

            await self._inject_persisted_cookies(context, domain)
            self._register_page_tracking(context)
            await self._apply_stealth_evasion(context, is_stealth)

            self._contexts[context_key] = context
            self._context_use_count[context_key] = 1
            self._context_last_used[context_key] = time.time()
            self.active_contexts = len(self._contexts)
            return context

    # ── Per-request isolated context acquisition ────────────────────────

    @asynccontextmanager
    async def acquire_context(
        self,
        *,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
        user_agent: str | None = None,
    ):
        """Acquire an isolated browser context via async context manager.

        Yields ``(context_id, context)``.  The context gets fresh
        cookies/storage per request (isolation) but shares the pool's
        Chromium process (reuse).  When the ``async with`` block exits
        the context is closed and the semaphore slot is released.

        The semaphore ensures at most ``BROWSER_MAX_CONTEXTS`` (default 10)
        concurrent isolated acquisitions.  Callers that exceed the cap
        will block until a slot opens up.

        If a hard recycle is in progress, the caller will wait for it to
        complete before acquiring — preventing isolated contexts from being
        created on a dying browser process.
        """
        # Wait for any in-progress recycle to complete before acquiring
        # a new isolated context.  Without this guard, a context could be
        # created on a browser process that's about to be torn down, leading
        # to orphaned contexts and potential crashes.
        await self._recycle_event.wait()

        await self._concurrency_semaphore.acquire()
        ctx_id = f"iso:{uuid.uuid4().hex[:12]}"
        try:
            ctx = await self._create_isolated_context(
                ctx_id,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                user_agent=user_agent,
            )
        except BaseException:
            self._concurrency_semaphore.release()
            raise
        # Safe within the single asyncio event loop: no two coroutines
        # execute this increment concurrently (asyncio is cooperative
        # and there is no ``await`` between read and write).
        self._active_acquires += 1
        self._last_activity = time.time()
        try:
            yield ctx_id, ctx
        finally:
            await self.release_context(ctx_id)

    async def release_context(self, ctx_id: str) -> None:
        """Close an isolated context and release its concurrency slot.

        Slot release (counter decrement + semaphore release) is always
        executed in a ``finally`` block so a ``ctx.close()`` failure cannot
        leak a slot. Unexpected close exception types are still propagated
        to the caller.
        """
        ctx = self._isolated_contexts.pop(ctx_id, None)
        # Wrap close + counter decrement + semaphore release all in
        # try/finally so that *any* unexpected ``ctx.close()`` failure
        # still releases the slot AND decrements the active acquire
        # counter. Single event loop, cooperative scheduling — the
        # read-modify-write sequence is race-free. ``max(0, ...)`` is a
        # defensive guard against any future edge case that might
        # double-decrement.
        try:
            if ctx:
                # Narrow suppress list preserves the historical contract
                # of propagating unexpected exception types. If a context
                # raises something exotic, the finally below still
                # releases the slot and decrements _active_acquires.
                with contextlib.suppress(Error, OSError, RuntimeError, ValueError, TypeError):
                    await ctx.close()
            self.active_contexts = len(self._contexts) + len(self._isolated_contexts)
        finally:
            # Always decrement the counter and release the semaphore,
            # even if ctx.close() raised. ``max(0, ...)`` defends against
            # any double-decrement edge case.
            self._active_acquires = max(0, self._active_acquires - 1)
            self._concurrency_semaphore.release()

    async def capture_screenshot(
        self,
        url: str,
        full_page: bool = False,
    ) -> str:
        import base64

        async with self.acquire_context() as (_ctx_id, context):
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                raw_bytes = await page.screenshot(full_page=full_page, type="jpeg", quality=60)
                return base64.b64encode(raw_bytes).decode("ascii")
            finally:
                await page.close()

    async def _create_isolated_context(
        self,
        ctx_id: str,
        *,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
        user_agent: str | None = None,
    ) -> BrowserContext:
        """Ensure the browser is running and create a fresh isolated context."""
        # Make sure the browser is up (reuse logic from get_context)
        await self._ensure_browser()

        opts: dict[str, Any] = {
            "user_agent": user_agent or settings.USER_AGENT,
            "viewport": {
                "width": viewport_width or settings.BROWSER_VIEWPORT_WIDTH,
                "height": viewport_height or settings.BROWSER_VIEWPORT_HEIGHT,
            },
            "is_mobile": False,
            "has_touch": False,
            "locale": settings.STEALTH_DEFAULT_LOCALE,
            "timezone_id": settings.STEALTH_TIMEZONE_POOL.split(",")[0],
        }

        if settings.PROXY_ROTATION_ENABLED:
            from app.proxy_manager import get_proxy_manager

            proxy_mgr = get_proxy_manager()
            if proxy_mgr.enabled:
                proxy_config = proxy_mgr.get_proxy_for_playwright()
                if proxy_config:
                    opts["proxy"] = proxy_config
                    logger.debug(
                        "[BrowserPool] Isolated context %s with proxy: %s",
                        ctx_id,
                        mask_proxy_url(proxy_config["server"]),
                    )

        if self._browser is None:
            msg = "_ensure_browser must have been called before _create_isolated_context"
            raise RuntimeError(msg)
        context = await self._browser.new_context(**opts)
        self._isolated_contexts[ctx_id] = context
        self.active_contexts = len(self._contexts) + len(self._isolated_contexts)
        logger.debug("[BrowserPool] Created isolated context %s (active=%d)", ctx_id, self._active_acquires)
        return context

    async def _evict_lru_if_needed(self) -> None:
        """Evict the least-recently-used reusable context when at capacity.

        Must be called under ``self._lock``. Raises only if the evicted
        context's ``close()`` itself raises after repeated retry; close
        errors are otherwise swallowed (best-effort cleanup, mirroring
        the rest of the pool's cleanup paths).
        """
        cap = settings.BROWSER_MAX_REUSABLE_CONTEXTS
        if cap < 1:
            return
        if len(self._contexts) < cap:
            return
        if not self._context_last_used:
            return
        # Get key with the oldest last-used timestamp
        lru_key = min(self._context_last_used, key=lambda k: self._context_last_used[k])  # type: ignore[arg-type,return-value]
        if lru_key not in self._contexts:
            self._context_last_used.pop(lru_key, None)
            return
        ctx = self._contexts.pop(lru_key)
        self._context_use_count.pop(lru_key, None)
        self._context_last_used.pop(lru_key, None)
        logger.info(
            "[BrowserPool] Reusable context cap reached (%d). Evicting LRU context %s",
            cap,
            lru_key,
        )
        # Best-effort cleanup: a dying context's close() may raise
        # Playwright/connection errors. Narrowly suppress only the
        # expected exception types so genuine bugs (KeyboardInterrupt,
        # MemoryError, asyncio.CancelledError propagating out) are not
        # hidden. Log at warning level so eviction-time failures are
        # visible — silent swallowed exceptions can mask browser-leak
        # pathologies during cap eviction.
        try:
            await ctx.close()
        except (Error, OSError, RuntimeError, ValueError, TypeError) as exc:
            logger.warning(
                "[BrowserPool] Swallowed close() exception while evicting LRU context %s: %s",
                lru_key,
                exc,
            )

    def _try_reserve_process_slot(self) -> bool:
        """Atomically reserve a process slot under ``_process_lock``.

        Returns True if a slot was acquired (caller may launch). The slot
        must be released via ``_release_process_slot`` once the browser
        exits.  Raises ``RuntimeError`` if cannot reserve (cap reached)
        """
        with self._process_lock:
            if self._process_count >= settings.BROWSER_MAX_PROCESSES:
                return False
            self._process_count += 1
            return True

    def _release_process_slot(self) -> None:
        """Release a previously reserved process slot."""
        with self._process_lock:
            if self._process_count > 0:
                self._process_count -= 1

    async def _ensure_browser(self) -> None:
        """Make sure playwright + browser are initialised (shared infra)."""
        async with self._lock:
            await self._ensure_browser_launched_locked()

    # ── Utility ────────────────────────────────────────────────────────

    def _get_random_ua(self) -> str:
        """Return a randomized browser user agent."""
        import random

        return random.choice(settings.STEALTH_UA_POOL.split(","))  # nosec B311

    async def check_health(self) -> bool:
        """Perform a basic health check on the browser instance."""
        if not self._browser or not self._browser.is_connected():
            return False

        try:
            # H4: wrap new_context + new_page in an outer try/finally so
            # ctx.close always runs even if new_page or page.close raises —
            # otherwise the BrowserContext leaks until pool shutdown.
            ctx = await self._browser.new_context()
            try:
                page = await ctx.new_page()
                await page.close()
                return True
            finally:
                with contextlib.suppress(Exception):
                    await ctx.close()
        except (Error, OSError, RuntimeError, ValueError) as e:
            logger.warning("[BrowserPool] Health check failed: %s", e)
            return False

    def get_metrics(self) -> dict[str, Any]:
        """Return browser pool operational metrics."""
        return {
            "startup_latency_ms": round(self.startup_latency_ms, 2),
            "active_contexts": self.active_contexts,
            "reusable_contexts": len(self._contexts),
            "isolated_contexts": len(self._isolated_contexts),
            "active_acquires": self._active_acquires,
            "context_reuse_rate": round(self.context_reuse_rate, 3),
            "total_fetches": self.total_fetches,
            "crash_count": self.crash_count,
            "connected": self._browser.is_connected() if self._browser else False,
        }

    async def close(self) -> None:
        """Gracefully close all contexts and the browser instance."""
        async with self._lock:
            # Close pool-managed (reusable) contexts
            for ctx in list(self._contexts.values()):
                try:
                    await ctx.close()
                except (Error, OSError, RuntimeError, ValueError, TypeError) as e:
                    logger.debug("[BrowserPool] Failed to close context during close(): %s", e)
            self._contexts.clear()
            self._context_use_count.clear()

            # Close isolated contexts
            for ctx in list(self._isolated_contexts.values()):
                try:
                    await ctx.close()
                except (Error, OSError, RuntimeError, ValueError, TypeError) as e:
                    logger.debug("[BrowserPool] Failed to close isolated context during close(): %s", e)
            self._isolated_contexts.clear()
            self._active_acquires = 0

            # Cancel any lingering background tasks to avoid RuntimeWarnings
            # about unawaited coroutines (AsyncMock in tests, or leaked tasks
            # in production).
            for task in list(self._background_tasks):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Error, OSError, RuntimeError, ValueError, TypeError):
                    await task
            self._background_tasks.clear()

            if self._browser:
                try:
                    await self._browser.close()
                except (Error, OSError, RuntimeError, ValueError, TypeError) as e:
                    logger.debug("[BrowserPool] Failed to close browser during close(): %s", e)
                self._browser = None
                # Return the process slot so the cap can be re-armed
                # after the next launch. If no slot had been reserved
                # (e.g. browser reference leaked without our tracking),
                # ``_release_process_slot`` is a no-op.
                self._release_process_slot()

            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Error, OSError, RuntimeError, ValueError, TypeError):
                    await self._cleanup_task
                self._cleanup_task = None

            if self._playwright:
                try:
                    await self._playwright.stop()
                except (Error, OSError, RuntimeError, ValueError, TypeError) as e:
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

        async with self._lock:
            if self._recycling:
                return
            self._recycling = True
            self._recycle_event.clear()

        while self._active_fetches > 0:
            logger.info("[BrowserPool] Waiting for %d active fetches to drain before recycling...", self._active_fetches)
            await asyncio.sleep(settings.BROWSER_DRAIN_POLL_INTERVAL)

        logger.info("[BrowserPool] Active fetches drained to 0. Performing hard browser process recycle.")
        try:
            await self._hard_recycle()
        except (Error, OSError, RuntimeError, ValueError, TypeError):
            logger.exception("[BrowserPool] Hard recycle failed")
        finally:
            async with self._lock:
                self._recycling = False
            self._recycle_event.set()

    async def _hard_recycle(self) -> None:
        # Close pooled contexts
        for ctx in list(self._contexts.values()):
            try:
                await ctx.close()
            except (Error, OSError, RuntimeError, ValueError, TypeError) as e:
                logger.debug("[BrowserPool] Failed to close context during hard recycle: %s", e)
        self._contexts.clear()
        self._context_use_count.clear()

        # Close isolated contexts (e.g. workflow replays, previews). These
        # were previously leaked during _hard_recycle, leaving orphaned
        # contexts on a dying browser process.
        #
        # Semaphore note: each acquire_context caller already holds a
        # semaphore slot and will release it in the `finally` block of
        # acquire_context's async context manager.  We must NOT release
        # the semaphore here — that would double-release, permanently
        # inflating the limit.  Instead, we just close the Playwright
        # contexts and clear the bookkeeping.  The pending
        # release_context calls in acquire_context's `finally` will
        # gracefully handle a context that's already been removed from
        # _isolated_contexts (pop returns None, semaphore.release is
        # safe even if redundant — asyncio.Semaphore tolerates release
        # beyond initial value).
        for ctx_id, ctx in list(self._isolated_contexts.items()):
            try:
                await ctx.close()
            except (Error, OSError, RuntimeError, ValueError, TypeError) as e:
                logger.debug(
                    "[BrowserPool] Failed to close isolated context %s during hard recycle: %s",
                    ctx_id,
                    e,
                )
        self._isolated_contexts.clear()
        self._active_acquires = 0

        if self._browser:
            try:
                await self._browser.close()
            except (Error, OSError, RuntimeError, ValueError, TypeError) as e:
                logger.debug("[BrowserPool] Failed to close browser during hard recycle: %s", e)
            self._browser = None
            # Return the process slot so the cap is reset for the next
            # launch. Mirrors the close() path.
            self._release_process_slot()

        if self._playwright:
            try:
                await self._playwright.stop()
            except (Error, OSError, RuntimeError, ValueError, TypeError) as e:
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
            except (Error, OSError, RuntimeError, ValueError) as e:
                # Don't let a transient cleanup failure (e.g. ``check_health``
                # raising) kill the watchdog loop — log and try again on the
                # next tick.
                logger.warning("[BrowserPool] Periodic cleanup raised: %s", e)


# Global Singleton
_pool: BrowserPool | None = None
_pool_lock = threading.Lock()


def get_browser_pool() -> BrowserPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = BrowserPool()
    return _pool


def reset_global_browser_pool() -> None:
    """Reset the global BrowserPool singleton.

    Test-only helper.  Drops the singleton reference without attempting
    graceful close (the pool's ``asyncio.Lock`` may already be bound to
    a dead event loop when this is called from conftest teardown).
    The underlying Playwright process is reclaimed by the OS on exit.

    Cancels the periodic cleanup task if it exists and is still pending,
    preventing ``Task was destroyed but it is pending!`` warnings when
    pytest-asyncio tears down the event loop between tests.

    Safely handles the case where the event loop is already closed
    by catching ``RuntimeError`` from ``task.cancel()``, which can
    happen when pytest-asyncio has already torn down the loop.
    """
    global _pool
    with _pool_lock:
        if _pool is not None:
            cleanup_task = _pool._cleanup_task
            if cleanup_task is not None and not cleanup_task.done():
                with contextlib.suppress(RuntimeError):
                    cleanup_task.cancel()
            # Cancel background tasks to avoid unawaited-coroutine warnings
            for task in list(_pool._background_tasks):
                with contextlib.suppress(RuntimeError):
                    task.cancel()
            _pool._background_tasks.clear()
        _pool = None


# ── Cookie Parsing ──────────────────────────────────────────────────────


def _parse_cookie_string_for_playwright(
    cookie_string: str,
    domain: str,
) -> list[dict[str, Any]]:
    """Parse a raw ``Set-Cookie``-style header into Playwright cookie dicts.

    Handles the format stored by ``AntiBotEngine`` (exampleInput format:
    ``"key1=val1; key2=val2"``).  Each cookie is mapped to Playwright's
    ``add_cookies()`` schema:
      - name, value, domain, path
      - secure: True if the domain starts with ``https://``
      - sameSite: ``"Lax"`` (sensible default)
      - httpOnly / expires are omitted (not parseable from flat strings)

    Robust against malformed input — bad entries are skipped rather than
    causing the whole injection to fail.
    """
    if not cookie_string or not cookie_string.strip():
        return []

    cookies: list[dict[str, Any]] = []
    # Strip leading "Cookie:" prefix if present (some storage formats
    # include it, some don't)
    raw = cookie_string.strip()
    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].strip()

    for pair in raw.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": "/",
                "secure": domain.startswith("localhost") is False,
                "sameSite": "Lax",
            }
        )

    return cookies
