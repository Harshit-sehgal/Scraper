"""Session URL detector — identifies ephemeral URL parameters.

Scans URLs for patterns that indicate session-bound, token-based, or
otherwise ephemeral query parameters that make URLs non-canonical.
This helps the acquisition system proactively flag URLs that are likely
to expire, rather than waiting for a redirect to discover the problem.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from app.config import settings

# Patterns that strongly indicate an ephemeral / session parameter
# These are parameter names (case-insensitive) that are commonly used
# for session tokens, tracking IDs, and other transient values.
SESSION_PARAM_PATTERNS: list[re.Pattern] = [
    # Session tokens
    re.compile(r"^(session|sess|sid|sessionid|session_id|jsessionid)$", re.I),
    # Authentication tokens
    re.compile(r"^(token|tok|auth|csrf|xsrf|_token|_csrf|csrf_token|csrfmiddlewaretoken)$", re.I),
    # Tracking / analytics parameters
    re.compile(r"^(utm_[a-z]+|fbclid|gclid|gclsrc|dclid|msclkid|mc_eid|mc_cid|_ga|_gl|_hsenc|hssc|hsCtaTracking)$", re.I),
    # Cache-busting / timestamp parameters
    re.compile(r"^(_|cache|nocache|nocache|rand|random|r|t|ts|timestamp|_t|_ts|v|ver|version)$", re.I),
    # OAuth / SSO state parameters
    re.compile(r"^(state|code|oauth_token|access_token|refresh_token|id_token)$", re.I),
    # Platform-specific ephemeral params
    re.compile(r"^(ref|referrer|source|src|click|clickid|affiliate|aff|campaign|medium)$", re.I),
    # Hash-like tokens (long hex or base64 strings as values)
    re.compile(r"^(hash|h|key|k|sig|signature|sign|checksum)$", re.I),
]

# Parameters that look like session tokens based on their VALUES
# (long hex strings, base64-like strings, UUIDs, etc.)
SESSION_VALUE_PATTERNS: list[re.Pattern] = [
    # UUIDs: 8 - 4-4 - 4-12 hex chars
    re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I),
    # Long hex strings (32+ chars, like MD5 / SHA hashes)
    re.compile(r"^[0-9a-f]{32,}$", re.I),
    # Base64-like strings (long, with +/ and = padding)
    re.compile(r"^[A-Za-z0-9+/]{40,}={0,2}$"),
    # Numeric IDs that are very long (10+ digits, likely internal tracking)
    re.compile(r"^\d{10,}$"),
]

SESSION_PATH_MARKERS: set[str] = {
    "id",
    "sid",
    "session",
    "sessionid",
    "session-id",
    "session_id",
    "token",
    "searchid",
    "search-id",
    "search_id",
}

SESSION_PATH_CONTEXTS: set[str] = {
    "search",
    "result",
    "results",
    "booking",
    "checkout",
    "quote",
    "availability",
}


def _normalize_segment(segment: str) -> str:
    return segment.strip().lower().replace("_", "-")


def _looks_like_opaque_path_token(segment: str) -> bool:
    """Return True when a path segment looks like a transient opaque token."""
    if len(segment) < 8:
        return False
    if re.fullmatch(r"[0-9a-f]{16,}", segment, re.I):
        return True
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", segment):
        has_alpha = bool(re.search(r"[A-Za-z]", segment))
        has_digit = bool(re.search(r"\d", segment))
        mixed_case = bool(re.search(r"[a-z]", segment)) and bool(re.search(r"[A-Z]", segment))
        return has_alpha and (has_digit or mixed_case)
    return False


def detect_session_params(url: str) -> dict:
    """Detect ephemeral / session-bound parameters in a URL.

    Scans the URL's query string for parameters that are likely to be
    session tokens, tracking IDs, or other ephemeral values that make
    the URL non-canonical and likely to expire.

    Args:
        url: The URL to analyze

    Returns:
        dict with:
        - is_session_bound: bool — whether the URL contains ephemeral params
        - ephemeral_params: list of param names that appear ephemeral
        - canonical_url: str — the URL with ephemeral params removed
        - confidence: float — 0.0 - 1.0 confidence that URL is session-bound
        - details: list of (param_name, reason) tuples explaining why each
          param was flagged
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)

    ephemeral_params: list[str] = []
    details: list[tuple[str, str]] = []
    confidence_score = 0.0

    for param_name in params:
        param_lower = param_name.lower()
        values = params[param_name]
        value = values[0] if values else ""

        # Check 1: Parameter name matches known session patterns
        name_matched = False
        for pattern in SESSION_PARAM_PATTERNS:
            if pattern.match(param_lower):
                ephemeral_params.append(param_name)
                details.append(
                    (
                        param_name,
                        f"param name matches pattern: {pattern.pattern}",
                    )
                )
                confidence_score = max(confidence_score, settings.SESSION_PARAM_NAME_CONFIDENCE)
                name_matched = True
                break

        if name_matched:
            continue

        # Check 2: Parameter value looks like a session token
        if value:
            for pattern in SESSION_VALUE_PATTERNS:
                if pattern.match(value):
                    ephemeral_params.append(param_name)
                    details.append(
                        (
                            param_name,
                            f"value matches session token pattern: {pattern.pattern}",
                        )
                    )
                    confidence_score = max(confidence_score, settings.SESSION_PARAM_VALUE_CONFIDENCE)
                    break

    # Check 3: URL path contains token-like segments.
    # This catches generic session / search routes such as:
    #   /search / id/<opaque-id>
    #   /results / session/<opaque-id>
    path_segments = [s for s in parsed.path.split("/") if s]
    ephemeral_path_indexes: set[int] = set()
    for idx, segment in enumerate(path_segments):
        # Long hex-like path segments (e.g., /search / abc123def456ghi)
        if re.match(r"^[0-9a-f]{16,}$", segment, re.I):
            confidence_score = max(confidence_score, settings.SESSION_PATH_HASH_CONFIDENCE)
            ephemeral_params.append(f"path:/{segment}")
            details.append((f"path:/{segment}", "path segment looks like a session hash"))
            ephemeral_path_indexes.add(idx)
            continue

        previous = _normalize_segment(path_segments[idx - 1]) if idx > 0 else ""
        earlier_context = {_normalize_segment(s) for s in path_segments[:idx]}
        if (
            previous in SESSION_PATH_MARKERS
            and _looks_like_opaque_path_token(segment)
            and (previous not in {"id"} or bool(earlier_context & SESSION_PATH_CONTEXTS))
        ):
            confidence_score = max(confidence_score, settings.SESSION_PATH_HASH_CONFIDENCE)
            ephemeral_params.append(f"path:/{previous}/{segment}")
            details.append((f"path:/{previous}/{segment}", "path marker followed by opaque session / search token"))
            ephemeral_path_indexes.add(idx)
            # For marker / token pairs such as /search / id/<token>, strip both
            # from canonical.
            if previous in SESSION_PATH_MARKERS:
                ephemeral_path_indexes.add(idx - 1)

    # Build canonical URL (with ephemeral params removed)
    canonical_params = {k: v for k, v in params.items() if k not in ephemeral_params}
    canonical_query = urlencode(canonical_params, doseq=True)
    canonical_path_segments = [segment for idx, segment in enumerate(path_segments) if idx not in ephemeral_path_indexes]
    canonical_path = "/" + "/".join(canonical_path_segments) if canonical_path_segments else parsed.path
    if parsed.path.endswith("/") and not canonical_path.endswith("/"):
        canonical_path += "/"

    canonical_url = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            canonical_path,
            parsed.params,
            canonical_query,
            parsed.fragment,
        )
    )

    # If no ephemeral params found but URL has query params, low confidence
    if not ephemeral_params and params:
        confidence_score = min(confidence_score, settings.SESSION_NO_EPHEMERAL_MAX_CONFIDENCE)

    return {
        "is_session_bound": len(ephemeral_params) > 0 or confidence_score >= settings.SESSION_BOUND_CONFIDENCE_THRESHOLD,
        "ephemeral_params": ephemeral_params,
        "canonical_url": canonical_url,
        "confidence": round(confidence_score, 2),
        "details": details,
    }


def strip_session_params(url: str) -> str:
    """Remove ephemeral parameters from a URL, returning the canonical form.

    Convenience function that calls detect_session_params and returns
    just the canonical URL.

    Args:
        url: The URL to strip

    Returns:
        The URL with ephemeral parameters removed
    """
    result = detect_session_params(url)
    return result["canonical_url"]
