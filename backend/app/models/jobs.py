"""Job domain models — the core job entity and all request/response models
for the jobs lifecycle (create, update, extract, clone, batch, events, etc.).
"""

import datetime
import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.scraping import (
    FilterRule,
    SchemaField,
    ScrapeMode,
    SelectorMap,
    SourcePolicy,
)


class JobStatus(StrEnum):
    PENDING = "pending"
    DISCOVERING = "discovering"
    RUNNING = "running"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    EMPTY_RESULT = "empty_result"
    CANCELED = "canceled"
    FAILED = "failed"


class LogEntry(BaseModel):
    """A single log entry for a job."""

    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat(), max_length=64)
    message: str = Field(max_length=8192)
    level: str = Field("info", max_length=16)


class JobCreate(BaseModel):
    """Request body to create a new scraping job."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., max_length=255, description="Human-readable job name")
    mode: ScrapeMode = Field(ScrapeMode.MANUAL, description="Manual or Auto discovery mode")
    intent: str = Field("", max_length=4096, description="Natural language extraction intent")
    # Manual mode
    urls: list[str] = Field(default_factory=list, max_length=100, description="List of URLs to scrape (manual mode)")
    # Auto mode
    topic: str = Field("", description="Topic for auto-discovery", max_length=512)
    location: str = Field("", description="Location focus for auto-discovery", max_length=256)
    preferred_domain: str = Field("", description="Preferred domain for auto-discovery", max_length=253)
    source_policy: SourcePolicy = Field(SourcePolicy.ALL_SOURCES, description="Controls which source types are included")
    max_per_domain: int = Field(4, ge=1, le=25, description="Maximum discovered URLs per domain")
    origin_location: str = Field("", description="Center location for distance optimization")
    max_distance_km: float | None = Field(None, ge=0, description="Keep records within this radius in km")
    # Schema & Filters
    schema_fields: list[SchemaField] = Field(default_factory=list, max_length=50, description="Data schema to extract")
    filters: list[FilterRule] = Field(default_factory=list, max_length=100, description="Post-processing filters")
    # Advanced options
    pagination: bool = Field(False, description="Whether to follow pagination links")
    max_pages: int = Field(10, ge=1, le=100, description="Max pages to follow per URL")
    deduplicate: bool = Field(True, description="Remove duplicate records")
    deduplicate_field: str = Field("", description="Field to use for deduplication", max_length=64)
    # Selectors map from URL analysis (item_container + field selectors)
    selectors_map: dict[str, Any] = Field(default_factory=dict, description="Pre-discovered CSS selectors map from URL analysis")
    search_params: dict[str, str] | None = Field(default=None, description="Search parameters for session-bound URL recovery")
    min_record_score: float = Field(0.35, ge=0.0, le=1.0, description="Minimum quality score required per extracted record")
    auth_profile_id: str | None = Field(
        default=None, description="Optional auth profile ID to use for authenticated scraping", max_length=128
    )
    headers: dict[str, str] = Field(default_factory=dict, description="Custom HTTP headers to send with requests")
    cookies: dict[str, str] = Field(default_factory=dict, description="Custom cookies to inject into requests/browser contexts")
    webhook_url: str | None = Field(
        default=None,
        description="URL to POST job-completion webhook to. Must be https:// or http://.",
        max_length=2048,
    )
    webhook_secret: str | None = Field(
        default=None,
        description="HMAC-SHA256 secret for signing webhook payloads. If set, the X-DataForge-Signature header is included.",
        max_length=128,
    )
    fetch_strategy: str = Field(
        default="",
        description="User-requested fetch strategy (playwright_full, httpx_smart, hybrid, etc.). Empty means auto-select.",
        max_length=32,
    )
    hydration_wait_ms: int | None = Field(
        default=None,
        ge=0,
        le=120_000,
        description=(
            "Override the post-navigation hydration wait (milliseconds). "
            "Higher values help lazy-loaded content; lower values speed up simple pages. "
            "None means the platform picks a sensible default."
        ),
    )
    scroll_attempts: int | None = Field(
        default=None,
        ge=0,
        le=20,
        description=(
            "Override how many scroll-down steps to perform before capturing page content. "
            "Needed for infinite-scroll pages; set to 0 to disable scrolling. "
            "None means the platform picks a sensible default."
        ),
    )
    request_delay_ms: int = Field(
        default=0,
        ge=0,
        le=60_000,
        description=(
            "Minimum delay between consecutive URL fetches within this job (milliseconds). "
            "Use this to avoid overwhelming a target domain. 0 = no extra delay."
        ),
    )
    max_concurrent_urls: int = Field(
        default=4,
        ge=1,
        le=20,
        description=(
            "Maximum number of URLs that can be fetched concurrently within this job. Lower values reduce load on target domains."
        ),
    )
    user_agent: str = Field(
        default="",
        description="Custom User-Agent string for this job. Empty means use platform default.",
        max_length=512,
    )

    @model_validator(mode="after")
    def validate_mode_requirements(self):
        if self.mode == ScrapeMode.MANUAL:
            cleaned_urls = [u.strip() for u in self.urls if str(u or "").strip()]
            if not cleaned_urls:
                msg = "Manual mode requires at least one URL"
                raise ValueError(msg)
            from app.url_safety import validate_public_http_url

            for u in cleaned_urls:
                try:
                    validate_public_http_url(u)
                except ValueError as e:
                    if (
                        "Only http and https are allowed" in str(e)
                        or "scheme" in str(e)
                        or not u.startswith(("http://", "https://"))
                    ):
                        msg = "Manual mode requires valid http(s) URLs"
                        raise ValueError(msg) from e
                    msg = "URL failed security check"
                    raise ValueError(msg) from e
            self.urls = cleaned_urls

        if self.mode == ScrapeMode.AUTO:
            self.topic = self.topic.strip()
            if not self.topic:
                msg = "Auto mode requires a non-empty topic"
                raise ValueError(msg)
            # Auto mode always discovers URLs itself.
            self.urls = []

        # Validate selectors_map shape if present while keeping the external
        # API as a dict.
        if self.selectors_map:
            if not isinstance(self.selectors_map, dict):
                msg = "selectors_map must be an object"
                raise ValueError(msg)
            if len(self.selectors_map) > 20:
                msg = "selectors_map must have at most 20 keys"
                raise ValueError(msg)
            self.selectors_map = SelectorMap.model_validate(self.selectors_map).model_dump()

        # ── search_params limits ──────────────────────────────────────────
        if self.search_params is not None:
            if len(self.search_params) > 50:
                msg = "search_params must have at most 50 keys"
                raise ValueError(msg)
            for k, v in self.search_params.items():
                if not isinstance(k, str) or len(k) > 100:
                    msg = f"search_params key '{k}' exceeds max length of 100"
                    raise ValueError(msg)
                if not isinstance(v, str) or len(v) > 500:
                    msg = f"search_params value for '{k}' exceeds max length of 500"
                    raise ValueError(msg)

        # ── headers limits ────────────────────────────────────────────────
        if self.headers:
            if len(self.headers) > 50:
                msg = "headers must have at most 50 keys"
                raise ValueError(msg)
            for k, v in self.headers.items():
                if not isinstance(k, str) or len(k) > 100:
                    msg = f"headers key '{k}' exceeds max length of 100"
                    raise ValueError(msg)
                if not isinstance(v, str) or len(v) > 2000:
                    msg = f"headers value for '{k}' exceeds max length of 2000"
                    raise ValueError(msg)

        # ── cookies limits ────────────────────────────────────────────────
        if self.cookies:
            if len(self.cookies) > 50:
                msg = "cookies must have at most 50 keys"
                raise ValueError(msg)
            for k, v in self.cookies.items():
                if not isinstance(k, str) or len(k) > 100:
                    msg = f"cookies key '{k}' exceeds max length of 100"
                    raise ValueError(msg)
                if not isinstance(v, str) or len(v) > 4096:
                    msg = f"cookies value for '{k}' exceeds max length of 4096"
                    raise ValueError(msg)

        # ── webhook_url validation ─────────────────────────────────────
        if self.webhook_url:
            stripped = self.webhook_url.strip()
            if not stripped.startswith(("https://", "http://")):
                msg = "webhook_url must start with https:// or http://"
                raise ValueError(msg)
            # SSRF defense: reject private IPs, loopback, link-local
            # at model level so bad URLs never reach webhook_delivery.
            try:
                from app.url_safety import validate_public_http_url

                validate_public_http_url(stripped)
            except ValueError as exc:
                msg = f"webhook_url failed security check: {exc}"
                raise ValueError(msg) from exc
            self.webhook_url = stripped

        # ── fetch_strategy validation ──────────────────────────────────
        if self.fetch_strategy:
            from app.strategy_evolution import FETCH_STRATEGY_VALUES

            if self.fetch_strategy not in FETCH_STRATEGY_VALUES:
                msg = f"fetch_strategy must be one of {sorted(FETCH_STRATEGY_VALUES)}, got {self.fetch_strategy!r}"
                raise ValueError(msg)

        return self


class Job(BaseModel):
    """A scraping job with its current state."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=64)
    name: str = Field(max_length=255)
    mode: ScrapeMode = ScrapeMode.MANUAL
    intent: str = Field("", max_length=4096)
    urls: list[str] = Field(default_factory=list)
    topic: str = Field("", max_length=512)
    location: str = Field("", max_length=256)
    preferred_domain: str = Field("", max_length=253)
    source_policy: SourcePolicy = SourcePolicy.ALL_SOURCES
    max_per_domain: int = 4
    origin_location: str = Field("", max_length=256)
    max_distance_km: float | None = None
    schema_fields: list[SchemaField] = Field(default_factory=list)
    filters: list[FilterRule] = Field(default_factory=list)
    pagination: bool = False
    max_pages: int = 10
    deduplicate: bool = True
    deduplicate_field: str = Field("", max_length=64)
    min_record_score: float = 0.35
    # Selectors map from URL analysis (pre-discovered CSS selectors)
    selectors_map: dict[str, Any] = Field(default_factory=dict, description="Pre-discovered CSS selectors map from URL analysis")
    search_params: dict[str, str] | None = Field(default=None, description="Search parameters for session-bound URL recovery")
    cancel_requested: bool = False
    status: JobStatus = JobStatus.PENDING
    created_by: str = Field(
        default="", description="Owner identity (user ID or API key fingerprint) for data isolation", max_length=128
    )
    org_id: str = Field(default="", description="Tenant org id; populated for persistent API keys (P0-SAAS-001)", max_length=128)
    project_id: str = Field(default="", description="Project id; populated for persistent API keys (P0-SAAS-001)", max_length=128)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat(), max_length=64)
    started_at: str | None = Field(None, max_length=64)
    completed_at: str | None = Field(None, max_length=64)
    total_records: int = 0
    filtered_records: int = 0
    error: str | None = Field(None, max_length=8192)
    results: list[dict] = Field(default_factory=list)
    analysis: str | None = Field(None, max_length=16384)
    discovered_urls: list[dict] = Field(default_factory=list)
    quality_report: dict[str, Any] = Field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    cost_breakdown: dict[str, Any] = Field(
        default_factory=dict, description="Per-job cost breakdown: cpu, browser, bandwidth, proxy costs"
    )
    total_llm_calls: int = 0
    logs: list[LogEntry] = Field(default_factory=list)
    progress_current: int = 0
    progress_total: int = 0
    results_on_disk: bool = Field(default=False, description="Whether results are stored in a compressed disk file")
    results_file_path: str | None = Field(default=None, description="Path to the compressed results file", max_length=1024)
    warnings: list[str] = Field(default_factory=list, description="Job warning logs and anomaly reports")
    cascade_telemetry: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-URL cascade layer telemetry: {url: {layer, score, duration_ms, quality_score}}",
    )
    quality_score_summary: float = Field(
        default=0.0,
        description="Aggregate quality score across all records (0-1)",
        ge=0.0,
        le=1.0,
    )
    acquisition_mode: str = Field(
        default="standard", description="Acquisition mode: standard, aggressive, or deep_scan", max_length=16
    )
    headers: dict[str, str] = Field(default_factory=dict, description="Custom HTTP headers to send with requests")
    cookies: dict[str, str] = Field(default_factory=dict, description="Custom cookies to inject into requests/browser contexts")
    webhook_url: str | None = Field(
        default=None,
        description="URL to POST job-completion webhook to",
        max_length=2048,
    )
    webhook_secret: str | None = Field(
        default=None,
        description="HMAC-SHA256 secret for signing webhook payloads",
        max_length=128,
    )
    webhook_delivered: bool = Field(default=False, description="Whether the job-completion webhook was delivered")
    webhook_delivered_at: str | None = Field(
        default=None, description="ISO timestamp when webhook was last delivered", max_length=64
    )
    hydration_wait_ms: int | None = Field(
        default=None,
        ge=0,
        le=120_000,
        description="User-overridable post-navigation hydration wait (milliseconds). None = use platform default.",
    )
    scroll_attempts: int | None = Field(
        default=None,
        ge=0,
        le=20,
        description="User-overridable number of scroll attempts before content extraction. None = use platform default.",
    )
    request_delay_ms: int = Field(
        default=0,
        ge=0,
        le=60_000,
        description="Per-job delay between consecutive URL fetches (milliseconds). 0 = no delay (use platform throttle).",
    )
    max_concurrent_urls: int = Field(
        default=4,
        ge=1,
        le=20,
        description="Maximum number of URLs that can be fetched concurrently within this job.",
    )
    fetch_strategy: str = Field(
        default="",
        description="User-requested fetch strategy. Empty means auto-select.",
        max_length=32,
    )
    user_agent: str = Field(
        default="",
        description="Custom User-Agent string for this job. Empty means use platform default.",
        max_length=512,
    )
    # JS wait condition overrides (Roadmap Wave 5, Item 3)
    wait_for_selector: str | None = Field(
        default=None,
        description="CSS selector to wait for before extraction. None = no custom selector wait.",
        max_length=500,
    )
    wait_for_function: str | None = Field(
        default=None,
        description=("JavaScript expression that must evaluate to truthy before extraction. None = no custom function wait."),
        max_length=2048,
    )
    wait_for_timeout: int | None = Field(
        default=None,
        ge=0,
        le=120_000,
        description=(
            "Explicit timeout (ms) to wait after navigation before extraction. None = use platform default hydration logic."
        ),
    )
    wait_for_navigation: bool | None = Field(
        default=None,
        description=(
            "If true, wait for a page navigation event after the initial load "
            "(useful for JS redirects). None = platform default (no extra wait)."
        ),
    )


class JobHeadersUpdate(BaseModel):
    """Request body to update job headers and cookies."""

    model_config = ConfigDict(extra="forbid")
    headers: dict[str, str] = Field(default_factory=dict, description="Custom HTTP headers to send with requests")
    cookies: dict[str, str] = Field(default_factory=dict, description="Custom cookies to inject into requests/browser contexts")

    @model_validator(mode="after")
    def validate_limits(self):
        if self.headers:
            if len(self.headers) > 50:
                msg = "headers must have at most 50 keys"
                raise ValueError(msg)
            for k, v in self.headers.items():
                if not isinstance(k, str) or len(k) > 100:
                    msg = f"headers key '{k}' exceeds max length of 100"
                    raise ValueError(msg)
                if not isinstance(v, str) or len(v) > 2000:
                    msg = f"headers value for '{k}' exceeds max length of 2000"
                    raise ValueError(msg)

        if self.cookies:
            if len(self.cookies) > 50:
                msg = "cookies must have at most 50 keys"
                raise ValueError(msg)
            for k, v in self.cookies.items():
                if not isinstance(k, str) or len(k) > 100:
                    msg = f"cookies key '{k}' exceeds max length of 100"
                    raise ValueError(msg)
                if not isinstance(v, str) or len(v) > 4096:
                    msg = f"cookies value for '{k}' exceeds max length of 4096"
                    raise ValueError(msg)
        return self


class JobWebhookUpdate(BaseModel):
    """Request body to update job webhook configuration."""

    model_config = ConfigDict(extra="forbid")

    webhook_url: str | None = Field(
        default=None,
        description="URL to POST job-completion webhook to. Set to null to remove.",
        max_length=2048,
    )
    webhook_secret: str | None = Field(
        default=None,
        description="HMAC-SHA256 secret for signing webhook payloads. Set to null to remove signing.",
        max_length=128,
    )

    @model_validator(mode="after")
    def validate_webhook_url(self):
        if self.webhook_url:
            stripped = self.webhook_url.strip()
            if not stripped.startswith(("https://", "http://")):
                msg = "webhook_url must start with https:// or http://"
                raise ValueError(msg)
            # SSRF defense at model level
            try:
                from app.url_safety import validate_public_http_url

                validate_public_http_url(stripped)
            except ValueError as exc:
                msg = f"webhook_url failed security check: {exc}"
                raise ValueError(msg) from exc
            self.webhook_url = stripped
        return self


class JobWaitConditionsUpdate(BaseModel):
    """Request body to update per-job JS wait condition configuration.

    All fields are optional; absent fields leave existing values unchanged.
    Set a field to ``null`` to clear it (restore platform default behaviour).
    """

    model_config = ConfigDict(extra="forbid")
    wait_for_selector: str | None = Field(
        default=None,
        description="CSS selector to wait for before extraction. None = no custom selector wait.",
        max_length=500,
    )
    wait_for_function: str | None = Field(
        default=None,
        description=("JavaScript expression that must evaluate to truthy before extraction. None = no custom function wait."),
        max_length=2048,
    )
    wait_for_timeout: int | None = Field(
        default=None,
        ge=0,
        le=120_000,
        description=(
            "Explicit timeout (ms) to wait after navigation before extraction. None = use platform default hydration logic."
        ),
    )
    wait_for_navigation: bool | None = Field(
        default=None,
        description=(
            "If true, wait for a page navigation event after the initial load "
            "(useful for JS redirects). None = platform default (no extra wait)."
        ),
    )


class JobStrategyUpdate(BaseModel):
    """Request body to update a job's fetch strategy."""

    model_config = ConfigDict(extra="forbid")
    fetch_strategy: str = Field(
        ...,
        description="Fetch strategy to use (playwright_full, httpx_smart, hybrid, etc.). Empty string resets to auto-select.",
        max_length=32,
    )

    @model_validator(mode="after")
    def validate_fetch_strategy(self):
        if self.fetch_strategy:
            from app.strategy_evolution import FETCH_STRATEGY_VALUES

            if self.fetch_strategy not in FETCH_STRATEGY_VALUES:
                msg = f"fetch_strategy must be one of {sorted(FETCH_STRATEGY_VALUES)}, got {self.fetch_strategy!r}"
                raise ValueError(msg)
        return self


class FetchStrategyUpdate(BaseModel):
    """Request body to update a job's fetch strategy (Literal-strained variant).

    Accepts the same values as ``JobStrategyUpdate`` but uses a
    ``Literal`` type so OpenAPI documentation and client code generators
    can enumerate the valid strategies without inspecting the
    ``strategy_evolution`` module at runtime.
    """

    model_config = ConfigDict(extra="forbid")
    strategy: Literal[
        "playwright_full",
        "playwright_lightweight",
        "playwright_stealth",
        "httpx_basic",
        "httpx_with_ua",
        "httpx_smart",
        "hybrid",
        "cached",
    ] = Field(
        ...,
        description="Fetch strategy to use. The empty-string reset supported by "
        "JobStrategyUpdate is not available via this model — callers that "
        "need auto-select should use ``PATCH /api/jobs/{id}/strategy`` with "
        '``fetch_strategy: ""``.',
    )


class JobExtractionUpdate(BaseModel):
    """Request body to update per-job extraction behaviour flags.

    All fields are optional; absent or ``null`` fields leave the existing value intact
    (or restore the platform default when the field is ``null``).  This lets callers

    model_config = ConfigDict(extra="forbid")
    PATCH a single knob without having to re-send the entire job config.
    """

    hydration_wait_ms: int | None = Field(
        default=None,
        ge=0,
        le=120_000,
        description=(
            "Override post-navigation hydration wait (ms). Set to 0 for a fast page-load "
            "exit; set to a positive value to wait longer for JavaScript hydration."
        ),
    )
    scroll_attempts: int | None = Field(
        default=None,
        ge=0,
        le=20,
        description=(
            "Override the number of auto-scroll attempts before capturing page content. Set to 0 to disable scrolling entirely."
        ),
    )
    max_pages: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Override the maximum number of pages to follow when pagination is enabled.",
    )
    request_delay_ms: int | None = Field(
        default=None,
        ge=0,
        le=60_000,
        description=("Override the minimum delay between consecutive URL fetches (milliseconds). 0 means no extra delay."),
    )
    max_concurrent_urls: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Override the maximum concurrent URLs within this job.",
    )
    selectors_map: dict | None = Field(
        default=None,
        description=(
            "Override CSS selectors map for extraction. Shape: ``{item_container: str, fields: {field_name: selector}}``."
        ),
    )

    @model_validator(mode="after")
    def validate_selectors_map_shape(self) -> "JobExtractionUpdate":
        if self.selectors_map is None:
            return self
        if not isinstance(self.selectors_map, dict):
            msg = "selectors_map must be an object"
            raise TypeError(msg)
        if len(self.selectors_map) > 20:
            msg = "selectors_map must have at most 20 keys"
            raise ValueError(msg)
        # Validate value shapes to keep the dict clean before persistence.
        item_container = self.selectors_map.get("item_container")
        if item_container is not None and (not isinstance(item_container, str) or len(item_container) > 500):
            msg = "selectors_map.item_container must be a string of at most 500 chars"
            raise ValueError(msg)
        fields = self.selectors_map.get("fields")
        if fields is not None:
            if not isinstance(fields, dict) or len(fields) > 30:
                msg = "selectors_map.fields must be an object with at most 30 keys"
                raise ValueError(msg)
            for k, v in fields.items():
                if not isinstance(k, str) or len(k) > 64:
                    msg = "selectors_map.fields keys must be strings of at most 64 chars"
                    raise ValueError(msg)
                if not isinstance(v, str) or len(v) > 500:
                    msg = f"selectors_map.fields[{k}] must be a string of at most 500 chars"
                    raise ValueError(msg)
        return self


class JobUserAgentUpdate(BaseModel):
    """Request body to update a job's custom User-Agent string."""

    model_config = ConfigDict(extra="forbid")
    user_agent: str = Field(
        default="",
        description="Custom User-Agent string. Empty string resets to platform default.",
        max_length=512,
    )


class JobExtractionUpdateResponse(BaseModel):
    """Response model for PATCH /api/jobs/{job_id}/extraction."""

    status: str
    job_id: str
    hydration_wait_ms: int | None
    scroll_attempts: int | None
    max_pages: int | None
    selectors_map: dict[str, Any]
    request_delay_ms: int
    max_concurrent_urls: int


class JobCreateResponse(BaseModel):
    """Response model for POST /api/jobs."""

    id: str
    job_id: str
    status: str
    idempotent_replay: bool


class ClearTerminalResponse(BaseModel):
    """Response model for DELETE /api/jobs/cleanup/terminal."""

    message: str
    cleared: int
    kept_recent: int
    remaining: int
    failed: list[str] | None = None


class JobResultsResponse(BaseModel):
    """Response model for GET /api/jobs/{job_id}/results."""

    job_id: str
    results: list[Any]
    total: int
    limit: int
    offset: int
    next_offset: int | None = None
    returned: int


class JobEventsResponse(BaseModel):
    """Response model for GET /api/jobs/{job_id}/events."""

    job_id: str
    status: str
    events: list[Any]
    total: int
    limit: int
    offset: int
    next_offset: int | None = None


class JobQualityResponse(BaseModel):
    """Response model for GET /api/jobs/{job_id}/quality."""

    job_id: str
    overall_quality: float
    record_count: int
    offset: int
    limit: int
    next_offset: int | None = None
    records: list[Any]


class JobQualityTrendsResponse(BaseModel):
    """Response model for GET /api/jobs/{job_id}/quality/trends."""

    job_id: str
    domain: str
    schema_hash: str
    summary: dict[str, Any]
    samples: list[Any]
    alert_threshold: float


class JobCloneRequest(BaseModel):
    """Request body to clone a job."""

    name: str | None = Field(default=None, max_length=255, description="Name for the cloned job")
    urls: list[str] | None = Field(default=None, description="Override URLs for the cloned job")


class BatchSubmitRequest(BaseModel):
    """Request body to submit multiple URLs as a single batch."""

    urls: list[str] = Field(..., max_length=1000, description="List of URLs to scrape")
    name: str = Field("batch", max_length=255)
    schema_fields: list[SchemaField] = Field(default_factory=list, max_length=50)
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: dict[str, str] = Field(default_factory=dict)


class BatchSubmitResponse(BaseModel):
    """Response for batch URL submission."""

    jobs: list[dict[str, Any]]
    batch_id: str
    total_urls: int
    message: str


class EmailDeliveryRequest(BaseModel):
    """Request body to email job results."""

    recipients: list[str] = Field(..., max_length=10, description="Email recipients")
    format: str = Field("csv", max_length=16, description="Export format (csv, json)")
    subject: str | None = Field(default=None, max_length=255)


class UsageRecord(BaseModel):
    """Request body for recording usage events (Feat 30)."""

    api_key: str = Field(default="", max_length=128, description="API key identifier")
    requests: int = Field(default=1, ge=0, description="Number of requests to record")
    records: int = Field(default=0, ge=0, description="Number of records extracted")
    failures: int = Field(default=0, ge=0, description="Number of failures")
    latency_ms: int = Field(default=0, ge=0, description="Maximum latency in milliseconds")


class DeleteMyDataResponse(BaseModel):
    """Response model for DELETE /api/user/data."""

    status: str
    user_id: str
    summary: dict[str, int]
    message: str
    receipt: dict[str, str]
