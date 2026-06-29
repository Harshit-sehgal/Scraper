"""Comp 7: Cookie consent handling — test detection and handling of cookie banners."""

from __future__ import annotations

import re
from typing import Any

COOKIE_BANNER_PATTERNS = [
    r"accept.*cookies",
    r"cookie.*consent",
    r"cookie.*notice",
    r"cookie.*settings",
    r"accept all cookies",
    r"reject.*cookies",
    r"cookie.*preferences",
    r"this website uses cookies",
    r"we use cookies",
    r"cookie.*banner",
    r"onetrust",
    r"cookiebot",
    r"osano",
    r"cookie.*policy",
    r"gdpr.*cookie",
    r"consent.*management",
    r"cookie.*wall",
    r"accept.*all.*tracking",
    r"your privacy",
    r"privacy.*preferences",
    r"manage.*consent",
]


def _detect_cookie_consent_banner(html: str) -> dict[str, Any]:
    """Detect if a page has a cookie consent banner."""
    lower_html = html.lower()
    detected_patterns = []
    for pattern in COOKIE_BANNER_PATTERNS:
        if re.search(pattern, lower_html):
            detected_patterns.append(pattern)
    return {
        "has_banner": len(detected_patterns) > 0,
        "detected_patterns": detected_patterns,
        "pattern_count": len(detected_patterns),
    }


def _handle_cookie_consent(html: str, policy: str = "accept_all") -> dict[str, Any]:
    """Simulate handling cookie consent based on policy.

    Policy: accept_all, reject_all, essential_only
    """
    detection = _detect_cookie_consent_banner(html)
    if not detection["has_banner"]:
        return {"action": "none_needed", "policy_applied": policy, **detection}
    if policy == "accept_all":
        return {"action": "accepted", "policy_applied": policy, **detection}
    if policy == "reject_all":
        return {"action": "rejected", "policy_applied": policy, **detection}
    return {"action": "essential_only", "policy_applied": policy, **detection}


class TestCookieBannerDetection:
    def test_detects_accept_cookies(self) -> None:
        html = "<html><body><div id='cookie-banner'>Accept cookies</div></body></html>"
        result = _detect_cookie_consent_banner(html)
        assert result["has_banner"] is True

    def test_detects_cookie_consent(self) -> None:
        html = "<html><body><div>Cookie consent notice</div></body></html>"
        result = _detect_cookie_consent_banner(html)
        assert result["has_banner"] is True

    def test_detects_we_use_cookies(self) -> None:
        html = "<html><body><p>We use cookies to improve your experience</p></body></html>"
        result = _detect_cookie_consent_banner(html)
        assert result["has_banner"] is True

    def test_detects_privacy_preferences(self) -> None:
        html = "<html><body><div>Privacy preferences</div></body></html>"
        result = _detect_cookie_consent_banner(html)
        assert result["has_banner"] is True

    def test_no_banner_on_clean_page(self) -> None:
        html = "<html><body><h1>Welcome</h1><p>General content without any tracking banners or consent popups</p></body></html>"
        result = _detect_cookie_consent_banner(html)
        assert result["has_banner"] is False

    def test_empty_html_no_banner(self) -> None:
        result = _detect_cookie_consent_banner("")
        assert result["has_banner"] is False

    def test_one_trust_detected(self) -> None:
        html = "<html><head><script src='https://cdn.onetrust.com/consent.js'></script></head><body>Content</body></html>"
        result = _detect_cookie_consent_banner(html)
        assert result["has_banner"] is True

    def test_cookiebot_detected(self) -> None:
        html = "<html><body><div id='CookieBot'>Cookie settings</div></body></html>"
        result = _detect_cookie_consent_banner(html)
        assert result["has_banner"] is True


class TestCookieConsentHandling:
    def test_accept_all_policy(self) -> None:
        html = "<html><body><div>Accept cookies</div></body></html>"
        result = _handle_cookie_consent(html, policy="accept_all")
        assert result["action"] == "accepted"

    def test_reject_all_policy(self) -> None:
        html = "<html><body><div>Cookie consent</div></body></html>"
        result = _handle_cookie_consent(html, policy="reject_all")
        assert result["action"] == "rejected"

    def test_no_banner_no_action(self) -> None:
        html = "<html><body><p>No cookies here</p></body></html>"
        result = _handle_cookie_consent(html)
        assert result["action"] == "none_needed"

    def test_essential_only_policy(self) -> None:
        html = "<html><body><div>Cookie preferences</div></body></html>"
        result = _handle_cookie_consent(html, policy="essential_only")
        assert result["action"] == "essential_only"
