"""Centralized Configuration for DataForge Scraper.

All hardcoded values, timeouts, thresholds, paths, and tunables
live here — not scattered across modules. Import via:

    from app.config import settings

To override, set the corresponding env var (e.g. PLAYWRIGHT_TIMEOUT=45000).
"""

from __future__ import annotations

import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SETTINGS_ENV_FILE = os.getenv("DATAFORGE_DOTENV_PATH", ".env").strip() or ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATAFORGE_",
        env_file=_SETTINGS_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ALLOWED_INTERNAL_HOSTS: str = ""
    """Comma-separated list of allowed internal hostnames (for testing / smoke)."""

    # ─── Browser / Playwright ──────────────────────────────────────────────
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
    """Enable basic stealth evasions for anti-bot resilience."""
    DOM_STABILIZATION_INTERVAL: int = 200
    """Ms between DOM change checks."""
    DOM_STABILIZATION_MIN_STABLE_CHECKS: int = 5
    """Consecutive stable checks required for quiescence."""
    DOM_STABILIZATION_MIN_TOTAL_CHECKS: int = 25
    """Minimum checks to perform before allowing early exit."""
    DOM_STABILIZATION_MAX_CHECKS: int = 60
    """Absolute limit on DOM stabilization checks."""

    # ─── HTTP Fetching ─────────────────────────────────────────────────────
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

    # ─── Extraction & AI Structuring ───────────────────────────────────────
    MAX_RECORDS_PER_SOURCE: int = 25
    """Max records kept from a single URL after scoring / dedup."""
    DEFAULT_MIN_RECORD_SCORE: float = 0.35
    """Default minimum quality score for a record to be accepted."""
    RECORD_ACCEPTANCE_FACTOR: float = 0.8
    """Factor applied to min_record_score for final record acceptance."""
    CONTACT_BOOST_MIN_RECORDS: int = 2
    """Minimum records required to trigger page-level contact boosting."""
    CONTACT_BOOST_THRESHOLD: float = 0.2
    """Percentage of records with contacts below which boosting is triggered."""
    AI_STRUCTURING_CHUNK_SIZE: int = 15
    """Records per chunk when batch-cleaning via LLM."""
    AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES: int = 5
    """Stop trying AI cleaning after this many consecutive failures."""
    AI_CLEAN_TARGET_RECORDS: int = 30
    """Max top-scored records sent to AI cleaning (to save tokens)."""
    SCORE_GATE_THRESHOLD_FACTOR: float = 0.5
    """Factor of min_record_score used as the selector quality gate floor."""
    SCORE_GATE_ABSOLUTE_MIN: float = 0.1
    """Absolute floor for the quality gate threshold."""

    # ─── Insight Engine ───────────────────────────────────────────────────
    INSIGHT_MAX_FIELDS: int = 8
    """Max fields suggested by intent parser."""
    INSIGHT_SAMPLE_SIZE: int = 20
    """Number of records used for dataset insight generation."""
    INSIGHT_TEMPERATURE: float = 0.5
    """Temperature for insight generation LLM calls."""

    # ─── URL Analyzer ──────────────────────────────────────────────────────
    URL_ANALYZER_MAX_FIELDS: int = 30
    """Max fields returned by the URL analyzer (higher than intent parser because
    we're analyzing an actual page with all its data columns)."""
    URL_ANALYZER_SNIPPET_MAX_CHARS: int = 30000
    """Max characters of HTML sent to LLM for URL analysis (higher than selector
    discovery because we need the LLM to see more of the page to find all fields)."""
    URL_ANALYZER_TEMPERATURE: float = 0.5
    """Temperature for URL analysis LLM calls (higher than default 0.1 to encourage
    more thorough exploration and descriptive field naming)."""

    # ─── Scraper Heuristics (Grounding abstractions) ───────────────────────
    SELECTOR_SNIPPET_MAX_CHARS: int = 16000
    """Max characters of HTML sent to LLM for selector discovery."""
    REGEX_MAX_CONTAINERS: int = 300
    """Hard limit on containers scanned by regex fallback."""
    SELECTOR_MIN_TEXT_LEN: int = 5
    """Min text length for a node to be considered a data container."""
    SELECTOR_HEADING_FALLBACK_LEN: int = 70
    """Max length of text considered as a heading fallback."""
    NOISE_COHESION_THRESHOLD: float = 0.2
    """Cohesion score below which a record is flagged as noise."""
    NOISE_MIN_VALUES_FOR_REPETITION_CHECK: int = 3
    """Number of identical fields required to trigger template-noise flag."""
    NOISE_SOCIAL_PLATFORM_THRESHOLD: int = 3
    """Number of social platforms seen in a row before flagging as footer noise."""
    CONTACT_VALID_PHONE_MIN_DIGITS: int = 7
    """Min digits for a valid phone number."""
    CONTACT_VALID_PHONE_MAX_DIGITS: int = 15
    """Max digits for a valid phone number."""
    SELECTOR_MEMORY_MAX_FAILURES: int = 3
    """Max consecutive failures for a remembered selector before it's suspended."""

    # ─── LLM Provider Timeouts ─────────────────────────────────────────────
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

    # ─── Job Runner ────────────────────────────────────────────────────────
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

    # ─── Scorer Heuristics ─────────────────────────────────────────────────
    SCORE_QUALITY_WEIGHT: float = 0.55
    SCORE_COVERAGE_WEIGHT: float = 0.20
    SCORE_SOURCE_TRUST_WEIGHT: float = 0.15
    SCORE_TYPE_INTEGRITY_WEIGHT: float = 0.10

    # ─── Discovery / Search ────────────────────────────────────────────────
    DDG_MAX_RESULTS_MULTIPLIER: int = 3
    """Multiply num_results to get raw DDG fetch size."""
    DDG_ABSOLUTE_MAX: int = 80
    """Hard cap on raw DDG results."""
    BLOCKED_DISCOVERY_DOMAINS: str = "quickfinds.org"
    """Comma-separated root domains excluded from discovery."""

    # ─── Semantic Pipeline Thresholds (field-derived ceilings) ─────────────
    # These are UPPER bounds — actual thresholds emerge from field pressure.
    PIPELINE_INSTABILITY_THRESHOLD_MAX: float = 0.9
    PIPELINE_CONTRADICTION_PENALTY_MAX: float = 0.8
    PIPELINE_COHERENCE_THRESHOLD_MAX: float = 0.7
    PIPELINE_INSTABILITY_DELTA_MAX: float = 0.4
    PIPELINE_CONTRADICTION_DELTA_MAX: float = 0.6
    PIPELINE_TOPOLOGY_DELTA_MAX: float = 0.15

    # ─── Observability ─────────────────────────────────────────────────────
    TELEMETRY_STREAM_MAXLEN: int = 1000
    DRIFT_LOG_MAXLEN: int = 100
    HEATMAP_MAX_SCORE: float = 10.0
    HEATMAP_DECAY_RATE: float = 0.9

    # ─── Memory / GC ───────────────────────────────────────────────────────
    RESOURCE_SHEDDING_MAX_BYTES: int = 10_000_000
    TOPOLOGY_MAX_REGIONS: int = 50
    MOTIF_PRUNE_THRESHOLD: float = 0.2

    # ─── Paths ─────────────────────────────────────────────────────────────
    SEMANTIC_STATE_PATH: str = "data/semantic_state.json"

    @property
    def SEMANTIC_STATE_PATH_DYNAMIC(self) -> str:
        """Semantic state path (dynamic). Reads from SEMANTIC_STATE_PATH env var
        dynamically, falls back to static SEMANTIC_STATE_PATH field.
        """
        return os.environ.get("SEMANTIC_STATE_PATH") or self.SEMANTIC_STATE_PATH

    STATE_FILE_PATH: str = ""
    """Override for jobs_state.json path. Empty = use default ./backend/data/jobs_state.json"""

    @property
    def STATE_FILE_PATH_DYNAMIC(self) -> str:
        """State file path (dynamic). Reads from DATAFORGE_STATE_FILE env var
        dynamically, falls back to static STATE_FILE_PATH field. This lets the
        test conftest isolate test runs from the developer runtime database
        without rewriting settings.STATE_FILE_PATH after import.
        """
        return os.environ.get("DATAFORGE_STATE_FILE") or self.STATE_FILE_PATH

    AUDIT_LOG_DIR: str = ""
    """Override for audit log directory. Empty = use audit logger default."""

    # ─── API Security ──────────────────────────────────────────────────────
    ENV: str = "development"
    """Application runtime environment: development or production."""
    ALLOW_INSECURE_DEV_AUTH: bool = False
    """Require an explicit bypass flag for insecure local development authentication bypass."""
    API_KEY: str = ""
    """If set, all /api/* endpoints require X-API-Key header."""
    OPERATOR_API_KEY: str = ""
    """If set, operator routes (creating and running jobs, manual scraper invocation) require this key."""
    ADMIN_API_KEY: str = ""
    """If set, powerful admin routes (/api / system / merge, /api / system / scheduler, etc.) require this key."""
    METRICS_TOKEN: str = ""
    """If set, /metrics endpoint requires Authorization: Bearer <token> or X-API-Key header."""
    ALERT_WEBHOOK_URL: str | None = None
    """URL to send webhook alerts for domain anti-bot level shifts."""
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:8000", "http://127.0.0.1:5173", "http://127.0.0.1:8000"]
    """Allowed origins for CORS. Defaults to localhost for dev; must be locked to real domains in production."""
    CSP_REPORT_ONLY: bool = True
    """Attach a report-only Content-Security-Policy header to every response.
    Never blocks anything; the browser POSTs violation reports to
    ``/api/system/csp-violations`` so the operator can iteratively tighten
    the policy. Defaults to True in development; set to False in production
    until the operator confirms the policy is clean (i.e. zero violations
    in the dashboard for at least one release cycle)."""
    METRICS_ENABLE_HISTOGRAMS: bool = True
    """Enable request duration and operation latency histograms in /metrics output."""
    METRICS_HISTOGRAM_BUCKETS: str = "0.01,0.05,0.1,0.25,0.5,1.0,2.5,5.0,10.0,30.0,60.0,120.0"
    """Comma-separated bucket boundaries for duration histograms (seconds)."""
    RATE_LIMIT_GLOBAL: str = "600/minute"
    """Aggregate rate limit across all clients for /api/* endpoints. Empty = disabled."""
    RATE_LIMIT_PER_IP: str = "100/minute"
    """Per-IP rate limit when per-IP tracking is enabled. Each client IP gets its own
    counter with this cap, separate from the aggregate global cap. Empty = disabled."""
    RATE_LIMIT_PER_IP_ENABLED: bool = True
    """Enable per-IP rate limiting. When True, each client IP is rate-limited
    independently using ``RATE_LIMIT_PER_IP`` as the cap. When False, only the
    aggregate ``RATE_LIMIT_GLOBAL`` applies across all clients combined.
    In-memory counters are used for single-process deployments; the database-backed
    store is used when ``RATE_LIMIT_DB_BACKED`` is True (auto-promoted in
    production/staging)."""
    RATE_LIMIT_JOB_CREATE: str = "10/minute"
    """Stricter rate limit for job creation (POST /api / jobs)."""
    RATE_LIMIT_DISCOVER: str = "20/minute"
    """Rate limit for discovery endpoint."""
    RATE_LIMIT_DB_BACKED: bool = False
    """Enable shared, database-backed rate limiting for multi-process environments."""

    # ─── Crawl Policy (operational governance) ─────────────────────────────
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

    # ─── LLM Output Validation ─────────────────────────────────────────────
    LLM_VALIDATE_JSON: bool = True
    """Validate LLM JSON output against expected schema."""
    LLM_VALIDATION_MAX_RETRIES: int = 2
    """Max retries for malformed LLM JSON."""

    # ─── Scrape Telemetry defaults (overridable) ───────────────────────────
    TELEMETRY_RECORD_EXTRACTION: bool = True
    """Emit per-URL scrape telemetry events."""

    # ─── LLM Provider Settings ───────────────────────────────────────────────
    GROQ_API_ENDPOINT: str = "https://api.groq.com/openai/v1/chat/completions"
    """Groq API endpoint for LLM calls."""
    POLLINATIONS_API_ENDPOINT: str = "https://text.pollinations.ai/openai"
    """Pollinations AI endpoint for LLM calls."""
    LLM_ENABLE_PUBLIC_FALLBACKS: bool = False
    """Allow unauthenticated public LLM fallbacks such as Pollinations/g4f.

    Disabled by default so local validation and production deployments do not
    make unconfigured external AI calls.
    """

    # ─── Proxy & Anti-Bot Evasion ──────────────────────────────────────────
    PROXY_ROTATION_ENABLED: bool = False
    """Enable proxy rotation for anti-bot resilience."""
    PROXY_LIST: str = ""
    """Comma-separated list of proxy URLs (http://ip:port or socks5://ip:port)."""
    PROXY_ROTATION_FAILURE_THRESHOLD: int = 5
    """Rotate proxy after this many consecutive failures."""
    PROXY_TIMEOUT_SECONDS: int = 30
    """Timeout for proxy connection attempts."""

    # ─── Email Validation ────────────────────────────────────────────────────
    EMAIL_BLOCKED_DOMAINS: str = "example.com,test.com,localhost"
    """Comma-separated list of email domains to reject as invalid."""

    # ─── Acquisition Pipeline ──────────────────────────────────────────────
    ACQUISITION_STANDARD_MAX_RETRIES: int = 1
    """Max retries for STANDARD acquisition mode."""
    ACQUISITION_AGGRESSIVE_MAX_RETRIES: int = 2
    """Max retries for AGGRESSIVE acquisition mode."""
    ACQUISITION_DEEP_SCAN_MAX_RETRIES: int = 3
    """Max retries for DEEP_SCAN acquisition mode."""
    ACQUISITION_AGGRESSIVE_TIMEOUT_MULT: float = 1.5
    """Timeout multiplier for AGGRESSIVE mode."""
    ACQUISITION_DEEP_SCAN_TIMEOUT_MULT: float = 2.0
    """Timeout multiplier for DEEP_SCAN mode."""
    ACQUISITION_TELEMETRY_MAX_HISTORY: int = 500
    """Max acquisition events retained in telemetry history."""
    ACQUISITION_TELEMETRY_RECENT_DEFAULT: int = 20
    """Default count for recent acquisition events query."""

    # ─── Session URL Detection ────────────────────────────────────────────
    SESSION_PARAM_NAME_CONFIDENCE: float = 0.8
    """Confidence boost for known session param name patterns."""
    SESSION_PARAM_VALUE_CONFIDENCE: float = 0.7
    """Confidence for param value matching session patterns."""
    SESSION_PATH_HASH_CONFIDENCE: float = 0.6
    """Confidence for path-hash-like param values."""
    SESSION_NO_EPHEMERAL_MAX_CONFIDENCE: float = 0.3
    """Max confidence when no ephemeral params detected."""
    SESSION_BOUND_CONFIDENCE_THRESHOLD: float = 0.6
    """Confidence threshold above which a URL is classified as session-bound."""

    # ─── Empty Response Detection ─────────────────────────────────────────
    EMPTY_RESPONSE_MIN_HTML_LEN: int = 50
    """HTML shorter than this is classified as blank."""
    EMPTY_RESPONSE_MINIMAL_TEXT_LEN: int = 100
    """Visible text shorter than this is classified as minimal."""
    EMPTY_RESPONSE_LOW_TEXT_LEN: int = 300
    """Text shorter than this with few data signals is likely empty."""
    EMPTY_RESPONSE_LOW_SIGNAL_COUNT: int = 2
    """Fewer than this many data signals is considered low-content."""
    EMPTY_RESPONSE_DATA_SIGNAL_THRESHOLD: int = 5
    """This many or more data signals means the page is not empty."""
    EMPTY_RESPONSE_MODERATE_SIGNAL_COUNT: int = 2
    """This many moderate data signals may still indicate content."""
    EMPTY_RESPONSE_CONFIDENCE_THRESHOLD: float = 0.5
    """Confidence above this means the page is empty."""
    EMPTY_PAGE_SIGNAL_CONFIDENCE: float = 0.8
    """Confidence for strong empty-page signals (login walls, etc.)."""

    # ─── Zero Result Classification ────────────────────────────────────────
    ZERO_RESULT_ANTIBOT_THRESHOLD: float = 0.8
    """Anti-bot score above this classifies zero-result as anti-bot block."""
    ZERO_RESULT_EMPTY_HTML_LEN: int = 100
    """HTML shorter than this is classified as a blank / empty page."""
    ZERO_RESULT_JS_SHELL_HTML_LEN: int = 1000
    """HTML longer than this without containers suggests JS shell."""
    ZERO_RESULT_AUTH_PATTERNS: list[str] = ["login", "sign in", "password"]
    """Text patterns that indicate an authentication gate."""

    # ─── Record Quality Scoring ───────────────────────────────────────────
    QUALITY_BASE_SCORE: float = 0.3
    """Base quality score for non-empty text values."""
    QUALITY_TEXT_LEN_THRESHOLD_1: int = 4
    """Text longer than this gets a length bonus (+0.2)."""
    QUALITY_TEXT_LEN_THRESHOLD_2: int = 20
    """Text longer than this gets another length bonus (+0.1)."""
    QUALITY_NOISE_PENALTY: float = 0.6
    """Penalty for noise phrases in identity fields."""
    QUALITY_SHORT_IDENTITY_PENALTY: float = 0.2
    """Penalty for short text in identity fields (< 3 chars)."""
    QUALITY_STATUS_LONG_PENALTY: float = 0.4
    """Penalty for long text in status fields (> 25 chars)."""
    QUALITY_STATUS_MISMATCH_PENALTY: float = 0.2
    """Penalty for status fields without known phrases and long text."""
    QUALITY_PRESENT_FIELD_THRESHOLD: float = 0.2
    """Field quality above this counts as 'present'."""
    QUALITY_REQUIRED_MISSING_THRESHOLD: float = 0.3
    """Required field quality below this increments missing count."""
    QUALITY_REQUIRED_WEIGHT: float = 1.2
    """Weight multiplier for required fields in scoring."""
    QUALITY_PRESENCE_COHESION_THRESHOLD: float = 0.3
    """Presence vote below this triggers a cohesion penalty."""
    QUALITY_PRESENCE_VOTE_WEIGHT: float = 0.3
    """Weight for presence vote in ensemble blend."""
    QUALITY_QUALITY_VOTE_WEIGHT: float = 0.7
    """Weight for quality vote in ensemble blend."""

    # ─── Selector Fallback Extraction ──────────────────────────────────────
    SELECTOR_FUZZY_MIN_WORDS: int = 2
    """Min words in example value for fuzzy matching."""
    SELECTOR_FUZZY_MAX_WORDS: int = 5
    """Max words in example value for fuzzy matching."""
    SELECTOR_FUZZY_MATCH_RATIO: float = 0.7
    """Min word match ratio for fuzzy example matching."""
    SELECTOR_CONTEXT_WINDOW_MAX_LEN: int = 120
    """Max characters for context window around fuzzy match."""
    SELECTOR_MIN_SEGMENT_LEN: int = 3
    """Min characters for extracted context segment."""

    @property
    def GROQ_API_KEY(self) -> str:
        """Groq API key for LLM calls. Read from GROQ_API_KEY env var dynamically."""
        return (os.environ.get("GROQ_API_KEY") or "").strip()

    @property
    def WORKER_QUEUE(self) -> bool:
        """Whether worker queue mode is enabled. Read from DATAFORGE_WORKER_QUEUE env var dynamically."""
        return (os.environ.get("DATAFORGE_WORKER_QUEUE") or "").strip().lower() in ("1", "true", "yes")

    @property
    def SMOKE_TEST_MODE(self) -> bool:
        """Whether smoke test mode is enabled. Reads from DATAFORGE_SMOKE_TEST_MODE env var dynamically."""
        return (os.environ.get("DATAFORGE_SMOKE_TEST_MODE") or "").strip().lower() in ("true", "1", "yes")

    @property
    def STORAGE_BACKEND(self) -> str:
        """Storage backend. Reads from DATAFORGE_STORAGE_BACKEND env var dynamically. Default: 'sqlite'."""
        return (os.environ.get("DATAFORGE_STORAGE_BACKEND") or "sqlite").strip().lower()

    @property
    def DATABASE_URL(self) -> str:
        """Database URL. Reads from DATAFORGE_DATABASE_URL env var dynamically."""
        return (os.environ.get("DATAFORGE_DATABASE_URL") or "").strip()

    @property
    def PG_MIN_CONN(self) -> int:
        """Postgres pool minimum size. Reads from DATAFORGE_PG_MIN_CONN.

        Default: 1 (matches the prior hard-coded psycopg2/psycopg3
        ``minconn=1`` / ``min_size=1`` behaviour so existing
        deployments see no change).
        """
        raw = (os.environ.get("DATAFORGE_PG_MIN_CONN") or "1").strip()
        try:
            value = int(raw)
        except ValueError:
            return 1
        return max(1, min(value, 1000))

    @property
    def PG_MAX_CONN(self) -> int:
        """Postgres pool maximum size. Reads from DATAFORGE_PG_MAX_CONN.

        Default: 10 (matches the prior hard-coded psycopg2
        ``maxconn=10`` / psycopg3 ``max_size=10`` behaviour so existing
        deployments see no change). The setting is clamped to a safe
        upper bound of 1000 to prevent accidental denial-of-service via
        a malformed env var.
        """
        raw = (os.environ.get("DATAFORGE_PG_MAX_CONN") or "10").strip()
        try:
            value = int(raw)
        except ValueError:
            return 10
        return max(1, min(value, 1000))

    @property
    def QUEUE_BACKEND_DYNAMIC(self) -> str:
        """Queue backend (dynamic). Reads from DATAFORGE_QUEUE_BACKEND env var
        dynamically, falls back to static QUEUE_BACKEND field.
        """
        return (os.environ.get("DATAFORGE_QUEUE_BACKEND") or self.QUEUE_BACKEND).strip().lower()

    @property
    def STATE_FILE(self) -> str:
        """State file path (legacy alias). Reads from DATAFORGE_STATE_FILE env var dynamically."""
        return (os.environ.get("DATAFORGE_STATE_FILE") or "").strip()

    # ─── Queue Backend ─────────────────────────────────────────────────────
    QUEUE_BACKEND: str = "sqlite"
    """Worker queue backend: 'sqlite' (single-node) or 'postgres' (multi-node).
    Postgres backend requires DATAFORGE_STORAGE_BACKEND=postgres and a running
    Postgres instance available via DATAFORGE_DATABASE_URL."""

    # ─── Anti-Bot Detection ────────────────────────────────────────────────
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

    # ─── Failure Classification ────────────────────────────────────────────
    CLASSIFY_HYDRATION_DOM_THRESHOLD: int = 50
    """DOM nodes below this suggests hydration failure."""
    CLASSIFY_EMPTY_PAGE_HTML_THRESHOLD: int = 500
    """HTML chars below this suggests empty page."""
    CLASSIFY_LAZYLOAD_DOM_THRESHOLD: int = 100
    """DOM nodes below this suggests lazy-load failure."""
    CLASSIFY_ANTIBOT_SCORE_THRESHOLD: float = 0.6
    """Anti-bot score above this classifies as bot detection."""
    CLASSIFY_LOW_SELECTOR_HIT_THRESHOLD: float = 0.3
    """Selector hit rate below this suggests selector decay."""
    CLASSIFY_DECAY_RATE_THRESHOLD: float = 0.5
    """Decay rate above this suggests selector quality degradation."""
    CLASSIFY_MALFORMED_DOM_RATIO: float = 0.3
    """DOM ratio below this suggests malformed HTML."""
    CLASSIFY_PARTIAL_EXTRACTION_FILL_RATE: float = 0.5
    """Fill rate below this suggests partial extraction."""
    CLASSIFY_FAILURE_PATTERN_THRESHOLD: int = 3
    """Failure count above this indicates a pattern."""
    CLASSIFY_HYDRATION_DELAY_INCREMENT: int = 500
    """Ms to add per detected loading indicator."""
    CLASSIFY_HYDRATION_DELAY_MAX: int = 10000
    """Max ms for hydration delay."""

    # ─── Discovery & Source Trust ──────────────────────────────────────────
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

    # ─── Browser Stealth Pool ─────────────────────────────────────────────
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
    """Comma-separated pool of stealth user-agent strings shared across browser_pool and anti_bot_engine."""
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

    # ─── LLM Provider Models ──────────────────────────────────────────────
    GROQ_DEFAULT_MODEL: str = "llama-3.3-70b-versatile"
    """Default model for Groq LLM calls."""
    GROQ_FALLBACK_MODEL: str = "llama-3.1-8b-instant"
    """Fallback model when default Groq model fails."""
    G4F_JSON_MODEL: str = "gpt-4o-mini"
    """Model for g4f JSON fallback calls."""
    G4F_TEXT_MODEL: str = "gpt-4o"
    """Model for g4f text fallback calls."""

    # ─── Search Form Recovery ─────────────────────────────────────────────
    SEARCH_FORM_MIN_SCORE: int = 3
    """Minimum score for a form to be classified as a search form."""
    SEARCH_FORM_RECOVERY_TIMEOUT: float = 30.0
    """Timeout in seconds for search form POST recovery."""

    # ─── Location / Locale ────────────────────────────────────────────────
    LOCATION_WORDS: str = (
        "chennai,bangalore,delhi,mumbai,kolkata,hyderabad,pune,ahmedabad,"
        "jaipur,lucknow,london,new york,los angeles,chicago,houston,phoenix,"
        "paris,berlin,tokyo,singapore,sydney,toronto,melbourne,dubai,amsterdam,"
        "beijing,seoul,bangkok,madrid,rome,dublin,sao paulo,mexico city,"
        "buenos aires,cairo,nairobi,lagos,jakarta,manila"
    )
    """Comma-separated location words for geographic field detection."""

    # ─── Scraper Recovery ──────────────────────────────────────────────────
    MAX_RECOVERY_ATTEMPTS: int = 3
    """Max recovery attempts per URL in scrape_url_with_recovery."""
    RECOVERY_TIMEOUT_MULTIPLIER: int = 4
    """Multiplier for per_url_timeout when recovery is active."""

    # ─── Job Runner ────────────────────────────────────────────────────────
    JOB_RESULTS_DISK_OFFLOAD_THRESHOLD: int = 1000
    """Record count above which job results are offloaded to disk."""
    COST_PER_LLM_CALL: float = 0.01
    """Cost model: dollars per LLM call."""
    COST_PER_FETCH_MS: float = 0.005
    """Cost model: dollars per 1000ms of fetch time."""
    COST_PER_URL_SCRAPE: float = 0.02
    """Cost model: dollars per URL scraped."""

    # ─── Semantic World State ──────────────────────────────────────────────
    MOTIF_MIN_COOCCURRENCE: int = 2
    """Minimum co-occurrence for field pair motif extraction."""
    REGRESSION_CAPTURE_SCORE_FACTOR: float = 0.5
    """Factor of min_record_score for regression capture threshold."""
    REGRESSION_LOW_QUALITY_CONFIDENCE: float = 0.6
    """Confidence threshold for low-quality regression capture."""

    # ─── Browser Pool Recycling ────────────────────────────────────────────
    BROWSER_MAX_CUMULATIVE_FETCHES: int = 200
    """Max cumulative fetches before a browser context is recycled."""
    BROWSER_MAX_RSS_MEMORY_MB: int = 1024
    """Max RSS memory in MB before triggering browser recycle."""
    BROWSER_DRAIN_POLL_INTERVAL: float = 0.5
    """Seconds between drain checks when closing browser pages."""
    BROWSER_CLEANUP_INTERVAL: int = 60
    """Seconds between periodic browser pool cleanup sweeps."""

    # ─── Domain Intelligence ───────────────────────────────────────────────
    DOMAIN_INTELLIGENCE_SMOOTHING_ALPHA: float = 0.3
    """Smoothing factor for exponential moving average in domain intelligence."""

    # ─── URL Analyzer ──────────────────────────────────────────────────────
    URL_ANALYZER_TIMEOUT: int = 120
    """Max seconds for URL analysis endpoint."""

    # ─── Gossip Propagation ────────────────────────────────────────────────
    GOSSIP_PROPAGATION_INTERVAL: int = 60
    """Seconds between gossip propagation cycles."""

    # ─── Domain Health Alerts ──────────────────────────────────────────────
    DOMAIN_HEALTH_ALERT_COOLDOWN: int = 60
    """Seconds between domain health alert notifications for the same domain."""

    # ─── Domain Intelligence Persistence ───────────────────────────────────
    DOMAIN_INTELLIGENCE_PATH: str = "data/domain_intelligence.json"
    """Path for domain intelligence persistence file."""
    SELECTOR_MEMORY_PATH: str = "data/selector_memory.json"
    """Path for selector memory persistence file."""
    SELECTOR_DECAY_SNAPSHOT_PATH: str = "data/selector_decay_snapshots.json"
    """Path for selector decay snapshots."""
    REGRESSION_REGISTRY_PATH: str = "data/regression_registry.json"
    """Path for regression capture registry."""
    SELECTOR_PROFILES_DIR: str = "profiles"
    """Directory for selector profile definitions."""
    FRONTEND_DIR: str = ""
    """Override for frontend static files directory. Empty = auto-detect."""
    HTTPX_BASIC_USER_AGENT: str = "python-httpx/0.27.0"
    """User-Agent for basic HTTPX requests (non-stealth)."""

    @property
    def TEST_SELECTOR_DECAY_PERSISTENCE(self) -> bool:
        """Whether to persist selector decay snapshots during tests. Reads from
        TEST_SELECTOR_DECAY_PERSISTENCE env var dynamically.
        """
        return (os.environ.get("TEST_SELECTOR_DECAY_PERSISTENCE") or "").strip().lower() in ("true", "1", "yes")

    ENABLE_EXPERIMENTAL_ROUTES: bool = False
    """Enable experimental / research-only API routes."""

    # ─── Federation / Sharding ──────────────────────────────────────────────
    NODE_ID: str = "node-1"
    """Unique identifier for this node / worker context."""
    SHARD_ID: str = "shard-1"
    """Unique identifier for the sharded workload context."""

    def __getattr__(self, name: str):
        """Provide backwards-compatible aliases for config parameters."""
        # Mapping of old names to new names
        aliases = {
            "BROWSER_POOL_SIZE": "BROWSER_MAX_CONTEXTS",
            "RENDER_TIMEOUT": "PLAYWRIGHT_TIMEOUT",
            "FETCH_TIMEOUT": "REQUEST_TIMEOUT",
            "MIN_RECORD_SCORE": "DEFAULT_MIN_RECORD_SCORE",
        }

        if name in aliases:
            return super().__getattribute__(aliases[name])

        msg = f"'{type(self).__name__}' object has no attribute '{name}'"
        raise AttributeError(msg)

    @model_validator(mode="after")
    def _auto_promote_db_backed_rate_limit(self) -> Settings:
        """Promote ``RATE_LIMIT_DB_BACKED`` to True in production-like envs.

        A multi-process / multi-worker deployment cannot share an
        in-process rate-limit counter across workers. When ``ENV`` is
        ``production`` or ``staging`` we therefore default the flag to
        True unless the operator has explicitly opted out.

        The check uses ``model_fields_set`` to detect an explicit
        assignment (env var, init kwarg, or ``.model_construct``). An
        unset field keeps its declared default ``False`` and is
        promoted here; an explicitly-set value is always respected.
        """
        if self.ENV.lower() in {"production", "staging"}:
            if "RATE_LIMIT_DB_BACKED" not in self.model_fields_set:
                self.RATE_LIMIT_DB_BACKED = True
        return self


settings = Settings()
