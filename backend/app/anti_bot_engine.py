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

# ── TLS Fingerprint Pool (Anti 4) ────────────────────────────────────
# Realistic TLS JA4 fingerprints for common browsers. Full TLS
# manipulation requires curl_cffi; this pool provides the *profile*
# that apply_tls_fingerprint() can apply partially depending on the
# transport (httpx vs Playwright).
TLS_FINGERPRINT_POOL: list[dict[str, Any]] = [
    {
        "label": "chrome_124",
        "ja4_fingerprint": "t13d1516h2_8daaf6152771_000000000000",
        "http2_settings": {
            "HEADER_TABLE_SIZE": 65536,
            "ENABLE_PUSH": 0,
            "MAX_CONCURRENT_STREAMS": 1000,
            "INITIAL_WINDOW_SIZE": 6291456,
            "MAX_FRAME_SIZE": 16384,
            "MAX_HEADER_LIST_SIZE": 262144,
        },
        "cipher_suites": [
            0x1301,
            0x1302,
            0x1303,  # TLS 1.3
            0xC02B,
            0xC02F,
            0xC02C,
            0xC030,  # TLS 1.2 ECDHE
            0x009E,
            0x009F,
            0x00A2,
            0x00A3,  # AES-GCM
            0xCC14,
            0xCC13,
        ],
        "tls_extensions_order": [
            0,
            10,
            11,
            35,
            16,
            5,
            65281,
            23,
            13,
            43,
            45,
            51,
            17513,
        ],
    },
    {
        "label": "chrome_123",
        "ja4_fingerprint": "t13d1515h2_8daaf6152771_000000000000",
        "http2_settings": {
            "HEADER_TABLE_SIZE": 65536,
            "ENABLE_PUSH": 0,
            "MAX_CONCURRENT_STREAMS": 1000,
            "INITIAL_WINDOW_SIZE": 6291456,
            "MAX_FRAME_SIZE": 16384,
            "MAX_HEADER_LIST_SIZE": 262144,
        },
        "cipher_suites": [
            0x1301,
            0x1302,
            0x1303,
            0xC02B,
            0xC02F,
            0xC02C,
            0xC030,
            0x009E,
            0x009F,
            0x00A2,
            0x00A3,
            0xCC14,
            0xCC13,
        ],
        "tls_extensions_order": [
            0,
            10,
            11,
            35,
            16,
            5,
            65281,
            23,
            13,
            43,
            45,
            51,
            17513,
        ],
    },
    {
        "label": "firefox_124",
        "ja4_fingerprint": "t13d1515h2_0b1565104d0b_000000000000",
        "http2_settings": {
            "HEADER_TABLE_SIZE": 65536,
            "ENABLE_PUSH": 0,
            "MAX_CONCURRENT_STREAMS": 100,
            "INITIAL_WINDOW_SIZE": 12517377,
            "MAX_FRAME_SIZE": 16384,
            "MAX_HEADER_LIST_SIZE": 262144,
        },
        "cipher_suites": [
            0x1301,
            0x1302,
            0x1303,
            0xC02B,
            0xC02F,
            0xCC14,
            0xCC13,
            0xC02C,
            0xC030,
            0x009E,
            0x009F,
            0x00A2,
            0x00A3,
        ],
        "tls_extensions_order": [
            0,
            10,
            11,
            35,
            16,
            5,
            65281,
            23,
            13,
            43,
            45,
            51,
            17513,
        ],
    },
    {
        "label": "edge_123",
        "ja4_fingerprint": "t13d1516h2_8daaf6152771_e3b62e79810c",
        "http2_settings": {
            "HEADER_TABLE_SIZE": 65536,
            "ENABLE_PUSH": 0,
            "MAX_CONCURRENT_STREAMS": 1000,
            "INITIAL_WINDOW_SIZE": 6291456,
            "MAX_FRAME_SIZE": 16384,
            "MAX_HEADER_LIST_SIZE": 262144,
        },
        "cipher_suites": [
            0x1301,
            0x1302,
            0x1303,
            0xC02B,
            0xC02F,
            0xC02C,
            0xC030,
            0x009E,
            0x009F,
            0x00A2,
            0x00A3,
            0xCC14,
            0xCC13,
        ],
        "tls_extensions_order": [
            0,
            10,
            11,
            35,
            16,
            5,
            65281,
            23,
            13,
            43,
            45,
            51,
            17513,
        ],
    },
    {
        "label": "safari_17",
        "ja4_fingerprint": "t13d1516h2_8daaf6152771_b0c8f4ea5619",
        "http2_settings": {
            "HEADER_TABLE_SIZE": 4096,
            "ENABLE_PUSH": 0,
            "MAX_CONCURRENT_STREAMS": 100,
            "INITIAL_WINDOW_SIZE": 65535,
            "MAX_FRAME_SIZE": 16384,
            "MAX_HEADER_LIST_SIZE": 16384,
        },
        "cipher_suites": [
            0x1301,
            0x1302,
            0x1303,
            0xC02B,
            0xC02F,
            0xC02C,
            0xC030,
            0xCC14,
            0xCC13,
        ],
        "tls_extensions_order": [
            0,
            10,
            11,
            35,
            16,
            5,
            65281,
            23,
            13,
            43,
            45,
            51,
        ],
    },
]


def get_random_tls_profile() -> dict[str, Any]:
    """Return a randomly selected TLS fingerprint profile.

    The returned dict contains ``ja4_fingerprint``, ``http2_settings``,
    ``cipher_suites``, and ``tls_extensions_order`` drawn from
    :data:`TLS_FINGERPRINT_POOL`.
    """
    profile = random.choice(TLS_FINGERPRINT_POOL)  # nosec B311
    # Return a shallow copy so callers can mutate without polluting the pool.
    return {
        "label": profile["label"],
        "ja4_fingerprint": profile["ja4_fingerprint"],
        "http2_settings": dict(profile["http2_settings"]),
        "cipher_suites": list(profile["cipher_suites"]),
        "tls_extensions_order": list(profile["tls_extensions_order"]),
    }


def apply_tls_fingerprint(context_or_client: Any, profile: dict[str, Any]) -> None:
    """Apply a TLS fingerprint profile to an HTTP client or Playwright context.

    This is intentionally partial — full TLS manipulation requires
    ``curl_cffi`` or an OS-level MITM proxy.  What we can do:

    * **httpx**: set HTTP/2 settings on the transport, which subtly
      changes the fingerprint observable by servers that inspect
      SETTINGS frames.
    * **Playwright**: add Chromium ``--cipher-suite-blacklist`` and
      ``--ssl-version-max/min`` args to influence which suites are
      advertised.  This is best-effort; Chromium doesn't expose
      fine-grained TLS control.
    """
    if context_or_client is None or profile is None:
        return

    # --- httpx path: apply HTTP/2 SETTINGS if the transport exposes it ---
    try:
        transport = getattr(context_or_client, "_transport", None) or getattr(context_or_client, "transport", None)
        h2_settings = profile.get("http2_settings")
        if transport is not None and h2_settings is not None:
            h2_conn = getattr(transport, "h2_conn", None) or getattr(transport, "_h2_conn", None)
            if h2_conn is not None:
                for key, value in h2_settings.items():
                    try:
                        setattr(h2_conn.local_settings, key, value)
                    except (AttributeError, TypeError, ValueError):
                        logger.debug("apply_tls_fingerprint: could not set h2 setting %s", key)
    except (AttributeError, TypeError, RuntimeError):
        logger.debug("apply_tls_fingerprint: httpx h2 settings application failed", exc_info=True)

    # --- Playwright path: influence TLS via Chromium args ---
    # Playwright contexts don't allow runtime TLS arg changes, but when
    # the browser was launched we could have applied cipher-suite
    # blacklists.  Record the profile label in context metadata so
    # diagnostic tooling can see which profile is active.
    try:
        if hasattr(context_or_client, "set_geolocation"):
            # This is a BrowserContext — store profile label for diagnostics.
            # The actual Chromium args are applied at browser launch time
            # in browser_pool._ensure_browser_launched_locked().
            context_or_client._tls_fingerprint_label = profile.get("label", "")  # type: ignore[attr-defined]
    except (AttributeError, TypeError, RuntimeError):
        logger.debug("apply_tls_fingerprint: Playwright context annotation failed", exc_info=True)


# ── Geolocation Pool (Anti 12) ────────────────────────────────────────
# Coordinates matching common proxy exit-node regions. When a proxy IP
# is selected, the geolocation should be derived from the nearest region
# with a +-0.05 degree jitter.
GEO_POOL: list[dict[str, Any]] = [
    {"label": "us_east", "city": "New York", "latitude": 40.7128, "longitude": -74.0060, "accuracy": 50.0},
    {"label": "us_west", "city": "San Francisco", "latitude": 37.7749, "longitude": -122.4194, "accuracy": 50.0},
    {"label": "london", "city": "London", "latitude": 51.5074, "longitude": -0.1278, "accuracy": 50.0},
    {"label": "frankfurt", "city": "Frankfurt", "latitude": 50.1109, "longitude": 8.6821, "accuracy": 50.0},
    {"label": "tokyo", "city": "Tokyo", "latitude": 35.6762, "longitude": 139.6503, "accuracy": 50.0},
    {"label": "singapore", "city": "Singapore", "latitude": 1.3521, "longitude": 103.8198, "accuracy": 50.0},
    {"label": "sydney", "city": "Sydney", "latitude": -33.8688, "longitude": 151.2093, "accuracy": 50.0},
    {"label": "mumbai", "city": "Mumbai", "latitude": 19.0760, "longitude": 72.8777, "accuracy": 50.0},
    {"label": "sao_paulo", "city": "Sao Paulo", "latitude": -23.5505, "longitude": -46.6333, "accuracy": 50.0},
    {"label": "toronto", "city": "Toronto", "latitude": 43.6532, "longitude": -79.3832, "accuracy": 50.0},
]


def get_random_geolocation() -> dict[str, float]:
    """Return a random geolocation entry from :data:`GEO_POOL`.

    Returns ``{latitude, longitude, accuracy}`` with a small random
    jitter (+-0.05 deg) applied so each session doesn't share an
    identical coordinate.
    """
    entry = random.choice(GEO_POOL)  # nosec B311
    jitter_lat = random.uniform(-0.05, 0.05)  # nosec B311
    jitter_lon = random.uniform(-0.05, 0.05)  # nosec B311
    return {
        "latitude": round(entry["latitude"] + jitter_lat, 4),
        "longitude": round(entry["longitude"] + jitter_lon, 4),
        "accuracy": entry["accuracy"],
    }


def get_geolocation_for_proxy(proxy_url: str | None) -> dict[str, float] | None:
    """Derive a geolocation near the proxy's IP region.

    Accepts a proxy URL string (e.g. ``"http://1.2.3.4:8080"``).  If the
    proxy IP can be matched to a known region in :data:`GEO_POOL`, returns
    a jittered coordinate for that region.  Falls back to
    :func:`get_random_geolocation` when the IP cannot be resolved.
    """
    if not proxy_url:
        return None

    # Best-effort: extract the host portion and try a simplistic region
    # heuristic.  In production, a GeoIP database would map the IP to a
    # region.  Here we use the host string itself as a seed for
    # deterministicity so the same proxy always maps to the same region.
    try:
        host_part = proxy_url.replace("http://", "").replace("https://", "").replace("socks5://", "")
        host = host_part.split(":")[0].split("@")[-1]
    except (ValueError, IndexError):
        return get_random_geolocation()

    # Simple hash-based region selection for deterministic proxy -> region
    # mapping without needing a GeoIP DB.
    pool_index = hash(host) % len(GEO_POOL)
    entry = GEO_POOL[pool_index]
    jitter_lat = random.uniform(-0.05, 0.05)  # nosec B311
    jitter_lon = random.uniform(-0.05, 0.05)  # nosec B311
    return {
        "latitude": round(entry["latitude"] + jitter_lat, 4),
        "longitude": round(entry["longitude"] + jitter_lon, 4),
        "accuracy": entry["accuracy"],
    }


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
          - geolocation: randomized {latitude, longitude, accuracy}
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
            "geolocation": get_random_geolocation(),
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
        # Then immediately rotate so the *next* attempt uses a fresh IP
        # instead of repeating against a burned endpoint.  Without this the
        # proxy stays on the failing address for PROXY_ROTATION_FAILURE_THRESHOLD
        # consecutive attempts, which damages IP reputation on every retry.
        if score > settings.ANTIBOT_HARD_BLOCK_THRESHOLD and self.proxy_manager.enabled:
            self.proxy_manager.record_failure(domain=domain)
            self.proxy_manager.rotate(domain=domain)
            logger.info("Hard block detected on %s, recorded proxy failure and rotated", domain)

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
_engine_lock = Lock()


def get_anti_bot_engine() -> AntiBotEngine:
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            _engine = AntiBotEngine()
    return _engine
