"""
Anti-Bot Resilience Engine — Surviving hostile web environments.

Responsible for:
- Detecting challenges (Cloudflare, Akamai, etc.)
- Identifying CAPTCHAs and blocking patterns
- Providing adaptive pacing and retry policies
- Browser entropy stabilization
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Primary detection patterns for common anti-bot platforms
CHALLENGE_PATTERNS = {
    "cloudflare": [
        "cf-browser-verification", "cf-challenge", "cf-turnstile", 
        "challenge-platform", "checking your browser"
    ],
    "akamai": ["akamai-ghost", "ak_bmsc", "bm_sz"],
    "datadome": ["dd-captcha", "datadome"],
    "perimeterx": ["perimeterx", "px-captcha"],
    "incapsula": ["incapsula", "visid_incap"],
    "generic_block": [
        "access denied", "blocked", "sorry, you have been blocked",
        "please verify", "security check", "suspicious activity"
    ],
    "js_required": [
        "enable javascript", "javascript is required", "browser is not supported"
    ]
}

# Probability weights for detection signals
SIGNAL_WEIGHTS = {
    "challenge-platform": 0.9,
    "cf-browser-verification": 0.9,
    "cf-turnstile": 0.9,
    "g-recaptcha": 0.9,
    "h-captcha": 0.9,
    "blocked": 0.7,
    "access denied": 0.7,
    "please verify": 0.6,
    "security check": 0.6,
    "sorry, you have been blocked": 0.95,
    "enable javascript": 0.5,
    "javascript is required": 0.5,
}


class AntiBotEngine:
    """Intelligent engine for detecting and bypassing anti-bot systems."""

    def __init__(self) -> None:
        self._block_history: Dict[str, List[float]] = {}

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
                
        # 2. Header-based Detection
        if headers:
            # Look for common anti-bot headers (e.g. Cloudflare Ray ID, Server names)
            server = headers.get("server", "").lower()
            if "cloudflare" in server:
                max_score = max(max_score, 0.4)
            if "akamai" in server:
                max_score = max(max_score, 0.5)
                
        return max_score

    def get_retry_policy(self, url: str, last_score: float) -> dict:
        """Determine the next step based on the block score and domain history."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc or "unknown"
        
        if last_score < 0.3:
            return {"action": "continue", "delay": 0}
            
        if last_score > 0.8:
            # Hard block: need significant slowdown or proxy rotation
            return {"action": "retry_slow", "delay": 30, "proxy_rotate": True}
            
        if last_score > 0.5:
            # Medium challenge: probably just need more wait time/js execution
            return {"action": "retry_wait", "delay": 5}
            
        return {"action": "continue", "delay": 0}

    def record_block(self, domain: str, score: float):
        """Track block patterns per domain for adaptive pacing."""
        if domain not in self._block_history:
            self._block_history[domain] = []
        self._block_history[domain].append(score)
        # Keep last 10 attempts
        self._block_history[domain] = self._block_history[domain][-10:]


# Global Singleton
_engine: AntiBotEngine | None = None

def get_anti_bot_engine() -> AntiBotEngine:
    global _engine
    if _engine is None:
        _engine = AntiBotEngine()
    return _engine
