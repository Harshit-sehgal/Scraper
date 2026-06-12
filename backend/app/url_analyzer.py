"""URL Intelligence — analyze a URL and classify its scraping risk.

This module provides intelligent URL analysis that helps the product
decide which extraction mode to recommend.  It classifies URLs into
product-relevant categories and returns a structured recommendation.

Example::

    from app.url_analyzer import analyze_url
    result = analyze_url("https://example.com/search?q=laptop")
    print(result.classification)      # "normal_static_page"
    print(result.recommended_mode)  # "direct_scrape"

Design goals
------------
- **Fast** — classification happens without fetching the page (URL-only).
- **Safe** — never attempts to bypass any protection; only reads the URL.
- **Extensible** — new heuristics are one-line regex additions.
- **Testable** — pure functions with no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

# ---------------------------------------------------------------------------
# Classification taxonomy (matches the product plan)
# ---------------------------------------------------------------------------


class UrlClassification(StrEnum):
    """Product-level classification for a URL."""

    NORMAL_STATIC_PAGE = "normal_static_page"
    SEARCH_RESULT_PAGE = "search_result_page"
    SESSION_BOUND_URL = "session_bound_url"
    LOGIN_REQUIRED_PAGE = "login_required_page"
    PAGINATION_PAGE = "pagination_page"
    INFINITE_SCROLL_PAGE = "infinite_scroll_page"
    LOAD_MORE_PAGE = "load_more_page"
    NETWORK_API_BACKED_PAGE = "network_api_backed_page"
    FILE_DOWNLOAD_PAGE = "file_download_page"
    BLOCKED_OR_CHALLENGE_PAGE = "blocked_or_challenge_page"
    EMPTY_OR_LOW_DATA_PAGE = "empty_or_low_data_page"
    UNSAFE_URL = "unsafe_url"
    UNKNOWN = "unknown"


class ScrapingMode(StrEnum):
    """Supported extraction modes the UI can switch to."""

    DIRECT_SCRAPE = "direct_scrape"
    WORKFLOW_REPLAY_RECOMMENDED = "workflow_replay_recommended"
    AUTH_PROFILE_RECOMMENDED = "auth_profile_recommended"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    BLOCKED_OR_UNSAFE = "blocked_or_unsafe"
    UNKNOWN = "unknown"

    # Compatibility aliases for older callers/tests.
    WORKFLOW_REPLAY = "workflow_replay_recommended"
    MANUAL_MAPPING = "manual_review_required"
    AUTH_PROFILE = "auth_profile_recommended"
    NOT_RECOMMENDED = "blocked_or_unsafe"


# ---------------------------------------------------------------------------
# Confidence / risk helpers
# ---------------------------------------------------------------------------


def _url_query_param_value(url: str, param: str) -> str | None:
    """Extract a specific query parameter value from a URL, or None."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    values = qs.get(param, [])
    return values[0] if values else None


# Heuristic constants: signals that indicate high-risk / session-bound URLs
_SESSION_PARAM_NAMES = frozenset(
    {
        "sessionid",
        "session_id",
        "sid",
        "jsessionid",
        "searchid",
        "search_id",
        "resultid",
        "resultsid",
        "journeyid",
        "tripid",
        "requestid",
        "cacheid",
        "token",
        "authtoken",
        "flowid",
        "state",
        "nonce",
        "conversationid",
        "transactionid",
        "bookingsession",
    },
)

_SEARCH_QUERY_PARAM_NAMES = frozenset({"q", "query", "search", "keyword", "keywords", "term", "terms"})
_SEARCH_PATH_SEQS = frozenset({"search", "results", "search-results", "find", "browse"})

_PAGINATION_PARAM_NAMES = frozenset(
    {
        "page",
        "p",
        "offset",
        "start",
        "startindex",
        "cursor",
        "next",
        "prev",
        "skip",
        "limit",
        "per_page",
        "from",
        "to",
        "go",
        "goto",
    },
)

# Segments commonly seen in paginated / list / search result URLs
_PAGINATION_PATH_SEQS = frozenset(
    {
        "page",
        "pages",
        "p",
        "offset",
        "pagination",
        "list",
        "results",
        "search-results",
        "search",
    },
)

# File extensions that indicate downloads or non-HTML content
_DOWNLOAD_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".7z",
        ".rar",
        ".csv",
        ".xls",
        ".xlsx",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".txt",
        ".rtf",
        ".json",
        ".xml",
        ".rss",
        ".atom",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".svg",
        ".webp",
        ".bmp",
        ".ico",
        ".tiff",
        ".psd",
        ".eps",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".otf",
    },
)

# Hostname and path fragments that commonly indicate login / auth pages
_LOGIN_PATH_FRAGMENTS = frozenset(
    {
        "/login",
        "/login/",
        "/signin",
        "/signin/",
        "/auth",
        "/auth/",
        "/authenticate",
        "/authenticate/",
        "/sso",
        "/sso/",
        "/oauth",
        "/oauth/",
        "/connect",
        "/connect/",
        "/authorize",
        "/authorize/",
    },
)

# API path prefixes that suggest the endpoint serves JSON directly
_API_PATH_PREFIXES = frozenset(
    {
        "/api/",
        "/api/v1/",
        "/api/v2/",
        "/api/v3/",
        "/api/v4/",
        "/v1/",
        "/v2/",
        "/v3/",
        "/v4/",
        "/graphql",
        "/rest/",
        "/json/",
        "/data/",
        "/service/",
        "/svc/",
        "/internal-api/",
        "/public-api/",
        "/api-gateway/",
    },
)

# Hostname prefixes that indicate an API-only domain
_API_HOST_PREFIXES = frozenset(
    {
        "api.",
        "api-",
        "graphql.",
        "rest.",
        "svc.",
        "service.",
    },
)

# ---------------------------------------------------------------------------
# Core classifiers (pure, no I/O)
# ---------------------------------------------------------------------------


def _detect_session_signals(url: str) -> dict:
    """Return a dict of session-signal heuristics for a URL."""
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    params = {k.lower(): v for k, v in pairs}
    matched_original = {name: value for name, value in pairs if name.lower() in _SESSION_PARAM_NAMES}
    matched = {name.lower() for name in matched_original}
    return {
        "has_session_param": bool(matched),
        "matched_session_params": matched,
        "matched_session_param_names": list(matched_original),
        "matched_session_param_values": {name: _redact_sensitive_value(value) for name, value in matched_original.items()},
        "param_count": len(params),
    }


def _detect_pagination_signals(url: str) -> dict:
    """Return pagination heuristic signals."""
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    params = {k.lower(): v for k, v in query_params.items()}

    matched = {name for name in params if name in _PAGINATION_PARAM_NAMES}

    path_pagination = any(seg in _PAGINATION_PATH_SEQS for seg in parsed.path.lower().split("/") if seg)

    return {
        "has_pagination_param": bool(matched),
        "matched_pagination_params": matched,
        "path_suggests_pagination": path_pagination,
    }


def _detect_login_path(url: str) -> bool:
    """Return True if the URL path contains a known login fragment."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    # Normalize trailing slash so `/app/login/` matches `/login`
    if not path.endswith("/"):
        path = path + "/"
    return any(path.startswith(fragment) for fragment in _LOGIN_PATH_FRAGMENTS) or any(
        "/" + fragment.strip("/") in path for fragment in _LOGIN_PATH_FRAGMENTS
    )


def _detect_file_download(url: str) -> bool:
    """Return True if the URL path ends with a known download extension."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in _DOWNLOAD_EXTENSIONS)


def _detect_api_endpoint(url: str) -> bool:
    """Return True if the URL path or hostname matches a known API pattern."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if any(host.startswith(prefix) for prefix in _API_HOST_PREFIXES):
        return True
    path = parsed.path.lower()
    if not path.endswith("/"):
        path = path + "/"
    return any(path.startswith(prefix.lower()) for prefix in _API_PATH_PREFIXES)


def _has_infinite_scroll_keywords(url: str) -> bool:
    """Keyword-only heuristic for infinite-scroll or load-more patterns."""
    parsed = urlparse(url)
    combined = f"{parsed.path} {parsed.query}".lower()
    keywords = (
        "infinite",
        "scroll",
        "loadmore",
        "load_more",
        "lazy",
        "endless",
        "masonry",
        "timeline",
        "feed",
        "stream",
        "more_items",
        "page_size",
    )
    return any(kw in combined for kw in keywords)


def _detect_search_result_url(url: str) -> bool:
    """Return True when URL-only signals suggest a search results page."""
    parsed = urlparse(url)
    params = {k.lower() for k, _v in parse_qsl(parsed.query, keep_blank_values=True)}
    if params & _SEARCH_QUERY_PARAM_NAMES:
        return True
    segments = {seg for seg in parsed.path.lower().split("/") if seg}
    return bool(segments & _SEARCH_PATH_SEQS)


def _redact_sensitive_value(value: str) -> str:
    """Redact a URL parameter value while preserving a short debugging hint."""
    raw = str(value or "")
    if not raw:
        return ""
    if len(raw) <= 4:
        return "..."
    if len(raw) <= 8:
        return f"{raw[:2]}...{raw[-2:]}"
    tail = raw[-6] + raw[-3:] if len(raw) >= 12 else raw[-4:]
    return f"{raw[:4]}...{tail}"


def redact_sensitive_url(url: str) -> tuple[str, bool]:
    """Return `url` with known temporary/session parameter values redacted."""
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if not pairs:
        return url, False

    safe_pairs: list[tuple[str, str]] = []
    redacted = False
    for name, value in pairs:
        if name.lower() in _SESSION_PARAM_NAMES:
            safe_pairs.append((name, _redact_sensitive_value(value)))
            redacted = True
        else:
            safe_pairs.append((name, value))
    if not redacted:
        return url, False
    return urlunparse(parsed._replace(query=urlencode(safe_pairs, doseq=True))), True


def suggested_start_urls(url: str) -> list[dict]:
    """Suggest stable start URLs for a temporary/session result URL."""
    parsed = urlparse(url)
    base = parsed._replace(params="", query="", fragment="")
    segments = [seg for seg in parsed.path.split("/") if seg]
    suggestions: list[dict] = []

    def add(path: str, confidence: float, reason: str) -> None:
        candidate = urlunparse(base._replace(path=path))
        if not any(item["url"] == candidate for item in suggestions):
            suggestions.append(
                {
                    "url": candidate,
                    "confidence": confidence,
                    "reason": reason,
                    "requires_confirmation": True,
                },
            )

    if len(segments) > 1:
        add("/" + "/".join(segments[:-1]), 0.72, "Parent path may be the stable search or listing page.")
    if segments:
        add("/", 0.55, "Site root is a safe fallback start page for manual confirmation.")
    return suggestions


def _json_safe(value):
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Recommendation engine
# ---------------------------------------------------------------------------


def _recommend_mode(
    classification: UrlClassification,
    _session_signals: dict,
    _pagination_signals: dict,
    is_login: bool,
    is_download: bool,
    is_api: bool,
) -> tuple[ScrapingMode, list[str]]:
    """Return the recommended scraping mode and next-step hints.

    The logic is deliberately conservative: when in doubt, recommend a
    workflow or manual approach rather than a direct scrape.
    """
    steps: list[str] = []

    if is_download:
        return ScrapingMode.MANUAL_REVIEW_REQUIRED, [
            "This URL points to a file download, not an HTML page.",
        ]

    if is_login:
        steps = [
            "Detect if the target data is behind a login wall.",
            "If so, create an Auth Profile for the domain.",
        ]
        return ScrapingMode.AUTH_PROFILE_RECOMMENDED, steps

    if classification == UrlClassification.SESSION_BOUND_URL:
        steps = [
            "Session tokens in the URL may expire.",
            "Detect the original search / entry page.",
            "Build a replay workflow with fresh parameters.",
        ]
        return ScrapingMode.WORKFLOW_REPLAY_RECOMMENDED, steps

    if classification == UrlClassification.PAGINATION_PAGE:
        steps = [
            "Pagination detected — configure max_pages and deduplication.",
            "Preview the first page before full scrape.",
        ]
        return ScrapingMode.DIRECT_SCRAPE, steps

    if is_api or classification == UrlClassification.NETWORK_API_BACKED_PAGE:
        steps = [
            "This URL appears to be an API endpoint.",
            "Consider using Network/API extraction mode for cleaner data.",
        ]
        return ScrapingMode.DIRECT_SCRAPE, steps

    if classification in (
        UrlClassification.INFINITE_SCROLL_PAGE,
        UrlClassification.LOAD_MORE_PAGE,
    ):
        steps = [
            "Dynamic content loading detected (infinite scroll / load more).",
            "Configure scroll limits and stop conditions.",
        ]
        return ScrapingMode.DIRECT_SCRAPE, steps

    if classification == UrlClassification.BLOCKED_OR_CHALLENGE_PAGE:
        return ScrapingMode.BLOCKED_OR_UNSAFE, [
            "This URL appears protected by anti-bot measures.",
            "Ethical scraping guidelines discourage bypass attempts.",
        ]

    # Default / normal_static_page / search_result_page / unknown
    steps = [
        "Analyze page structure for extractable data.",
        "Detect schema fields.",
        "Preview extraction before full run.",
    ]
    return ScrapingMode.DIRECT_SCRAPE, steps


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UrlAnalysisResult:
    """Structured result of URL analysis."""

    url: str
    classification: UrlClassification
    risk: str
    recommended_mode: ScrapingMode
    confidence: float
    reason: str
    next_steps: list[str] = field(default_factory=list)
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON responses."""
        redacted_url, _redactions_applied = redact_sensitive_url(self.url)
        return {
            "url": redacted_url,
            "classification": self.classification.value,
            "risk": self.risk,
            "recommended_mode": self.recommended_mode.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "next_steps": self.next_steps,
            "signals": _json_safe(self.signals),
        }

    def to_guided_dict(
        self,
        *,
        safe_to_fetch: bool = True,
        safety_error: str | None = None,
    ) -> dict:
        """Serialize to the Prompt 8 guided scrape-entry response shape."""
        redacted_url, redactions_applied = redact_sensitive_url(self.url)
        if safety_error:
            return {
                "url": redacted_url,
                "safe_to_fetch": False,
                "classifications": [
                    {
                        "type": UrlClassification.UNSAFE_URL.value,
                        "confidence": 1.0,
                        "evidence": "URL safety validation rejected this target.",
                    },
                ],
                "risk_level": "blocked",
                "recommended_mode": ScrapingMode.BLOCKED_OR_UNSAFE.value,
                "user_message": "This URL is blocked by the safety policy.",
                "technical_findings": [f"Safety validation failed: {safety_error}"],
                "suggested_start_urls": [],
                "next_steps": ["Choose a public http(s) URL that is lawful to access."],
                "redactions_applied": redactions_applied,
            }

        classifications = [
            {
                "type": self.classification.value,
                "confidence": self.confidence,
                "evidence": self.reason,
            },
        ]
        session_signals = self.signals.get("session", {}) if isinstance(self.signals, dict) else {}
        pagination_signals = self.signals.get("pagination", {}) if isinstance(self.signals, dict) else {}
        matched_names = session_signals.get("matched_session_param_names") or []
        redacted_values = session_signals.get("matched_session_param_values") or {}

        technical_findings: list[str] = [
            f"Temporary parameter detected: {name}={redacted_values.get(name, '')}" for name in matched_names
        ]
        if pagination_signals.get("has_pagination_param"):
            params = ", ".join(sorted(pagination_signals.get("matched_pagination_params") or []))
            technical_findings.append(f"Pagination parameter detected: {params}")

        if self.recommended_mode == ScrapingMode.DIRECT_SCRAPE:
            user_message = "This looks like a normal page. Recommended mode: Direct Scrape."
        elif self.recommended_mode == ScrapingMode.WORKFLOW_REPLAY_RECOMMENDED:
            name = matched_names[0] if matched_names else "a temporary parameter"
            user_message = f"This URL looks temporary because it contains {name}. Direct scraping may fail later."
        elif self.recommended_mode == ScrapingMode.AUTH_PROFILE_RECOMMENDED:
            user_message = "This page may require login. Recommended mode: Auth Profile."
        elif self.recommended_mode == ScrapingMode.BLOCKED_OR_UNSAFE:
            user_message = "This URL is blocked by the safety policy."
        else:
            user_message = "This URL needs manual review before scraping."

        needs_start = self.classification in {
            UrlClassification.SESSION_BOUND_URL,
            UrlClassification.SEARCH_RESULT_PAGE,
        }

        return {
            "url": redacted_url,
            "safe_to_fetch": safe_to_fetch,
            "classifications": classifications,
            "risk_level": self.risk,
            "recommended_mode": self.recommended_mode.value,
            "user_message": user_message,
            "technical_findings": technical_findings,
            "suggested_start_urls": suggested_start_urls(self.url) if needs_start else [],
            "next_steps": self.next_steps,
            "redactions_applied": redactions_applied,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_url(url: str) -> UrlAnalysisResult:
    """Analyze a single URL and return a structured recommendation.

    This is a pure function that does **no** network I/O.  It inspects the
    URL string only and returns a ``UrlAnalysisResult``.
    """
    if not url or not url.startswith(("http://", "https://")):
        return UrlAnalysisResult(
            url=url,
            classification=UrlClassification.UNKNOWN,
            risk="high",
            recommended_mode=ScrapingMode.BLOCKED_OR_UNSAFE,
            confidence=1.0,
            reason="Invalid or non-HTTP URL.",
            next_steps=["Provide a valid http(s) URL."],
            signals={"invalid_url": True},
        )

    urlparse(url)

    # --- Heuristic extraction ------------------------------------------------
    session_signals = _detect_session_signals(url)
    pagination_signals = _detect_pagination_signals(url)
    is_login = _detect_login_path(url)
    is_download = _detect_file_download(url)
    is_api = _detect_api_endpoint(url)
    is_infinite_scroll = _has_infinite_scroll_keywords(url)
    is_search_result = _detect_search_result_url(url)

    # --- Decision tree (ordered by specificity) ------------------------------
    classification = UrlClassification.UNKNOWN
    risk = "low"
    reason = "Default static page analysis."

    if is_download:
        classification = UrlClassification.FILE_DOWNLOAD_PAGE
        risk = "low"
        reason = "URL points to a downloadable file, not an HTML page."

    elif is_login:
        classification = UrlClassification.LOGIN_REQUIRED_PAGE
        risk = "medium"
        reason = "URL path suggests a login or authentication page."

    elif is_api:
        classification = UrlClassification.NETWORK_API_BACKED_PAGE
        risk = "low"
        reason = "URL path suggests an API endpoint that may return structured JSON."

    elif session_signals["has_session_param"]:
        classification = UrlClassification.SESSION_BOUND_URL
        risk = "high"
        reason = (
            f"URL contains session-like parameters ({', '.join(session_signals['matched_session_params'])}). These may expire."
        )

    elif is_infinite_scroll:
        classification = UrlClassification.INFINITE_SCROLL_PAGE
        risk = "medium"
        reason = "URL contains keywords suggesting dynamic or infinite-scroll content."

    elif is_search_result:
        classification = UrlClassification.SEARCH_RESULT_PAGE
        risk = "medium"
        reason = "URL path or query suggests a search results page."

    elif pagination_signals["has_pagination_param"] or pagination_signals["path_suggests_pagination"]:
        classification = UrlClassification.PAGINATION_PAGE
        risk = "low"
        reason = "Pagination parameters or path pattern detected."

    else:
        # Default: assume normal static page
        classification = UrlClassification.NORMAL_STATIC_PAGE
        risk = "low"
        reason = "No special signals detected; appears to be a normal static or search result page."

    # --- Mode recommendation ------------------------------------------------
    mode, next_steps = _recommend_mode(
        classification,
        session_signals,
        pagination_signals,
        is_login,
        is_download,
        is_api,
    )

    confidence = 0.95 if classification != UrlClassification.UNKNOWN else 0.5

    return UrlAnalysisResult(
        url=url,
        classification=classification,
        risk=risk,
        recommended_mode=mode,
        confidence=confidence,
        reason=reason,
        next_steps=next_steps,
        signals={
            "session": session_signals,
            "pagination": pagination_signals,
            "is_login": is_login,
            "is_download": is_download,
            "is_api": is_api,
            "is_infinite_scroll": is_infinite_scroll,
            "is_search_result": is_search_result,
        },
    )
