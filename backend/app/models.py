"""Pydantic models for the scraper API.

Defines the data structures for jobs, schemas, filters, and results.
"""

import datetime
import re
import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Field names reserved for system / metadata use — cannot be used as schema field names
# These are internal fields injected by the extraction pipeline at runtime
RESERVED_FIELD_NAMES: frozenset = frozenset(
    {
        "_provenance",
        "_extraction_method",
        "_ai_source_structured",
        "_calibrated_confidence",
        "_acquisition_lineage",
        "source_url",
        "source_type",
        "source_trust_score",
        "scraped_at",
        "record_score",
        "_source_url",
        "_field_provenance",
        "_zero_result_failure",
        "_element_text",
        "_record_id",
    },
)


class FieldType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    EMAIL = "email"
    URL = "url"
    PHONE = "phone"
    LOCATION = "location"
    DATE = "date"
    LIST_STRING = "list_string"
    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    CODE = "code"
    RATING = "rating"
    NUMBER = "number"


class FilterOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IN_LIST = "in_list"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    MATCHES_REGEX = "matches_regex"
    DISTANCE_WITHIN = "distance_within"


class ScrapeMode(StrEnum):
    MANUAL = "manual"  # User provides URLs
    AUTO = "auto"  # AI discovers best URLs


class SourcePolicy(StrEnum):
    OFFICIAL_ONLY = "official_only"
    OFFICIAL_PLUS_DIRECTORY = "official_plus_directory"
    ALL_SOURCES = "all_sources"


class SchemaField(BaseModel):
    """A single field definition in the extraction schema."""

    name: str = Field(..., description="Field name, e.g. 'company_name'", max_length=64)
    field_type: FieldType = Field(..., description="Data type for this field")
    description: str = Field("", description="Optional hint for the LLM about what this field is")
    required: bool = Field(True, description="Whether this field is required")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", v):
            msg = "Field name must be snake_case, start with a letter, and be at most 64 characters"
            raise ValueError(msg)
        if v in RESERVED_FIELD_NAMES:
            msg = f"Field name '{v}' is reserved for system use"
            raise ValueError(msg)
        return v


class FilterRule(BaseModel):
    """A single filter rule to apply to scraped data."""

    field_name: str = Field(..., description="Which schema field to filter on")
    operator: FilterOperator = Field(..., description="Filter operator")
    value: str = Field("", description="Value to compare against")
    origin_address: str | None = Field(None, description="Origin address for distance calculation")
    distance_unit: str | None = Field("km", description="km or miles")


class DiscoveryRequest(BaseModel):
    """Request body for auto-discovery mode."""

    topic: str = Field(..., description="What topic / data to search for")
    location: str = Field("", description="Geographic focus, e.g. 'New York, USA'")
    domain: str = Field("", description="Preferred domain to search, e.g. 'example.com'")
    num_results: int = Field(8, ge=1, le=50, description="How many URLs to discover")
    max_per_domain: int = Field(4, ge=1, le=25, description="Maximum URLs allowed per domain in discovery")
    source_policy: SourcePolicy = Field(SourcePolicy.ALL_SOURCES, description="Source inclusion policy for discovery")
    schema_field_names: list[str] = Field(
        default_factory=list,
        description="Optional schema field names to improve search relevance",
    )
    origin_location: str = Field("", description="Center point for radius-aware optimization")
    max_distance_km: float | None = Field(None, ge=0, description="Optional discovery radius in kilometers")


class SchemaSuggestionRequest(BaseModel):
    """Request body to infer topic and schema fields from plain language."""

    intent: str = Field(..., description="Natural language description of what data to scrape")
    max_fields: int = Field(8, ge=1, le=20, description="Maximum number of fields to generate")


class SelectorMap(BaseModel):
    """Validated selector map produced by URL analysis."""

    item_container: str = Field("", max_length=500)
    fields: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_fields(self):
        if len(self.fields) > 50:
            msg = "selectors_map.fields must have at most 50 entries"
            raise ValueError(msg)
        for name, selector in self.fields.items():
            if not isinstance(name, str) or not name.strip():
                msg = "selectors_map.fields keys must be non-empty strings"
                raise ValueError(msg)
            if not isinstance(selector, str) or len(selector) > 500:
                msg = "selectors_map field selectors must be strings up to 500 characters"
                raise ValueError(msg)
        return self


class ScraperDiagnosticsRequest(BaseModel):
    """Request body for the scraper diagnostics endpoint.

    Replaces the broken inline ``fields: list[SchemaField]`` signature
    that caused PydanticUserError in OpenAPI generation.
    """

    url: str = Field(..., description="The URL to run diagnostics on")
    fields: list[SchemaField] = Field(..., description="Schema fields to attempt extraction for", max_length=50)
    min_score: float = Field(0.3, ge=0.0, le=1.0, description="Minimum quality score for records to be included")


class JobCreate(BaseModel):
    """Request body to create a new scraping job."""

    name: str = Field(..., description="Human-readable job name")
    mode: ScrapeMode = Field(ScrapeMode.MANUAL, description="Manual or Auto discovery mode")
    intent: str = Field("", description="Natural language extraction intent")
    # Manual mode
    urls: list[str] = Field(default_factory=list, max_length=100, description="List of URLs to scrape (manual mode)")
    # Auto mode
    topic: str = Field("", description="Topic for auto-discovery")
    location: str = Field("", description="Location focus for auto-discovery")
    preferred_domain: str = Field("", description="Preferred domain for auto-discovery")
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
    deduplicate_field: str = Field("", description="Field to use for deduplication")
    # Selectors map from URL analysis (item_container + field selectors)
    selectors_map: dict[str, Any] = Field(default_factory=dict, description="Pre-discovered CSS selectors map from URL analysis")
    search_params: dict[str, str] | None = Field(default=None, description="Search parameters for session-bound URL recovery")
    min_record_score: float = Field(0.35, ge=0.0, le=1.0, description="Minimum quality score required per extracted record")
    auth_profile_id: str | None = Field(default=None, description="Optional auth profile ID to use for authenticated scraping")

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
                    msg = f"URL '{u}' failed security check: {e}"
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

        return self


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

    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())
    message: str
    level: str = "info"


class Job(BaseModel):
    """A scraping job with its current state."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    mode: ScrapeMode = ScrapeMode.MANUAL
    intent: str = ""
    urls: list[str] = Field(default_factory=list)
    topic: str = ""
    location: str = ""
    preferred_domain: str = ""
    source_policy: SourcePolicy = SourcePolicy.ALL_SOURCES
    max_per_domain: int = 4
    origin_location: str = ""
    max_distance_km: float | None = None
    schema_fields: list[SchemaField] = Field(default_factory=list)
    filters: list[FilterRule] = Field(default_factory=list)
    pagination: bool = False
    max_pages: int = 10
    deduplicate: bool = True
    deduplicate_field: str = ""
    min_record_score: float = 0.35
    # Selectors map from URL analysis (pre-discovered CSS selectors)
    selectors_map: dict[str, Any] = Field(default_factory=dict, description="Pre-discovered CSS selectors map from URL analysis")
    search_params: dict[str, str] | None = Field(default=None, description="Search parameters for session-bound URL recovery")
    cancel_requested: bool = False
    status: JobStatus = JobStatus.PENDING
    created_by: str = Field(default="", description="Owner identity (user ID or API key fingerprint) for data isolation")
    org_id: str = Field(default="", description="Tenant org id; populated for persistent API keys (P0-SAAS-001)")
    project_id: str = Field(default="", description="Project id; populated for persistent API keys (P0-SAAS-001)")
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    total_records: int = 0
    filtered_records: int = 0
    error: str | None = None
    results: list[dict] = Field(default_factory=list)
    analysis: str | None = None
    discovered_urls: list[dict] = Field(default_factory=list)
    quality_report: dict[str, Any] = Field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    total_llm_calls: int = 0
    logs: list[LogEntry] = Field(default_factory=list)
    progress_current: int = 0
    progress_total: int = 0
    results_on_disk: bool = Field(default=False, description="Whether results are stored in a compressed disk file")
    results_file_path: str | None = Field(default=None, description="Path to the compressed results file")
    warnings: list[str] = Field(default_factory=list, description="Job warning logs and anomaly reports")
    acquisition_mode: str = Field(default="standard", description="Acquisition mode: standard, aggressive, or deep_scan")


# ─── Workflow System ──────────────────────────────────────────────────────


class WorkflowStatus(StrEnum):
    """Status of a saved workflow."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    FAILED = "failed"
    ARCHIVED = "archived"
    DISABLED = "disabled"


class WorkflowStepType(StrEnum):
    """Type of action in a workflow step."""

    GOTO = "goto"
    OPEN = "goto"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    CHECK = "check"
    UNCHECK = "uncheck"
    PRESS = "press"
    SCROLL = "scroll"
    WAIT = "wait_for_timeout_limited"
    WAIT_FOR_URL = "wait_for_url"
    WAIT_FOR_SELECTOR = "wait_for_selector"
    WAIT_FOR_TEXT = "wait_for_text"
    WAIT_FOR_TIMEOUT_LIMITED = "wait_for_timeout_limited"
    EXTRACT = "extract"


class WorkflowStep(BaseModel):
    """A single step in a scraping workflow."""

    step_type: WorkflowStepType = Field(..., description="Action type for this step")
    selector: str = Field("", description="CSS or XPath selector for the target element", max_length=500)
    value: str = Field("", description="Value to fill in or select", max_length=500)
    description: str = Field("", description="Human-readable description of this step", max_length=255)
    order: int = Field(0, ge=0, description="Execution order within the workflow")

    @field_validator("selector")
    @classmethod
    def validate_selector(cls, v: str) -> str:
        if v and len(v) > 500:
            msg = "Selector must be at most 500 characters"
            raise ValueError(msg)
        return v


class WorkflowPaginationConfig(BaseModel):
    """Pagination configuration for a workflow."""

    enabled: bool = Field(False, description="Whether pagination is enabled")
    strategy: Literal[
        "next_button",
        "page_number",
        "url_pattern",
        "infinite_scroll",
        "load_more",
    ] = Field(
        "next_button",
        description="Pagination strategy: next_button, page_number, url_pattern, infinite_scroll, load_more",
    )
    max_pages: int = Field(10, ge=1, le=100, description="Maximum pages to follow")
    stop_condition: str = Field("none", description="Stop condition: none, no_more_records, duplicate_threshold, custom")
    selector: str = Field("", description="Selector for next button or page links", max_length=500)


class Workflow(BaseModel):
    """A saved scraping workflow that can be replayed."""

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Human-readable workflow name", max_length=255)
    description: str = Field("", description="Optional workflow description", max_length=1000)

    # Ownership
    user_id: str = Field(default="", description="Creator user ID")
    org_id: str = Field(default="", description="Organization ID for multi-tenant isolation")
    project_id: str = Field(default="", description="Project ID for grouping")

    # Target
    mode: str = Field(default="workflow_replay", description="Workflow execution mode", max_length=64)
    domain: str = Field(default="", description="Target domain for this workflow", max_length=255)
    start_url: str = Field(default="", description="Starting URL for replay", max_length=2048)
    original_url: str = Field(default="", description="Original URL that inspired this workflow", max_length=2048)

    # Workflow definition
    search_params: dict[str, str] = Field(default_factory=dict, description="Search parameters for form submission")
    steps: list[WorkflowStep] = Field(default_factory=list, description="Ordered list of workflow steps")
    extraction_schema: list[SchemaField] = Field(default_factory=list, description="Fields to extract after replay")
    auth_profile_id: str | None = Field(default=None, description="Optional auth profile for authenticated scraping")
    pagination_config: WorkflowPaginationConfig = Field(
        default_factory=WorkflowPaginationConfig,
        description="Pagination settings",
    )

    # Status
    status: WorkflowStatus = Field(default=WorkflowStatus.DRAFT, description="Current workflow status")
    version: int = Field(1, ge=1, description="Workflow version for change tracking")

    # Timestamps
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())
    last_run_at: str | None = Field(default=None, description="When this workflow was last executed")
    last_success_at: str | None = Field(default=None, description="When this workflow last completed successfully")
    last_failure_reason: str | None = Field(default=None, description="Last workflow failure reason")
    last_run_job_id: str | None = Field(default=None, description="ID of the last job created from this workflow")

    # Statistics
    total_runs: int = Field(0, ge=0, description="Total number of times this workflow has been run")
    success_runs: int = Field(0, ge=0, description="Number of successful executions")

    @model_validator(mode="after")
    def validate_workflow(self):
        if len(self.steps) > 100:
            msg = "Workflow cannot have more than 100 steps"
            raise ValueError(msg)
        if len(self.search_params) > 50:
            msg = "search_params cannot have more than 50 keys"
            raise ValueError(msg)
        return self


class WorkflowCreate(BaseModel):
    """Request body to create a new workflow."""

    name: str = Field(..., description="Human-readable workflow name", max_length=255)
    description: str = Field("", max_length=1000)
    mode: str = Field(default="workflow_replay", max_length=64)
    start_url: str = Field(default="", max_length=2048)
    original_url: str = Field(default="", max_length=2048)
    search_params: dict[str, str] = Field(default_factory=dict)
    steps: list[WorkflowStep] = Field(default_factory=list)
    extraction_schema: list[SchemaField] = Field(default_factory=list)
    auth_profile_id: str | None = Field(default=None, description="Optional auth profile for authenticated scraping")
    pagination_config: WorkflowPaginationConfig = Field(default_factory=WorkflowPaginationConfig)

    @model_validator(mode="after")
    def validate_create(self):
        if not self.name or not self.name.strip():
            msg = "Workflow name is required"
            raise ValueError(msg)
        if len(self.steps) > 100:
            msg = "Workflow cannot have more than 100 steps"
            raise ValueError(msg)
        if len(self.search_params) > 50:
            msg = "search_params cannot have more than 50 keys"
            raise ValueError(msg)
        return self


class WorkflowUpdate(BaseModel):
    """Request body to update an existing workflow."""

    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    mode: str | None = Field(default=None, max_length=64)
    start_url: str | None = Field(default=None, max_length=2048)
    original_url: str | None = Field(default=None, max_length=2048)
    search_params: dict[str, str] | None = Field(default=None)
    steps: list[WorkflowStep] | None = Field(default=None)
    extraction_schema: list[SchemaField] | None = Field(default=None)
    pagination_config: WorkflowPaginationConfig | None = Field(default=None)
    status: WorkflowStatus | None = Field(default=None)


# ─── Auth Profiles ────────────────────────────────────────────────────────


class AuthProfileStatus(StrEnum):
    """Status of an auth profile."""

    PENDING_LOGIN = "pending_login"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    FAILED = "failed"


class AuthProfile(BaseModel):
    """Stored browser session for authenticated scraping.

    Encrypted ``storage_state`` is never exposed in API responses;
    it is only decrypted inside the job runner when needed.
    """

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Human-readable profile name", max_length=255)
    description: str = Field("", max_length=1000)

    # Ownership
    user_id: str = Field(default="", description="Owner user ID")
    org_id: str = Field(default="", description="Organization ID")
    project_id: str = Field(default="", description="Project ID")

    # Target domain (enforced to prevent cross-domain leakage)
    domain: str = Field(..., description="Domain this auth profile is restricted to", max_length=255)

    # Session state (opaque to the API; encrypted at rest)
    encrypted_storage_state: str = Field(
        "",
        description="Base64-encoded encrypted Playwright storage state",
        max_length=100000,
    )
    encryption_key_version: str = Field("", description="Version of the encryption key used")

    # Status
    status: AuthProfileStatus = AuthProfileStatus.PENDING_LOGIN
    failure_reason: str = Field("", max_length=1000, description="Reason for failure if applicable")

    # Timestamps
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())
    expires_at: str | None = Field(default=None, description="Optional expiration timestamp (ISO 8601)")
    last_validated_at: str | None = None

    # Statistics
    last_used_at: str | None = None
    usage_count: int = Field(0, ge=0)


# ─── Scheduled Monitoring ────────────────────────────────────────────────


class ScheduledJobFrequency(StrEnum):
    """How often a scheduled job should run."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ScheduledJob(BaseModel):
    """A recurring scraping job that runs on a schedule.

    Each scheduled job is linked to a base job template. When the
    schedule fires, a new job is created from the template and
    queued for execution.
    """

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Human-readable schedule name", max_length=255)

    # Ownership
    user_id: str = Field(default="", description="Owner user ID")
    org_id: str = Field(default="", description="Organization ID")
    project_id: str = Field(default="", description="Project ID")

    # Scheduling
    frequency: ScheduledJobFrequency = Field(default=ScheduledJobFrequency.DAILY)
    cron_expression: str = Field("", description="Optional custom cron expression", max_length=100)
    timezone: str = Field("UTC", max_length=50)
    next_run_at: str | None = Field(default=None, description="ISO 8601 timestamp of next scheduled execution")
    last_run_at: str | None = None

    # Job template (snapshot of a JobCreate payload)
    job_name: str = Field(..., description="Name pattern for generated jobs", max_length=255)
    mode: ScrapeMode = Field(ScrapeMode.MANUAL)
    urls: list[str] = Field(default_factory=list)
    topic: str = Field("", max_length=255)
    location: str = Field("", max_length=255)
    schema_fields: list[SchemaField] = Field(default_factory=list)
    filters: list[FilterRule] = Field(default_factory=list)
    pagination: bool = False
    max_pages: int = 10
    deduplicate: bool = True
    min_record_score: float = 0.35

    # Status
    enabled: bool = True
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())

    # Statistics
    total_executions: int = Field(0, ge=0)
    successful_executions: int = Field(0, ge=0)
