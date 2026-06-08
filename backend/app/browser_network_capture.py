"""Browser Network Capture — Intercepts fetch / XHR / GraphQL responses during Playwright page loads.

This module captures actual browser network responses (not just inline scripts) for
structured data extraction. Many modern SPAs load their data via API calls that never
appear in HTML <script> tags.

Usage:
    from app.browser_network_capture import setup_network_capture, store_captures, get_captures

    # Inside a Playwright page block:
    captured = await setup_network_capture(page)
    await page.goto(url)
    store_captures(url, captured)

    # Later, in the extraction pipeline:
    payloads = get_captures(url)
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Global capture registry
# ---------------------------------------------------------------------------

_captured_payloads: dict[str, list[dict[str, Any]]] = {}
"""Maps URL → list of captured network JSON payloads for that URL."""

_captured_browser_state: dict[str, dict[str, Any]] = {}
"""Maps URL → sanitized browser-side state evidence captured after page load."""

# Safety caps to prevent unbounded memory growth
_MAX_PAYLOADS_PER_URL: int = 50
"""Maximum number of network payloads stored per URL."""
_MAX_BYTES_PER_URL: int = 10 * 1024 * 1024
"""Maximum total bytes of network payloads stored per URL (10 MB)."""
_MAX_URLS: int = 1000
"""Maximum number of distinct URLs tracked globally (LRU eviction)."""
_MAX_GLOBAL_BYTES: int = 256 * 1024 * 1024
"""Maximum total bytes across all URLS (256 MB)."""
_MAX_STORAGE_ENTRIES_PER_AREA: int = 50
"""Maximum cookies / storage entries stored per browser state area."""
_MAX_STORAGE_NAME_CHARS: int = 128
"""Maximum key / name length retained for browser state evidence."""

_SESSION_STATE_KEY_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"session",
        r"\bsid\b",
        r"search[_-]?id",
        r"request[_-]?id",
        r"result[_-]?id",
        r"token",
        r"csrf",
        r"xsrf",
        r"auth",
    )
)


def clear(url: str) -> None:
    """Clear captured payloads for a URL."""
    _captured_payloads.pop(url, None)
    _captured_browser_state.pop(url, None)


def clear_all() -> None:
    """Clear all captured payloads."""
    _captured_payloads.clear()
    _captured_browser_state.clear()


def clear_job_captures(urls: list[str]) -> None:
    """Clear captured payloads for a list of job-specific URLs.

    Called after job extraction completes to free memory.
    """
    for url in urls:
        _captured_payloads.pop(url, None)
        _captured_browser_state.pop(url, None)
    if urls:
        logger.info("[BrowserNetwork] Cleared captures for %d job URLs", len(urls))


def get_captures(url: str) -> list[dict]:
    """Get captured network JSON payloads for a URL.

    Returns a list of payload dicts, each with:
    - url: str — the request URL
    - method: str — HTTP method (GET, POST, etc.)
    - resource_type: str — "xhr", "fetch", etc.
    - body: Any — parsed JSON body
    - status: int — HTTP status code
    """
    return _captured_payloads.get(url, [])


def get_browser_state(url: str) -> dict[str, Any]:
    """Get sanitized browser state evidence captured for a URL."""
    return _captured_browser_state.get(url, {})


def store_browser_state(url: str, state: dict[str, Any]) -> None:
    """Store sanitized browser state evidence for a URL."""
    if not state:
        return
    _captured_browser_state[url] = state


def _value_digest(value: Any) -> str:
    text = "" if value is None else str(value)
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _redacted_preview(value: Any) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}...{text[-4:]}"


def _sanitize_name(name: Any) -> str:
    return str(name or "")[:_MAX_STORAGE_NAME_CHARS]


def _is_session_state_name(name: str) -> bool:
    return any(pattern.search(name or "") for pattern in _SESSION_STATE_KEY_PATTERNS)


def _sanitize_storage_entry(name: Any, value: Any, source: str) -> dict[str, Any]:
    text = "" if value is None else str(value)
    return {
        "source": source,
        "name": _sanitize_name(name),
        "value_length": len(text),
        "value_sha256": _value_digest(text),
        "value_preview": _redacted_preview(text),
        "session_candidate": _is_session_state_name(str(name or "")),
    }


def _sanitize_storage_mapping(mapping: Any, source: str) -> list[dict[str, Any]]:
    if not isinstance(mapping, dict):
        return []
    entries: list[dict[str, Any]] = []
    for name, value in list(mapping.items())[:_MAX_STORAGE_ENTRIES_PER_AREA]:
        entries.append(_sanitize_storage_entry(name, value, source))
    return entries


def _sanitize_cookies(cookies: Any) -> list[dict[str, Any]]:
    if not isinstance(cookies, list):
        return []
    sanitized: list[dict[str, Any]] = []
    for cookie in cookies[:_MAX_STORAGE_ENTRIES_PER_AREA]:
        if not isinstance(cookie, dict):
            continue
        entry = _sanitize_storage_entry(cookie.get("name", ""), cookie.get("value", ""), "cookie")
        entry.update(
            {
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", ""),
                "expires": cookie.get("expires"),
                "http_only": bool(cookie.get("httpOnly")),
                "secure": bool(cookie.get("secure")),
                "same_site": cookie.get("sameSite", ""),
            },
        )
        sanitized.append(entry)
    return sanitized


def build_cookie_header(cookies: Any) -> str:
    """Build a Cookie header from raw Playwright cookie dicts."""
    if not isinstance(cookies, list):
        return ""
    pairs: list[str] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        if name and value:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def _collect_session_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for entry in state.get("cookies", []):
        if entry.get("session_candidate"):
            candidates.append(entry)
    for area_name in ("localStorage", "sessionStorage"):
        for entry in state.get("storage", {}).get(area_name, []):
            if entry.get("session_candidate"):
                candidates.append(entry)
    return candidates[:_MAX_STORAGE_ENTRIES_PER_AREA]


async def collect_browser_state(page) -> dict[str, Any]:
    """Capture sanitized browser-side state evidence after a Playwright load.

    Raw cookie and storage values are intentionally not returned. The live
    browser context keeps the real values for navigation / API requests; this
    evidence is only for diagnostics and recovery decisions.
    """
    raw_cookies: list[dict[str, Any]] = []
    try:
        raw_cookies = await page.context.cookies()
    except Exception as exc:
        logger.debug("[BrowserState] Could not read context cookies: %s", exc)

    storage_snapshot: dict[str, Any] = {}
    try:
        storage_snapshot = await page.evaluate("""async () => {
                const readStorage = (storage) => {
                    const out = {};
                    if (!storage) return out;
                    for (let i = 0; i < Math.min(storage.length, 50); i++) {
                        const key = storage.key(i);
                        if (key) out[key] = storage.getItem(key);
                    }
                    return out;
                };
                let indexedDbDatabases = [];
                try {
                    if (window.indexedDB && indexedDB.databases) {
                        indexedDbDatabases = await indexedDB.databases();
                    }
                } catch (_) {}
                let cacheStorageKeys = [];
                try {
                    if (window.caches && caches.keys) {
                        cacheStorageKeys = await caches.keys();
                    }
                } catch (_) {}
                return {
                    localStorage: readStorage(window.localStorage),
                    sessionStorage: readStorage(window.sessionStorage),
                    indexedDbDatabases: indexedDbDatabases || [],
                    cacheStorageKeys: cacheStorageKeys || []
                };
            }""")
    except Exception as exc:
        logger.debug("[BrowserState] Could not read browser storage: %s", exc)
    if not isinstance(storage_snapshot, dict):
        storage_snapshot = {}

    state: dict[str, Any] = {
        "cookies": _sanitize_cookies(raw_cookies),
        "storage": {
            "localStorage": _sanitize_storage_mapping(storage_snapshot.get("localStorage", {}), "localStorage"),
            "sessionStorage": _sanitize_storage_mapping(storage_snapshot.get("sessionStorage", {}), "sessionStorage"),
        },
        "indexed_db": [
            {
                "name": _sanitize_name(db.get("name", "")),
                "version": db.get("version"),
            }
            for db in storage_snapshot.get("indexedDbDatabases", [])[:_MAX_STORAGE_ENTRIES_PER_AREA]
            if isinstance(db, dict)
        ],
        "cache_storage_keys": [
            _sanitize_name(key) for key in storage_snapshot.get("cacheStorageKeys", [])[:_MAX_STORAGE_ENTRIES_PER_AREA]
        ],
    }
    candidates = _collect_session_candidates(state)
    state["session_candidates"] = candidates
    state["session_candidate_count"] = len(candidates)
    return state


def get_all_hydration_objects(url: str) -> list[dict]:
    """Get all candidate hydration / subset objects from captured network data.

    Returns a list of objects that look like they could contain structured records
    (arrays of dicts with meaningful keys). This is useful for feeding into
    network_extractor.py's generic extraction logic.
    """
    payloads = get_captures(url)
    candidates: list[dict] = []

    for payload in payloads:
        body = payload.get("body")
        if isinstance(body, dict):
            candidates.append(body)
        elif isinstance(body, list):
            # Wrap list payloads as dict
            candidates.append({"items": body})

    return candidates


def store_captures(url: str, payloads: list[dict]) -> None:
    """Store captured payloads for a URL with memory limits.

    Caps total stored payloads per URL at _MAX_PAYLOADS_PER_URL and total
    byte size at _MAX_BYTES_PER_URL to prevent unbounded memory growth.

    Args:
        url: The page URL these payloads were captured from.
        payloads: List of captured payload dicts.

    """
    if not payloads:
        return

    # Estimate total bytes of new payloads
    import json

    total_new_bytes = 0
    for p in payloads:
        try:
            total_new_bytes += len(json.dumps(p, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            logger.debug("[BrowserNetwork] Failed to estimate payload size for %s", url)
            total_new_bytes += 1024  # Conservative fallback estimate

    # Enforce memory caps
    existing = _captured_payloads.get(url, [])
    existing.extend(payloads)

    # Cap by count — keep newest _MAX_PAYLOADS_PER_URL
    if len(existing) > _MAX_PAYLOADS_PER_URL:
        existing = existing[-_MAX_PAYLOADS_PER_URL:]

    # Cap by total bytes — drop oldest until under limit
    total_bytes = 0
    for p in reversed(existing):
        try:
            total_bytes += len(json.dumps(p, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            logger.debug("[BrowserNetwork] Failed to size existing payload for %s", url)
            total_bytes += 1024
    while total_bytes > _MAX_BYTES_PER_URL and len(existing) > 1:
        removed = existing.pop(0)
        try:
            total_bytes -= len(json.dumps(removed, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            logger.debug("[BrowserNetwork] Failed to size removed payload for %s", url)
            total_bytes -= 1024

    _captured_payloads[url] = existing

    # Global LRU eviction: keep most recently accessed URLs
    # Order by recency and cap at _MAX_URLS / _MAX_GLOBAL_BYTES
    _evict_lru_captures()

    logger.info(
        "[BrowserNetwork] Stored %d network payloads for %s (total ~%.1f KB, %d URLs tracked)",
        len(payloads),
        url,
        total_bytes / 1024,
        len(_captured_payloads),
    )


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------


def _evict_lru_captures() -> None:
    """Evict the least-recently-used URLs when global caps are exceeded.

    Maintains a simple LRU order by URL key insertion order (Python 3.7+).
    When _MAX_URLS or _MAX_GLOBAL_BYTES is exceeded, drops the oldest URLs
    until both limits are satisfied.
    """
    import json as _json

    # Cap by total URLs first
    while len(_captured_payloads) > _MAX_URLS:
        oldest_url = next(iter(_captured_payloads))
        dropped = _captured_payloads.pop(oldest_url, None)
        if dropped:
            logger.debug(
                "[BrowserNetwork] LRU evicted %s (%d payloads, %d URLs remain)",
                oldest_url,
                len(dropped),
                len(_captured_payloads),
            )

    # Cap by total bytes
    total_bytes = 0
    url_bytes: list[tuple[str, int]] = []
    for u, payloads in _captured_payloads.items():
        try:
            bytes_for_url = sum(len(_json.dumps(p, ensure_ascii=False, default=str)) for p in payloads)
        except (TypeError, ValueError):
            logger.debug("[BrowserNetwork] Failed to compute bytes for URL %s", u)
            bytes_for_url = len(payloads) * 1024
        url_bytes.append((u, bytes_for_url))
        total_bytes += bytes_for_url

    while total_bytes > _MAX_GLOBAL_BYTES and len(url_bytes) > 1:
        # Drop from the oldest URL (first in insertion order)
        oldest_url, oldest_bytes = url_bytes.pop(0)
        dropped = _captured_payloads.pop(oldest_url, None)
        if dropped:
            total_bytes -= oldest_bytes
            logger.debug(
                "[BrowserNetwork] LRU byte-evicted %s (~%.1f KB, %d URLs remain)",
                oldest_url,
                oldest_bytes / 1024,
                len(_captured_payloads),
            )


# ---------------------------------------------------------------------------
# Playwright interception setup
# ---------------------------------------------------------------------------


async def setup_network_capture(page) -> list[dict]:
    """Set up network response interception on a Playwright page.

    Registers a response listener that captures:
    - XHR / fetch responses with JSON bodies
    - GraphQL responses
    - API responses

    Args:
        page: A Playwright Page object.

    Returns:
        A mutable list reference that will be populated with captured
        payloads as responses arrive. Each payload dict has:
        - url: str
        - method: str
        - resource_type: str
        - body: Any (parsed JSON)
        - status: int

    """
    captured: list[dict] = []

    async def _on_response(response) -> None:
        """Handle a Playwright response event."""
        try:
            req = response.request

            # Only capture XHR / fetch and API-like documents
            resource_type = req.resource_type
            if resource_type not in ("xhr", "fetch", "websocket"):
                # Also capture document responses that return JSON
                # (some SPAs use document requests for API data)
                content_type = response.headers.get("content-type", "")
                if "json" not in content_type.lower() and resource_type != "document":
                    return

            # Check status
            status = response.status
            if status >= 400:
                return

            # Check content type from headers
            content_type = response.headers.get("content-type", "")
            url = req.url

            # Skip same-page resources that won't have structured data
            if _is_irrelevant_url(url):
                return

            # Try to parse JSON body
            try:
                body = await response.json()
            except (TypeError, ValueError):
                # Not JSON — skip with debug log
                logger.debug("[BrowserNetwork] Response %s is not JSON", _truncate_url(url))
                return

            if body is None:
                return

            # Skip empty or trivial payloads
            if _is_empty_payload(body):
                return

            # Enforce temporary count cap in live capture
            if len(captured) >= _MAX_PAYLOADS_PER_URL:
                logger.debug(
                    "[BrowserNetwork] Live capture payload count cap (%d) reached, skipping %s",
                    _MAX_PAYLOADS_PER_URL,
                    _truncate_url(url),
                )
                return

            # Estimate total bytes of existing captured payloads
            import json

            total_bytes = 0
            for p in captured:
                try:
                    total_bytes += len(json.dumps(p, ensure_ascii=False, default=str))
                except (TypeError, ValueError):
                    logger.debug("[BrowserNetwork] Failed to size captured payload for %s", url)
                    total_bytes += 1024

            # Estimate new payload size
            try:
                new_bytes = len(json.dumps(body, ensure_ascii=False, default=str))
            except (TypeError, ValueError):
                logger.debug("[BrowserNetwork] Failed to estimate response payload size for %s", url)
                new_bytes = 1024

            if total_bytes + new_bytes > _MAX_BYTES_PER_URL:
                logger.debug(
                    "[BrowserNetwork] Live capture byte cap (%.1f MB) reached, skipping %s",
                    _MAX_BYTES_PER_URL / (1024 * 1024),
                    _truncate_url(url),
                )
                return

            payload = {
                "url": url,
                "method": req.method,
                "resource_type": resource_type,
                "body": body,
                "status": status,
            }
            captured.append(payload)

            logger.debug(
                "[BrowserNetwork] Captured %s %s (%s, status=%d, type=%s)",
                req.method,
                _truncate_url(url),
                type(body).__name__,
                status,
                resource_type,
            )

        except Exception as e:
            logger.debug("[BrowserNetwork] Error capturing response: %s", e)

    page.on("response", _on_response)
    return captured


def _is_irrelevant_url(url: str) -> bool:
    """Check if a URL is likely irrelevant for data extraction.

    Skips analytics, tracking, CDN assets, static files, etc.
    """
    skip_patterns = [
        "/analytics",
        "/tracking",
        "/collect",
        "/beacon",
        "/telemetry",
        "/metrics",
        "/sentry",
        "/logging",
        "/favicon",
        "/manifest",
        "/sw.js",
        "/worker",
        "/service-worker",
        "google-analytics",
        "googletagmanager",
        "facebook.net",
        "cdn.",
        "cloudfront.net",
        "akamai",
        "fastly",
        "jsdelivr",
        "unpkg.com",
        "cdnjs",
    ]
    url_lower = url.lower()
    for pattern in skip_patterns:
        if pattern in url_lower:
            return True

    # Skip non-JSON extensions
    path = urlparse(url).path.lower() if "//" in url else url.lower()
    skip_extensions = (
        ".js",
        ".css",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp4",
        ".webm",
        ".mp3",
        ".wav",
    )
    return bool(path.endswith(skip_extensions))


def _is_empty_payload(body: Any) -> bool:
    """Check if a parsed JSON body is empty or trivial."""
    if body is None:
        return True
    if isinstance(body, (str, int, float, bool)):
        return True  # Single values aren't useful
    if isinstance(body, list):
        if len(body) == 0:
            return True
        # All-trivial list
        if all(isinstance(item, (str, int, float, bool)) for item in body):
            return True
    if isinstance(body, dict):
        if len(body) == 0:
            return True
        # Check for common empty / error responses
        if any(k in body for k in ("errors", "error")):
            error_val = body.get("errors") or body.get("error")
            if error_val and isinstance(error_val, str):
                return True
        # Single-key dict with trivial value
        if len(body) == 1:
            val = next(iter(body.values()))
            if isinstance(val, (str, int, float, bool)):
                return True
    return False


def _truncate_url(url: str, max_len: int = 100) -> str:
    """Truncate a URL for logging."""
    if len(url) > max_len:
        return url[:max_len] + "..."
    return url


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------


def filter_structured_payloads(payloads: list[dict]) -> list[dict]:
    """Filter captured payloads to only those likely containing structured records.

    Filters for payloads whose JSON bodies look like they could contain
    extractable records (arrays of dicts, or dicts with meaningful keys).
    """
    filtered = []
    for payload in payloads:
        body = payload.get("body")
        if isinstance(body, list):
            # Check if any items are dicts (structured records)
            if any(isinstance(item, dict) for item in body):
                filtered.append(payload)
        elif isinstance(body, dict):
            # Check for keys that suggest data content
            body_keys = set(body.keys())
            # Skip metadata-only payloads
            if body_keys <= {"status", "message", "code", "timestamp", "version", "success"}:
                continue
            # Skip pagination-only payloads
            if body_keys <= {"page", "per_page", "total", "total_pages", "offset", "limit"}:
                continue
            filtered.append(payload)
    return filtered
