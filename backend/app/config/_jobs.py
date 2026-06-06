"""Job runner, crawl policy, queue, discovery, and recovery configuration."""

from pydantic_settings import BaseSettings


class JobRunnerSettings(BaseSettings):
    """Job runner, crawl policy, queue, discovery, and recovery settings."""

    # ─── Job Runner ────────────────────────────────────────────────────
    PER_URL_TIMEOUT_SECONDS: int = 120
    """Max seconds to spend scraping a single URL."""
    MAX_JOB_RUNTIME_SECONDS: int = 1800
    """Max total wall-clock seconds for one job."""
    AI_STRUCTURING_TIMEOUT_SECONDS: int = 240
    """Max seconds for the global AI structuring pass."""
    INSIGHT_TIMEOUT_SECONDS: int = 25
    """Max seconds for AI insight generation."""
    MAX_DISCOVERY_URLS: int = 20
    """Max URLs discovered per auto-discovery."""
    MAX_JOB_HISTORY: int = 300
    """Max completed / canceled jobs retained before pruning."""
    MAX_RECYCLE_BIN_HISTORY: int = 300
    """Max deleted jobs retained before pruning."""
    JOB_RESULTS_DISK_OFFLOAD_THRESHOLD: int = 1000
    """Record count above which job results are offloaded to disk."""
    COST_PER_LLM_CALL: float = 0.01
    """Cost model: dollars per LLM call."""
    COST_PER_FETCH_MS: float = 0.005
    """Cost model: dollars per 1000ms of fetch time."""
    COST_PER_URL_SCRAPE: float = 0.02
    """Cost model: dollars per URL scraped."""

    # ─── Crawl Policy (operational governance) ─────────────────────────
    CRAWL_MAX_TOTAL_CONCURRENCY: int = 10
    """Absolute cap on global parallel fetches."""
    JOB_MAX_PARALLEL_URLS: int = 3
    """Max URLs processed in parallel within a single job."""
    CRAWL_PER_DOMAIN_CONCURRENCY: int = 2
    """Max concurrent fetches per domain."""
    CRAWL_DEFAULT_DELAY_SECONDS: float = 1.0
    """Base delay between requests to the same domain."""
    CRAWL_MAX_RETRIES_PER_DOMAIN: int = 3
    """Max consecutive failures before domain cooldown."""
    CRAWL_COOLDOWN_SECONDS: int = 60
    """Seconds to cool down a domain after max retries."""
    CRAWL_RESPECT_ROBOTS: bool = True
    """Whether to check robots.txt before fetching (best-effort)."""
    CRAWL_MAX_PAGES_PER_DOMAIN: int = 50
    """Max pages scraped from a single domain per job."""

    # ─── Queue Backend ─────────────────────────────────────────────────
    QUEUE_BACKEND: str = "sqlite"
    """Worker queue backend: 'sqlite' (single-node) or 'postgres' (multi-node)."""

    # ─── Discovery / Search ────────────────────────────────────────────
    DDG_MAX_RESULTS_MULTIPLIER: int = 3
    """Multiply num_results to get raw DDG fetch size."""
    DDG_ABSOLUTE_MAX: int = 80
    """Hard cap on raw DDG results."""
    BLOCKED_DISCOVERY_DOMAINS: str = "quickfinds.org"
    """Comma-separated root domains excluded from discovery."""
    DISCOVERY_SOCIAL_DOMAINS: str = (
        "facebook.com,twitter.com,x.com,instagram.com,linkedin.com,reddit.com,pinterest.com,tiktok.com,youtube.com"
    )
    """Comma-separated social root domains for source classification."""
    DISCOVERY_DIRECTORY_DOMAINS: str = (
        "yelp.com,yellowpages.com,justdial.com,sulekha.com,indiamart.com,"
        "tripadvisor.com,glassdoor.com,angieslist.com,homeadvisor.com,houzz.com"
    )
    """Comma-separated directory domains for source classification."""
    DISCOVERY_SEARCH_DOMAINS: str = "google.com,bing.com,yahoo.com,duckduckgo.com,baidu.com"
    """Comma-separated search engine domains for source classification."""
    SOURCE_TRUST_OFFICIAL: float = 0.92
    """Default trust score for official domains."""
    SOURCE_TRUST_DIRECTORY: float = 0.62
    """Default trust score for directory domains."""
    SOURCE_TRUST_SOCIAL: float = 0.5
    """Default trust score for social media domains."""
    SOURCE_TRUST_SEARCH: float = 0.35
    """Default trust score for search engine results."""

    # ─── Search Form Recovery ─────────────────────────────────────────
    SEARCH_FORM_MIN_SCORE: int = 3
    """Minimum score for a form to be classified as a search form."""
    SEARCH_FORM_RECOVERY_TIMEOUT: float = 30.0
    """Timeout in seconds for search form POST recovery."""

    # ─── Session URL Detection ─────────────────────────────────────────
    SESSION_PARAM_NAME_CONFIDENCE: float = 0.8
    SESSION_PARAM_VALUE_CONFIDENCE: float = 0.7
    SESSION_PATH_HASH_CONFIDENCE: float = 0.6
    SESSION_NO_EPHEMERAL_MAX_CONFIDENCE: float = 0.3
    SESSION_BOUND_CONFIDENCE_THRESHOLD: float = 0.6

    # ─── Empty Response Detection ─────────────────────────────────────
    EMPTY_RESPONSE_MIN_HTML_LEN: int = 50
    EMPTY_RESPONSE_MINIMAL_TEXT_LEN: int = 100
    EMPTY_RESPONSE_LOW_TEXT_LEN: int = 300
    EMPTY_RESPONSE_LOW_SIGNAL_COUNT: int = 2
    EMPTY_RESPONSE_DATA_SIGNAL_THRESHOLD: int = 5
    EMPTY_RESPONSE_MODERATE_SIGNAL_COUNT: int = 2
    EMPTY_RESPONSE_CONFIDENCE_THRESHOLD: float = 0.5
    EMPTY_PAGE_SIGNAL_CONFIDENCE: float = 0.8

    # ─── Zero Result Classification ────────────────────────────────────
    ZERO_RESULT_ANTIBOT_THRESHOLD: float = 0.8
    ZERO_RESULT_EMPTY_HTML_LEN: int = 100
    ZERO_RESULT_JS_SHELL_HTML_LEN: int = 1000
    ZERO_RESULT_AUTH_PATTERNS: list[str] = ["login", "sign in", "password"]

    # ─── Failure Classification ────────────────────────────────────────
    CLASSIFY_HYDRATION_DOM_THRESHOLD: int = 50
    CLASSIFY_EMPTY_PAGE_HTML_THRESHOLD: int = 500
    CLASSIFY_LAZYLOAD_DOM_THRESHOLD: int = 100
    CLASSIFY_ANTIBOT_SCORE_THRESHOLD: float = 0.6
    CLASSIFY_LOW_SELECTOR_HIT_THRESHOLD: float = 0.3
    CLASSIFY_DECAY_RATE_THRESHOLD: float = 0.5
    CLASSIFY_MALFORMED_DOM_RATIO: float = 0.3
    CLASSIFY_PARTIAL_EXTRACTION_FILL_RATE: float = 0.5
    CLASSIFY_FAILURE_PATTERN_THRESHOLD: int = 3
    CLASSIFY_HYDRATION_DELAY_INCREMENT: int = 500
    CLASSIFY_HYDRATION_DELAY_MAX: int = 10000

    # ─── Scraper Recovery ──────────────────────────────────────────────
    MAX_RECOVERY_ATTEMPTS: int = 3
    """Max recovery attempts per URL in scrape_url_with_recovery."""
    RECOVERY_TIMEOUT_MULTIPLIER: int = 4
    """Multiplier for per_url_timeout when recovery is active."""

    # ─── Acquisition Pipeline ──────────────────────────────────────────
    ACQUISITION_STANDARD_MAX_RETRIES: int = 1
    ACQUISITION_AGGRESSIVE_MAX_RETRIES: int = 2
    ACQUISITION_DEEP_SCAN_MAX_RETRIES: int = 3
    ACQUISITION_AGGRESSIVE_TIMEOUT_MULT: float = 1.5
    ACQUISITION_DEEP_SCAN_TIMEOUT_MULT: float = 2.0
    ACQUISITION_TELEMETRY_MAX_HISTORY: int = 500
    ACQUISITION_TELEMETRY_RECENT_DEFAULT: int = 20

    # ─── Location / Locale ────────────────────────────────────────────
    LOCATION_WORDS: str = (
        "chennai,bangalore,delhi,mumbai,kolkata,hyderabad,pune,ahmedabad,"
        "jaipur,lucknow,london,new york,los angeles,chicago,houston,phoenix,"
        "paris,berlin,tokyo,singapore,sydney,toronto,melbourne,dubai,amsterdam,"
        "beijing,seoul,bangkok,madrid,rome,dublin,sao paulo,mexico city,"
        "buenos aires,cairo,nairobi,lagos,jakarta,manila"
    )
    """Comma-separated location words for geographic field detection."""
