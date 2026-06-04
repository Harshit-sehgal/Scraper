"""Rate Limiter — in-memory sliding window rate limiting middleware.

Provides per-IP rate limiting for API endpoints without
external dependencies. Uses a sliding window counter approach.

Supports:
- Global rate limit across all /api/ endpoints
- Route-specific stricter limits for expensive endpoints
- Safe IP extraction (behind nginx reverse proxy only)
- TTL-based cleanup to prevent unbounded counter map growth

Usage:
    from app.rate_limiter import RateLimiterMiddleware

    rate_limiter = RateLimiterMiddleware(global_limit="100 / minute")
    app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limiter.middleware)
"""

from __future__ import annotations

import ipaddress
import logging
import time
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import Request, Response

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when a client exceeds their rate limit."""


_ROUTE_LIMITS: dict[str, tuple[int, float]] = {
    # Format: prefix -> (max_requests, window_seconds)
    # 10 per minute — expensive browser + LLM
    "/api/url/analyze": (10, 60.0),
    # 15 per minute — network calls
    "/api/discover": (15, 60.0),
    "/api/schema/suggest": (15, 60.0),  # 15 per minute — LLM calls
    # 5 per minute — expensive diagnostic
    "/api/scraper/diagnostics": (5, 60.0),
    # 20 per minute — ML computation
    "/api/scraper/ml": (20, 60.0),
    # 20 per minute — strategy mutations
    "/api/scraper/strategy": (20, 60.0),
    # 60 per minute — job creation / mutation
    "/api/jobs": (60, 60.0),
    # 30 per minute — recycle bin mutations
    "/api/recycle_bin": (30, 60.0),
}


def _get_effective_route_limits(method: str | None = None) -> dict[str, tuple[int, float]]:
    from app.config import settings

    limits = dict(_ROUTE_LIMITS)
    if hasattr(settings, "RATE_LIMIT_JOB_CREATE") and settings.RATE_LIMIT_JOB_CREATE:
        if method is None or method.upper() == "POST":
            parsed = _parse_rate_limit(settings.RATE_LIMIT_JOB_CREATE)
            if parsed != (0, 0):
                limits["/api/jobs"] = parsed
    if hasattr(settings, "RATE_LIMIT_DISCOVER") and settings.RATE_LIMIT_DISCOVER:
        parsed = _parse_rate_limit(settings.RATE_LIMIT_DISCOVER)
        if parsed != (0, 0):
            limits["/api/discover"] = parsed
    return limits


def _parse_rate_limit(limit_str: str) -> tuple[int, float]:
    """Parse a rate limit string like '100 / minute' into (max_requests, window_seconds).

    Supported formats: N / second, N / minute, N / hour.
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
    if unit in ("minute", "minutes", "m"):
        return max_requests, 60.0
    if unit in ("hour", "hours", "h"):
        return max_requests, 3600.0
    return 0, 0


def _get_route_key(path: str, method: str | None = None) -> str:
    """Determine the per-route rate limit key from an API path.

    Matches against known route prefixes, returning the most specific match.
    Falls back to the default key for unmapped routes.
    """
    limits = _get_effective_route_limits(method)
    for prefix in sorted(limits.keys(), key=len, reverse=True):
        if path.startswith(prefix):
            return prefix
    return "default"


class DatabaseSlidingWindowCounter:
    """Sliding window rate limit counter backed by a SQLite or Postgres database."""

    def __init__(self, max_requests: int, window_seconds: float, key: str) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key = key
        self._initialized = False
        self._fallback_counter = SlidingWindowCounter(max_requests, window_seconds)

    def _ensure_table(self) -> None:
        if self._initialized:
            return
        from app.config import settings

        backend = settings.STORAGE_BACKEND
        if backend == "postgres":
            try:
                from app.postgres_repository import _conn, _execute

                with _conn() as conn:
                    _execute(
                        conn,
                        """
                        CREATE TABLE IF NOT EXISTS rate_limits (
                            key VARCHAR(255) NOT NULL,
                            timestamp DOUBLE PRECISION NOT NULL
                        )
                    """,
                    )
                    _execute(conn, "CREATE INDEX IF NOT EXISTS idx_rate_limits_key_ts ON rate_limits(key, timestamp)")
                self._initialized = True
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to initialize Postgres rate limit table: %s", e)
        else:
            try:
                from app.job_store import _DB_LOCK, _get_connection

                with _DB_LOCK:
                    conn = _get_connection()
                    try:
                        conn.execute("""
                            CREATE TABLE IF NOT EXISTS rate_limits (
                                key TEXT NOT NULL,
                                timestamp REAL NOT NULL
                            )
                        """)
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_key_ts ON rate_limits(key, timestamp)")
                        conn.commit()
                    finally:
                        conn.close()
                self._initialized = True
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to initialize SQLite rate limit table: %s", e)

    def allow(self) -> bool:
        self._ensure_table()
        from app.config import settings

        backend = settings.STORAGE_BACKEND
        now = time.time()
        cutoff = now - self.window_seconds

        if backend == "postgres":
            try:
                from app.postgres_repository import _conn, _execute, _fetch_one

                with _conn() as conn:
                    # Prune old entries
                    _execute(conn, "DELETE FROM rate_limits WHERE key = %s AND timestamp <= %s", (self.key, cutoff))
                    # Check current count
                    row = _fetch_one(conn, "SELECT COUNT(*) AS count FROM rate_limits WHERE key = %s", (self.key,))
                    count = row["count"] if row else 0
                    if count >= self.max_requests:
                        return False
                    # Insert new request timestamp
                    _execute(conn, "INSERT INTO rate_limits (key, timestamp) VALUES (%s, %s)", (self.key, now))
                return True
            except Exception as e:  # noqa: BLE001
                logger.warning("Postgres rate limiter database error: %s. Falling back to in-memory behavior.", e)
                return self._fallback_counter.allow()
        else:
            try:
                from app.job_store import _DB_LOCK, _get_connection

                with _DB_LOCK:
                    conn = _get_connection()
                    try:
                        # Prune old entries
                        conn.execute("DELETE FROM rate_limits WHERE key = ? AND timestamp <= ?", (self.key, cutoff))
                        # Check current count
                        row = conn.execute("SELECT COUNT(*) AS count FROM rate_limits WHERE key = ?", (self.key,)).fetchone()
                        count = row["count"] if row else 0
                        if count >= self.max_requests:
                            return False
                        # Insert new request timestamp
                        conn.execute("INSERT INTO rate_limits (key, timestamp) VALUES (?, ?)", (self.key, now))
                        conn.commit()
                    finally:
                        conn.close()
                return True
            except Exception as e:  # noqa: BLE001
                logger.warning("SQLite rate limiter database error: %s. Falling back to in-memory behavior.", e)
                return self._fallback_counter.allow()

    def remaining(self) -> int:
        self._ensure_table()
        from app.config import settings

        backend = settings.STORAGE_BACKEND
        now = time.time()
        cutoff = now - self.window_seconds

        if backend == "postgres":
            try:
                from app.postgres_repository import _conn, _execute, _fetch_one

                with _conn() as conn:
                    _execute(conn, "DELETE FROM rate_limits WHERE key = %s AND timestamp <= %s", (self.key, cutoff))
                    row = _fetch_one(conn, "SELECT COUNT(*) AS count FROM rate_limits WHERE key = %s", (self.key,))
                    count = row["count"] if row else 0
                    return max(0, self.max_requests - count)
            except Exception:  # noqa: BLE001
                return self._fallback_counter.remaining()
        else:
            try:
                from app.job_store import _DB_LOCK, _get_connection

                with _DB_LOCK:
                    conn = _get_connection()
                    try:
                        conn.execute("DELETE FROM rate_limits WHERE key = ? AND timestamp <= ?", (self.key, cutoff))
                        row = conn.execute("SELECT COUNT(*) AS count FROM rate_limits WHERE key = ?", (self.key,)).fetchone()
                        count = row["count"] if row else 0
                        return max(0, self.max_requests - count)
                    finally:
                        conn.close()
            except Exception:  # noqa: BLE001
                return self._fallback_counter.remaining()

    def reset_in(self) -> float:
        self._ensure_table()
        from app.config import settings

        backend = settings.STORAGE_BACKEND
        now = time.time()

        if backend == "postgres":
            try:
                from app.postgres_repository import _conn, _fetch_one

                with _conn() as conn:
                    row = _fetch_one(conn, "SELECT MIN(timestamp) AS min_ts FROM rate_limits WHERE key = %s", (self.key,))
                    min_ts = row["min_ts"] if row and row.get("min_ts") is not None else None
                    if min_ts is None:
                        return 0.0
                    return max(0.0, self.window_seconds - (now - min_ts))  # type: ignore[no-any-return]
            except Exception:  # noqa: BLE001
                return self._fallback_counter.reset_in()
        else:
            try:
                from app.job_store import _DB_LOCK, _get_connection

                with _DB_LOCK:
                    conn = _get_connection()
                    try:
                        row = conn.execute(
                            "SELECT MIN(timestamp) AS min_ts FROM rate_limits WHERE key = ?",
                            (self.key,),
                        ).fetchone()
                        min_ts = row["min_ts"] if row and row[0] is not None else None
                        if min_ts is None:
                            return 0.0
                        return max(0.0, self.window_seconds - (now - min_ts))  # type: ignore[no-any-return]
                    finally:
                        conn.close()
            except Exception:  # noqa: BLE001
                return self._fallback_counter.reset_in()

    def is_expired(self) -> bool:
        return False


class SlidingWindowCounter:
    """Sliding window rate limit counter for a single key."""

    __slots__ = ("_timestamps", "max_requests", "window_seconds")

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

    def is_expired(self) -> bool:
        """Check if this counter has no recent activity and can be pruned."""
        if not self._timestamps:
            return True
        cutoff = time.time() - self.window_seconds
        return all(t <= cutoff for t in self._timestamps)


class RateLimiterMiddleware:
    """In-memory sliding window rate limiter for FastAPI.

    Applies a global rate limit across all /api/ endpoints,
    plus optional stricter limits for specific route patterns.

    Safe IP extraction:
    - Only trusts X-Forwarded-For when the connection comes from localhost / 127.0.0.1
      (i.e., through nginx on the same machine or Docker network).
    - In all other cases, falls back to the direct remote address.
    """

    def __init__(
        self,
        global_limit: str = "",
        per_ip: bool = True,
        cleanup_interval: int = 300,
    ) -> None:
        self._global_max, self._global_window = _parse_rate_limit(global_limit)
        self._per_ip = per_ip
        self._counters: dict[str, SlidingWindowCounter | DatabaseSlidingWindowCounter] = {}
        self._last_cleanup = time.time()
        self._cleanup_interval = cleanup_interval  # seconds between TTL cleanups

        if self._global_max > 0:
            logger.info(
                "Rate limiter: %d requests per %.0fs (global), cleanup every %ds",
                self._global_max,
                self._global_window,
                self._cleanup_interval,
            )
        else:
            logger.info("Rate limiter: disabled")

    @staticmethod
    def _extract_client_ip(request: Request) -> str:
        """Extract the client IP safely.

        Trusts X-Forwarded-For ONLY when the direct connection comes from
        a trusted internal address (localhost, Docker subnet). This prevents
        IP spoofing by external clients.

        Falls back to the direct TCP remote address.
        """
        client_host = request.client.host if request.client else ""
        if not client_host:
            return "unknown"

        # Only trust X-Forwarded-For when the immediate peer is internal
        try:
            peer_ip = ipaddress.ip_address(client_host)
            is_trusted_proxy = peer_ip.is_private or peer_ip.is_loopback
        except ValueError:
            is_trusted_proxy = client_host == "localhost"

        if is_trusted_proxy:
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                # Take the first (original client) IP from the chain
                return forwarded.split(",")[0].strip()

        return client_host

    def _get_client_key(self, path: str, method: str, client_ip: str | None = None) -> str:
        """Build a composite key from client identity and route pattern."""
        if client_ip is None:
            client_ip = method
            method = "POST"
        route_key = _get_route_key(path, method)
        return f"{route_key}:{method}:{client_ip}"

    def _get_limits_for_path(self, path: str, method: str = "POST") -> tuple[int, float]:
        """Determine the most restrictive limits for a path.

        Uses the global limit as a baseline, then applies route-specific
        limits if they are stricter (smaller max or same max with shorter window).
        """
        route_key = _get_route_key(path, method)
        limits = _get_effective_route_limits(method)
        if route_key in limits:
            route_max, route_window = limits[route_key]
            if self._global_max <= 0:
                return route_max, route_window
            # Use the stricter of global vs route-specific limits
            if route_max < self._global_max:
                return route_max, min(route_window, self._global_window)
            if route_window < self._global_window:
                return min(route_max, self._global_max), route_window
        return self._global_max, self._global_window

    def _prune_expired_counters(self) -> None:
        """Remove expired counters to prevent unbounded memory growth.

        Runs periodically based on cleanup_interval.
        """
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        before = len(self._counters)
        self._counters = {k: v for k, v in self._counters.items() if not v.is_expired()}
        after = len(self._counters)
        if before > after:
            logger.debug("Rate limiter: pruned %d expired counter(s)", before - after)

    async def middleware(self, request: Request, call_next: Callable) -> Response:
        """ASGI middleware dispatch."""
        if self._global_max <= 0:
            return await call_next(request)  # type: ignore[no-any-return]

        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)  # type: ignore[no-any-return]

        if "/docs" in path or "/openapi" in path:
            return await call_next(request)  # type: ignore[no-any-return]

        # Prune expired counters periodically
        self._prune_expired_counters()

        # Determine client identity
        client_ip = self._extract_client_ip(request)
        method = request.method

        # Build per-route, per-IP limit key
        key = self._get_client_key(path, method, client_ip) if self._per_ip else f"{_get_route_key(path, method)}:{method}"

        # Get limits for this route (stricter of global and route-specific)
        max_req, window_sec = self._get_limits_for_path(path, method)
        if max_req <= 0:
            return await call_next(request)  # type: ignore[no-any-return]

        # Get or create counter
        if key not in self._counters:
            from app.config import settings

            if settings.RATE_LIMIT_DB_BACKED:
                self._counters[key] = DatabaseSlidingWindowCounter(max_req, window_sec, key)
            else:
                self._counters[key] = SlidingWindowCounter(max_req, window_sec)
        counter = self._counters[key]

        # Check rate limit
        if not counter.allow():
            logger.warning(
                "Rate limit exceeded for %s on %s (%d/%d per %.0fs)",
                client_ip,
                path,
                counter.remaining(),
                max_req,
                window_sec,
            )
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

        return response  # type: ignore[no-any-return]

    def get_stats(self) -> dict:
        """Return current rate limiter stats (for observability)."""
        return {
            "enabled": self._global_max > 0,
            "limit_per_window": self._global_max,
            "window_seconds": self._global_window,
            "active_keys": len(self._counters),
            "route_limits": {k: {"max_requests": v[0], "window_seconds": v[1]} for k, v in _get_effective_route_limits().items()},
        }

    def reset(self) -> None:
        """Clear all counters (for testing)."""
        self._counters.clear()
