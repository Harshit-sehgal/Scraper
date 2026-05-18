"""
Centralized Configuration for DataForge Scraper.

All hardcoded values, timeouts, thresholds, paths, and tunables
live here — not scattered across modules. Import via:

    from app.config import settings

To override, set the corresponding env var (e.g. PLAYWRIGHT_TIMEOUT=45000).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATAFORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

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
    PAGE_LOADING_INDICATOR_TIMEOUT: int = 2000
    """Ms to wait for each common loading indicator to disappear."""
    PAGE_SCROLL_DELAY: float = 0.5
    """Seconds to wait after auto-scrolling to trigger lazy loaders."""
    MAX_SCROLL_ATTEMPTS: int = 3
    """Maximum number of sequential scrolls for infinite-scroll pages."""
    PLAYWRIGHT_STEALTH: bool = True
    """Enable basic stealth evasions for anti-bot resilience."""
    DOM_STABILIZATION_INTERVAL: int = 200
    """Ms between DOM change checks."""
    DOM_STABILIZATION_MIN_STABLE_CHECKS: int = 5
    """Consecutive stable checks required for quiescence."""
    DOM_STABILIZATION_MIN_TOTAL_CHECKS: int = 15
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
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    GEOCODER_USER_AGENT: str = "DataForge-Scraper/2.0 (geocoder)"
    """User-agent for geocoding services."""
    MAX_RETRIES: int = 2
    """Number of retries for HTTP requests (httpx)."""
    HTTP_BACKOFF_FACTOR: float = 0.5
    """Backoff multiplier for HTTP retries."""

    # ─── Extraction & AI Structuring ───────────────────────────────────────
    MAX_RECORDS_PER_SOURCE: int = 25
    """Max records kept from a single URL after scoring/dedup."""
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
    """Default timeout for LLM JSON/text calls (seconds)."""
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
    """Max completed/canceled jobs retained before pruning."""
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
    SEMANTIC_STATE_PATH: str = "./backend/data/semantic_state.json"
    STATE_FILE_PATH: str = ""
    """Override for jobs_state.json path. Empty = use default ./backend/data/jobs_state.json"""

    # ─── API Security ──────────────────────────────────────────────────────
    API_KEY: str = ""
    """If set, all /api/* endpoints require X-API-Key header."""
    RATE_LIMIT_GLOBAL: str = "100/minute"
    """Global rate limit for /api/* endpoints (slowapi format). Empty = disabled."""
    RATE_LIMIT_JOB_CREATE: str = "10/minute"
    """Stricter rate limit for job creation (POST /api/jobs)."""
    RATE_LIMIT_DISCOVER: str = "20/minute"
    """Rate limit for discovery endpoint."""

    # ─── Crawl Policy (operational governance) ─────────────────────────────
    CRAWL_MAX_TOTAL_CONCURRENCY: int = 10
    """Absolute cap on global parallel fetches."""
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


settings = Settings()
