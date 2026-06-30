"""Graceful degradation utilities for fault tolerance.

Provides fallback mechanisms when services are unavailable.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
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
        # F-GD-002: protect cache reads/writes when multiple coroutines
        # call ``execute_with_fallback`` for the same key concurrently.
        # Without this guard, parallel calls could both miss the cache
        # and both fall through to the fallback path.
        # Lazily initialized to avoid binding to a dead event loop.
        self._cache_lock: asyncio.Lock | None = None

    def _get_cache_lock(self) -> asyncio.Lock:
        """Lazily create the asyncio.Lock so it's bound to the running loop."""
        if self._cache_lock is None:
            self._cache_lock = asyncio.Lock()
        return self._cache_lock

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
            # Cache successful result under a lock so concurrent
            # coroutines cannot interleave the write with the
            # expiry check below.
            async with self._get_cache_lock():
                self._cache[key] = result
                # ``time.monotonic`` is loop-independent and avoids the
                # deprecated ``asyncio.get_event_loop().time()`` pattern.
                self._cache_ttl[key] = time.monotonic() + cache_ttl
            return result
        except Exception as e:
            logger.warning("Primary function %s failed: %s", key, e)

            # Check cache first (also under the lock to avoid a
            # ``clear_cache`` racing with our TTL read).
            async with self._get_cache_lock():
                cached = self._cache.get(key)
                cache_time = self._cache_ttl.get(key, 0.0)
            if cached is not None and time.monotonic() < cache_time:
                logger.info("Using cached result for %s", key)
                return cached

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
        """Clear cache for a specific key or all keys.

        Synchronous helper that mutates the same dicts that
        ``execute_with_fallback`` reads via ``asyncio.Lock``.  Python's
        GIL makes per-key dict assignment atomic, so worst case is a
        single stale read inside an in-flight coroutine — acceptable
        for a cache whose entries expire on their own.
        """
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
