"""Rate limiter — simple in-memory sliding window rate limiter for the kernel.

Ported from the existing app.rate_limiter with a clean interface.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_after: float  # seconds until the window resets


class SlidingWindowCounter:
    """In-memory sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str = "default") -> RateLimitResult:
        now = time.time()
        window_start = now - self.window_seconds

        # Prune old entries
        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if t > window_start]

        count = len(self._requests[key])
        if count >= self.max_requests:
            oldest = min(self._requests[key]) if self._requests[key] else now
            reset_after = max(0.0, self.window_seconds - (now - oldest))
            return RateLimitResult(allowed=False, remaining=0, reset_after=reset_after)

        self._requests[key].append(now)
        oldest = min(self._requests[key]) if self._requests[key] else now
        reset_after = max(0.0, self.window_seconds - (now - oldest))
        return RateLimitResult(
            allowed=True,
            remaining=self.max_requests - count - 1,
            reset_after=reset_after,
        )


_global_limiter: SlidingWindowCounter | None = None
_job_create_limiter: SlidingWindowCounter | None = None


def _parse_rate_limit(rate_str: str) -> tuple[int, float]:
    """Parse a rate limit string like '600/minute' into (count, window_seconds)."""
    count_str, window = rate_str.split("/")
    count = int(count_str.strip())
    window_map = {
        "second": 1.0,
        "seconds": 1.0,
        "minute": 60.0,
        "minutes": 60.0,
        "hour": 3600.0,
        "hours": 3600.0,
    }
    return count, window_map.get(window.strip(), 60.0)


def get_global_limiter() -> SlidingWindowCounter:
    global _global_limiter
    if _global_limiter is None:
        from forge_kernel.config import settings

        count, window = _parse_rate_limit(settings.security.RATE_LIMIT_GLOBAL)
        _global_limiter = SlidingWindowCounter(max_requests=count, window_seconds=window)
    return _global_limiter


def get_job_create_limiter() -> SlidingWindowCounter:
    global _job_create_limiter
    if _job_create_limiter is None:
        from forge_kernel.config import settings

        count, window = _parse_rate_limit(settings.security.RATE_LIMIT_JOB_CREATE)
        _job_create_limiter = SlidingWindowCounter(max_requests=count, window_seconds=window)
    return _job_create_limiter
