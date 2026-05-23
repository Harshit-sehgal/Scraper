"""
Browser Network Capture — Intercepts fetch/XHR/GraphQL responses during Playwright page loads.

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

import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Global capture registry
# ---------------------------------------------------------------------------

_captured_payloads: dict[str, list[dict[str, Any]]] = {}
"""Maps URL → list of captured network JSON payloads for that URL."""

# Safety caps to prevent unbounded memory growth
_MAX_PAYLOADS_PER_URL: int = 50
"""Maximum number of network payloads stored per URL."""
_MAX_BYTES_PER_URL: int = 10 * 1024 * 1024
"""Maximum total bytes of network payloads stored per URL (10 MB)."""


def clear(url: str) -> None:
    """Clear captured payloads for a URL."""
    _captured_payloads.pop(url, None)


def clear_all() -> None:
    """Clear all captured payloads."""
    _captured_payloads.clear()


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


def get_all_hydration_objects(url: str) -> list[dict]:
    """Get all candidate hydration/subset objects from captured network data.

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
        except Exception:
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
        except Exception:
            total_bytes += 1024
    while total_bytes > _MAX_BYTES_PER_URL and len(existing) > 1:
        removed = existing.pop(0)
        try:
            total_bytes -= len(json.dumps(removed, ensure_ascii=False, default=str))
        except Exception:
            total_bytes -= 1024

    _captured_payloads[url] = existing
    logger.info(
        "[BrowserNetwork] Stored %d network payloads for %s (total ~%.1f KB)",
        len(payloads), url, total_bytes / 1024,
    )


# ---------------------------------------------------------------------------
# Playwright interception setup
# ---------------------------------------------------------------------------

async def setup_network_capture(page) -> list[dict]:
    """Set up network response interception on a Playwright page.

    Registers a response listener that captures:
    - XHR/fetch responses with JSON bodies
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

    async def _on_response(response):
        """Handle a Playwright response event."""
        try:
            req = response.request

            # Only capture XHR/fetch and API-like documents
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
            except Exception:
                # Not JSON — skip
                return

            if body is None:
                return

            # Skip empty or trivial payloads
            if _is_empty_payload(body):
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
                req.method, _truncate_url(url), type(body).__name__, status, resource_type,
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
    path = urlparse(url).path.lower() if '//' in url else url.lower()
    skip_extensions = (
        ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
        ".webp", ".ico", ".woff", ".woff2", ".ttf", ".eot",
        ".mp4", ".webm", ".mp3", ".wav",
    )
    if path.endswith(skip_extensions):
        return True

    return False


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
        # Check for common empty/error responses
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



