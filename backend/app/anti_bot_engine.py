"""
Anti-Bot Resilience Engine — Surviving hostile web environments.

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
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Primary detection patterns for common anti-bot platforms
CHALLENGE_PATTERNS = {
    "cloudflare": [
        "cf-browser-verification", "cf-challenge", "cf-turnstile", 
        "challenge-platform", "checking your browser", "attention required"
    ],
    "akamai": ["akamai-ghost", "ak_bmsc", "bm_sz", "_abck"],
    "datadome": ["dd-captcha", "datadome", "dd="],
    "perimeterx": ["perimeterx", "px-captcha", "_px"],
    "incapsula": ["incapsula", "visid_incap", "incap_ses", "imperva"],
    "generic_block": [
        "access denied", "blocked", "sorry, you have been blocked",
        "please verify", "security check", "suspicious activity",
        "captcha", "human verify", "bot detection", "robot"
    ],
    "js_required": [
        "enable javascript", "javascript is required", "browser is not supported"
    ],
    "rate_limit": ["too many requests", "429", "rate limit"]
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
    """Intelligent engine for detecting and bypassing anti-bot systems."""

    def __init__(self) -> None:
        self._block_history: Dict[str, List[float]] = {}
        # Lazy import to avoid circular dependencies
        self._proxy_manager: Optional[object] = None
        self._cookies: Dict[str, str] = {}  # domain -> cookie_string
        self._last_cookie_update: Dict[str, float] = {}
        self._ua_history: Dict[str, List[str]] = {}  # domain -> user agents used

    @property
    def proxy_manager(self):
        """Lazy-load proxy manager."""
        if self._proxy_manager is None:
            from app.proxy_manager import get_proxy_manager
            self._proxy_manager = get_proxy_manager()
        return self._proxy_manager

    def detect_challenges(self, html: str, headers: Optional[dict] = None) -> float:
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
        for platform, patterns in CHALLENGE_PATTERNS.items():
            for p in patterns:
                if p in lower_html:
                    # Platform matches boost score
                    max_score = max(max_score, 0.6)
                
        # 3. Header-based Detection
        if headers:
            headers_lower = {k.lower(): str(v).lower() for k, v in headers.items()}
            # Look for common anti-bot headers
            server = headers_lower.get("server", "")
            if "cloudflare" in server: max_score = max(max_score, 0.45)
            if "akamai" in server: max_score = max(max_score, 0.55)
            
            # Check for set-cookie headers related to bot detection
            cookies = headers_lower.get("set-cookie", "")
            if any(p in cookies for p in ["_abck", "_px", "datadome", "incap_ses"]):
                max_score = max(max_score, 0.5)
                
        return max_score

    def should_evolve_to_stealth(self, domain: str) -> bool:
        """Heuristic check if a domain requires stealth mode."""
        history = self._block_history.get(domain, [])
        if not history:
            return False
            
        # If mean score of last 3 attempts is > 0.4, or any is > 0.8
        recent = history[-3:]
        if any(s > 0.8 for s in recent):
            return True
        if len(recent) >= 2 and sum(recent) / len(recent) > 0.4:
            return True
            
        return False

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
        ua_pool = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
        ]
        
        # Track UAs used per domain to avoid reusing the same one
        used_uas = self._ua_history.get(domain, [])
        available = [ua for ua in ua_pool if ua not in used_uas]
        if not available:
            available = ua_pool
        ua = random.choice(available)
        
        # Update history
        if domain not in self._ua_history:
            self._ua_history[domain] = []
        self._ua_history[domain].append(ua)
        self._ua_history[domain] = self._ua_history[domain][-5:]  # Keep last 5
        
        # Randomize additional headers to mimic real browsers
        is_chromium = "Chrome" in ua and "Firefox" not in ua
        extra_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        }
        if not is_chromium:
            # Firefox-style headers
            extra_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
            extra_headers["Sec-Fetch-Dest"] = "document"
            extra_headers["Sec-Fetch-Mode"] = "navigate"
            extra_headers["Sec-Fetch-Site"] = "none"
            extra_headers.pop("Sec-Ch-Ua", None)
            extra_headers.pop("Sec-Ch-Ua-Mobile", None)
            extra_headers.pop("Sec-Ch-Ua-Platform", None)
        
        # Viewport randomization (with reasonable ranges)
        viewport_width = random.choice([1280, 1366, 1440, 1536, 1600, 1920])
        viewport_height = random.choice([720, 768, 800, 900, 1024, 1080])
        
        profile = {
            "user_agent": ua,
            "extra_headers": extra_headers,
            "viewport": {"width": viewport_width, "height": viewport_height},
            "cookie_string": self._cookies.get(domain, ""),
            "timezone": random.choice(["America/New_York", "America/Chicago", "America/Los_Angeles", "Europe/London", "Asia/Singapore"]),
            "locale": "en-US",
            "platform": "Win32" if "Windows" in ua else ("MacIntel" if "Mac" in ua else "Linux x86_64"),
            "device_scale_factor": random.choice([1.0, 1.25, 1.5, 2.0]),
        }
        return profile

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

    def should_refresh_cookies(self, domain: str, max_age_hours: int = 24) -> bool:
        """Check if stored cookies for a domain should be refreshed."""
        last_update = self._last_cookie_update.get(domain, 0)
        if last_update == 0:
            return True
        age_hours = (time.time() - last_update) / 3600
        return age_hours > max_age_hours

    def get_retry_policy(self, url: str, last_score: float) -> dict:
        """Determine the next step based on the block score and domain history."""
        policy = {}
        
        if last_score < 0.3:
            policy = {"action": "continue", "delay": 0}
            
        elif last_score > 0.8:
            # Hard block: need significant slowdown and proxy rotation
            policy = {"action": "retry_slow", "delay": 30, "rotate_proxy": True}
            
        elif last_score > 0.5:
            # Medium challenge: probably just need more wait time/js execution
            policy = {"action": "retry_wait", "delay": 5}
            
        else:
            policy = {"action": "continue", "delay": 0}
        
        # Include current proxy info if available
        if self.proxy_manager.enabled:
            policy["current_proxy"] = self.proxy_manager.current_proxy
        
        return policy

    def record_block(self, domain: str, score: float):
        """Track block patterns per domain for adaptive pacing."""
        if domain not in self._block_history:
            self._block_history[domain] = []
        self._block_history[domain].append(score)
        # Keep last 10 attempts
        self._block_history[domain] = self._block_history[domain][-10:]
        
        # If score indicates hard block, record proxy failure
        if score > 0.8 and self.proxy_manager.enabled:
            self.proxy_manager.record_failure()
            logger.info(f"Hard block detected on {domain}, recorded proxy failure")

    def record_success(self, domain: str):
        """Record successful fetch from domain."""
        if self.proxy_manager.enabled:
            self.proxy_manager.record_success()

    def rotate_proxy(self) -> Optional[str]:
        """Explicitly rotate to next proxy and return it."""
        if self.proxy_manager.enabled:
            new_proxy = self.proxy_manager.rotate()
            logger.info(f"Rotated proxy: {new_proxy}")
            return new_proxy
        return None


# Global Singleton
_engine: AntiBotEngine | None = None

def get_anti_bot_engine() -> AntiBotEngine:
    global _engine
    if _engine is None:
        _engine = AntiBotEngine()
    return _engine
