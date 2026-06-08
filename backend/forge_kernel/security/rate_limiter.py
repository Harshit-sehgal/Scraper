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
        return RateLimitResult(
            allowed=True,
            remaining=self.max_requests - count - 1,
            reset_after=self.window_seconds,
        )


_global_limiter: SlidingWindowCounter | None = None
_job_create_limiter: SlidingWindowCounter | None = None


def get_global_limiter() -> SlidingWindowCounter:
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = SlidingWindowCounter(max_requests=600, window_seconds=60.0)
    return _global_limiter


def get_job_create_limiter() -> SlidingWindowCounter:
    global _job_create_limiter
    if _job_create_limiter is None:
        _job_create_limiter = SlidingWindowCounter(max_requests=10, window_seconds=60.0)
    return _job_create_limiter
