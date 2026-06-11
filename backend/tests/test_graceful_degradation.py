"""Unit tests for the graceful degradation utilities in ``app.utils.graceful_degradation``."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.utils.graceful_degradation import (
    GracefulDegradation,
    graceful_degradation,
    with_circuit_breaker_fallback,
    with_fallback_value,
    with_graceful_degradation,
)


@pytest.mark.asyncio
class TestGracefulDegradationClass:
    async def test_register_and_get_fallback(self) -> None:
        """Verify fallbacks can be registered and retrieved."""
        gd = GracefulDegradation()
        fallback_fn = MagicMock()
        gd.register_fallback("test_service", fallback_fn)
        assert gd.get_fallback("test_service") is fallback_fn
        assert gd.get_fallback("non_existent") is None

    async def test_execute_with_fallback_success(self) -> None:
        """Verify successful primary execution caches and returns the result."""
        gd = GracefulDegradation()
        primary_fn = AsyncMock(return_value="primary_success")

        result = await gd.execute_with_fallback("service_a", primary_fn, cache_ttl=10.0)

        assert result == "primary_success"
        primary_fn.assert_called_once()
        assert gd._cache["service_a"] == "primary_success"

    async def test_execute_with_fallback_primary_fails_cache_hit(self) -> None:
        """Verify fallback to cache if primary fails within TTL."""
        gd = GracefulDegradation()
        gd._cache["service_b"] = "cached_val"
        gd._cache_ttl["service_b"] = asyncio.get_event_loop().time() + 10.0

        primary_fn = AsyncMock(side_effect=RuntimeError("primary failed"))
        fallback_fn = AsyncMock()
        gd.register_fallback("service_b", fallback_fn)

        result = await gd.execute_with_fallback("service_b", primary_fn)

        assert result == "cached_val"
        primary_fn.assert_called_once()
        fallback_fn.assert_not_called()

    async def test_execute_with_fallback_primary_fails_cache_expired_uses_fallback(self) -> None:
        """Verify fallback function is called if cache is expired."""
        gd = GracefulDegradation()
        gd._cache["service_c"] = "expired_val"
        gd._cache_ttl["service_c"] = asyncio.get_event_loop().time() - 10.0  # Expired

        primary_fn = AsyncMock(side_effect=RuntimeError("primary failed"))
        fallback_fn = AsyncMock(return_value="fallback_val")
        gd.register_fallback("service_c", fallback_fn)

        result = await gd.execute_with_fallback("service_c", primary_fn)

        assert result == "fallback_val"
        primary_fn.assert_called_once()
        fallback_fn.assert_called_once()

    async def test_execute_with_fallback_both_fail_raises(self) -> None:
        """Verify exception is raised if both primary and fallback fail."""
        gd = GracefulDegradation()
        primary_fn = AsyncMock(side_effect=RuntimeError("primary failed"))
        fallback_fn = AsyncMock(side_effect=ValueError("fallback failed"))
        gd.register_fallback("service_d", fallback_fn)

        with pytest.raises(RuntimeError, match="primary failed"):
            await gd.execute_with_fallback("service_d", primary_fn)

    async def test_clear_cache(self) -> None:
        """Verify cache clearing works globally and selectively."""
        gd = GracefulDegradation()
        gd._cache["service_1"] = "val_1"
        gd._cache_ttl["service_1"] = 100.0
        gd._cache["service_2"] = "val_2"
        gd._cache_ttl["service_2"] = 200.0

        gd.clear_cache("service_1")
        assert "service_1" not in gd._cache
        assert "service_2" in gd._cache

        gd.clear_cache()
        assert not gd._cache


@pytest.mark.asyncio
class TestGracefulDegradationDecorators:
    async def test_decorator_with_graceful_degradation(self) -> None:
        """Verify with_graceful_degradation decorator invokes execute_with_fallback."""
        fallback_fn = MagicMock(return_value="decorator_fallback")
        graceful_degradation.clear_cache()

        @with_graceful_degradation("dec_service", fallback=fallback_fn)
        async def mock_primary():
            msg = "fail"
            raise RuntimeError(msg)

        result = await mock_primary()
        assert result == "decorator_fallback"

    async def test_decorator_with_fallback_value_success(self) -> None:
        """Verify with_fallback_value returns normal result when successful."""

        @with_fallback_value("my_default")
        async def mock_func():
            return "real_result"

        assert await mock_func() == "real_result"

    async def test_decorator_with_fallback_value_failure(self) -> None:
        """Verify with_fallback_value returns default when function fails."""

        @with_fallback_value("my_default")
        async def mock_fail_func():
            msg = "bad parameter"
            raise ValueError(msg)

        assert await mock_fail_func() == "my_default"

    async def test_decorator_with_circuit_breaker_fallback_success(self) -> None:
        """Verify with_circuit_breaker_fallback returns normal result when successful."""

        @with_circuit_breaker_fallback("cb_test", fallback_value="cb_fallback")
        async def mock_cb_func():
            return "cb_real"

        assert await mock_cb_func() == "cb_real"

    async def test_decorator_with_circuit_breaker_fallback_failure(self) -> None:
        """Verify with_circuit_breaker_fallback returns fallback when function fails."""

        @with_circuit_breaker_fallback("cb_test", fallback_value="cb_fallback")
        async def mock_cb_fail():
            msg = "cb failed"
            raise ValueError(msg)

        assert await mock_cb_fail() == "cb_fallback"
