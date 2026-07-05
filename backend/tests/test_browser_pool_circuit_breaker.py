"""Tests for browser pool circuit breaker integration (Prod 8).

Validates that the browser pool circuit breaker:
- Opens after 3 consecutive RuntimeError failures
- Rejects requests when OPEN (raises CircuitBreakerError)
- Transitions to HALF_OPEN after recovery timeout
- Closes on success in HALF_OPEN state
- get_browser_pool_health returns expected dict structure
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import app.browser_pool as _bp_module
import pytest
from app.browser_pool import (
    BrowserPool,
    get_browser_pool_health,
    reset_browser_pool_circuit_breaker,
)
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerError, CircuitState


@pytest.fixture(autouse=True)
def _reset_cb():
    """Reset the browser pool circuit breaker before each test."""
    reset_browser_pool_circuit_breaker()
    yield
    reset_browser_pool_circuit_breaker()


def _sync_mock_context() -> MagicMock:
    """Create a context mock where sync methods don't return unawaited coroutines."""
    ctx = AsyncMock()
    ctx.on = MagicMock()
    ctx.new_page = AsyncMock()
    return ctx


def _sync_browser_mock(is_connected: bool = True) -> MagicMock:
    """Create a browser mock with sync is_connected."""
    b = MagicMock()
    b.is_connected = MagicMock(return_value=is_connected)
    b.new_context = AsyncMock()
    b.close = AsyncMock()
    return b


class TestCircuitBreakerOpensAfterFailures:
    """After 3 consecutive RuntimeError failures the breaker must be OPEN."""

    @pytest.mark.asyncio
    async def test_opens_after_three_runtime_errors(self) -> None:
        pool = BrowserPool()
        reset_browser_pool_circuit_breaker()

        for _ in range(3):
            with (
                patch("app.browser_pool.async_playwright") as mock_async_pw,
                patch("app.browser_pool.settings.PLAYWRIGHT_HEADLESS", True),
            ):
                mock_pw = AsyncMock()
                mock_pw.chromium.launch.side_effect = RuntimeError("browser crash")
                mock_pw_manager = MagicMock()
                mock_pw_manager.start = AsyncMock(return_value=mock_pw)
                mock_async_pw.return_value = mock_pw_manager

                with pytest.raises(RuntimeError, match="browser crash"):
                    await pool.get_context("example.com")

        assert _bp_module.browser_pool_circuit_breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_does_not_open_on_non_runtime_errors(self) -> None:
        """Non-RuntimeError exceptions should NOT trip the circuit breaker."""
        pool = BrowserPool()
        reset_browser_pool_circuit_breaker()

        # OSError is not RuntimeError, so it shouldn't affect the breaker
        with (
            patch("app.browser_pool.async_playwright") as mock_async_pw,
            patch("app.browser_pool.settings.PLAYWRIGHT_HEADLESS", True),
        ):
            mock_pw = AsyncMock()
            mock_pw.chromium.launch.side_effect = OSError("connection refused")
            mock_pw_manager = MagicMock()
            mock_pw_manager.start = AsyncMock(return_value=mock_pw)
            mock_async_pw.return_value = mock_pw_manager

            with pytest.raises(OSError, match="connection refused"):
                await pool.get_context("example.com")

        assert _bp_module.browser_pool_circuit_breaker.state == CircuitState.CLOSED
        assert _bp_module.browser_pool_circuit_breaker.failure_count == 0


class TestCircuitBreakerRejectsWhenOpen:
    """When the breaker is OPEN, get_context must raise CircuitBreakerError."""

    @pytest.mark.asyncio
    async def test_rejects_with_circuit_breaker_error(self) -> None:
        pool = BrowserPool()
        reset_browser_pool_circuit_breaker()
        cb = _bp_module.browser_pool_circuit_breaker

        # Force breaker open by recording 3 failures directly
        for _ in range(3):
            await cb._on_failure()

        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerError, match="Browser pool circuit breaker is OPEN"):
            await pool.get_context("example.com")


class TestCircuitBreakerHalfOpenTransition:
    """After recovery_timeout, the breaker transitions to HALF_OPEN."""

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self) -> None:
        cb = CircuitBreaker(
            name="browser_pool",
            failure_threshold=3,
            recovery_timeout=0.01,
            expected_exception=RuntimeError,
        )
        # Use a very short recovery timeout for testing
        with patch("app.browser_pool.browser_pool_circuit_breaker", cb):
            # Trip the breaker open
            for _ in range(3):
                await cb._on_failure()

            assert cb.state == CircuitState.OPEN

            # Deterministic clock advance instead of awaiting asyncio.sleep(0.05).
            # The breaker compares (time.time() - _last_failure_time) to
            # recovery_timeout, so shifting time forward by 0.05 simulates a
            # 50ms wall-clock wait without actually sleeping (matters under CI).
            import app.utils.circuit_breaker as _cb_mod

            original = _cb_mod.time.time
            _cb_mod.time.time = lambda: original() + 0.05

            assert cb.state == CircuitState.HALF_OPEN


class TestCircuitBreakerSuccessClosesCircuit:
    """A successful request in HALF_OPEN state closes the circuit."""

    @pytest.mark.asyncio
    async def test_success_in_half_open_closes_circuit(self) -> None:
        cb = CircuitBreaker(
            name="browser_pool",
            failure_threshold=3,
            recovery_timeout=0.01,
            expected_exception=RuntimeError,
        )
        with patch("app.browser_pool.browser_pool_circuit_breaker", cb):
            # Trip the breaker open
            for _ in range(3):
                await cb._on_failure()

            assert cb.state == CircuitState.OPEN

            # Deterministic clock advance instead of awaiting asyncio.sleep(0.05).
            # The breaker compares (time.time() - _last_failure_time) to
            # recovery_timeout, so shifting time forward by 0.05 simulates a
            # 50ms wall-clock wait without actually sleeping.
            import app.utils.circuit_breaker as _cb_mod

            original = _cb_mod.time.time
            _cb_mod.time.time = lambda: original() + 0.05
            assert cb.state == CircuitState.HALF_OPEN

            # Simulate a successful context acquisition
            pool = BrowserPool()
            mock_browser = _sync_browser_mock(is_connected=True)
            mock_context = _sync_mock_context()
            mock_browser.new_context.return_value = mock_context
            pool._browser = mock_browser
            pool._playwright = MagicMock()

            with (
                patch("app.browser_pool.settings.PLAYWRIGHT_HEADLESS", True),
                patch("app.browser_pool.settings.USER_AGENT", "TestUA"),
                patch("app.browser_pool.settings.BROWSER_VIEWPORT_WIDTH", 1280),
                patch("app.browser_pool.settings.BROWSER_VIEWPORT_HEIGHT", 720),
                patch("app.browser_pool.settings.STEALTH_DEFAULT_LOCALE", "en-US"),
                patch("app.browser_pool.settings.STEALTH_TIMEZONE_POOL", "America/New_York"),
                patch("app.browser_pool.settings.PROXY_ROTATION_ENABLED", False),
                patch("app.browser_pool.settings.PLAYWRIGHT_STEALTH", False),
                patch("app.browser_pool.settings.BROWSER_CONTEXT_LIFETIME", 50),
            ):
                await pool.get_context("newdomain.com")

            assert cb.state == CircuitState.CLOSED


class TestGetBrowserPoolHealth:
    """get_browser_pool_health returns the expected dict structure."""

    def test_returns_expected_keys(self) -> None:
        health = get_browser_pool_health()

        assert "circuit_breaker" in health
        assert "pool" in health
        assert "healthy" in health

        # Circuit breaker subdict
        cb = health["circuit_breaker"]
        assert "name" in cb
        assert "state" in cb
        assert "failure_count" in cb
        assert "success_count" in cb
        assert "config" in cb
        assert cb["name"] == "browser_pool"
        assert cb["state"] == "closed"

        # Pool subdict
        pool = health["pool"]
        assert "active_contexts" in pool
        assert "connected" in pool

        # Overall health flag
        assert health["healthy"] is True

    @pytest.mark.asyncio
    async def test_healthy_is_false_when_circuit_open(self) -> None:
        """When breaker is OPEN, healthy flag should be False."""
        reset_browser_pool_circuit_breaker()
        cb = _bp_module.browser_pool_circuit_breaker
        # Force it open
        for _ in range(3):
            await cb._on_failure()

        health = get_browser_pool_health()
        assert health["healthy"] is False
        assert health["circuit_breaker"]["state"] == "open"
