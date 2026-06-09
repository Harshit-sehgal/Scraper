"""Browser & Playwright configuration settings."""

from pydantic_settings import BaseSettings


class BrowserSettings(BaseSettings):
    """Browser, Playwright, and fingerprint-management settings."""

    # ─── Browser / Playwright ──────────────────────────────────────────
    PLAYWRIGHT_TIMEOUT: int = 45000
    """Max ms to wait for page navigation / networkidle."""
    PLAYWRIGHT_FALLBACK_TIMEOUT: int = 35000
    """Max ms for domcontentloaded fallback if networkidle fails."""
    PLAYWRIGHT_HEADLESS: bool = True
    """Whether to run browser in headless mode."""
    BROWSER_VIEWPORT_WIDTH: int = 1280
    """Width of browser viewport."""
    BROWSER_VIEWPORT_HEIGHT: int = 900
    """Height of browser viewport."""
    BROWSER_MAX_CONTEXTS: int = 10
    """Maximum number of browser contexts before restarting the browser."""
    BROWSER_CONTEXT_LIFETIME: int = 50
    """Number of pages a single context can fetch before being replaced."""
    BROWSER_IDLE_TIMEOUT: int = 300
    """Seconds a browser instance can stay idle before closing."""
    PAGE_SETTLE_DELAY: float = 2.0
    """Seconds to wait after networkidle for JS rendering to finish."""
    PAGE_FALLBACK_EXTRA_WAIT: float = 5.0
    """Extra seconds when networkidle times out and we fall back to domcontentloaded."""
    PROFILE_MAX_WAIT: int = 30
    """Max seconds for a selector profile to find its wait_for selector."""
    PROFILE_CONTAINER_POLL_ATTEMPTS: int = 8
    """Max polls while waiting for profile item_container count to stabilize."""
    PROFILE_CONTAINER_STABLE_POLLS: int = 2
    """Consecutive stable container counts before extraction proceeds."""
    PROFILE_ALIGNMENT_SCORE_EXACT: float = 1000.0
    PROFILE_ALIGNMENT_SCORE_PLURAL: float = 85.0
    PROFILE_ALIGNMENT_SCORE_TOKEN_OVERLAP: float = 55.0
    PROFILE_ALIGNMENT_SCORE_SUBSTRING: float = 45.0
    PROFILE_ALIGNMENT_SCORE_REVERSE_SUBSTRING: float = 40.0
    PROFILE_ALIGNMENT_SCORE_SYNONYM: float = 50.0
    PROFILE_ALIGNMENT_SCORE_TYPE_BONUS: float = 25.0
    PROFILE_ALIGNMENT_NEGATIVE_PENALTY: float = 500.0
    PROFILE_SELECTOR_TYPE_COMPATIBILITY: dict[str, tuple[str, ...]] = {
        "currency": ("currency", "float", "number"),
        "number": ("number", "float", "integer"),
        "text": ("string",),
        "href": ("url",),
    }
    PAGE_LOADING_INDICATOR_TIMEOUT: int = 2000
    """Ms to wait for each common loading indicator to disappear."""
    PAGE_SCROLL_DELAY: float = 0.5
    """Seconds to wait after auto-scrolling to trigger lazy loaders."""
    POST_SCROLL_RESET_DELAY: float = 0.2
    """Seconds to wait after resetting scroll position to top."""
    MAX_SCROLL_ATTEMPTS: int = 3
    """Maximum number of sequential scrolls for infinite-scroll pages."""
    PLAYWRIGHT_STEALTH: bool = True
    """Enable basic fingerprint randomization for reducing bot detection risk."""
    DOM_STABILIZATION_INTERVAL: int = 200
    """Ms between DOM change checks."""
    DOM_STABILIZATION_MIN_STABLE_CHECKS: int = 5
    """Consecutive stable checks required for quiescence."""
    DOM_STABILIZATION_MIN_TOTAL_CHECKS: int = 25
    """Minimum checks to perform before allowing early exit."""
    DOM_STABILIZATION_MAX_CHECKS: int = 60
    """Absolute limit on DOM stabilization checks."""

    # ─── Browser Stealth Pool ──────────────────────────────────────────
    STEALTH_UA_POOL: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36,"
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36,"
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 "
        "Firefox/123.0,"
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 "
        "Firefox/123.0,"
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
    """Comma-separated pool of stealth user-agent strings."""
    STEALTH_VIEWPORT_WIDTHS: str = "1280,1366,1440,1536,1600,1920"
    """Comma-separated viewport widths for stealth randomization."""
    STEALTH_VIEWPORT_HEIGHTS: str = "720,768,800,900,1024,1080"
    """Comma-separated viewport heights for stealth randomization."""
    STEALTH_DEVICE_SCALE_FACTORS: str = "1.0,1.25,1.5,2.0"
    """Comma-separated device scale factors for stealth randomization."""
    STEALTH_NAVIGATOR_LANGUAGES: str = "en-US,en"
    """Comma-separated navigator.languages for stealth JS injection."""
    STEALTH_TIMEZONE_POOL: str = (
        "America/New_York,America/Chicago,America/Los_Angeles,"
        "Europe/London,Europe/Berlin,Asia/Singapore,Asia/Tokyo,Australia/Sydney"
    )
    """Comma-separated timezone IDs for stealth randomization."""
    STEALTH_HARDWARE_CONCURRENCY: int = 4
    """navigator.hardwareConcurrency value for stealth JS injection."""
    STEALTH_ACCEPT_LANGUAGE: str = "en-US,en;q=0.9"
    """Accept-Language header for stealth HTTP requests."""
    STEALTH_DEFAULT_LOCALE: str = "en-US"
    """Default locale for browser contexts."""

    # ─── Browser Pool Recycling ────────────────────────────────────────
    BROWSER_MAX_CUMULATIVE_FETCHES: int = 200
    """Max cumulative fetches before a browser context is recycled."""
    BROWSER_MAX_RSS_MEMORY_MB: int = 1024
    """Max RSS memory in MB before triggering browser recycle."""
    BROWSER_DRAIN_POLL_INTERVAL: float = 0.5
    """Seconds between drain checks when closing browser pages."""
    BROWSER_CLEANUP_INTERVAL: int = 60
    """Seconds between periodic browser pool cleanup sweeps."""
