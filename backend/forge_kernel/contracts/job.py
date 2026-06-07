"""Job domain contract — canonical model for scraping job lifecycle."""

from __future__ import annotations

import datetime
import re
import uuid
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

# Field names reserved for system / metadata use
RESERVED_FIELD_NAMES: frozenset = frozenset(
    {
        "_provenance",
        "_extraction_method",
        "_ai_source_structured",
        "source_url",
        "source_type",
        "source_trust_score",
        "scraped_at",
        "record_score",
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
    description: str = Field("", description="Optional hint about what this field is")
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

    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    message: str
    level: str = "info"


class Job(BaseModel):
    """A scraping job with its current lifecycle state."""

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
    selectors_map: dict = Field(default_factory=dict)
    search_params: dict[str, str] | None = Field(default=None)
    cancel_requested: bool = False
    status: JobStatus = JobStatus.PENDING
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    total_records: int = 0
    filtered_records: int = 0
    error: str | None = None
    results: list[dict] = Field(default_factory=list)
    analysis: str | None = None
    results_on_disk: bool = False
    results_file_path: str | None = None
    quality_report: dict = Field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    total_llm_calls: int = 0
    logs: list[LogEntry] = Field(default_factory=list)
    progress_current: int = 0
    progress_total: int = 0
    warnings: list[str] = Field(default_factory=list)
    acquisition_mode: str = "standard"


class CreateJobRequest(BaseModel):
    """Request body to create a new scraping job."""

    name: str = Field(..., description="Human-readable job name")
    mode: ScrapeMode = Field(ScrapeMode.MANUAL, description="Manual or Auto discovery mode")
    intent: str = Field("", description="Natural language extraction intent")
    urls: list[str] = Field(default_factory=list, max_length=100, description="URLs to scrape (manual mode)")
    topic: str = Field("", description="Topic for auto-discovery")
    location: str = Field("", description="Location focus for auto-discovery")
    preferred_domain: str = Field("", description="Preferred domain for auto-discovery")
    source_policy: SourcePolicy = Field(SourcePolicy.ALL_SOURCES)
    max_per_domain: int = Field(4, ge=1, le=25)
    origin_location: str = Field("")
    max_distance_km: float | None = Field(None, ge=0)
    schema_fields: list[SchemaField] = Field(default_factory=list, max_length=50)
    filters: list[FilterRule] = Field(default_factory=list, max_length=100)
    pagination: bool = False
    max_pages: int = Field(10, ge=1, le=100)
    deduplicate: bool = True
    deduplicate_field: str = ""
    selectors_map: dict = Field(default_factory=dict)
    search_params: dict[str, str] | None = Field(default=None)
    min_record_score: float = Field(0.35, ge=0.0, le=1.0)
