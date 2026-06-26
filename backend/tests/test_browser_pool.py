"""Unit tests for browser_pool — BrowserPool lifecycle, metrics, and context management."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.browser_pool import BrowserPool, get_browser_pool
from playwright.async_api import Error


def _sync_mock_context() -> MagicMock:
    """Create a context mock where sync methods don't return unawaited coroutines.

    ``AsyncMock`` auto-mocks every attribute access, so ``ctx.on(…)" creates a
    coroutine that is never awaited — producing a ``RuntimeWarning``. This helper
    explicitly marks sync Playwright methods as ``MagicMock`` so the event loop
    stays quiet.
    """
    ctx = AsyncMock()
    ctx.on = MagicMock()
    ctx.new_page = AsyncMock()
    return ctx


def _sync_browser_mock(is_connected: bool = True) -> MagicMock:
    """Create a browser mock where ``is_connected`` is a sync method.

    ``AsyncMock`` would make ``is_connected()`` return an unawaited coroutine.
    Production ``Browser.is_connected`` is a sync property, so we use a
    ``MagicMock`` for the browser and only keep ``new_context`` as async.
    """
    b = MagicMock()
    b.is_connected = MagicMock(return_value=is_connected)
    b.new_context = AsyncMock()
    b.close = AsyncMock()
    return b


# ═══════════════════════════════════════════════════════════════════════════════
# Initialization & Basic Properties
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrowserPoolInit:
    def test_initial_state(self) -> None:
        pool = BrowserPool()
        assert pool._browser is None
        assert pool._playwright is None
        assert pool._contexts == {}
        assert pool._context_use_count == {}
        assert pool._active_fetches == 0
        assert pool._cumulative_fetches == 0
        assert pool._recycling is False
        assert pool._cleanup_task is None
        assert pool.total_fetches == 0
        assert pool.reused_fetches == 0
        assert pool.crash_count == 0
        assert pool.active_contexts == 0
        assert pool.context_reuse_rate == 0.0
        assert pool.startup_latency_ms == 0.0
        assert pool._isolated_contexts == {}
        assert pool._active_acquires == 0

    def test_initially_recycle_event_set(self) -> None:
        pool = BrowserPool()
        assert pool._recycle_event.is_set()


# ═══════════════════════════════════════════════════════════════════════════════
# Metrics
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetMetrics:
    def test_returns_default_values_before_any_activity(self) -> None:
        pool = BrowserPool()
        metrics = pool.get_metrics()
        assert metrics["startup_latency_ms"] == 0.0
        assert metrics["active_contexts"] == 0
        assert metrics["context_reuse_rate"] == 0.0
        assert metrics["total_fetches"] == 0
        assert metrics["crash_count"] == 0
        assert metrics["connected"] is False
        assert metrics["reusable_contexts"] == 0
        assert metrics["isolated_contexts"] == 0
        assert metrics["active_acquires"] == 0

    def test_reflects_activity(self) -> None:
        pool = BrowserPool()
        pool.startup_latency_ms = 150.5
        pool.active_contexts = 3
        pool.context_reuse_rate = 0.75
        pool.total_fetches = 10
        pool.crash_count = 1
        metrics = pool.get_metrics()
        assert metrics["startup_latency_ms"] == 150.5
        assert metrics["active_contexts"] == 3
        assert metrics["context_reuse_rate"] == 0.75
        assert metrics["total_fetches"] == 10
        assert metrics["crash_count"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Random User Agent
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetRandomUa:
    def test_returns_a_string(self) -> None:
        pool = BrowserPool()
        ua = pool._get_random_ua()
        assert isinstance(ua, str)
        assert len(ua) > 0

    @patch("app.browser_pool.settings.STEALTH_UA_POOL", "Mozilla/1,Mozilla/2,Mozilla/3")
    def test_returns_one_of_pool_values(self) -> None:
        pool = BrowserPool()
        ua = pool._get_random_ua()
        assert ua in ("Mozilla/1", "Mozilla/2", "Mozilla/3")


# ═══════════════════════════════════════════════════════════════════════════════
# Should Recycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestShouldRecycle:
    def test_returns_false_when_below_threshold(self) -> None:
        pool = BrowserPool()
        pool._cumulative_fetches = 50
        with (
            patch.object(pool, "_get_rss_memory", return_value=10),
            patch("app.browser_pool.settings.BROWSER_MAX_CUMULATIVE_FETCHES", 100),
            patch("app.browser_pool.settings.BROWSER_MAX_RSS_MEMORY_MB", 1000),
        ):
            assert pool._should_recycle() is False

    @patch("app.browser_pool.settings.BROWSER_MAX_CUMULATIVE_FETCHES", 100)
    def test_returns_true_when_at_threshold(self) -> None:
        pool = BrowserPool()
        pool._cumulative_fetches = 100
        assert pool._should_recycle() is True

    @patch("app.browser_pool.settings.BROWSER_MAX_CUMULATIVE_FETCHES", 100)
    def test_returns_true_when_exceeds_threshold(self) -> None:
        pool = BrowserPool()
        pool._cumulative_fetches = 150
        assert pool._should_recycle() is True

    @patch("app.browser_pool.settings.BROWSER_MAX_RSS_MEMORY_MB", 1)
    def test_returns_true_when_rss_exceeds_limit(self) -> None:
        pool = BrowserPool()
        # Mock _get_rss_memory to return a value above the 1 MB limit
        with patch.object(pool, "_get_rss_memory", return_value=2 * 1024 * 1024):
            assert pool._should_recycle() is True


# ═══════════════════════════════════════════════════════════════════════════════
# Close (when no browser is active)
# ═══════════════════════════════════════════════════════════════════════════════


class TestClose:
    @pytest.mark.asyncio
    async def test_close_when_browser_is_none_does_not_raise(self) -> None:
        pool = BrowserPool()
        await pool.close()
        assert pool._browser is None
        assert pool._playwright is None
        assert pool._contexts == {}

    @pytest.mark.asyncio
    async def test_close_clears_metrics(self) -> None:
        pool = BrowserPool()
        pool.active_contexts = 5
        pool._active_fetches = 3
        pool._cumulative_fetches = 10
        await pool.close()
        assert pool.active_contexts == 0
        assert pool._active_fetches == 0
        assert pool._cumulative_fetches == 0

    @pytest.mark.asyncio
    async def test_close_with_contexts_closes_them(self) -> None:
        pool = BrowserPool()
        mock_ctx = _sync_mock_context()
        pool._contexts["test"] = mock_ctx
        pool._context_use_count["test"] = 5
        await pool.close()
        mock_ctx.close.assert_awaited_once()
        assert pool._contexts == {}

    @pytest.mark.asyncio
    async def test_close_with_browser_closes_it(self) -> None:
        pool = BrowserPool()
        mock_browser = AsyncMock()
        mock_browser.is_connected.return_value = True
        pool._browser = mock_browser
        pool._playwright = MagicMock()
        await pool.close()
        mock_browser.close.assert_awaited_once()
        assert pool._browser is None


# ═══════════════════════════════════════════════════════════════════════════════
# Get Context (with mocked Playwright)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetContext:
    @pytest.mark.asyncio
    async def test_launches_playwright_and_browser(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=True)
        mock_context = _sync_mock_context()
        mock_browser.new_context.return_value = mock_context

        with (
            patch("app.browser_pool.async_playwright") as mock_async_pw,
            patch("app.browser_pool.settings.PLAYWRIGHT_HEADLESS", True),
            patch("app.browser_pool.settings.USER_AGENT", "TestUA"),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_WIDTH", 1920),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_HEIGHT", 1080),
            patch("app.browser_pool.settings.STEALTH_DEFAULT_LOCALE", "en-US"),
            patch("app.browser_pool.settings.STEALTH_TIMEZONE_POOL", "America/New_York"),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
            patch("app.browser_pool.settings.PLAYWRIGHT_STEALTH", False),
            patch("app.browser_pool.settings.BROWSER_CONTEXT_LIFETIME", 50),
        ):
            mock_pw = AsyncMock()
            mock_pw.chromium.launch.return_value = mock_browser
            # async_playwright() returns a manager whose .start() is awaitable
            mock_pw_manager = MagicMock()
            mock_pw_manager.start = AsyncMock(return_value=mock_pw)
            mock_async_pw.return_value = mock_pw_manager

            from app.strategy_evolution import FetchStrategy

            context = await pool.get_context("example.com", FetchStrategy.PLAYWRIGHT_FULL)

        assert context is mock_context
        assert pool._browser is mock_browser
        assert pool._playwright is mock_pw
        assert pool.total_fetches == 1
        assert pool.active_contexts == 1

    @pytest.mark.asyncio
    async def test_reuses_existing_browser(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=True)
        mock_context = _sync_mock_context()
        mock_browser.new_context.return_value = mock_context
        pool._browser = mock_browser
        pool._playwright = MagicMock()

        with (
            patch("app.browser_pool.async_playwright") as mock_async_pw,
            patch("app.browser_pool.settings.PLAYWRIGHT_HEADLESS", True),
            patch("app.browser_pool.settings.USER_AGENT", "TestUA"),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_WIDTH", 1920),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_HEIGHT", 1080),
            patch("app.browser_pool.settings.STEALTH_DEFAULT_LOCALE", "en-US"),
            patch("app.browser_pool.settings.STEALTH_TIMEZONE_POOL", "America/New_York"),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
            patch("app.browser_pool.settings.PLAYWRIGHT_STEALTH", False),
            patch("app.browser_pool.settings.BROWSER_CONTEXT_LIFETIME", 50),
        ):
            from app.strategy_evolution import FetchStrategy

            context = await pool.get_context("example.com", FetchStrategy.PLAYWRIGHT_FULL)

        assert context is mock_context
        mock_async_pw.return_value.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_reuses_existing_context_within_lifetime(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=True)
        mock_context = _sync_mock_context()
        pool._browser = mock_browser
        pool._playwright = MagicMock()
        pool._contexts["example.com:playwright_full"] = mock_context
        pool._context_use_count["example.com:playwright_full"] = 1

        with (
            patch("app.browser_pool.settings.BROWSER_CONTEXT_LIFETIME", 50),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
            patch("app.browser_pool.settings.PLAYWRIGHT_STEALTH", False),
        ):
            from app.strategy_evolution import FetchStrategy

            context = await pool.get_context("example.com", FetchStrategy.PLAYWRIGHT_FULL)

        assert context is mock_context
        assert pool._context_use_count["example.com:playwright_full"] == 2
        assert pool.reused_fetches == 1

    @pytest.mark.asyncio
    async def test_rotates_context_when_lifetime_exceeded(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=True)
        old_context = _sync_mock_context()
        new_context = _sync_mock_context()
        mock_browser.new_context.return_value = new_context
        pool._browser = mock_browser
        pool._playwright = MagicMock()
        pool._contexts["example.com:playwright_full"] = old_context
        pool._context_use_count["example.com:playwright_full"] = 50  # At lifetime limit

        with (
            patch("app.browser_pool.settings.BROWSER_CONTEXT_LIFETIME", 50),
            patch("app.browser_pool.settings.USER_AGENT", "TestUA"),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_WIDTH", 1920),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_HEIGHT", 1080),
            patch("app.browser_pool.settings.STEALTH_DEFAULT_LOCALE", "en-US"),
            patch("app.browser_pool.settings.STEALTH_TIMEZONE_POOL", "America/New_York"),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
            patch("app.browser_pool.settings.PLAYWRIGHT_STEALTH", False),
        ):
            from app.strategy_evolution import FetchStrategy

            context = await pool.get_context("example.com", FetchStrategy.PLAYWRIGHT_FULL)

        assert context is new_context
        old_context.close.assert_awaited_once()
        assert "example.com:playwright_full" in pool._contexts

    @pytest.mark.asyncio
    async def test_increments_crash_count_on_launch_failure(self) -> None:
        pool = BrowserPool()
        with (
            patch("app.browser_pool.async_playwright") as mock_async_pw,
            patch("app.browser_pool.settings.PLAYWRIGHT_HEADLESS", True),
        ):
            mock_pw = AsyncMock()
            mock_pw.chromium.launch.side_effect = Error("Launch failed")
            # async_playwright() returns a manager whose .start() is awaitable
            mock_pw_manager = MagicMock()
            mock_pw_manager.start = AsyncMock(return_value=mock_pw)
            mock_async_pw.return_value = mock_pw_manager

            from app.strategy_evolution import FetchStrategy

            with pytest.raises(Exception, match="Launch failed"):
                await pool.get_context("example.com", FetchStrategy.PLAYWRIGHT_FULL)

            assert pool.crash_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Check Health
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckHealth:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_browser(self) -> None:
        pool = BrowserPool()
        assert await pool.check_health() is False

    @pytest.mark.asyncio
    async def test_returns_true_when_browser_healthy(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=True)
        mock_ctx = _sync_mock_context()
        mock_page = AsyncMock()
        mock_browser.new_context.return_value = mock_ctx
        mock_ctx.new_page.return_value = mock_page
        pool._browser = mock_browser

        result = await pool.check_health()
        assert result is True
        mock_page.close.assert_awaited_once()
        mock_ctx.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_browser_disconnected(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=False)
        pool._browser = mock_browser

        result = await pool.check_health()
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_health_check_raises(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=True)
        mock_browser.new_context.side_effect = Error("Connection error")
        pool._browser = mock_browser

        result = await pool.check_health()
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# Hard Recycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestHardRecycle:
    @pytest.mark.asyncio
    async def test_clears_all_contexts_and_browser(self) -> None:
        pool = BrowserPool()
        pool._contexts["test"] = _sync_mock_context()
        pool._context_use_count["test"] = 5
        pool._browser = _sync_browser_mock(is_connected=True)
        pool._playwright = MagicMock()
        pool.active_contexts = 3
        pool._active_fetches = 2
        pool._cumulative_fetches = 10

        await pool._hard_recycle()

        assert pool._contexts == {}
        assert pool._context_use_count == {}
        assert pool._browser is None
        assert pool._playwright is None
        assert pool.active_contexts == 0
        assert pool._active_fetches == 0
        assert pool._cumulative_fetches == 0

    @pytest.mark.asyncio
    async def test_handles_close_exceptions_gracefully(self) -> None:
        pool = BrowserPool()
        failing_ctx = _sync_mock_context()
        failing_ctx.close.side_effect = Error("Close failed")
        pool._contexts["test"] = failing_ctx
        pool._browser = _sync_browser_mock(is_connected=True)
        pool._playwright = MagicMock()

        await pool._hard_recycle()  # Should not raise
        assert pool._contexts == {}

    @pytest.mark.asyncio
    async def test_handles_none_browser(self) -> None:
        pool = BrowserPool()
        await pool._hard_recycle()  # Should not raise
        assert pool._contexts == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Stealth Strategy Context
# ═══════════════════════════════════════════════════════════════════════════════


class TestStealthContext:
    @pytest.mark.asyncio
    async def test_creates_context_with_stealth_profile(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=True)
        mock_context = _sync_mock_context()
        mock_browser.new_context.return_value = mock_context
        pool._browser = mock_browser
        pool._playwright = MagicMock()

        with (
            patch("app.browser_pool.settings.PLAYWRIGHT_HEADLESS", True),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
            patch("app.browser_pool.settings.PLAYWRIGHT_STEALTH", True),
            patch("app.browser_pool.settings.STEALTH_NAVIGATOR_LANGUAGES", "en-US,en"),
            patch("app.browser_pool.settings.STEALTH_HARDWARE_CONCURRENCY", 4),
            patch("app.browser_pool.settings.BROWSER_CONTEXT_LIFETIME", 50),
        ):
            from app.strategy_evolution import FetchStrategy

            context = await pool.get_context("example.com", FetchStrategy.PLAYWRIGHT_STEALTH)

        assert context is mock_context
        mock_browser.new_context.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# Proxy Context
# ═══════════════════════════════════════════════════════════════════════════════


class TestProxyContext:
    @pytest.mark.asyncio
    async def test_creates_context_with_proxy_settings(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=True)
        mock_context = _sync_mock_context()
        mock_browser.new_context.return_value = mock_context
        pool._browser = mock_browser
        pool._playwright = MagicMock()

        mock_proxy = MagicMock()
        mock_proxy.enabled = True
        mock_proxy.get_proxy_for_playwright.return_value = {"server": "http://proxy:8080"}

        with (
            patch("app.browser_pool.settings.PLAYWRIGHT_HEADLESS", True),
            patch("app.browser_pool.settings.USER_AGENT", "TestUA"),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_WIDTH", 1920),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_HEIGHT", 1080),
            patch("app.browser_pool.settings.STEALTH_DEFAULT_LOCALE", "en-US"),
            patch("app.browser_pool.settings.STEALTH_TIMEZONE_POOL", "America/New_York"),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", True),
            patch("app.browser_pool.settings.PLAYWRIGHT_STEALTH", False),
            patch("app.browser_pool.settings.BROWSER_CONTEXT_LIFETIME", 50),
            patch("app.proxy_manager.get_proxy_manager", return_value=mock_proxy),
        ):
            from app.strategy_evolution import FetchStrategy

            context = await pool.get_context("example.com", FetchStrategy.PLAYWRIGHT_FULL)

        assert context is mock_context
        # Verify proxy was passed to new_context
        _, kwargs = mock_browser.new_context.call_args
        assert "proxy" in kwargs
        assert kwargs["proxy"]["server"] == "http://proxy:8080"


# ═══════════════════════════════════════════════════════════════════════════════
# Browser Reconnection
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrowserReconnection:
    @pytest.mark.asyncio
    async def test_relaunches_when_browser_disconnected(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=False)
        new_browser = _sync_browser_mock(is_connected=True)
        mock_context = _sync_mock_context()
        new_browser.new_context.return_value = mock_context

        pool._browser = mock_browser
        # Don't pre-set playwright — let async_playwright mock handle everything
        pool._playwright = None

        with (
            patch("app.browser_pool.async_playwright") as mock_async_pw,
            patch("app.browser_pool.settings.PLAYWRIGHT_HEADLESS", True),
            patch("app.browser_pool.settings.USER_AGENT", "TestUA"),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_WIDTH", 1920),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_HEIGHT", 1080),
            patch("app.browser_pool.settings.STEALTH_DEFAULT_LOCALE", "en-US"),
            patch("app.browser_pool.settings.STEALTH_TIMEZONE_POOL", "America/New_York"),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
            patch("app.browser_pool.settings.PLAYWRIGHT_STEALTH", False),
            patch("app.browser_pool.settings.BROWSER_CONTEXT_LIFETIME", 50),
        ):
            mock_pw = AsyncMock()
            mock_pw.chromium.launch.return_value = new_browser
            mock_pw_manager = MagicMock()
            mock_pw_manager.start = AsyncMock(return_value=mock_pw)
            mock_async_pw.return_value = mock_pw_manager

            from app.strategy_evolution import FetchStrategy

            context = await pool.get_context("example.com", FetchStrategy.PLAYWRIGHT_FULL)

        # New browser should be launched and used
        assert context is mock_context
        assert pool._browser is new_browser


# ═══════════════════════════════════════════════════════════════════════════════
# RSS Memory
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetRssMemory:
    def test_returns_int(self) -> None:
        pool = BrowserPool()
        rss = pool._get_rss_memory()
        assert isinstance(rss, int)
        assert rss >= 0

    def test_returns_zero_on_failure(self) -> None:
        with patch("resource.getrusage", side_effect=OSError("Not available")):
            pool = BrowserPool()
            rss = pool._get_rss_memory()
            assert rss == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Close with Cleanup Task
# ═══════════════════════════════════════════════════════════════════════════════


class TestCloseWithCleanup:
    @pytest.mark.asyncio
    async def test_cancels_cleanup_task(self) -> None:
        pool = BrowserPool()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        pool._cleanup_task = mock_task
        pool._browser = AsyncMock()
        pool._playwright = MagicMock()

        await pool.close()

        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_stops_playwright(self) -> None:
        pool = BrowserPool()
        mock_pw = AsyncMock()
        pool._playwright = mock_pw

        await pool.close()

        mock_pw.stop.assert_awaited_once()
        assert pool._playwright is None

    @pytest.mark.asyncio
    async def test_handles_playwright_stop_exception(self) -> None:
        pool = BrowserPool()
        mock_pw = AsyncMock()
        mock_pw.stop.side_effect = Error("Stop failed")
        pool._playwright = mock_pw

        await pool.close()  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# Check and Trigger Recycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckAndTriggerRecycle:
    @pytest.mark.asyncio
    async def test_returns_early_when_not_needed(self) -> None:
        pool = BrowserPool()
        pool._cumulative_fetches = 0  # Below threshold
        await pool._check_and_trigger_recycle()
        assert pool._recycling is False
        assert pool._recycle_event.is_set()

    @pytest.mark.asyncio
    async def test_returns_early_when_already_recycling(self) -> None:
        pool = BrowserPool()
        pool._recycling = True
        pool._cumulative_fetches = 999  # Would trigger if not already recycling
        with patch("app.browser_pool.settings.BROWSER_MAX_CUMULATIVE_FETCHES", 100):
            await pool._check_and_trigger_recycle()
        assert pool._recycling is True  # Still True (didn't change)

    @pytest.mark.asyncio
    async def test_triggers_recycle_and_resets(self) -> None:
        pool = BrowserPool()
        pool._cumulative_fetches = 200
        pool._active_fetches = 0
        pool._recycle_event.set()

        with (
            patch("app.browser_pool.settings.BROWSER_MAX_CUMULATIVE_FETCHES", 100),
            patch("app.browser_pool.settings.BROWSER_DRAIN_POLL_INTERVAL", 0.01),
            patch.object(pool, "_hard_recycle", AsyncMock()),
        ):
            await pool._check_and_trigger_recycle()

        assert pool._recycling is False
        assert pool._recycle_event.is_set()


# ═══════════════════════════════════════════════════════════════════════════════
# Get Browser Pool (Singleton Factory)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetBrowserPool:
    def teardown_method(self) -> None:
        """Reset the module-level singleton after each test."""
        import app.browser_pool as bp

        bp._pool = None

    def test_returns_browser_pool_instance(self) -> None:
        pool = get_browser_pool()
        assert isinstance(pool, BrowserPool)

    def test_returns_same_instance_on_second_call(self) -> None:
        p1 = get_browser_pool()
        p2 = get_browser_pool()
        assert p1 is p2


# ═══════════════════════════════════════════════════════════════════════════════
# Acquire / Release Isolated Contexts
# ═══════════════════════════════════════════════════════════════════════════════


class TestAcquireContext:
    @pytest.mark.asyncio
    async def test_acquire_yields_context_and_id(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=True)
        mock_context = _sync_mock_context()
        mock_browser.new_context.return_value = mock_context
        pool._browser = mock_browser
        pool._playwright = MagicMock()

        with (
            patch("app.browser_pool.settings.USER_AGENT", "TestUA"),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_WIDTH", 1280),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_HEIGHT", 720),
            patch("app.browser_pool.settings.STEALTH_DEFAULT_LOCALE", "en-US"),
            patch("app.browser_pool.settings.STEALTH_TIMEZONE_POOL", "America/New_York"),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
            patch("app.browser_pool.settings.BROWSER_MAX_CONTEXTS", 10),
        ):
            async with pool.acquire_context() as (ctx_id, ctx):
                assert ctx_id.startswith("iso:")
                assert ctx is mock_context
                assert pool._active_acquires == 1
                assert ctx_id in pool._isolated_contexts

        # After exit the context should be released
        assert pool._active_acquires == 0
        assert len(pool._isolated_contexts) == 0

    @pytest.mark.asyncio
    async def test_acquire_releases_on_exception(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=True)
        mock_context = _sync_mock_context()
        mock_browser.new_context.return_value = mock_context
        pool._browser = mock_browser
        pool._playwright = MagicMock()

        with (
            patch("app.browser_pool.settings.USER_AGENT", "TestUA"),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_WIDTH", 1280),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_HEIGHT", 720),
            patch("app.browser_pool.settings.STEALTH_DEFAULT_LOCALE", "en-US"),
            patch("app.browser_pool.settings.STEALTH_TIMEZONE_POOL", "America/New_York"),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
            patch("app.browser_pool.settings.BROWSER_MAX_CONTEXTS", 10),
        ):
            with pytest.raises(RuntimeError, match="simulated"):
                async with pool.acquire_context() as (_ctx_id, _ctx):
                    _err = RuntimeError("simulated")
                    raise _err

        # Even after exception, slot should be released
        assert pool._active_acquires == 0
        assert len(pool._isolated_contexts) == 0

    @pytest.mark.asyncio
    async def test_acquire_launches_browser_if_none(self) -> None:
        pool = BrowserPool()
        # No pre-existing browser

        with (
            patch("app.browser_pool.async_playwright") as mock_async_pw,
            patch("app.browser_pool.settings.PLAYWRIGHT_HEADLESS", True),
            patch("app.browser_pool.settings.BROWSER_SECURITY_HARDENING", True),
            patch("app.browser_pool.settings.USER_AGENT", "TestUA"),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_WIDTH", 1280),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_HEIGHT", 720),
            patch("app.browser_pool.settings.STEALTH_DEFAULT_LOCALE", "en-US"),
            patch("app.browser_pool.settings.STEALTH_TIMEZONE_POOL", "America/New_York"),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
            patch("app.browser_pool.settings.BROWSER_MAX_CONTEXTS", 10),
        ):
            mock_context = _sync_mock_context()
            mock_browser = _sync_browser_mock(is_connected=True)
            mock_browser.new_context.return_value = mock_context
            mock_pw = AsyncMock()
            mock_pw.chromium.launch.return_value = mock_browser
            mock_pw_manager = MagicMock()
            mock_pw_manager.start = AsyncMock(return_value=mock_pw)
            mock_async_pw.return_value = mock_pw_manager

            async with pool.acquire_context() as (ctx_id, ctx):
                assert ctx is mock_context
                assert pool._browser is mock_browser

    @pytest.mark.asyncio
    async def test_acquire_custom_viewport_and_ua(self) -> None:
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=True)
        mock_context = _sync_mock_context()
        mock_browser.new_context.return_value = mock_context
        pool._browser = mock_browser
        pool._playwright = MagicMock()

        with (
            patch("app.browser_pool.settings.USER_AGENT", "DefaultUA"),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_WIDTH", 1920),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_HEIGHT", 1080),
            patch("app.browser_pool.settings.STEALTH_DEFAULT_LOCALE", "en-US"),
            patch("app.browser_pool.settings.STEALTH_TIMEZONE_POOL", "America/New_York"),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
            patch("app.browser_pool.settings.BROWSER_MAX_CONTEXTS", 10),
        ):
            async with pool.acquire_context(
                viewport_width=800,
                viewport_height=600,
                user_agent="CustomBot/1.0",
            ) as (_ctx_id, _ctx):
                _, kwargs = mock_browser.new_context.call_args
                assert kwargs["viewport"]["width"] == 800
                assert kwargs["viewport"]["height"] == 600
                assert kwargs["user_agent"] == "CustomBot/1.0"

    @pytest.mark.asyncio
    async def test_semaphore_released_on_create_failure(self) -> None:
        """If _create_isolated_context raises, the semaphore slot is released."""
        pool = BrowserPool()
        mock_browser = _sync_browser_mock(is_connected=True)
        mock_browser.new_context.side_effect = Error("context creation failed")
        pool._browser = mock_browser
        pool._playwright = MagicMock()

        with (
            patch("app.browser_pool.settings.USER_AGENT", "TestUA"),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_WIDTH", 1280),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_HEIGHT", 720),
            patch("app.browser_pool.settings.STEALTH_DEFAULT_LOCALE", "en-US"),
            patch("app.browser_pool.settings.STEALTH_TIMEZONE_POOL", "America/New_York"),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
            patch("app.browser_pool.settings.BROWSER_MAX_CONTEXTS", 10),
        ):
            with pytest.raises(Error, match="context creation failed"):
                async with pool.acquire_context():
                    pass

        # Semaphore should be back to fully available
        assert pool._concurrency_semaphore._value == 10


class TestConcurrencyCap:
    @pytest.mark.asyncio
    async def test_semaphore_blocks_at_max(self) -> None:
        """With max_contexts=2, the 3rd acquire blocks until a slot opens."""
        pool = BrowserPool()
        # Override semaphore (constructed with default settings before patch)
        pool._concurrency_semaphore = asyncio.Semaphore(2)
        mock_browser = _sync_browser_mock(is_connected=True)
        pool._browser = mock_browser
        pool._playwright = MagicMock()

        with (
            patch("app.browser_pool.settings.USER_AGENT", "TestUA"),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_WIDTH", 1280),
            patch("app.browser_pool.settings.BROWSER_VIEWPORT_HEIGHT", 720),
            patch("app.browser_pool.settings.STEALTH_DEFAULT_LOCALE", "en-US"),
            patch("app.browser_pool.settings.STEALTH_TIMEZONE_POOL", "America/New_York"),
            patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
        ):
            acquired = []
            release_events: list[asyncio.Event] = [asyncio.Event() for _ in range(3)]

            async def holder(idx: int) -> None:
                mock_ctx = _sync_mock_context()
                mock_browser.new_context.return_value = mock_ctx
                async with pool.acquire_context() as (ctx_id, _ctx):
                    acquired.append(ctx_id)
                    # Hold until told to release
                    await release_events[idx].wait()

            # Acquire 2 slots (cap = 2)
            t0 = asyncio.create_task(holder(0))
            t1 = asyncio.create_task(holder(1))
            # Give them time to acquire
            await asyncio.sleep(0.05)
            assert pool._active_acquires == 2

            # 3rd attempt should block
            t2_started = asyncio.Event()

            async def holder2() -> None:
                t2_started.set()
                mock_ctx = _sync_mock_context()
                mock_browser.new_context.return_value = mock_ctx
                async with pool.acquire_context() as (ctx_id, _ctx):
                    acquired.append(ctx_id)
                    await release_events[2].wait()

            t2 = asyncio.create_task(holder2())
            await asyncio.sleep(0.05)
            # t2 should be waiting on the semaphore — active acquires still 2
            assert pool._active_acquires == 2

            # Release slot 0 — now t2 should acquire
            release_events[0].set()
            await asyncio.sleep(0.05)
            assert pool._active_acquires == 2  # t2 got the slot

            # Cleanup
            release_events[1].set()
            release_events[2].set()
            await asyncio.gather(t0, t1, t2, return_exceptions=True)
            assert pool._active_acquires == 0


class TestReleaseContext:
    @pytest.mark.asyncio
    async def test_release_closes_context(self) -> None:
        pool = BrowserPool()
        mock_ctx = _sync_mock_context()
        pool._isolated_contexts["iso:abc123"] = mock_ctx
        pool._active_acquires = 1
        pool.active_contexts = 1

        await pool.release_context("iso:abc123")

        mock_ctx.close.assert_awaited_once()
        assert "iso:abc123" not in pool._isolated_contexts
        assert pool._active_acquires == 0

    @pytest.mark.asyncio
    async def test_release_unknown_id_is_noop(self) -> None:
        pool = BrowserPool()
        await pool.release_context("iso:nonexistent")  # should not raise

    @pytest.mark.asyncio
    async def test_release_handles_close_exception(self) -> None:
        pool = BrowserPool()
        mock_ctx = _sync_mock_context()
        mock_ctx.close.side_effect = Error("close failed")
        pool._isolated_contexts["iso:failing"] = mock_ctx
        pool._active_acquires = 1

        await pool.release_context("iso:failing")  # should not raise
        assert pool._active_acquires == 0


class TestCloseWithIsolatedContexts:
    @pytest.mark.asyncio
    async def test_close_cleans_up_isolated_contexts(self) -> None:
        pool = BrowserPool()
        mock_ctx = _sync_mock_context()
        pool._isolated_contexts["iso:test"] = mock_ctx
        pool._active_acquires = 1

        await pool.close()

        mock_ctx.close.assert_awaited_once()
        assert pool._isolated_contexts == {}
        assert pool._active_acquires == 0


class TestGetMetricsWithIsolated:
    def test_metrics_include_isolated_counts(self) -> None:
        pool = BrowserPool()
        pool._isolated_contexts["iso:1"] = MagicMock()
        pool._isolated_contexts["iso:2"] = MagicMock()
        pool._active_acquires = 2
        pool._contexts["test:default"] = MagicMock()

        metrics = pool.get_metrics()
        assert metrics["isolated_contexts"] == 2
        assert metrics["reusable_contexts"] == 1
        assert metrics["active_acquires"] == 2

    def test_metrics_default_zero(self) -> None:
        pool = BrowserPool()
        metrics = pool.get_metrics()
        assert metrics["isolated_contexts"] == 0
        assert metrics["reusable_contexts"] == 0
        assert metrics["active_acquires"] == 0


class TestEnsureBrowser:
    @pytest.mark.asyncio
    async def test_launches_browser_when_none(self) -> None:
        pool = BrowserPool()

        with (
            patch("app.browser_pool.async_playwright") as mock_async_pw,
            patch("app.browser_pool.settings.PLAYWRIGHT_HEADLESS", True),
            patch("app.browser_pool.settings.BROWSER_SECURITY_HARDENING", False),
        ):
            mock_browser = _sync_browser_mock(is_connected=True)
            mock_pw = AsyncMock()
            mock_pw.chromium.launch.return_value = mock_browser
            mock_pw_manager = MagicMock()
            mock_pw_manager.start = AsyncMock(return_value=mock_pw)
            mock_async_pw.return_value = mock_pw_manager

            await pool._ensure_browser()

        assert pool._browser is mock_browser
        assert pool._playwright is mock_pw

    @pytest.mark.asyncio
    async def test_relaunches_disconnected_browser(self) -> None:
        pool = BrowserPool()
        dead_browser = _sync_browser_mock(is_connected=False)
        pool._browser = dead_browser
        pool._playwright = AsyncMock()

        with (
            patch("app.browser_pool.settings.PLAYWRIGHT_HEADLESS", True),
            patch("app.browser_pool.settings.BROWSER_SECURITY_HARDENING", False),
        ):
            new_browser = _sync_browser_mock(is_connected=True)
            pool._playwright.chromium.launch = AsyncMock(return_value=new_browser)

            await pool._ensure_browser()

        assert pool._browser is new_browser
