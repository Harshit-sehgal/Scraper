"""Rate Limiter — in-memory sliding window rate limiting middleware.

Provides per-IP rate limiting for API endpoints without
external dependencies. Uses a sliding window counter approach.

Supports:
- Global rate limit across all /api/ endpoints
- Route-specific stricter limits for expensive endpoints
- Safe IP extraction (behind nginx reverse proxy only)
- TTL-based cleanup to prevent unbounded counter map growth
- RFC 6585 X-RateLimit-* headers on every API response
- Per-user job concurrency caps (JobRateLimiter)
- Per-job domain request delays with cooldown integration

Usage:
    from app.rate_limiter import RateLimiterMiddleware

    rate_limiter = RateLimiterMiddleware(global_limit="100 / minute")
    app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limiter.middleware)
"""

from __future__ import annotations

import ipaddress
import logging
import os
import sqlite3
import threading
import time
from typing import TYPE_CHECKING, Any

from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import Request, Response

logger = logging.getLogger(__name__)

# Collect DB exception types for fallback handling in rate-limit counter
# operations so we don't swallow programming errors with bare except Exception.
_DB_FALLBACK_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    RuntimeError,
    ImportError,
    ValueError,
    sqlite3.Error,  # type: ignore[misc]
)

try:
    from psycopg2 import Error as _Psycopg2Error

    _DB_FALLBACK_ERRORS = (*_DB_FALLBACK_ERRORS, _Psycopg2Error)
except ImportError as exc:
    logger.debug("Optional psycopg2 driver not available: %s", exc)

try:
    from psycopg import Error as _Psycopg3Error

    _DB_FALLBACK_ERRORS = (*_DB_FALLBACK_ERRORS, _Psycopg3Error)
except ImportError as exc:
    logger.debug("Optional psycopg (v3) driver not available: %s", exc)


# ─── H5: Redis-backed rate limiting for distributed deployments ────────
# When Redis is configured but unreachable, the limiter must NEVER
# silently fail open: a brief Redis outage would otherwise disable rate
# limiting across the fleet. Instead we keep an in-memory per-process
# counter so a single process at least bounds its own load, and emit a
# metric so operators can observe the degraded mode.
_REDIS_FAIL_OPEN_FALLBACK_LIMIT = 10_000  # degraded-mode global ceiling per process
_REDIS_FALLBACK_COUNTERS_MAX = 50_000  # OOM guard: evict oldest entries above this size
_redis_fail_open_count = 0
_redis_fail_open_lock = None
_redis_fallback_counters: dict[str, int] = {}

# F-RL-006: import-time guard against the TOCTOU race in
# ``_get_redis_fail_open_lock``.  Without a module-level init guard,
# two concurrent threads could both see ``None``, each allocate a fresh
# ``threading.Lock()``, and the slower writer's Lock instance would
# overwrite the one other threads already acquired — silently breaking
# mutual exclusion on ``_redis_fail_open_count``.
import threading as _rl_threading

_redis_fail_open_lock_init_guard = _rl_threading.Lock()


def _get_redis_fail_open_lock() -> Any:
    """Lazily allocate the fail-open tracker lock (avoids module-import
    side-effects for cold-start imports / test rigs that never touch Redis).
    """
    global _redis_fail_open_lock
    if _redis_fail_open_lock is not None:
        return _redis_fail_open_lock

    with _redis_fail_open_lock_init_guard:
        if _redis_fail_open_lock is None:
            _redis_fail_open_lock = _rl_threading.Lock()
    return _redis_fail_open_lock


class RedisRateLimiter:
    """H5: Distributed rate limiting using Redis for multi-worker deployments."""

    def __init__(self, redis_url: str = ""):
        self.redis_url = redis_url or os.environ.get("DATAFORGE_REDIS_URL", "")
        self.redis = None
        if self.redis_url:
            try:
                import redis

                self.redis = redis.from_url(self.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
                self.redis.ping()
                logger.info("H5: Redis rate limiter initialized: %s", self.redis_url[:20])
            except Exception as e:
                logger.warning("H5: Redis connection failed, falling back to in-memory degraded mode: %s", e)
                self.redis = None

    def allow(self, key: str, limit: int, window: int) -> bool:
        """H5: Check if request within limit; uses Redis INCR with TTL.

        When Redis is unreachable we DO NOT fail open (a brief outage
        must not disable rate limiting across the fleet). Instead we
        keep an in-memory per-process counter and a hard ceiling so the
        worst case is a process-local degenerate limit of
        ``_REDIS_FAIL_OPEN_FALLBACK_LIMIT`` requests.
        """
        if not self.redis:
            return _redis_fallback_check(key, limit, window, primary_unavailable=True)
        try:
            rate_key = f"rate:{key}"
            count = self.redis.incr(rate_key)
            if count == 1:
                self.redis.expire(rate_key, window)
            return count <= limit
        except Exception as e:
            # A transient Redis failure must not disable rate limiting
            # globally; switch to in-process fallback rather than
            # silently allow every request through. The previous
            # ``return True`` behaviour left a single process exposed
            # to unbounded request load during the outage window.
            logger.warning(
                "H5: Redis check failed, switching to in-process fallback: %s",
                e,
            )
            return _redis_fallback_check(key, limit, window, primary_unavailable=False)


def _redis_fallback_check(key: str, limit: int, window: int, primary_unavailable: bool) -> bool:
    """Per-process fallback rate-limit when Redis is unavailable.

    Bounded counter, expensive-windowed cleanup is intentionally omitted
    because this code path is reserved for genuine outages — operators
    must see the fail-open metric and act.  Resets on the next ``reset_redis_fail_open()``
    invocation or process restart.
    """
    global _redis_fail_open_count
    lock = _get_redis_fail_open_lock()
    with lock:
        if primary_unavailable:
            _redis_fail_open_count += 1
        rate_key = f"redis-fallback:{key}"
        current = _redis_fallback_counters.get(rate_key, 0) + 1
        _redis_fallback_counters[rate_key] = current
        # Evict oldest entries when the dict exceeds the cap, preventing
        # an attacker from OOM-ing the process by spraying unique IPs
        # during a Redis outage.  Arbitrary but stable eviction: drop
        # the first 25% of keys (ordered by insertion).
        if len(_redis_fallback_counters) > _REDIS_FALLBACK_COUNTERS_MAX:
            evict_count = len(_redis_fallback_counters) // 4
            keys_to_evict = list(_redis_fallback_counters.keys())[:evict_count]
            for k in keys_to_evict:
                del _redis_fallback_counters[k]
        # Reset the per-key counter every ``window`` seconds by
        # computing against a stored deadline — kept simple here
        # because this fallback is itself a degraded mode; the global
        # ceiling below is the actual safety net.
        return current <= min(limit, _REDIS_FAIL_OPEN_FALLBACK_LIMIT)


def get_redis_fail_open_count() -> int:
    """How many times the Redis rate-limiter has fallen back to in-process mode.

    Process-local — restart resets. Surface in metrics to detect Redis
    outages that compound across worker restarts.
    """
    lock = _get_redis_fail_open_lock()
    with lock:
        return _redis_fail_open_count


def reset_redis_fail_open_count() -> None:
    lock = _get_redis_fail_open_lock()
    with lock:
        global _redis_fail_open_count
        _redis_fail_open_count = 0


# ─── Trusted-proxy allowlist ──────────────────────────────────────────
# Only TCP peers whose address is in this list may inject X-Forwarded-For
# headers. The previous default of ``127.0.0.0/8`` + RFC1918 ranges
# (10/8, 172.16/12, 192.168/16) meant any neighbour inside the same VPC
# could forge XFF values and evade per-IP rate limits. Operators must now
# set ``DATAFORGE_TRUSTED_PROXIES`` explicitly to the exact CIDR list of
# the load balancer / reverse proxy that fronts the API.  The new
# default is loopback only, which is correct for single-host deployments
# (nginx on the same machine) but secure in any environment: peers
# outside loopback cannot inject XFF.
# Production deployments MUST set the env var; an earnest ``WARNING``
# fires at startup if it is not configured.
_LOOPBACK_ONLY_DEFAULT = "127.0.0.0/8,::1/128"
_TRUSTED_PROXIES_ENV = (os.environ.get("DATAFORGE_TRUSTED_PROXIES") or _LOOPBACK_ONLY_DEFAULT).strip()
_TRUSTED_PROXY_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(cidr.strip(), strict=False) for cidr in _TRUSTED_PROXIES_ENV.split(",") if cidr.strip()
)
if not os.environ.get("DATAFORGE_TRUSTED_PROXIES"):
    # Use the explicit-default banner so operators recognise they
    # have *not* opted in to broader ranges.
    logger.warning(
        "DATAFORGE_TRUSTED_PROXIES is unset — trusted-proxy list "
        "defaults to LOOPBACK ONLY (%s). Any peers outside loopback "
        "cannot inject X-Forwarded-For, but legitimate proxy hops "
        "across VPCs / containers will be IGNORED. Set the env var "
        "explicitly if your reverse proxy is not on the same host.",
        _LOOPBACK_ONLY_DEFAULT,
    )


def _is_trusted_proxy(client_host: str) -> bool:
    """Return True when ``client_host`` is in the configured trusted-proxy allowlist."""
    if not client_host:
        return False
    try:
        peer = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    return any(peer in net for net in _TRUSTED_PROXY_NETWORKS)


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
    if (
        hasattr(settings, "RATE_LIMIT_JOB_CREATE")
        and settings.RATE_LIMIT_JOB_CREATE
        and (method is None or method.upper() == "POST")
    ):
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

    Supported formats: N / second, N / minute, N / hour. Whitespace around
    the ``/`` separator is tolerated so ``"100 / minute"`` parses the same
    as ``"100/minute"`` — the function is the single point of truth for
    translating the human-readable config string into a windowed counter.
    Returns (max_requests, window_seconds), or (0, 0) if invalid.
    """
    if not limit_str or not isinstance(limit_str, str):
        return 0, 0

    limit_str = limit_str.strip().lower()
    parts = limit_str.split("/")
    if len(parts) != 2:
        return 0, 0

    try:
        max_requests = int(parts[0].strip())
    except ValueError:
        return 0, 0

    unit = parts[1].strip()
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
        # L10: explicit last-access timestamp so the LRU eviction in
        # ``_get_or_create_counter`` works for DB-backed counters the
        # same way it does for in-memory ones. Without it every DB
        # counter ties at 0.0 and ``min()`` deterministically picks
        # whichever happens to be first in dict iteration order —
        # effectively single-key churn under attack traffic.
        self._last_access: float = time.time()

    def _touch(self) -> None:
        """Stamp the counter as freshly used for LRU eviction."""
        self._last_access = time.time()

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
            except _DB_FALLBACK_ERRORS as e:
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
            except _DB_FALLBACK_ERRORS as e:
                logger.warning("Failed to initialize SQLite rate limit table: %s", e)

    def allow(self) -> bool:
        # L10: update the LRU stamp for DB-backed counters as soon as
        # they're touched, so eviction is no longer biased toward them.
        self._touch()
        self._ensure_table()
        from app.config import settings

        backend = settings.STORAGE_BACKEND
        now = time.time()
        cutoff = now - self.window_seconds

        if backend == "postgres":
            try:
                from app.postgres_repository import _conn, _execute, _fetch_one

                with _conn() as conn:
                    # Cross-connection contract: the rate_limits table is
                    # shared across every API replica. The CTE-based
                    # count+insert is atomic *within a single statement*,
                    # but two API replicas running the same query at the
                    # same time can both observe ``count < N`` and both
                    # insert (the snapshot is statement-local, not
                    # transaction-locked against concurrent writers).
                    # To make the count+insert mutually exclusive we
                    # take a Postgres transaction-scoped advisory lock
                    # keyed by ``self.key`` before counting. The lock
                    # is released automatically when the connection
                    # returns to the pool, so we never need an explicit
                    # unlock. The key is hashed into a 64-bit signed
                    # integer so the same logical bucket always maps to
                    # the same lock across replicas. The SQLite path
                    # below uses ``BEGIN IMMEDIATE`` for the same
                    # mutual-exclusion guarantee.
                    _execute(
                        conn,
                        "SELECT pg_advisory_xact_lock(hashtext(%s))",
                        (self.key,),
                    )
                    # Prune old entries first; safe in the same
                    # transaction as the count+insert below.
                    _execute(
                        conn,
                        "DELETE FROM rate_limits WHERE key = %s AND timestamp <= %s",
                        (self.key, cutoff),
                    )
                    # Atomic count+insert: the CTE selects the current
                    # count and the outer INSERT runs only when the
                    # count is strictly less than the limit. The whole
                    # statement runs after we've taken the advisory
                    # lock above, so two concurrent requests on
                    # different connections cannot both see ``count < N``
                    # and both insert. ``RETURNING`` tells us whether
                    # the row was actually written.
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
                return bool(row and row.get("allowed"))
            except _DB_FALLBACK_ERRORS as e:
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
            except _DB_FALLBACK_ERRORS as e:
                logger.warning("SQLite rate limiter database error: %s. Falling back to in-memory behavior.", e)
                return self._fallback_counter.allow()

    def remaining(self) -> int:
        self._touch()
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
            except _DB_FALLBACK_ERRORS as e:
                logger.warning("Postgres rate limiter remaining() failed: %s", e)
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
            except _DB_FALLBACK_ERRORS as e:
                logger.warning("SQLite rate limiter remaining() failed: %s", e)
                return self._fallback_counter.remaining()

    def reset_in(self) -> float:
        self._touch()
        self._ensure_table()
        from app.config import settings

        backend = settings.STORAGE_BACKEND
        now = time.time()

        if backend == "postgres":
            try:
                from app.postgres_repository import _conn, _fetch_one

                with _conn() as conn:
                    row = _fetch_one(conn, "SELECT MIN(timestamp) AS min_ts FROM rate_limits WHERE key = %s", (self.key,))
                    min_ts = row["min_ts"] if row is not None and row["min_ts"] is not None else None
                    if min_ts is None:
                        return 0.0
                    return max(0.0, self.window_seconds - (now - min_ts))  # type: ignore[no-any-return]
            except _DB_FALLBACK_ERRORS as e:
                logger.warning("Postgres rate limiter reset_in() failed: %s", e)
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
                        min_ts = row["min_ts"] if row is not None and row["min_ts"] is not None else None
                        if min_ts is None:
                            return 0.0
                        return max(0.0, self.window_seconds - (now - min_ts))  # type: ignore[no-any-return]
                    finally:
                        conn.close()
            except _DB_FALLBACK_ERRORS as e:
                logger.warning("SQLite rate limiter reset_in() failed: %s", e)
                return self._fallback_counter.reset_in()

    def is_expired(self) -> bool:
        """Check if this DB-backed counter has any recent entries for its key."""
        if not self._initialized:
            return True
        from app.config import settings

        backend = settings.STORAGE_BACKEND
        now = time.time()
        cutoff = now - self.window_seconds

        if backend == "postgres":
            try:
                from app.postgres_repository import _conn, _fetch_one

                with _conn() as conn:
                    row = _fetch_one(
                        conn,
                        "SELECT 1 AS alive FROM rate_limits WHERE key = %s AND timestamp > %s LIMIT 1",
                        (self.key, cutoff),
                    )
                    return row is None
            except _DB_FALLBACK_ERRORS as e:
                logger.warning("Postgres rate limiter is_expired() failed: %s", e)
                return True
        else:
            try:
                from app.job_store import _DB_LOCK, _get_connection

                with _DB_LOCK:
                    conn = _get_connection()
                    try:
                        row = conn.execute(
                            "SELECT 1 FROM rate_limits WHERE key = ? AND timestamp > ? LIMIT 1",
                            (self.key, cutoff),
                        ).fetchone()
                        return row is None
                    finally:
                        conn.close()
            except _DB_FALLBACK_ERRORS as e:
                logger.warning("SQLite rate limiter is_expired() failed: %s", e)
                return True

    @staticmethod
    def prune_all(max_age_seconds: float = 3600.0) -> int:
        """Delete all rate_limits rows older than ``max_age_seconds`` across every key.

        Returns the count of remaining rows after pruning (caller uses this
        only for debug logging). Called periodically by the rate limiter
        middleware's ``_prune_expired_counters()`` to prevent the
        ``rate_limits`` table from accumulating orphaned rows for keys that
        are no longer active. The default retention is 1 hour (3600s),
        which is well beyond the longest rate-limit window (1 hour).

        Safe to call before any ``_ensure_table()`` has run — the SQL
        ``DELETE`` is a no-op on a missing table (Postgres returns 0;
        SQLite silently ignores).
        """
        # L5: broaden the error filter to cover lazy-import +
        # settings-resolution failures that aren't DB-specific. The
        # previous ``_DB_FALLBACK_ERRORS`` tuple masked these but let
        # other tunexpected attributes fall through unfettered.
        try:
            from app.config import settings

            backend = settings.STORAGE_BACKEND
        except (AttributeError, KeyError, ImportError, RuntimeError, OSError, ValueError, TypeError) as e:
            logger.debug("rate_limits prune_all: settings unavailable: %s", e)
            return 0

        cutoff = time.time() - max_age_seconds

        if backend == "postgres":
            try:
                from app.postgres_repository import _conn, _execute, _fetch_one

                with _conn() as conn:
                    _execute(conn, "DELETE FROM rate_limits WHERE timestamp <= %s", (cutoff,))
                    remaining = _fetch_one(conn, "SELECT COUNT(*) AS c FROM rate_limits")
                    return remaining["c"] if remaining else 0
            except _DB_FALLBACK_ERRORS:
                logger.debug("Postgres rate_limits prune_all failed")
                return 0
        else:
            result = 0
            try:
                from app.job_store import _DB_LOCK, _get_connection

                with _DB_LOCK:
                    conn = _get_connection()
                    try:
                        conn.execute("DELETE FROM rate_limits WHERE timestamp <= ?", (cutoff,))
                        row = conn.execute("SELECT COUNT(*) AS c FROM rate_limits").fetchone()
                        result = row["c"] if row else 0
                        conn.commit()
                    finally:
                        conn.close()
            except _DB_FALLBACK_ERRORS:
                logger.debug("SQLite rate_limits prune_all failed")
                return 0
            return result


class SlidingWindowCounter:
    """Sliding window rate limit counter for a single key."""

    __slots__ = ("_last_access", "_lock", "_timestamps", "max_requests", "window_seconds")

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: list[float] = []
        self._last_access: float = time.time()
        # F-RATE-005: thread-safe guard for prune-check-append sequences.
        # Without this, two concurrent coroutines could both pass the
        # len<max check and both append, exceeding the limit by 1+.
        self._lock = threading.Lock()

    def allow(self) -> bool:
        """Check if a request is allowed, and record it if so.

        Returns True if within limit, False if exceeded.
        """
        now = time.time()
        with self._lock:
            self._last_access = now
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
        with self._lock:
            self._last_access = now
            cutoff = now - self.window_seconds
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            return max(0, self.max_requests - len(self._timestamps))

    def reset_in(self) -> float:
        """Seconds until the window resets."""
        with self._lock:
            if not self._timestamps:
                return 0.0
            return max(0.0, self.window_seconds - (time.time() - self._timestamps[0]))

    def is_expired(self) -> bool:
        """Check if this counter has no recent activity and can be pruned."""
        with self._lock:
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
        a trusted proxy in the ``_TRUSTED_PROXY_NETWORKS`` allowlist
        (configurable via ``DATAFORGE_TRUSTED_PROXIES``). The default
        allowlist is the localhost / RFC1918 ranges; tighten it for
        multi-VPC deployments. This prevents IP spoofing by external
        clients and by malicious co-tenants on internal subnets that
        are not part of the proxy chain.

        Falls back to the direct TCP remote address.
        """
        client_host = request.client.host if request.client else ""
        if not client_host:
            return "unknown"

        if _is_trusted_proxy(client_host):
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
        route-specific caps. Returns (max_requests, window_seconds).
        """
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
        self,
        key: str,
        max_req: int,
        window_sec: float,
    ) -> SlidingWindowCounter | DatabaseSlidingWindowCounter:
        """Get an existing counter or create a new one.

        Uses ``DatabaseSlidingWindowCounter`` when ``RATE_LIMIT_DB_BACKED``
        is True, otherwise falls back to in-memory ``SlidingWindowCounter``.

        MEDIUM (#140): LRU cap. Without a bound on the number of
        concurrent counters, an attacker can flood the middleware with
        requests from a large number of distinct IPs, causing unbounded
        ``_counters`` growth and memory exhaustion (DoS).  When the cap
        is hit, the least recently accessed counter is evicted — a
        legitimate client behind the same IP that has been pushed out
        may see one 429 then get a fresh counter on the next request.

        The cap is set via ``DATAFORGE_RATE_LIMITER_MAX_COUNTERS``
        (default 5000), which is sufficient for any reasonable traffic
        pattern — if a deployment is hitting 5000 distinct IPs within
        a window, it is either under attack or needs a bigger fleet
        (and a DB-backed config for shared state).
        """
        if key in self._counters:
            return self._counters[key]

        # Enforce the LRU cap BEFORE allocating a new counter.
        _max = int(os.environ.get("DATAFORGE_RATE_LIMITER_MAX_COUNTERS", "5000"))
        if _max > 0 and len(self._counters) >= _max:
            # Evict the least recently accessed counter.
            try:
                oldest_key = min(
                    self._counters,
                    key=lambda k: getattr(self._counters[k], "_last_access", 0.0),
                )
            except (ValueError, TypeError):
                oldest_key = None
            if oldest_key:
                logger.warning(
                    "Rate limiter: LRU cap (%d) hit; evicting counter for key=%r. "
                    "Consider increasing DATAFORGE_RATE_LIMITER_MAX_COUNTERS or "
                    "enabling RATE_LIMIT_DB_BACKED for shared multi-process state.",
                    _max,
                    oldest_key,
                )
                del self._counters[oldest_key]

        from app.config import settings

        if settings.RATE_LIMIT_DB_BACKED:
            counter: SlidingWindowCounter | DatabaseSlidingWindowCounter = DatabaseSlidingWindowCounter(max_req, window_sec, key)
        else:
            counter = SlidingWindowCounter(max_req, window_sec)
        self._counters[key] = counter
        return counter

    def _prune_expired_counters(self) -> None:
        """Remove expired counters to prevent unbounded memory growth.

        Also prunes stale rows from the shared ``rate_limits`` table
        so that orphaned per-IP entries (from clients that have not
        sent a request in over an hour) do not accumulate indefinitely.
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

        # Global rate_limits table pruning (DB-backed counters).
        # Remove rows older than 1 hour (3600s) across all keys.
        try:
            from app.config import settings

            if settings.RATE_LIMIT_DB_BACKED:
                deleted = DatabaseSlidingWindowCounter.prune_all()
                if deleted:
                    logger.debug("Rate limiter: pruned %d stale rate_limits row(s)", deleted)
        except _DB_FALLBACK_ERRORS:
            logger.debug("Rate limiter: rate_limits table prune_all failed (non-blocking)")

    # ── Rate-limit response builder ───────────────────────────────────

    def _build_429_response(
        self,
        counter: SlidingWindowCounter | DatabaseSlidingWindowCounter,
        client_ip: str,
        path: str,
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
        except (AttributeError, TypeError, ValueError) as exc:
            logger.debug("Could not attach rate-limit headers: %s", exc)

    @staticmethod
    def _add_disabled_rate_limit_headers(response: Response, global_max: int = 0, global_window: float = 0.0) -> None:
        """Attach RFC 6585 rate-limit headers when rate limiting is disabled.

        When no limits are configured, synthesises headers so API clients
        always see a consistent contract.  ``X-RateLimit-Limit`` is set to
        ``0`` (semantics: unlimited / not enforced), Remaining is ``0``
        (no quota tracking), and Reset is the current epoch (no window).
        """
        try:
            if global_max > 0:
                response.headers["X-RateLimit-Limit"] = str(global_max)
                response.headers["X-RateLimit-Remaining"] = str(global_max)
                response.headers["X-RateLimit-Reset"] = str(int(time.time() + global_window))
            else:
                response.headers["X-RateLimit-Limit"] = "0"
                response.headers["X-RateLimit-Remaining"] = "0"
                response.headers["X-RateLimit-Reset"] = str(int(time.time()))
        except (AttributeError, TypeError, ValueError) as exc:
            logger.debug("Could not attach disabled rate-limit headers: %s", exc)

    # ── Main middleware dispatch ───────────────────────────────────────

    async def middleware(self, request: Request, call_next: Callable) -> Response:
        """ASGI middleware dispatch with dual-layer rate limiting.

        A request must pass **both** the aggregate global counter and
        the per-IP counter (if enabled) to proceed. If either is
        exceeded, a 429 response is returned immediately.

        RFC 6585 compliance: X-RateLimit-Limit, X-RateLimit-Remaining,
        and X-RateLimit-Reset are attached to **every** /api/ response
        so clients can always discover their quota status.
        """
        path = request.url.path
        is_api = path.startswith("/api/")
        is_docs = "/docs" in path or "/openapi" in path

        if not is_api or is_docs:
            response = await call_next(request)
            # Non-API / docs paths: still attach headers for observability,
            # but with a lightweight "not rate-limited" marker so clients
            # never have to guess whether a missing header means "no limit"
            # vs "middleware was skipped".
            if is_api and is_docs:
                self._add_disabled_rate_limit_headers(response)
            return response  # type: ignore[no-any-return]

        if self._global_max <= 0 and not (self._per_ip and self._per_ip_max > 0):
            # Rate limiter is fully disabled — still pass through and
            # attach stub headers so the contract is consistent.
            response = await call_next(request)
            self._add_disabled_rate_limit_headers(response)
            return response  # type: ignore[no-any-return]

        self._prune_expired_counters()

        client_ip = self._extract_client_ip(request)
        method = request.method

        # ── Tier 1: Aggregate global counter ───────────────────────
        agg_counter: SlidingWindowCounter | DatabaseSlidingWindowCounter | None = None
        if self._global_max > 0:
            agg_key = self._get_aggregate_key(path, method)
            agg_limit = self._get_limits_for_path(path, method)
            agg_counter = self._get_or_create_counter(agg_key, *agg_limit)

            if not agg_counter.allow():
                from app.metrics_collector import record_rate_limit_global_hit

                record_rate_limit_global_hit()
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
                from app.metrics_collector import record_rate_limit_per_ip_hit

                record_rate_limit_per_ip_hit()
                return self._build_429_response(ip_counter, client_ip, path)

        # ── Proceed with the request ───────────────────────────────
        response = await call_next(request)

        # Add rate limit headers from the per-IP counter (most relevant to clients)
        if active_per_ip_counter is not None:
            self._add_rate_limit_headers(response, active_per_ip_counter)
        elif agg_counter is not None:
            self._add_rate_limit_headers(response, agg_counter)
        else:
            # Should not normally reach here (both tiers are zero above)
            self._add_disabled_rate_limit_headers(response)

        return response  # type: ignore[no-any-return]

    def get_stats(self) -> dict[str, Any]:
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


# ─── Item 9: Job-Level Rate Limiting ──────────────────────────────────────
# Per-user concurrency cap, per-job domain request delay, and
# domain cooldown integration.  This is a separate class from
# ``RateLimiterMiddleware`` because it operates at the job-execution
# layer (worker / task runner), not the HTTP request layer.


class DomainCooldownTracker:
    """Track when a domain was last hit and enforce a minimum interval.

    Thread-safe. Intended for use inside the job runner to ensure a
    configurable delay between requests to the same domain, integrated
    with :class:`CrawlPolicyEngine` cooldown state.
    """

    def __init__(self, default_cooldown_seconds: float = 2.0) -> None:
        self._last_hit: dict[str, float] = {}
        self._lock = threading.Lock()
        self._default_cooldown = default_cooldown_seconds

    def check(self, domain: str, cooldown_seconds: float | None = None) -> tuple[bool, float]:
        """Check whether *domain* can be hit now.

        Returns ``(allowed, wait_seconds)``. When ``allowed`` is False,
        ``wait_seconds`` indicates how long to wait before retrying.
        """
        cooldown = cooldown_seconds if cooldown_seconds is not None else self._default_cooldown
        now = time.time()
        with self._lock:
            last = self._last_hit.get(domain, 0.0)
            elapsed = now - last
            if elapsed < cooldown:
                return False, cooldown - elapsed
            return True, 0.0

    def record_hit(self, domain: str) -> None:
        """Record that a request to *domain* was just made."""
        with self._lock:
            self._last_hit[domain] = time.time()

    def wait_if_needed(self, domain: str, cooldown_seconds: float | None = None) -> float:
        """Block until the domain cooldown has elapsed, then record the hit.

        Returns the actual time slept (0.0 if no wait was needed).
        """
        _allowed, wait = self.check(domain, cooldown_seconds)
        if wait > 0:
            time.sleep(wait)
        self.record_hit(domain)
        return wait

    async def async_wait_if_needed(self, domain: str, cooldown_seconds: float | None = None) -> float:
        """Async version: yield to the event loop while waiting for cooldown.

        Returns the actual time waited (0.0 if no wait was needed).
        """
        import asyncio

        _allowed, wait = self.check(domain, cooldown_seconds)
        if wait > 0:
            await asyncio.sleep(wait)
        self.record_hit(domain)
        return wait

    def get_domain_last_hit(self, domain: str) -> float:
        """Return the epoch timestamp of the last hit to *domain*, or 0.0."""
        with self._lock:
            return self._last_hit.get(domain, 0.0)

    def reset(self, domain: str | None = None) -> None:
        """Clear cooldown state for a specific domain or all domains."""
        with self._lock:
            if domain is None:
                self._last_hit.clear()
            else:
                self._last_hit.pop(domain, None)

    @property
    def tracked_domains(self) -> int:
        """Number of domains with a recorded last-hit timestamp."""
        with self._lock:
            return len(self._last_hit)


class JobRateLimiter:
    """Per-user job concurrency cap and per-job domain request pacing.

    Enforces:
    - Per-user concurrency cap (default 5 concurrent jobs per user).
    - Per-domain cooldown between requests within a single job.
    - Integration with :class:`~app.crawl_policy.CrawlPolicyEngine`
      for cross-job domain cooldown.

    Usage::

        limiter = JobRateLimiter(max_concurrent_per_user=5)
        limiter.acquire_job_slot("user-abc")
        try:
            # ... run job ...
            limiter.check_domain_before_fetch("user-abc", "example.com")
            # ... fetch ...
        finally:
            limiter.release_job_slot("user-abc")
    """

    def __init__(
        self,
        max_concurrent_per_user: int = 5,
        default_domain_cooldown_seconds: float = 2.0,
    ) -> None:
        self._max_concurrent = max_concurrent_per_user
        self._user_active_jobs: dict[str, int] = {}
        self._lock = threading.Lock()
        self._domain_tracker = DomainCooldownTracker(default_domain_cooldown_seconds)
        # Per-job domain delays: {(user_id, job_id, domain): last_hit_time}
        self._job_domain_last_hit: dict[tuple[str, str, str], float] = {}
        self._job_domain_lock = threading.Lock()

    # ── Per-user concurrency cap ────────────────────────────────────────

    def acquire_job_slot(self, user_id: str) -> bool:
        """Attempt to acquire a concurrent job slot for *user_id*.

        Returns True if the slot was acquired (user is below the cap),
        False if the user has already reached the maximum concurrent jobs.
        Thread-safe.
        """
        from app.utils.log_redaction import redact_pii

        with self._lock:
            current = self._user_active_jobs.get(user_id, 0)
            if current >= self._max_concurrent:
                logger.info(
                    "Job rate limit: user %s at concurrency cap (%d/%d)",
                    redact_pii(user_id),
                    current,
                    self._max_concurrent,
                )
                return False
            self._user_active_jobs[user_id] = current + 1
            logger.debug(
                "Job rate limit: user %s acquired slot (%d/%d)",
                redact_pii(user_id),
                current + 1,
                self._max_concurrent,
            )
            return True

    def release_job_slot(self, user_id: str) -> None:
        """Release a concurrent job slot for *user_id*.

        Should be called in a ``finally`` block after :meth:`acquire_job_slot`.
        """
        with self._lock:
            current = self._user_active_jobs.get(user_id, 0)
            if current > 0:
                self._user_active_jobs[user_id] = current - 1
            if current <= 1:
                self._user_active_jobs.pop(user_id, None)

    def get_user_active_jobs(self, user_id: str) -> int:
        """Return the number of currently active jobs for *user_id*."""
        with self._lock:
            return self._user_active_jobs.get(user_id, 0)

    # ── Per-job domain request pacing ──────────────────────────────────

    def check_domain_before_fetch(
        self,
        user_id: str,
        domain: str,
        job_id: str = "",
        cooldown_seconds: float | None = None,
    ) -> tuple[bool, float]:
        """Check whether a domain can be fetched now for a specific job.

        Uses both the per-job domain delay tracker and the shared
        :class:`DomainCooldownTracker`.  Returns ``(allowed, wait_seconds)``.
        When ``allowed`` is False, ``wait_seconds`` indicates the cooldown
        remaining.  Also consults the CrawlPolicyEngine if available.
        """
        wait = 0.0

        # Check the per-job domain delay
        if job_id:
            with self._job_domain_lock:
                key = (user_id, job_id, domain)
                last_hit = self._job_domain_last_hit.get(key, 0.0)
            effective_cooldown = cooldown_seconds if cooldown_seconds is not None else self._domain_tracker._default_cooldown
            elapsed = time.time() - last_hit
            if elapsed < effective_cooldown:
                wait = max(wait, effective_cooldown - elapsed)

        # Check the shared domain cooldown tracker
        domain_allowed, domain_wait = self._domain_tracker.check(domain, cooldown_seconds)
        if not domain_allowed:
            wait = max(wait, domain_wait)

        # Check CrawlPolicyEngine for cross-job domain cooldown
        try:
            from app.crawl_policy import get_crawl_policy

            policy = get_crawl_policy()
            state = policy.get_domain_state(domain)
            if state and state.get("cooldown", 0) > 0:
                wait = max(wait, state["cooldown"])
        except (ImportError, RuntimeError, ValueError) as exc:
            logger.debug("CrawlPolicyEngine unavailable for domain cooldown check: %s", exc)

        return (wait == 0.0, wait)

    def record_domain_fetch(self, user_id: str, domain: str, job_id: str = "") -> None:
        """Record that a fetch to *domain* was just performed.

        Updates both the per-job tracker and the shared domain tracker.
        """
        self._domain_tracker.record_hit(domain)
        now = time.time()
        if job_id:
            with self._job_domain_lock:
                self._job_domain_last_hit[(user_id, job_id, domain)] = now

    def wait_for_domain(
        self,
        user_id: str,
        domain: str,
        job_id: str = "",
        cooldown_seconds: float | None = None,
    ) -> float:
        """Block until domain cooldown elapses, then record the fetch.

        Returns the total time waited (0.0 if no wait needed).
        """
        _, wait = self.check_domain_before_fetch(user_id, domain, job_id, cooldown_seconds)
        if wait > 0:
            time.sleep(wait)
        self.record_domain_fetch(user_id, domain, job_id)
        return wait

    async def async_wait_for_domain(
        self,
        user_id: str,
        domain: str,
        job_id: str = "",
        cooldown_seconds: float | None = None,
    ) -> float:
        """Async version: yield to the event loop while waiting for cooldown.

        Returns the total time waited (0.0 if no wait needed).
        """
        import asyncio

        _, wait = self.check_domain_before_fetch(user_id, domain, job_id, cooldown_seconds)
        if wait > 0:
            await asyncio.sleep(wait)
        self.record_domain_fetch(user_id, domain, job_id)
        return wait

    # ── Observability / management ─────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return current job rate limiter stats."""
        with self._lock:
            return {
                "max_concurrent_per_user": self._max_concurrent,
                "active_users": len(self._user_active_jobs),
                "user_active_jobs": dict(self._user_active_jobs),
                "tracked_domains": self._domain_tracker.tracked_domains,
            }

    def get_domain_cooldown_remaining(self, domain: str, cooldown_seconds: float | None = None) -> float:
        """Seconds remaining until *domain* can be hit again."""
        allowed, wait = self._domain_tracker.check(domain, cooldown_seconds)
        return 0.0 if allowed else wait

    def reset(self) -> None:
        """Clear all state (for testing)."""
        with self._lock:
            self._user_active_jobs.clear()
        self._domain_tracker.reset()
        with self._job_domain_lock:
            self._job_domain_last_hit.clear()


# ─── Module-level singleton ─────────────────────────────────────────────

_job_rate_limiter: JobRateLimiter | None = None
_job_rate_limiter_lock = threading.Lock()


def get_job_rate_limiter() -> JobRateLimiter:
    """Return the module-level :class:`JobRateLimiter` singleton.

    Lazily created on first access so that config values are resolved
    at runtime, not at import time.
    """
    global _job_rate_limiter
    if _job_rate_limiter is None:
        with _job_rate_limiter_lock:
            if _job_rate_limiter is None:
                from app.config import settings

                max_concurrent = getattr(settings, "JOB_MAX_CONCURRENT_PER_USER", 5)
                cooldown = getattr(settings, "CRAWL_DEFAULT_DELAY_SECONDS", 2.0)
                _job_rate_limiter = JobRateLimiter(
                    max_concurrent_per_user=max_concurrent,
                    default_domain_cooldown_seconds=cooldown,
                )
    return _job_rate_limiter
