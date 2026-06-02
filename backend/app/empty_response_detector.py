"""Empty response detector — flags pages that return HTTP 200 but contain
no useful data content.

Detects "empty but 200" responses: pages that technically succeed (200 OK)
but are effectively useless — blank pages, cookie consent walls, JavaScript
shell pages with no rendered content, redirect pages that don't actually
redirect, and other degenerate cases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from app.config import settings


@dataclass
class EmptyResponseCheck:
    """Result of checking a response for empty-but-200 conditions."""

    is_empty: bool
    """Whether the response is effectively empty despite a 200 status."""

    empty_type: str = ""
    """Classification: blank, cookie_wall, js_shell, redirect_meta, captcha, login_wall, minimal"""

    confidence: float = 0.0
    """0.0 - 1.0 confidence that this is an empty / unhelpful response."""

    message: str = ""
    """Human-readable explanation."""

    text_length: int = 0
    """Length of visible text content after stripping tags."""

    data_signals: int = 0
    """Number of data-like signals found (prices, dates, structured content)."""

    suggestions: list[str] | None = None
    """Actionable suggestions for the user."""

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


# Patterns that indicate a page has real data content
DATA_SIGNAL_PATTERNS: list[re.Pattern] = [
    re.compile(r"\$\d+[\d,.]*"),  # Currency: $450, $1,234.56
    re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"),  # Dates: 05 / 15 / 2026
    re.compile(r"\d{4}-\d{2}-\d{2}"),  # ISO dates: 2026 - 05 - 15
    re.compile(r"\d+\.\d{1,2}%"),  # Percentages: 85.5%
    re.compile(r"\b\d{1,3}(,\d{3})*\b"),  # Large numbers: 1,234,567
    re.compile(r"@[a-zA-Z0-9._-]+\.[a-z]{2,}"),  # Emails
    re.compile(r"\+\d{1,3}[\s-]?\d{3,}"),  # Phone numbers
    re.compile(r"https?://[^\s<\"]+"),  # URLs
]

# Patterns that indicate an empty / unhelpful page — checked against RAW HTML
EMPTY_PAGE_SIGNALS: dict[str, list[re.Pattern]] = {
    "cookie_wall": [
        re.compile(r"cookie\s*(consent|banner|notice|policy|preferences)", re.I),
        re.compile(r"accept\s+all\s+cookies", re.I),
        re.compile(r"we\s+use\s+cookies", re.I),
    ],
    "login_wall": [
        re.compile(r"sign\s*in\s+to\s+(continue|view|access)", re.I),
        re.compile(r"log\s*in\s+to\s+(continue|view|access)", re.I),
        re.compile(r"please\s+(log|sign)\s*in", re.I),
        re.compile(r"create\s+(an?\s+)?account\s+to\s+continue", re.I),
    ],
    "captcha": [
        re.compile(r"captcha", re.I),
        re.compile(r"recaptcha", re.I),
        re.compile(r"hcaptcha", re.I),
        re.compile(r"cloudflare.*challenge", re.I),
        re.compile(r"verify\s+you\s+are\s+human", re.I),
    ],
    "redirect_meta": [
        re.compile(r'<meta[^>]*http-equiv\s*=\s*["\']?refresh["\']?', re.I),
        re.compile(r"redirecting\s+to", re.I),
        re.compile(r"you\s+will\s+be\s+redirected", re.I),
    ],
    "js_shell": [
        re.compile(r"<noscript>.*?please\s+enable\s+javascript.*?</noscript>", re.I | re.S),
        re.compile(r"you\s+need\s+to\s+enable\s+javascript", re.I),
        re.compile(r"javascript\s+is\s+required", re.I),
    ],
}


def detect_empty_response(html: str, status_code: int = 200) -> EmptyResponseCheck:
    """Detect if an HTTP response is effectively empty despite returning 200.

    Checks for various "empty but 200" conditions: blank pages, cookie walls,
    login walls, CAPTCHAs, JavaScript-only shells, meta redirects, and pages
    with minimal visible text.

    Args:
        html: The page HTML content
        status_code: HTTP status code (defaults to 200)

    Returns:
        EmptyResponseCheck with classification and suggestions
    """
    if not html or len(html.strip()) < settings.EMPTY_RESPONSE_MIN_HTML_LEN:
        return EmptyResponseCheck(
            is_empty=True,
            empty_type="blank",
            confidence=1.0,
            message="Page is blank or has less than 50 characters of HTML",
            text_length=0,
            data_signals=0,
            suggestions=["The URL may be incorrect or the server returned an empty page"],
        )

    # ── Step 1: Check raw HTML for empty-page signals (before stripping tags) ──
    detected_types: list[tuple[str, float]] = []

    for empty_type, patterns in EMPTY_PAGE_SIGNALS.items():
        for pattern in patterns:
            if pattern.search(html):
                detected_types.append((empty_type, settings.EMPTY_PAGE_SIGNAL_CONFIDENCE))
                break

    # ── Step 2: Extract visible text and count data signals ──
    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, and other non-content elements
    for tag in soup(["script", "style", "noscript", "svg", "link"]):
        tag.decompose()

    visible_text = soup.get_text(separator=" ", strip=True)
    text_length = len(visible_text)

    # Count data signals in visible text
    data_signals = 0
    for pattern in DATA_SIGNAL_PATTERNS:
        matches = pattern.findall(visible_text)
        data_signals += len(matches)

    # ── Step 3: Check for minimal content ──
    if text_length < settings.EMPTY_RESPONSE_MINIMAL_TEXT_LEN:
        detected_types.append(("minimal", 0.9))
    elif text_length < settings.EMPTY_RESPONSE_LOW_TEXT_LEN and data_signals < settings.EMPTY_RESPONSE_LOW_SIGNAL_COUNT:
        detected_types.append(("minimal", settings.EMPTY_RESPONSE_CONFIDENCE_THRESHOLD))

    # ── Step 4: If we found strong data signals, the page is not empty ──
    if data_signals >= settings.EMPTY_RESPONSE_DATA_SIGNAL_THRESHOLD:
        return EmptyResponseCheck(
            is_empty=False,
            empty_type="",
            confidence=0.0,
            message=f"Page has {data_signals} data signals and {text_length} chars of visible text",
            text_length=text_length,
            data_signals=data_signals,
        )

    # Moderate data signals reduce empty confidence
    if data_signals >= settings.EMPTY_RESPONSE_MODERATE_SIGNAL_COUNT:
        detected_types = [(etype, conf * 0.5) for etype, conf in detected_types]

    # ── Step 5: Determine the best classification ──
    if detected_types:
        # Prioritize specific types over "minimal"
        specific_types = [(etype, conf) for etype, conf in detected_types if etype != "minimal"]
        if specific_types:
            best_type, best_conf = max(specific_types, key=lambda x: x[1])
        else:
            best_type, best_conf = max(detected_types, key=lambda x: x[1])

        is_empty = best_conf >= settings.EMPTY_RESPONSE_CONFIDENCE_THRESHOLD

        suggestions = []
        if best_type == "cookie_wall":
            suggestions.append("Page shows a cookie consent wall — try accepting cookies first")
        elif best_type == "login_wall":
            suggestions.append("Page requires login — provide authentication credentials")
        elif best_type == "captcha":
            suggestions.append("Page has CAPTCHA protection — try a different fetch strategy or add delays")
        elif best_type == "js_shell":
            suggestions.append("Page requires JavaScript rendering — ensure Playwright is used for fetching")
        elif best_type == "redirect_meta":
            suggestions.append("Page uses meta-refresh redirect — follow the redirect target URL")
        elif best_type == "minimal":
            suggestions.append("Page has very little content — URL may be incorrect or page may need different parameters")

        return EmptyResponseCheck(
            is_empty=is_empty,
            empty_type=best_type,
            confidence=round(best_conf, 2),
            message=f"Page appears to be a {best_type} with {text_length} chars of visible text and {data_signals} data signals",
            text_length=text_length,
            data_signals=data_signals,
            suggestions=suggestions,
        )

    # No empty signals detected and some content exists
    return EmptyResponseCheck(
        is_empty=False,
        empty_type="",
        confidence=0.0,
        message=f"Page has {text_length} chars of visible text and {data_signals} data signals",
        text_length=text_length,
        data_signals=data_signals,
    )
