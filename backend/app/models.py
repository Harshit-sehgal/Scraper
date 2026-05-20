"""
Pydantic models for the scraper API.
Defines the data structures for jobs, schemas, filters, and results.
"""

import datetime
import uuid
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator


class FieldType(str, Enum):
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


class FilterOperator(str, Enum):
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


class ScrapeMode(str, Enum):
    MANUAL = "manual"       # User provides URLs
    AUTO = "auto"           # AI discovers best URLs


class SourcePolicy(str, Enum):
    OFFICIAL_ONLY = "official_only"
    OFFICIAL_PLUS_DIRECTORY = "official_plus_directory"
    ALL_SOURCES = "all_sources"


class SchemaField(BaseModel):
    """A single field definition in the extraction schema."""
    name: str = Field(..., description="Field name, e.g. 'company_name'")
    field_type: FieldType = Field(..., description="Data type for this field")
    description: str = Field("", description="Optional hint for the LLM about what this field is")
    required: bool = Field(True, description="Whether this field is required")


class FilterRule(BaseModel):
    """A single filter rule to apply to scraped data."""
    field_name: str = Field(..., description="Which schema field to filter on")
    operator: FilterOperator = Field(..., description="Filter operator")
    value: str = Field("", description="Value to compare against")
    origin_address: Optional[str] = Field(None, description="Origin address for distance calculation")
    distance_unit: Optional[str] = Field("km", description="km or miles")


class DiscoveryRequest(BaseModel):
    """Request body for auto-discovery mode."""
    topic: str = Field(..., description="What topic/data to search for")
    location: str = Field("", description="Geographic focus, e.g. 'Chennai, India'")
    domain: str = Field("", description="Preferred domain to search, e.g. 'justdial.com'")
    num_results: int = Field(8, ge=1, le=50, description="How many URLs to discover")
    max_per_domain: int = Field(4, ge=1, le=25, description="Maximum URLs allowed per domain in discovery")
    source_policy: SourcePolicy = Field(SourcePolicy.ALL_SOURCES, description="Source inclusion policy for discovery")
    schema_field_names: list[str] = Field(default_factory=list, description="Optional schema field names to improve search relevance")
    origin_location: str = Field("", description="Center point for radius-aware optimization")
    max_distance_km: Optional[float] = Field(None, ge=0, description="Optional discovery radius in kilometers")


class SchemaSuggestionRequest(BaseModel):
    """Request body to infer topic and schema fields from plain language."""
    intent: str = Field(..., description="Natural language description of what data to scrape")
    max_fields: int = Field(8, ge=1, le=20, description="Maximum number of fields to generate")


class JobCreate(BaseModel):
    """Request body to create a new scraping job."""
    name: str = Field(..., description="Human-readable job name")
    mode: ScrapeMode = Field(ScrapeMode.MANUAL, description="Manual or Auto discovery mode")
    intent: str = Field("", description="Natural language extraction intent")
    # Manual mode
    urls: list[str] = Field(default_factory=list, description="List of URLs to scrape (manual mode)")
    # Auto mode
    topic: str = Field("", description="Topic for auto-discovery")
    location: str = Field("", description="Location focus for auto-discovery")
    preferred_domain: str = Field("", description="Preferred domain for auto-discovery")
    source_policy: SourcePolicy = Field(SourcePolicy.ALL_SOURCES, description="Controls which source types are included")
    max_per_domain: int = Field(4, ge=1, le=25, description="Maximum discovered URLs per domain")
    origin_location: str = Field("", description="Center location for distance optimization")
    max_distance_km: Optional[float] = Field(None, ge=0, description="Keep records within this radius in km")
    # Schema & Filters
    schema_fields: list[SchemaField] = Field(default_factory=list, description="Data schema to extract")
    filters: list[FilterRule] = Field(default_factory=list, description="Post-processing filters")
    # Advanced options
    pagination: bool = Field(False, description="Whether to follow pagination links")
    max_pages: int = Field(10, ge=1, description="Max pages to follow per URL")
    deduplicate: bool = Field(True, description="Remove duplicate records")
    deduplicate_field: str = Field("", description="Field to use for deduplication")
    min_record_score: float = Field(0.35, ge=0.0, le=1.0, description="Minimum quality score required per extracted record")

    @model_validator(mode="after")
    def validate_mode_requirements(self):
        if self.mode == ScrapeMode.MANUAL:
            cleaned_urls = [u.strip() for u in self.urls if str(u or "").strip()]
            if not cleaned_urls:
                raise ValueError("Manual mode requires at least one URL")
            invalid_urls = [
                u
                for u in cleaned_urls
                if urlparse(u).scheme not in {"http", "https"} or not urlparse(u).netloc
            ]
            if invalid_urls:
                raise ValueError("Manual mode requires valid http(s) URLs")
            self.urls = cleaned_urls

        if self.mode == ScrapeMode.AUTO:
            self.topic = self.topic.strip()
            if not self.topic:
                raise ValueError("Auto mode requires a non-empty topic")
            # Auto mode always discovers URLs itself.
            self.urls = []
        return self


class JobStatus(str, Enum):
    PENDING = "pending"
    DISCOVERING = "discovering"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"


class LogEntry(BaseModel):
    """A single log entry for a job."""
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
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
    max_distance_km: Optional[float] = None
    schema_fields: list[SchemaField] = Field(default_factory=list)
    filters: list[FilterRule] = Field(default_factory=list)
    pagination: bool = False
    max_pages: int = 10
    deduplicate: bool = True
    deduplicate_field: str = ""
    min_record_score: float = 0.35
    cancel_requested: bool = False
    status: JobStatus = JobStatus.PENDING
    created_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_records: int = 0
    filtered_records: int = 0
    error: Optional[str] = None
    results: list[dict] = Field(default_factory=list)
    analysis: Optional[str] = None
    discovered_urls: list[dict] = Field(default_factory=list)
    quality_report: dict = Field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    total_llm_calls: int = 0
    logs: list[LogEntry] = Field(default_factory=list)
    progress_current: int = 0
    progress_total: int = 0
    results_on_disk: bool = Field(default=False, description="Whether results are stored in a compressed disk file")
    results_file_path: Optional[str] = Field(default=None, description="Path to the compressed results file")

