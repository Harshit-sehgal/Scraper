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
    INSIGHT_TIMEOUT: int = 25
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
    PROXY_TIMEOUT_SECONDS: int = 30
    """Timeout for proxy connection attempts."""

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
