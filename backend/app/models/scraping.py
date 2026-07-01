"""Shared types and constants used across model domains.

Contains field enums, filter definitions, discovery requests, and
reserved-field-name constants.  These are imported by the ``jobs``,
``workflow``, and ``auth`` sub-modules as well as by extraction code
throughout the codebase.
"""

import re
from enum import StrEnum

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
    description: str = Field("", description="Optional hint for the LLM about what this field is", max_length=1024)
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

    field_name: str = Field(..., description="Which schema field to filter on", max_length=64)
    operator: FilterOperator = Field(..., description="Filter operator")
    value: str = Field("", description="Value to compare against", max_length=2048)
    origin_address: str | None = Field(None, description="Origin address for distance calculation", max_length=512)
    distance_unit: str | None = Field("km", description="km or miles", max_length=10)


class DiscoveryRequest(BaseModel):
    """Request body for auto-discovery mode."""

    topic: str = Field(..., description="What topic / data to search for", max_length=512)
    location: str = Field("", description="Geographic focus, e.g. 'New York, USA'", max_length=256)
    domain: str = Field("", description="Preferred domain to search, e.g. 'example.com'", max_length=253)
    num_results: int = Field(8, ge=1, le=50, description="How many URLs to discover")
    max_per_domain: int = Field(4, ge=1, le=25, description="Maximum URLs allowed per domain in discovery")
    source_policy: SourcePolicy = Field(SourcePolicy.ALL_SOURCES, description="Source inclusion policy for discovery")
    schema_field_names: list[str] = Field(
        default_factory=list,
        description="Optional schema field names to improve search relevance",
    )
    origin_location: str = Field("", description="Center point for radius-aware optimization", max_length=256)
    max_distance_km: float | None = Field(None, ge=0, description="Optional discovery radius in kilometers")


class SchemaSuggestionRequest(BaseModel):
    """Request body to infer topic and schema fields from plain language."""

    intent: str = Field(..., description="Natural language description of what data to scrape", max_length=4096)
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

    url: str = Field(..., max_length=2048, description="The URL to run diagnostics on")
    fields: list[SchemaField] = Field(..., description="Schema fields to attempt extraction for", max_length=50)
    min_score: float = Field(0.3, ge=0.0, le=1.0, description="Minimum quality score for records to be included")
