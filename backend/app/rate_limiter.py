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
            except Exception as e:
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
            except Exception as e:
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
                    # Prune old entries first; safe in the same
                    # transaction as the count+insert below.
                    _execute(conn, "DELETE FROM rate_limits WHERE key = %s AND timestamp <= %s", (self.key, cutoff))
                    # Atomic count+insert: the CTE selects the current
                    # count and the outer INSERT runs only when the
                    # count is strictly less than the limit. The whole
                    # statement is a single SQL command, so two
                    # concurrent requests cannot both see ``count < N``
                    # and both insert. ``RETURNING`` tells us whether
                    # the row was actually written. Postgres supports
                    # this since 9.1 (CTEs) and 9.5 (INSERT...RETURNING
                    # in CTEs).
                    row = _fetch_one(
                        conn,
                        """
                        WITH slot AS (
                            SELECT COUNT(*) AS count
                            FROM rate_limits
                            WHERE key = %s
                        ), inserted AS (
                            INSERT INTO rate_limits (key, timestamp)
                            SELECT %s, %s
                            WHERE (SELECT count FROM slot) < %s
                            RETURNING key
                        )
                        SELECT (SELECT count FROM slot) AS count,
                               EXISTS (SELECT 1 FROM inserted) AS allowed
                        """,
                        (self.key, self.key, now, self.max_requests),
                    )
                if not row or not row.get("allowed"):
                    return False
                return True
            except Exception as e:
                logger.warning("Postgres rate limiter database error: %s. Falling back to in-memory behavior.", e)
                return self._fallback_counter.allow()
        else:
            try:
                from app.job_store import _DB_LOCK, _get_connection

                with _DB_LOCK:
                    conn = _get_connection()
                    try:
                        # BEGIN IMMEDIATE acquires the writer lock at
                        # the start of the transaction, so the
                        # count+insert below runs without any other
                        # connection being able to interleave. This
                        # closes the time-of-check / time-of-use race
                        # between ``SELECT COUNT`` and ``INSERT`` that
                        # the previous implementation had. SQLite
                        # does not support atomic count+insert via a
                        # CTE the way Postgres does, so the explicit
                        # write lock is the portable alternative.
                        conn.execute("BEGIN IMMEDIATE")
                        # Prune old entries first.
                        conn.execute("DELETE FROM rate_limits WHERE key = ? AND timestamp <= ?", (self.key, cutoff))
                        # Check current count.
                        row = conn.execute("SELECT COUNT(*) AS count FROM rate_limits WHERE key = ?", (self.key,)).fetchone()
                        count = row["count"] if row else 0
                        if count >= self.max_requests:
                            conn.execute("COMMIT")
                            return False
                        # Insert new request timestamp.
                        conn.execute("INSERT INTO rate_limits (key, timestamp) VALUES (?, ?)", (self.key, now))
                        conn.execute("COMMIT")
                    finally:
                        conn.close()
                return True
            except Exception as e:
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
            except Exception:
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
            except Exception:
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
            except Exception:
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
            except Exception:
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
    """Sliding window rate limiter for FastAPI with dual-layer support.

    Applies an **aggregate global** rate limit across all /api/ endpoints,
    plus optional **per-IP** limits that are enforced independently for each
    client. A request must pass BOTH tiers to proceed.

    Features:
    - Aggregate global cap across all clients combined
    - Per-IP cap for fair sharing across clients
    - Route-specific stricter limits for expensive endpoints
    - In-memory counters for single-process deployments
    - Database-backed counters (``DatabaseSlidingWindowCounter``) for
      multi-process / multi-worker deployments
    - Safe IP extraction behind nginx reverse proxy

    Safe IP extraction:
    - Only trusts X-Forwarded-For when the connection comes from localhost / 127.0.0.1
      (i.e., through nginx on the same machine or Docker network).
    - In all other cases, falls back to the direct remote address.

    Usage:
        rate_limiter = RateLimiterMiddleware(
            global_limit="10000/minute",
            per_ip=True,
            per_ip_limit="100/minute",
        )
        app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limiter.middleware)
    """

    def __init__(
        self,
        global_limit: str = "",
        per_ip: bool = True,
        per_ip_limit: str = "",
        cleanup_interval: int = 300,
    ) -> None:
        self._global_max, self._global_window = _parse_rate_limit(global_limit)
        self._per_ip = per_ip
        self._per_ip_max, self._per_ip_window = _parse_rate_limit(per_ip_limit)
        self._counters: dict[str, SlidingWindowCounter | DatabaseSlidingWindowCounter] = {}
        self._last_cleanup = time.time()
        self._cleanup_interval = cleanup_interval

        if self._global_max > 0 or self._per_ip_max > 0:
            logger.info(
                "Rate limiter: global=%d/%.0fs per_ip=%s/%.0fs (per_ip_enabled=%s) cleanup=%ds",
                self._global_max,
                self._global_window,
                self._per_ip_max,
                self._per_ip_window,
                self._per_ip,
                self._cleanup_interval,
            )
        else:
            logger.info("Rate limiter: disabled")

    # ── IP extraction ──────────────────────────────────────────────────

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

        try:
            peer_ip = ipaddress.ip_address(client_host)
            is_trusted_proxy = peer_ip.is_private or peer_ip.is_loopback
        except ValueError:
            is_trusted_proxy = client_host == "localhost"

        if is_trusted_proxy:
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",")[0].strip()

        return client_host

    # ── Key building ───────────────────────────────────────────────────

    def _get_aggregate_key(self, path: str, method: str) -> str:
        """Composite key for the aggregate (global) counter."""
        route_key = _get_route_key(path, method)
        return f"_global:{route_key}:{method}"

    def _get_per_ip_key(self, path: str, method: str, client_ip: str) -> str:
        """Composite key for the per-IP counter."""
        route_key = _get_route_key(path, method)
        return f"{route_key}:{method}:{client_ip}"

    # ── Limit resolution ───────────────────────────────────────────────

    def _get_limits_for_path(self, path: str, method: str = "POST") -> tuple[int, float]:
        """Resolve the effective limit for a path by merging global and
        route-specific caps. Returns (max_requests, window_seconds)."""
        route_key = _get_route_key(path, method)
        limits = _get_effective_route_limits(method)
        if route_key in limits:
            route_max, route_window = limits[route_key]
            if self._global_max <= 0:
                return route_max, route_window
            if route_max < self._global_max:
                return route_max, min(route_window, self._global_window)
            if route_window < self._global_window:
                return min(route_max, self._global_max), route_window
        return self._global_max, self._global_window

    # ── Counter lifecycle ──────────────────────────────────────────────

    def _get_or_create_counter(
        self, key: str, max_req: int, window_sec: float
    ) -> SlidingWindowCounter | DatabaseSlidingWindowCounter:
        """Get an existing counter or create a new one.

        Uses ``DatabaseSlidingWindowCounter`` when ``RATE_LIMIT_DB_BACKED``
        is True, otherwise falls back to in-memory ``SlidingWindowCounter``.
        """
        if key in self._counters:
            return self._counters[key]

        from app.config import settings

        if settings.RATE_LIMIT_DB_BACKED:
            counter: SlidingWindowCounter | DatabaseSlidingWindowCounter = DatabaseSlidingWindowCounter(max_req, window_sec, key)
        else:
            counter = SlidingWindowCounter(max_req, window_sec)
        self._counters[key] = counter
        return counter

    def _prune_expired_counters(self) -> None:
        """Remove expired counters to prevent unbounded memory growth."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        before = len(self._counters)
        self._counters = {k: v for k, v in self._counters.items() if not v.is_expired()}
        after = len(self._counters)
        if before > after:
            logger.debug("Rate limiter: pruned %d expired counter(s)", before - after)

    # ── Rate-limit response builder ───────────────────────────────────

    def _build_429_response(
        self, counter: SlidingWindowCounter | DatabaseSlidingWindowCounter, client_ip: str, path: str
    ) -> JSONResponse:
        """Build a 429 Too Many Requests response with standard headers."""
        logger.warning(
            "Rate limit exceeded for %s on %s (%d/%d per %.0fs)",
            client_ip,
            path,
            counter.remaining(),
            counter.max_requests,
            counter.window_seconds,
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

    def _add_rate_limit_headers(self, response: Response, counter: SlidingWindowCounter | DatabaseSlidingWindowCounter) -> None:
        """Attach rate-limit metadata headers to the outgoing response."""
        try:
            response.headers["X-RateLimit-Limit"] = str(counter.max_requests)
            response.headers["X-RateLimit-Remaining"] = str(counter.remaining())
            response.headers["X-RateLimit-Reset"] = str(int(time.time() + counter.reset_in()))
        except (AttributeError, TypeError, ValueError):
            pass

    # ── Main middleware dispatch ───────────────────────────────────────

    async def middleware(self, request: Request, call_next: Callable) -> Response:
        """ASGI middleware dispatch with dual-layer rate limiting.

        A request must pass **both** the aggregate global counter and
        the per-IP counter (if enabled) to proceed. If either is
        exceeded, a 429 response is returned immediately.
        """
        if self._global_max <= 0 and not (self._per_ip and self._per_ip_max > 0):
            return await call_next(request)  # type: ignore[no-any-return]

        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)  # type: ignore[no-any-return]

        if "/docs" in path or "/openapi" in path:
            return await call_next(request)  # type: ignore[no-any-return]

        self._prune_expired_counters()

        client_ip = self._extract_client_ip(request)
        method = request.method

        # ── Tier 1: Aggregate global counter ───────────────────────
        if self._global_max > 0:
            agg_key = self._get_aggregate_key(path, method)
            agg_limit = self._get_limits_for_path(path, method)
            agg_counter = self._get_or_create_counter(agg_key, *agg_limit)

            if not agg_counter.allow():
                return self._build_429_response(agg_counter, client_ip, path)

        # ── Tier 2: Per-IP counter ─────────────────────────────────
        # The per-IP tier is a pure fair-sharing cap — it uses ONLY the
        # configured ``per_ip_limit`` and does NOT apply route-specific
        # overrides (which are already enforced by the aggregate tier).
        # This keeps the two tiers cleanly separated:
        #   Tier 1 = aggregate (global + route-specific)
        #   Tier 2 = fair-share (per-IP only)
        active_per_ip_counter: SlidingWindowCounter | DatabaseSlidingWindowCounter | None = None
        if self._per_ip and self._per_ip_max > 0:
            ip_key = self._get_per_ip_key(path, method, client_ip)
            ip_counter = self._get_or_create_counter(ip_key, self._per_ip_max, self._per_ip_window)
            active_per_ip_counter = ip_counter

            if not ip_counter.allow():
                return self._build_429_response(ip_counter, client_ip, path)

        # ── Proceed with the request ───────────────────────────────
        response = await call_next(request)

        # Add rate limit headers from the per-IP counter (most relevant to clients)
        if active_per_ip_counter is not None:
            self._add_rate_limit_headers(response, active_per_ip_counter)
        elif self._global_max > 0:
            agg_counter = self._get_or_create_counter(
                self._get_aggregate_key(path, method),
                *self._get_limits_for_path(path, method),
            )
            self._add_rate_limit_headers(response, agg_counter)

        return response  # type: ignore[no-any-return]

    def get_stats(self) -> dict:
        """Return current rate limiter stats (for observability)."""
        return {
            "enabled": self._global_max > 0 or (self._per_ip and self._per_ip_max > 0),
            "global_limit_per_window": self._global_max,
            "global_window_seconds": self._global_window,
            "per_ip_enabled": self._per_ip,
            "per_ip_limit_per_window": self._per_ip_max,
            "per_ip_window_seconds": self._per_ip_window,
            "active_keys": len(self._counters),
            "route_limits": {k: {"max_requests": v[0], "window_seconds": v[1]} for k, v in _get_effective_route_limits().items()},
        }

    def reset(self) -> None:
        """Clear all counters (for testing)."""
        self._counters.clear()
