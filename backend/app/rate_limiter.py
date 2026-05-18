"""
Rate Limiter — in-memory sliding window rate limiting middleware.

Provides simple per-IP rate limiting for API endpoints without
external dependencies. Uses a sliding window counter approach.

Usage:
    from app.rate_limiter import RateLimiterMiddleware

    rate_limiter = RateLimiterMiddleware(global_limit="100/minute")
    app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limiter.middleware)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when a client exceeds their rate limit."""


def _parse_rate_limit(limit_str: str) -> tuple[int, float]:
    """Parse a rate limit string like '100/minute' into (max_requests, window_seconds).

    Supported formats: N/second, N/minute, N/hour.
    Returns (max_requests, window_seconds), or (0, 0) if invalid.
    """
    if not limit_str or not isinstance(limit_str, str):
        return 0, 0

    limit_str = limit_str.strip().lower()
    parts = limit_str.split("/")
    if len(parts) != 2:
        return 0, 0

    try:
        max_requests = int(parts[0])
    except ValueError:
        return 0, 0

    unit = parts[1]
    if unit in ("second", "seconds", "s"):
        return max_requests, 1.0
    elif unit in ("minute", "minutes", "m"):
        return max_requests, 60.0
    elif unit in ("hour", "hours", "h"):
        return max_requests, 3600.0
    else:
        return 0, 0


class SlidingWindowCounter:
    """Sliding window rate limit counter for a single key."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: list[float] = []

    def allow(self) -> bool:
        """Check if a request is allowed, and record it if so.

        Returns True if within limit, False if exceeded.
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # Prune expired timestamps
        self._timestamps = [t for t in self._timestamps if t > cutoff]

        if len(self._timestamps) >= self.max_requests:
            return False

        self._timestamps.append(now)
        return True

    def remaining(self) -> int:
        """How many requests remain in the current window."""
        now = time.time()
        cutoff = now - self.window_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        return max(0, self.max_requests - len(self._timestamps))

    def reset_in(self) -> float:
        """Seconds until the window resets."""
        if not self._timestamps:
            return 0.0
        return max(0.0, self.window_seconds - (time.time() - self._timestamps[0]))


class RateLimiterMiddleware:
    """In-memory sliding window rate limiter for FastAPI.

    Applies a global rate limit across all /api/ endpoints,
    plus optional stricter limits for specific route patterns.
    """

    def __init__(
        self,
        global_limit: str = "",
        per_ip: bool = True,
    ) -> None:
        self._global_max, self._global_window = _parse_rate_limit(global_limit)
        self._per_ip = per_ip
        self._counters: dict[str, SlidingWindowCounter] = {}

        if self._global_max > 0:
            logger.info(
                "Rate limiter: %d requests per %.0fs (global)",
                self._global_max, self._global_window,
            )
        else:
            logger.info("Rate limiter: disabled")

    async def middleware(self, request: Request, call_next: Callable) -> Response:
        """ASGI middleware dispatch."""
        if self._global_max <= 0:
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        if "/docs" in path or "/openapi" in path:
            return await call_next(request)

        # Determine client key
        if self._per_ip:
            client_ip = request.client.host if request.client else "unknown"
            key = f"global:{client_ip}"
        else:
            key = "global"

        # Check rate limit
        counter = self._get_counter(key)
        if not counter.allow():
            logger.warning("Rate limit exceeded for %s on %s", key, path)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Try again later.",
                    "retry_after_seconds": counter.reset_in(),
                },
                headers={
                    "X-RateLimit-Limit": str(counter.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + counter.reset_in())),
                    "Retry-After": str(int(counter.reset_in())),
                },
            )

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(counter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(counter.remaining())
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + counter.reset_in()))

        return response

    def _get_counter(self, key: str) -> SlidingWindowCounter:
        if key not in self._counters:
            self._counters[key] = SlidingWindowCounter(self._global_max, self._global_window)
        return self._counters[key]

    def get_stats(self) -> dict:
        """Return current rate limiter stats (for observability)."""
        return {
            "enabled": self._global_max > 0,
            "limit_per_window": self._global_max,
            "window_seconds": self._global_window,
            "active_keys": len(self._counters),
        }
