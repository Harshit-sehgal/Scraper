"""HTML size limits — guard against pathological inputs before parsing.

Most public web pages are well under 1 MB, but anti-bot systems, scraping
targets, and malicious endpoints can return arbitrarily large payloads.
Parsing multi-hundred-megabyte HTML responses with BeautifulSoup is
extremely expensive (quadratic in the worst case) and can pin a worker
for minutes, blocking other jobs.

This module exposes:

- :data:`MAX_HTML_BYTES` — the hard cap.  Configurable via the
  ``DATAFORGE_MAX_HTML_BYTES`` env var (default 10 MB).
- :func:`enforce_html_size` — raises :class:`HTMLSizeExceeded` if the
  payload is too large, otherwise returns the (possibly truncated)
  string.  Truncation is opt-in via ``must_truncate=True`` so callers
  can preserve raw length for metrics while still defending parsers.
- :func:`truncate_html` — chop the string to the size limit with a
  trailing sentinel so downstream parsers don't see broken tags at the
  cut-off.
- :class:`HTMLSizeExceeded` — raised by :func:`enforce_html_size`.

The limit is *inclusive* — payloads exactly at the cap are allowed,
payloads above the cap are rejected.
"""

from __future__ import annotations

import logging
import os
from typing import Final

logger = logging.getLogger(__name__)

ENV_VAR: Final[str] = "DATAFORGE_MAX_HTML_BYTES"

# 10 MB accommodates heavy pages (e.g. government-data dumps, large tables)
# while still bounding parse time to ~1 s on commodity hardware.
_DEFAULT_MAX_HTML_BYTES: Final[int] = 10 * 1024 * 1024


class HTMLSizeExceeded(ValueError):
    """Raised when an HTML payload exceeds the configured size limit.

    Carries the original size and the limit so callers can log both
    without re-measuring.
    """

    def __init__(self, observed: int, limit: int, url: str | None = None) -> None:
        self.observed = observed
        self.limit = limit
        self.url = url
        msg = f"HTML payload of {observed:,} bytes exceeds the {limit:,}-byte limit"
        if url:
            msg += f" (url={url})"
        msg += "; increase DATAFORGE_MAX_HTML_BYTES to allow larger payloads"
        super().__init__(msg)


def _resolve_max_bytes() -> int:
    """Resolve the HTML size cap from env, falling back to default.

    Negative or non-numeric values fall back to the default rather than
    raising — a misconfigured cap shouldn't take the whole API down.
    """
    raw = os.environ.get(ENV_VAR)
    if not raw:
        return _DEFAULT_MAX_HTML_BYTES
    try:
        val = int(raw)
    except (ValueError, TypeError):
        logger.debug(
            "Invalid %s value %r; using default %d",
            ENV_VAR,
            raw,
            _DEFAULT_MAX_HTML_BYTES,
        )
        return _DEFAULT_MAX_HTML_BYTES
    if val <= 0:
        return _DEFAULT_MAX_HTML_BYTES
    return val


# Resolved lazily; tests can patch ``os.environ`` and re-call to pick up
# the change without having to monkeypatch a module attribute.
def get_max_html_bytes() -> int:
    """Return the configured HTML size cap in bytes."""
    return _resolve_max_bytes()


def enforce_html_size(
    html: str,
    *,
    url: str | None = None,
    must_truncate: bool = False,
    limit: int | None = None,
) -> str:
    """Validate ``html`` is within the size cap, optionally truncating.

    Args:
        html: The payload to check.
        url: Optional source URL; included in the exception/log message.
        must_truncate: When ``True``, oversized payloads are silently
            truncated to the cap and a warning is logged.  When
            ``False`` (default), oversized payloads raise
            :class:`HTMLSizeExceeded`.
        limit: Override the configured cap (used by tests).

    Returns:
        The original string (if within the cap) or a truncated copy (if
        ``must_truncate=True`` and the string was over the cap).

    Raises:
        HTMLSizeExceeded: When the payload exceeds the cap and
            ``must_truncate`` is ``False``.
    """
    cap = limit if limit is not None else get_max_html_bytes()
    if len(html) <= cap:
        return html
    if must_truncate:
        logger.warning(
            "HTML payload exceeds %d-byte cap (%d bytes observed); truncating (url=%s). Increase DATAFORGE_MAX_HTML_BYTES to avoid truncation",
            cap,
            len(html),
            url or "unknown",
        )
        return truncate_html(html, cap=cap)
    raise HTMLSizeExceeded(observed=len(html), limit=cap, url=url)


def truncate_html(html: str, *, cap: int) -> str:
    """Return a copy of ``html`` whose length is at most ``cap`` bytes.

    A trailing sentinel is included so downstream parsers see that the
    payload was cut (rather than treating the last few chars as valid).
    The sentinel is appended *inside* the cap so the returned string is
    ``<= cap`` bytes — never larger than the caller can atomically copy.
    """
    if len(html) <= cap:
        return html
    sentinel = "\n<!-- truncated by DATAFORGE_MAX_HTML_BYTES -->"
    # Reserve room for the sentinel; if cap < len(sentinel), just clip.
    if cap <= len(sentinel):
        return html[: max(0, cap - 0)]  # cap smaller than sentinel; just cut
    keep = cap - len(sentinel)
    return html[:keep] + sentinel
