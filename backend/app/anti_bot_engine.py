"""Anti-Bot Detection Engine — Identifying when automated access is blocked.

Responsible for:
- Detecting challenges (Cloudflare, Akamai, etc.)
- Identifying CAPTCHAs and blocking patterns
- Providing adaptive pacing and retry policies
- Browser entropy stabilization
- Proxy rotation coordination
"""

from __future__ import annotations

import logging
import random
import re
import time
from typing import Any

from app.config import settings
from app.utils.log_redaction import mask_proxy_url

logger = logging.getLogger(__name__)

# Primary detection patterns for common anti-bot platforms
CHALLENGE_PATTERNS = {
    "cloudflare": [
        "cf-browser-verification",
        "cf-challenge",
        "cf-turnstile",
        "challenge-platform",
        "checking your browser",
        "attention required",
    ],
    "akamai": ["akamai-ghost", "ak_bmsc", "bm_sz", "_abck"],
    "datadome": ["dd-captcha", "datadome", "dd="],
    "perimeterx": ["perimeterx", "px-captcha", "_px"],
    "incapsula": ["incapsula", "visid_incap", "incap_ses", "imperva"],
    "captcha": ["g-recaptcha", "h-captcha", "recaptcha", "hcaptcha"],
    "generic_block": [
        "access denied",
        "blocked",
        "sorry, you have been blocked",
        "please verify",
        "security check",
        "suspicious activity",
        "captcha",
        "human verify",
        "bot detection",
        "robot",
    ],
    "js_required": ["enable javascript", "javascript is required", "browser is not supported"],
    "rate_limit": ["too many requests", "429", "rate limit"],
}

# Probability weights for detection signals
SIGNAL_WEIGHTS = {
    "challenge-platform": 0.95,
    "cf-browser-verification": 0.95,
    "cf-turnstile": 0.95,
    "g-recaptcha": 0.9,
    "h-captcha": 0.9,
    "datadome": 0.95,
    "perimeterx": 0.95,
    "incapsula": 0.9,
    "imperva": 0.9,
    "access denied": 0.8,
    "blocked": 0.8,
    "please verify": 0.7,
    "security check": 0.7,
    "sorry, you have been blocked": 0.95,
    "enable javascript": 0.6,
    "javascript is required": 0.6,
    "too many requests": 0.85,
}


class AntiBotEngine:
    """Intelligent engine for detecting and responding to anti-bot systems."""

    def __init__(self) -> None:
        self._block_history: dict[str, list[float]] = {}
        # Lazy import to avoid circular dependencies
        self._proxy_manager: Any = None
        self._cookies: dict[str, str] = {}  # domain -> cookie_string
        self._last_cookie_update: dict[str, float] = {}
        # domain -> user agents used
        self._ua_history: dict[str, list[str]] = {}

    @property
    def proxy_manager(self):
        """Lazy-load proxy manager."""
        if self._proxy_manager is None:
            from app.proxy_manager import get_proxy_manager

            self._proxy_manager = get_proxy_manager()
        return self._proxy_manager

    def detect_challenges(self, html: str, headers: dict | None = None) -> float:
        """Score how likely the page is a challenge or block page.

        Returns a score from 0.0 (clean) to 1.0 (certainly blocked).
        """
        if not html:
            return 0.0

        lower_html = html.lower()
        max_score = 0.0

        # 1. HTML Signal Detection
        for signal, score in SIGNAL_WEIGHTS.items():
            if signal in lower_html:
                max_score = max(max_score, score)

        # 2. Pattern-based structural checks
        for patterns in CHALLENGE_PATTERNS.values():
            for p in patterns:
                if p in lower_html:
                    # Platform matches boost score
                    max_score = max(max_score, settings.ANTIBOT_PLATFORM_MATCH_SCORE)

        # 3. Header-based Detection
        if headers:
            headers_lower = {k.lower(): str(v).lower() for k, v in headers.items()}
            # Look for common anti-bot headers
            server = headers_lower.get("server", "")
            if "cloudflare" in server:
                max_score = max(max_score, settings.ANTIBOT_CLOUDFLARE_SCORE)
            if "akamai" in server:
                max_score = max(max_score, settings.ANTIBOT_AKAMAI_SCORE)

            # Check for set-cookie headers related to bot detection
            cookies = headers_lower.get("set-cookie", "")
            if any(p in cookies for p in ["_abck", "_px", "datadome", "incap_ses"]):
                max_score = max(max_score, 0.5)

        return max_score

    def detect_challenge_platform(self, html: str, headers: dict | None = None) -> str:
        """Identify which anti-bot platform matched (best-effort, single label).

        Returns the platform name (``"cloudflare"``, ``"akamai"``, ``"datadome"``,
        ``"perimeterx"``, ``"incapsula"``, ``"captcha"``, ``"rate_limit"``,
        ``"generic_block"``, ``"js_required"``) or ``"ok"`` when no platform
        matched. Used by the observability layer to record
        ``dataforge_anti_bot_classifications_total{classification=...}``.
        """
        if not html:
            return "ok"

        lower_html = html.lower()

        # Order matters: more specific patterns win over generic ones.
        ordered_platforms = (
            "cloudflare",
            "akamai",
            "datadome",
            "perimeterx",
            "incapsula",
            "captcha",
            "rate_limit",
            "js_required",
            "generic_block",
        )
        for platform in ordered_platforms:
            patterns = CHALLENGE_PATTERNS.get(platform, [])
            for p in patterns:
                if p in lower_html:
                    return platform

        if headers:
            headers_lower = {k.lower(): str(v).lower() for k, v in headers.items()}
            server = headers_lower.get("server", "")
            if "cloudflare" in server:
                return "cloudflare"
            if "akamai" in server:
                return "akamai"
            cookies = headers_lower.get("set-cookie", "")
            if any(p in cookies for p in ["_abck", "_px", "datadome", "incap_ses"]):
                return "captcha"

        return "ok"

    def should_evolve_to_stealth(self, domain: str) -> bool:
        """Heuristic check if a domain requires stealth mode."""
        history = self._block_history.get(domain, [])
        if not history:
            return False

        # If mean score of last 3 attempts is > 0.4, or any is > 0.8
        recent = history[-3:]
        if any(s > settings.ANTIBOT_HARD_BLOCK_THRESHOLD for s in recent):
            return True
        return bool(len(recent) >= 2 and sum(recent) / len(recent) > settings.ANTIBOT_STEALTH_ESCALATION_MEAN)

    def get_stealth_profile(self, domain: str) -> dict:
        """Return a comprehensive stealth profile for a domain.

        Returns a dict with:
          - user_agent: randomized UA string
          - extra_headers: dict of browser-specific headers
          - viewport: randomized viewport dimensions
          - cookie_string: persisted cookies for this domain (if any)
          - timezone: randomized timezone ID
          - locale: browser locale string
          - platform: OS platform string
        """
        # UA rotation based on attempt history
        ua_pool = settings.STEALTH_UA_POOL.split(",")

        # Track UAs used per domain to avoid reusing the same one
        used_uas = self._ua_history.get(domain, [])
        available = [ua for ua in ua_pool if ua not in used_uas]
        if not available:
            available = ua_pool
        ua = random.choice(available)  # nosec B311

        # Update history
        if domain not in self._ua_history:
            self._ua_history[domain] = []
        self._ua_history[domain].append(ua)
        # Keep last 5
        self._ua_history[domain] = self._ua_history[domain][-settings.ANTIBOT_UA_HISTORY_SIZE :]

        # Randomize additional headers to mimic real browsers
        is_chromium = "Chrome" in ua and "Firefox" not in ua
        chrome_ver_match = re.search(r"Chrome/(\d+)", ua)
        chrome_ver = chrome_ver_match.group(1) if chrome_ver_match else "122"
        if "Windows" in ua:
            sec_ch_ua_platform = '"Windows"'
        elif "Mac" in ua:
            sec_ch_ua_platform = '"macOS"'
        else:
            sec_ch_ua_platform = '"Linux"'
        extra_headers = {
            "Accept": "text / html,application / xhtml+xml,application / xml;q=0.9,image / avif,image / webp,*/*;q=0.8",
            "Accept-Language": settings.STEALTH_ACCEPT_LANGUAGE,
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua": f'"Chromium";v="{chrome_ver}", "Not(A:Brand";v="24", "Google Chrome";v="{chrome_ver}"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": sec_ch_ua_platform,
        }
        if not is_chromium:
            # Firefox-style headers
            extra_headers["Accept"] = (
                "text / html,application / xhtml+xml,application / xml;q=0.9,image / avif,image / webp,*/*;q=0.8"
            )
            extra_headers["Sec-Fetch-Dest"] = "document"
            extra_headers["Sec-Fetch-Mode"] = "navigate"
            extra_headers["Sec-Fetch-Site"] = "none"
            extra_headers.pop("Sec-Ch-Ua", None)
            extra_headers.pop("Sec-Ch-Ua-Mobile", None)
            extra_headers.pop("Sec-Ch-Ua-Platform", None)

        # Viewport randomization (with reasonable ranges)
        viewport_width = random.choice([int(x) for x in settings.STEALTH_VIEWPORT_WIDTHS.split(",")])  # nosec B311
        viewport_height = random.choice([int(x) for x in settings.STEALTH_VIEWPORT_HEIGHTS.split(",")])  # nosec B311

        return {
            "user_agent": ua,
            "extra_headers": extra_headers,
            "viewport": {"width": viewport_width, "height": viewport_height},
            "cookie_string": self._cookies.get(domain, ""),
            "timezone": random.choice(settings.STEALTH_TIMEZONE_POOL.split(",")),  # nosec B311
            "locale": settings.STEALTH_DEFAULT_LOCALE,
            "platform": "Win32" if "Windows" in ua else ("MacIntel" if "Mac" in ua else "Linux x86_64"),
            "device_scale_factor": random.choice([float(x) for x in settings.STEALTH_DEVICE_SCALE_FACTORS.split(",")]),  # nosec B311
        }

    def update_cookies(self, domain: str, cookie_string: str) -> None:
        """Persist cookies for a domain to reuse on subsequent requests."""
        if not domain or not cookie_string:
            return
        self._cookies[domain] = cookie_string
        self._last_cookie_update[domain] = time.time()
        logger.debug("Cookies updated for domain %s (%d chars)", domain, len(cookie_string))

    def get_cookies(self, domain: str) -> str:
        """Get persisted cookies for a domain."""
        return self._cookies.get(domain, "")

    def should_refresh_cookies(self, domain: str, max_age_hours: int = settings.ANTIBOT_COOKIE_MAX_AGE_HOURS) -> bool:
        """Check if stored cookies for a domain should be refreshed."""
        last_update = self._last_cookie_update.get(domain, 0)
        if last_update == 0:
            return True
        age_hours = (time.time() - last_update) / 3600
        return age_hours > max_age_hours

    def get_retry_policy(self, url: str, last_score: float) -> dict:  # noqa: ARG002, RUF100
        """Determine the next step based on the block score and domain history."""
        policy = {}

        if last_score < 0.3:
            policy = {"action": "continue", "delay": 0}

        elif last_score > settings.ANTIBOT_HARD_BLOCK_THRESHOLD:
            policy = {"action": "retry_slow", "delay": settings.ANTIBOT_HARD_BLOCK_DELAY, "rotate_proxy": True}

        elif last_score > 0.5:
            # Medium challenge: probably just need more wait time / js
            # execution
            policy = {"action": "retry_wait", "delay": settings.ANTIBOT_MEDIUM_CHALLENGE_DELAY}

        else:
            policy = {"action": "continue", "delay": 0}

        # Include current proxy info if available
        if self.proxy_manager.enabled:
            policy["current_proxy"] = self.proxy_manager.current_proxy

        return policy

    def record_block(self, domain: str, score: float) -> None:
        """Track block patterns per domain for adaptive pacing."""
        if domain not in self._block_history:
            self._block_history[domain] = []
        self._block_history[domain].append(score)
        # Keep last 10 attempts
        self._block_history[domain] = self._block_history[domain][-settings.ANTIBOT_BLOCK_HISTORY_SIZE :]

        # If score indicates hard block, record proxy failure
        if score > settings.ANTIBOT_HARD_BLOCK_THRESHOLD and self.proxy_manager.enabled:
            self.proxy_manager.record_failure()
            logger.info("Hard block detected on %s, recorded proxy failure", domain)

    def record_success(self, domain: str) -> None:  # noqa: ARG002, RUF100
        """Record successful fetch from domain."""
        if self.proxy_manager.enabled:
            self.proxy_manager.record_success()

    def rotate_proxy(self) -> str | None:
        """Explicitly rotate to next proxy and return it."""
        if self.proxy_manager.enabled:
            new_proxy = self.proxy_manager.rotate()
            logger.info("Rotated proxy: %s", mask_proxy_url(new_proxy))
            return new_proxy  # type: ignore[no-any-return]
        return None


# Global Singleton
_engine: AntiBotEngine | None = None


def get_anti_bot_engine() -> AntiBotEngine:
    global _engine
    if _engine is None:
        _engine = AntiBotEngine()
    return _engine
