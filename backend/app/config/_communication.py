"""HTTP fetching, LLM providers, proxy, and anti-bot configuration."""

from pydantic_settings import BaseSettings


class CommunicationSettings(BaseSettings):
    """HTTP fetch, LLM, proxy, anti-bot, and email validation settings."""

    # ─── HTTP Fetching ─────────────────────────────────────────────────
    REQUEST_TIMEOUT: int = 20
    """Seconds before plain-HTTP fallback request times out."""
    ROBOTS_TIMEOUT: float = 10.0
    """Timeout for robots.txt fetching."""
    GEOCODER_TIMEOUT: int = 10
    """Timeout for reverse geocoding lookups."""
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    GEOCODER_USER_AGENT: str = "DataForge-Scraper/2.0 (geocoder)"
    """User-agent for geocoding services."""
    MAX_RETRIES: int = 2
    """Number of retries for HTTP requests (httpx)."""
    HTTP_BACKOFF_FACTOR: float = 0.5
    """Backoff multiplier for HTTP retries."""
    HTTPX_BASIC_USER_AGENT: str = "python-httpx/0.27.0"
    """User-Agent for basic HTTPX requests (non-stealth)."""

    # ─── LLM Provider Timeouts ─────────────────────────────────────────
    LLM_TIMEOUT: int = 45
    """Default timeout for LLM JSON / text calls (seconds)."""
    LLM_FAST_TIMEOUT: int = 12
    """Fast-path timeout for throughput-sensitive LLM calls."""
    LLM_SELECTOR_TIMEOUT: int = 30
    """Timeout for selector discovery LLM calls."""
    INSIGHT_TIMEOUT_SECONDS: int = 25
    """Timeout for insight generation calls."""
    LLM_TEMPERATURE: float = 0.1
    """Default LLM temperature for JSON calls."""
    LLM_FAST_TEMPERATURE: float = 0.0
    """Temperature for fast-path JSON calls."""
    LLM_TEXT_TEMPERATURE: float = 0.4
    """Temperature for free-form text calls."""
    LLM_MAX_ATTEMPTS: int = 2
    """Retries for LLM API calls."""
    LLM_BACKOFF_SECONDS: float = 0.8
    """Base backoff for LLM retries."""

    # ─── LLM Output Validation ─────────────────────────────────────────
    LLM_VALIDATE_JSON: bool = True
    """Validate LLM JSON output against expected schema."""
    LLM_VALIDATION_MAX_RETRIES: int = 2
    """Max retries for malformed LLM JSON."""

    # ─── LLM Provider Settings ─────────────────────────────────────────
    GROQ_API_ENDPOINT: str = "https://api.groq.com/openai/v1/chat/completions"
    """Groq API endpoint for LLM calls."""
    POLLINATIONS_API_ENDPOINT: str = "https://text.pollinations.ai/openai"
    """Pollinations AI endpoint for LLM calls."""
    LLM_ENABLE_PUBLIC_FALLBACKS: bool = False
    """Allow unauthenticated public LLM fallbacks such as Pollinations/g4f."""

    # ─── LLM Cascade Circuit Breaker ──────────────────────────────────
    LLM_CIRCUIT_FAILURE_THRESHOLD: int = 5
    """Open the cascade circuit after this many consecutive cascade
    exhaustions (from any provider).  Lets the caller fail fast
    instead of paying full timeout cost on every subsequent call."""
    LLM_CIRCUIT_OPEN_WINDOW_SECONDS: int = 60
    """How long the cascade circuit stays open before auto-resetting
    to half-open.  Half-open lets a single probe call through."""
    LLM_CIRCUIT_HALF_OPEN_MAX_PROBES: int = 1
    """How many probe calls are permitted while the circuit is
    half-open.  If all succeed, the circuit closes; otherwise it
    re-opens for another full window."""
    LLM_CIRCUIT_ENABLED: bool = True
    """Master switch for the cascade circuit breaker.  Disable when
    running unit tests that intentionally exhaust cascades for
    failure-path validation."""

    # ─── LLM Provider Models ───────────────────────────────────────────
    GROQ_DEFAULT_MODEL: str = "llama-3.3-70b-versatile"
    """Default model for Groq LLM calls."""
    GROQ_FALLBACK_MODEL: str = "llama-3.1-8b-instant"
    """Fallback model when default Groq model fails."""
    G4F_JSON_MODEL: str = "gpt-4o-mini"
    """Model for g4f JSON fallback calls."""
    G4F_TEXT_MODEL: str = "gpt-4o"
    """Model for g4f text fallback calls."""

    # ─── Proxy & Anti-Bot Evasion ──────────────────────────────────────
    PROXY_ROTATION_ENABLED: bool = False
    """Enable proxy rotation for anti-bot resilience."""
    PROXY_LIST: str = ""
    """Comma-separated list of proxy URLs (http://ip:port or socks5://ip:port)."""
    PROXY_ROTATION_FAILURE_THRESHOLD: int = 5
    """Rotate proxy after this many consecutive failures."""
    PROXY_PROVIDER_TYPE: str = "static"
    """Proxy provider plug-in: 'static' (PROXY_LIST), 'file', 'url', 'brightdata',
    'oxylabs', 'smartproxy'. File/URL providers emit a JSON array of proxy URLs;
    'brightdata'/'oxylabs'/'smartproxy' reuse the URL provider with preset
    auth-header conventions and default endpoints."""
    PROXY_PROVIDER_FILE: str = ""
    """Path to JSON file containing an array of proxy URLs (used when
    PROXY_PROVIDER_TYPE=='file')."""
    PROXY_PROVIDER_URL: str = ""
    """HTTP endpoint returning a JSON array of proxy URLs (used when
    PROXY_PROVIDER_TYPE=='url'|'brightdata'|'oxylabs'|'smartproxy')."""
    PROXY_PROVIDER_REFRESH_INTERVAL_S: int = 300
    """Seconds between automatic proxy list refreshes from the provider.
    Operators may invoke ProxyManager.refresh_from_provider() manually to bypass."""

    # ─── CAPTCHA Solver ────────────────────────────────────────────────
    CAPTCHA_SOLVER_ENABLED: bool = False
    """Master switch for CAPTCHA solving integration. When True, the
    recovery pipeline will attempt to solve detected CAPTCHAs before
    falling through to proxy rotation + backoff."""
    CAPTCHA_PROVIDER: str = "2captcha"
    """CAPTCHA solver backend: '2captcha' or 'anticaptcha'."""
    CAPTCHA_API_KEY: str = ""
    """API key for the selected CAPTCHA solving provider."""
    CAPTCHA_SOLVE_TIMEOUT_S: int = 120
    """Maximum seconds to wait for a CAPTCHA solve response from the provider."""

    # ─── Cloudflare Harvester ──────────────────────────────────────────
    CF_HARVESTER_ENABLED: bool = False
    """Enable Cloudflare cf_clearance cookie harvesting. When True and a
    Cloudflare challenge is detected, a dedicated browser context is
    opened to wait for the JS challenge to auto-resolve and the resulting
    cf_clearance cookie is persisted for subsequent requests."""
    CF_HARVESTER_TIMEOUT_S: float = 30.0
    """Maximum seconds to wait for cf_clearance cookie after navigating
    to a Cloudflare challenge page."""
    CF_HARVESTER_MAX_RENDER_WAIT_S: float = 15.0
    """Maximum seconds to wait for the page to initially render before
    beginning the cookie-poll loop."""

    # ─── Anti-Bot Detection ────────────────────────────────────────────
    ANTIBOT_PLATFORM_MATCH_SCORE: float = 0.6
    """Score boost when platform matches expected pattern."""
    ANTIBOT_CLOUDFLARE_SCORE: float = 0.45
    """Score for Cloudflare server header detection."""
    ANTIBOT_AKAMAI_SCORE: float = 0.55
    """Score for Akamai server header detection."""
    ANTIBOT_HARD_BLOCK_THRESHOLD: float = 0.8
    """Anti-bot score above this means hard block."""
    ANTIBOT_STEALTH_ESCALATION_MEAN: float = 0.4
    """Mean score above this triggers stealth escalation."""
    ANTIBOT_UA_HISTORY_SIZE: int = 5
    """Number of recent user-agent strings to track."""
    ANTIBOT_BLOCK_HISTORY_SIZE: int = 10
    """Number of historical block events to retain."""
    ANTIBOT_HARD_BLOCK_DELAY: int = 30
    """Seconds to delay after a hard block detection."""
    ANTIBOT_MEDIUM_CHALLENGE_DELAY: int = 5
    """Seconds to delay after a medium challenge detection."""
    ANTIBOT_COOKIE_MAX_AGE_HOURS: int = 24
    """Max age in hours before cookie refresh is required."""

    # ─── Email Validation ──────────────────────────────────────────────
    EMAIL_BLOCKED_DOMAINS: str = "example.com,test.com,localhost"
    """Comma-separated list of email domains to reject as invalid."""

    # ─── Telegram Notifications ─────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    """Telegram bot token for sending notifications. Get from @BotFather."""
    TELEGRAM_CHAT_ID: str = ""
    """Telegram chat ID to send notifications to. Get from @userinfobot or similar."""
    TELEGRAM_ENABLED: bool = False
    """Enable Telegram notifications for tests and critical events."""
    TELEGRAM_NOTIFY_ON_TEST_START: bool = True
    """Send notification when test suite starts."""
    TELEGRAM_NOTIFY_ON_TEST_END: bool = True
    """Send notification when test suite ends (pass/fail)."""
    TELEGRAM_NOTIFY_ON_TEST_FAILURE: bool = True
    """Send notification on individual test failures."""
    TELEGRAM_NOTIFY_ON_CRITICAL_ERROR: bool = True
    """Send notification on critical application errors."""
    TELEGRAM_API_BASE: str = "https://api.telegram.org"
    """Telegram Bot API base URL. Override for local Bot API server."""
