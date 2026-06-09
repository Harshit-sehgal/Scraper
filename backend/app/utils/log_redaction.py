"""Shared PII redaction utilities for logging.

Provides consistent URL, proxy, and PII redaction across the codebase.
All log output should route through these functions to prevent credential leakage.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\+?\b\d[\d\s()\-]{8,14}\d\b")
_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "auth",
        "api_key",
        "key",
        "password",
        "token",
        "secret",
        "signature",
        "alert_webhook_url",
        "credential",
        "session",
        "cookie",
        "bearer",
        "private",
        "client_secret",
        "api_secret",
        "access_key",
        "secret_key",
    },
)


def redact_url(url: str, max_len: int = 80) -> str:
    """Strip query params, fragments, and embedded credentials from a URL for logging.

    This prevents session tokens, search queries, and API keys from leaking
    into log output. Preserves scheme + host + truncated path.
    """
    if not url:
        return url
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "<invalid-url>"
    # Mask userinfo (proxy credentials, embedded auth)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    # Strip query and fragment entirely; keep scheme + netloc + path
    path = parsed.path
    if len(path) > max_len:
        path = path[:max_len] + "..."
    return urlunsplit((parsed.scheme, f"{host}{port}", path, "", ""))


def mask_proxy_url(proxy: str) -> str:
    """Mask credentials in a proxy URL (e.g. http://user:pass@host:port).

    Replaces userinfo with '****@' to prevent credential leakage in logs.
    """
    if not proxy:
        return proxy
    try:
        parsed = urlsplit(proxy)
    except ValueError:
        return "<invalid-proxy>"
    if parsed.username:
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        auth = "****@" if parsed.username else ""
        return urlunsplit((parsed.scheme, f"{auth}{host}{port}", parsed.path, parsed.query, parsed.fragment))
    return proxy


def redact_pii(text: str) -> str:
    """Redact email addresses and phone numbers from a string."""
    if not text:
        return text
    return _PHONE_RE.sub("<redacted_phone>", _EMAIL_RE.sub("<redacted_email>", text))


def sanitize_log_value(val: object, _depth: int = 0, _max_depth: int = 50) -> object:
    """Recursively redact PII and sensitive keys from a value for logging.

    - Strings: emails and phones are redacted
    - Dicts: keys matching sensitive patterns are replaced with '********'
    - Lists: items are recursively sanitized
    - Depth-limited to prevent stack overflow on pathological structures
    """
    if _depth >= _max_depth:
        return val
    if isinstance(val, str):
        return redact_pii(val)
    if isinstance(val, dict):
        return {
            "********" if any(s in k.lower() for s in _SENSITIVE_KEYS) else k: sanitize_log_value(v, _depth + 1, _max_depth)
            for k, v in val.items()
        }
    if isinstance(val, list):
        return [sanitize_log_value(item, _depth + 1, _max_depth) for item in val]
    return val


def truncate_url(url: str, max_len: int = 100) -> str:
    """Truncate a URL to max_len characters for logging."""
    if len(url) > max_len:
        return url[:max_len] + "..."
    return url
