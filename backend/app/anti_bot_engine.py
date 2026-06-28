"""Anti-Bot Detection Engine — Identifying when automated access is blocked.

Responsible for:
- Detecting challenges (Cloudflare, Akamai, etc.)
- Identifying CAPTCHAs and blocking patterns
- Providing adaptive pacing and retry policies
- Browser entropy stabilization
- Proxy rotation coordination
- Cookie persistence (SQLite-backed, survives restarts)
"""

from __future__ import annotations

import logging
import random
import re
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Any

from app.config import settings
from app.utils.log_redaction import mask_proxy_url

logger = logging.getLogger(__name__)

# ── Cookie persistence (SQLite) ──────────────────────────────────────
_COOKIE_DB_LOCK = Lock()
_COOKIE_DB_INITIALIZED: set[Path] = set()


def _cookie_db_path() -> Path:
    """Resolve the cookie database path from settings (or default)."""
    if settings.STATE_FILE_PATH_DYNAMIC:
        base = Path(settings.STATE_FILE_PATH_DYNAMIC).expanduser()
    else:
        base = Path(__file__).resolve().parent.parent / "data" / "jobs_state.json"
    return base.parent / "anti_bot_cookies.db"


def _cookie_db_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (or create) the cookie database with WAL mode."""
    path = db_path or _cookie_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    if path not in _COOKIE_DB_INITIALIZED:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cookies (
                domain  TEXT PRIMARY KEY,
                cookie_string TEXT NOT NULL,
                updated_at    REAL NOT NULL
            )
            """
        )
        conn.commit()
        _COOKIE_DB_INITIALIZED.add(path)
    return conn


# Primary detection patterns for common anti-bot platforms
CHALLENGE_PATTERNS = {
    "cloudflare": [
        "cf-browser-verification",
        "cf-challenge",
        "cf-turnstile",
        "cf-turnstile-v2",
        "challenge-platform",
        "checking your browser",
        "attention required",
        "__cfruid",
        "cf_clearance",
        "cdn-cgi/challenge-platform",
        "_cf_chl_opt",
        "_cf_chl_tk",
        "cloudflare-challenge",
    ],
    "akamai": ["akamai-ghost", "ak_bmsc", "bm_sz", "_abck", "bm_mi"],
    "datadome": ["dd-captcha", "datadome", "dd=", "x-datadome"],
    "perimeterx": ["perimeterx", "px-captcha", "_px", "px_"],
    "incapsula": ["incapsula", "visid_incap", "incap_ses", "imperva", "_incap"],
    "captcha": ["g-recaptcha", "h-captcha", "recaptcha", "hcaptcha", "turnstile"],
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
        "automated access",
        "unusual traffic",
        "automated queries",
    ],
    "js_required": ["enable javascript", "javascript is required", "browser is not supported", "javascript must be enabled"],
    "rate_limit": ["too many requests", "429", "rate limit", "try again later", "slow down"],
}

# Probability weights for detection signals
SIGNAL_WEIGHTS = {
    "challenge-platform": 0.95,
    "cf-browser-verification": 0.95,
    "cf-turnstile": 0.95,
    "cf-turnstile-v2": 0.95,
    "cdn-cgi/challenge-platform": 0.95,
    "g-recaptcha": 0.9,
    "h-captcha": 0.9,
    "datadome": 0.95,
    "perimeterx": 0.95,
    "px-captcha": 0.95,
    "incapsula": 0.9,
    "imperva": 0.9,
    "access denied": 0.8,
    "blocked": 0.8,
    "please verify": 0.7,
    "security check": 0.7,
    "sorry, you have been blocked": 0.95,
    "unusual traffic": 0.8,
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
        self._cookies: dict[str, str] = {}  # domain -> cookie_string (in-memory cache)
        self._last_cookie_update: dict[str, float] = {}
        # domain -> user agents used
        self._ua_history: dict[str, list[str]] = {}
        # On startup, hydrate the in-memory cache from SQLite
        self._load_cookies_from_db()

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
            # Disambiguate anti-bot cookies by their associated platform
            # so observability labels reflect the actual blocker. Previously
            # every bot-cookie name collapsed to "captcha", which masked
            # Akamai / PerimeterX / DataDome / Incapsula specificity from
            # the dataforge_anti_bot_classifications_total{classification=*}
            # metric.
            if "_abck" in cookies:
                return "akamai"
            if "_px" in cookies:
                return "perimeterx"
            if "datadome" in cookies:
                return "datadome"
            if "incap_ses" in cookies:
                return "incapsula"

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

    def get_stealth_profile(self, domain: str) -> dict[str, Any]:
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
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
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
            extra_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
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
        """Persist cookies for a domain to reuse on subsequent requests.

        Writes to both the in-memory cache and the SQLite backing store
        so cookies survive container/process restarts.
        """
        if not domain or not cookie_string:
            return
        now = time.time()
        self._cookies[domain] = cookie_string
        self._last_cookie_update[domain] = now
        # Persist to SQLite
        try:
            with _COOKIE_DB_LOCK:
                conn = _cookie_db_conn()
                try:
                    conn.execute(
                        """
                        INSERT INTO cookies (domain, cookie_string, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(domain) DO UPDATE SET
                            cookie_string = excluded.cookie_string,
                            updated_at     = excluded.updated_at
                        """,
                        (domain, cookie_string, now),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except sqlite3.Error:
            logger.warning("Failed to persist cookies for %s to SQLite", domain, exc_info=True)
        logger.debug("Cookies updated for domain %s (%d chars)", domain, len(cookie_string))

    def _load_cookies_from_db(self) -> None:
        """Hydrate the in-memory cookie cache from SQLite on startup."""
        try:
            with _COOKIE_DB_LOCK:
                conn = _cookie_db_conn()
                try:
                    rows = conn.execute("SELECT domain, cookie_string, updated_at FROM cookies").fetchall()
                finally:
                    conn.close()
            for domain, cookie_string, updated_at in rows:
                self._cookies[domain] = cookie_string
                self._last_cookie_update[domain] = updated_at
            if rows:
                logger.info("Loaded %d persisted cookies from SQLite", len(rows))
        except sqlite3.Error:
            logger.warning("Failed to load cookies from SQLite, starting fresh", exc_info=True)

    def get_cookies(self, domain: str) -> str:
        """Get persisted cookies for a domain."""
        return self._cookies.get(domain, "")

    def should_refresh_cookies(
        self,
        domain: str,
        max_age_hours: int | None = None,
    ) -> bool:
        """Check if stored cookies for a domain should be refreshed.

        Uses domain-specific TTL when available (computed from block
        history — domains with frequent blocks get shorter cookie TTL)
        falling back to ``settings.ANTIBOT_COOKIE_MAX_AGE_HOURS``.
        """
        if max_age_hours is None:
            max_age_hours = self._domain_specific_cookie_ttl(domain)
        last_update = self._last_cookie_update.get(domain, 0)
        if last_update == 0:
            return True
        age_hours = (time.time() - last_update) / 3600
        return age_hours > max_age_hours

    def _domain_specific_cookie_ttl(self, domain: str, default: int | None = None) -> int:
        """Compute a domain-specific cookie TTL based on block history.

        Domains with frequent hard blocks get shorter cookie validity
        so we refresh more aggressively.  Stable domains keep the default.
        """
        base = default or int(getattr(settings, "ANTIBOT_COOKIE_MAX_AGE_HOURS", 24))
        history = self._block_history.get(domain, [])
        if not history:
            return base
        # If any recent block was a hard block (score > 0.8), halve the TTL
        recent = history[-5:]
        hard_blocks = sum(1 for s in recent if s > 0.8)
        if hard_blocks >= 2:
            return max(base // 4, 1)  # aggressive: 25% of default, min 1h
        if hard_blocks >= 1:
            return max(base // 2, 2)  # moderate: 50% of default, min 2h
        soft_blocks = sum(1 for s in recent if 0.4 < s <= 0.8)
        if soft_blocks >= 3:
            return max(base * 3 // 4, 4)  # mild: 75% of default
        return base

    def get_retry_policy(self, url: str, last_score: float) -> dict[str, Any]:
        """Determine the next step based on the block score and domain history."""
        policy: dict[str, Any] = {}

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

        # Add jitter to the delay so concurrent scrapers hitting the same
        # domain don't retry in lockstep (which amplifies the burst
        # pattern that bot detectors key off of). Capped at ±25 % so the
        # operator-configured base delay still dominates the policy.
        base_delay = int(policy.get("delay", 0) or 0)
        if base_delay > 0:
            jitter = random.uniform(-0.25, 0.25)  # nosec B311 — jitter, not crypto
            policy["delay"] = max(0, round(base_delay * (1.0 + jitter)))

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

        # If score indicates hard block, record proxy failure for the domain
        # so domain-aware rotation can skip this proxy for this domain.
        if score > settings.ANTIBOT_HARD_BLOCK_THRESHOLD and self.proxy_manager.enabled:
            self.proxy_manager.record_failure(domain=domain)
            logger.info("Hard block detected on %s, recorded proxy failure", domain)

    def record_success(self, domain: str) -> None:
        """Record successful fetch from domain."""
        if self.proxy_manager.enabled:
            self.proxy_manager.record_success(domain=domain)

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
