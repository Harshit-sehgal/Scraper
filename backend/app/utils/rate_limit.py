"""Rate-limit awareness utilities for the scraper's worker queue.

Provides helpers to detect rate-limit-related errors from HTTP responses
and LLM providers, so the worker queue can apply smarter backoff instead
of burning retries on transient rate-limit blocks.
"""

import datetime
import re
import time

# ── Rate-limit indicator patterns ──────────────────────────────────────

_RATE_LIMIT_STATUS_CODES = {429, 503}
"""HTTP status codes that commonly indicate rate limiting."""

_RATE_LIMIT_HEADER_PATTERNS = [
    re.compile(r"retry-after", re.IGNORECASE),
    re.compile(r"x-ratelimit-remaining", re.IGNORECASE),
    re.compile(r"x-rate-limit", re.IGNORECASE),
]

_RATE_LIMIT_BODY_PATTERNS = [
    re.compile(r"rate.?limit", re.IGNORECASE),
    re.compile(r"too many requests", re.IGNORECASE),
    re.compile(r"try again later", re.IGNORECASE),
    re.compile(r"quota exceeded", re.IGNORECASE),
    re.compile(r"request limit", re.IGNORECASE),
    re.compile(r"throttl", re.IGNORECASE),
]


def is_rate_limit_error(
    status_code: int | None = None,
    headers: dict | None = None,
    body: str | None = None,
) -> bool:
    """Heuristic check for whether an error is rate-limit-related.

    Args:
        status_code: HTTP status code, if available.
        headers: Response headers, if available.
        body: Response body text, if available.

    Returns:
        True if the error looks like a rate limit.
    """
    if status_code is not None and status_code in _RATE_LIMIT_STATUS_CODES:
        return True

    if headers:
        for key in headers:
            for pattern in _RATE_LIMIT_HEADER_PATTERNS:
                if pattern.search(key):
                    return True

    if body:
        for pattern in _RATE_LIMIT_BODY_PATTERNS:
            if pattern.search(body):
                return True

    return False


def parse_retry_after(headers: dict | None = None) -> float | None:
    """Parse Retry-After header into seconds.

    Supports both integer seconds and HTTP-date format.
    Returns None if the header is missing or unparseable.
    """
    if not headers:
        return None

    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None

    try:
        return float(raw)
    except (ValueError, TypeError):
        pass

    # Try parsing as HTTP-date
    try:
        from email.utils import parsedate_to_datetime

        retry_dt = parsedate_to_datetime(raw)
        delta = (retry_dt - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        return max(0.0, delta)
    except Exception:  # nosec B110
        pass

    return None


_RATE_LIMIT_STATE: dict[str, float] = {}
"""In-memory rate-limit state keyed by domain / task-type: next_allowed_at timestamp."""


def get_cooldown_seconds(domain_or_type: str, base_cooldown: float = 30.0) -> float:
    """Return the cooldown remaining (seconds) for a domain or task type.

    Checks if we're currently cooling down after a rate-limit hit.
    """
    now = time.time()
    next_allowed = _RATE_LIMIT_STATE.get(domain_or_type, 0.0)
    remaining = next_allowed - now
    return max(0.0, remaining)


def mark_rate_limited(
    domain_or_type: str,
    retry_after: float | None = None,
    max_cooldown: float = 300.0,
) -> None:
    """Record that a rate limit was hit for a domain / task-type.

    Subsequent calls to ``get_cooldown_seconds`` will return > 0 until
    the cooldown expires.

    Args:
        domain_or_type: The domain or task type that was rate limited.
        retry_after: Explicit retry-after seconds (e.g. from Retry-After header).
            If None, uses exponential backoff based on existing cooldown.
        max_cooldown: Maximum cooldown in seconds (default 5 minutes).
    """
    now = time.time()
    if retry_after is not None:
        cooldown = min(retry_after, max_cooldown)
    else:
        existing = _RATE_LIMIT_STATE.get(domain_or_type, now)
        backoff = min((existing - now) * 2 + 30, max_cooldown)
        cooldown = max(backoff, 30.0)

    _RATE_LIMIT_STATE[domain_or_type] = now + cooldown


def reset_rate_limit_state(domain_or_type: str | None = None) -> None:
    """Clear rate-limit cooldown state for a domain (or all domains)."""
    if domain_or_type:
        _RATE_LIMIT_STATE.pop(domain_or_type, None)
    else:
        _RATE_LIMIT_STATE.clear()
