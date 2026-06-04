"""Unit tests for browser_pool — BrowserPool lifecycle, metrics, and context management."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.browser_pool import BrowserPool, get_browser_pool

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
    @patch("app.browser_pool.settings.BROWSER_MAX_CUMULATIVE_FETCHES", 100)
    def test_returns_false_when_below_threshold(self) -> None:
        pool = BrowserPool()
        pool._cumulative_fetches = 50
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
        mock_ctx = AsyncMock()
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
        mock_browser = AsyncMock()
        mock_browser.is_connected.return_value = True
        mock_context = AsyncMock()
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
        mock_browser = AsyncMock()
        mock_browser.is_connected.return_value = True
        mock_context = AsyncMock()
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
        mock_browser = AsyncMock()
        mock_browser.is_connected.return_value = True
        mock_context = AsyncMock()
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
        mock_browser = AsyncMock()
        mock_browser.is_connected.return_value = True
        old_context = AsyncMock()
        new_context = AsyncMock()
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
            mock_pw.chromium.launch.side_effect = Exception("Launch failed")
            # async_playwright() returns a manager whose .start() is awaitable
            mock_pw_manager = MagicMock()
            mock_pw_manager.start = AsyncMock(return_value=mock_pw)
            mock_async_pw.return_value = mock_pw_manager

            from app.strategy_evolution import FetchStrategy

            with pytest.raises(Exception, match="Launch failed"):
                await pool.get_context("example.com", FetchStrategy.PLAYWRIGHT_FULL)

            assert pool.crash_count == 1


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
