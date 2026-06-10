"""Graceful degradation utilities for fault tolerance.

Provides fallback mechanisms when services are unavailable.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class GracefulDegradation:
    """Provides fallback behavior when services fail."""

    def __init__(self):
        self._fallbacks: dict[str, Callable] = {}
        self._cache: dict[str, Any] = {}
        self._cache_ttl: dict[str, float] = {}

    def register_fallback(self, key: str, fallback_fn: Callable) -> None:
        """Register a fallback function for a service."""
        self._fallbacks[key] = fallback_fn

    def get_fallback(self, key: str) -> Callable | None:
        """Get fallback function for a service."""
        return self._fallbacks.get(key)

    async def execute_with_fallback(
        self,
        key: str,
        primary_fn: Callable,
        *args,
        cache_ttl: float = 300.0,
        **kwargs,
    ) -> Any:
        """Execute primary function with fallback on failure."""
        try:
            result = await primary_fn(*args, **kwargs)
            # Cache successful result
            self._cache[key] = result
            self._cache_ttl[key] = asyncio.get_event_loop().time() + cache_ttl
            return result
        except Exception as e:
            logger.warning("Primary function %s failed: %s", key, e)

            # Check cache first
            if key in self._cache:
                cache_time = self._cache_ttl.get(key, 0)
                if asyncio.get_event_loop().time() < cache_time:
                    logger.info("Using cached result for %s", key)
                    return self._cache[key]

            # Use fallback
            fallback = self.get_fallback(key)
            if fallback:
                logger.info("Using fallback for %s", key)
                try:
                    return await fallback(*args, **kwargs) if asyncio.iscoroutinefunction(fallback) else fallback(*args, **kwargs)
                except Exception:
                    logger.exception("Fallback %s also failed", key)

            raise

    def clear_cache(self, key: str | None = None) -> None:
        """Clear cache for a specific key or all keys."""
        if key:
            self._cache.pop(key, None)
            self._cache_ttl.pop(key, None)
        else:
            self._cache.clear()
            self._cache_ttl.clear()


# Global instance
graceful_degradation = GracefulDegradation()


def with_graceful_degradation(
    key: str,
    fallback: Callable | None = None,
    cache_ttl: float = 300.0,
) -> Callable:
    """Decorator for graceful degradation."""

    def decorator(func: Callable) -> Callable:
        if fallback:
            graceful_degradation.register_fallback(key, fallback)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await graceful_degradation.execute_with_fallback(
                key,
                func,
                *args,
                cache_ttl=cache_ttl,
                **kwargs,
            )

        return wrapper

    return decorator


def with_fallback_value(default: Any, log_error: bool = True) -> Callable:
    """Decorator that returns a default value on failure."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception:
                if log_error:
                    logger.exception("Function %s failed", func.__name__)
                return default

        return wrapper

    return decorator


def with_circuit_breaker_fallback(
    circuit_breaker_name: str,
    fallback_value: Any = None,
) -> Callable:
    """Decorator that uses circuit breaker with fallback."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                from app.utils.circuit_breaker import get_all_circuit_breakers

                for cb in get_all_circuit_breakers():
                    if cb.name == circuit_breaker_name:
                        async with cb:
                            return await func(*args, **kwargs)
                return await func(*args, **kwargs)
            except Exception as e:
                logger.warning("Circuit breaker %s triggered: %s", circuit_breaker_name, e)
                return fallback_value

        return wrapper

    return decorator
