"""Auth profile and scheduled monitoring domain models.

Contains auth profiles, scheduled jobs, notification channels, and
extraction templates — all belonging to the auth/scheduling domain.
"""

import datetime
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.models.scraping import FilterRule, SchemaField, ScrapeMode

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
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=64)
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

    Scheduling can be specified via the ``frequency`` enum (HOURLY/
    DAILY/WEEKLY/MONTHLY) or via a standard cron expression
    (``cron_expression``).  When ``cron_expression`` is set it takes
    precedence over ``frequency``.
    """

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=64)
    name: str = Field(..., description="Human-readable schedule name", max_length=255)

    # Ownership
    user_id: str = Field(default="", description="Owner user ID", max_length=128)
    org_id: str = Field(default="", description="Organization ID", max_length=128)
    project_id: str = Field(default="", description="Project ID", max_length=128)

    # Scheduling
    frequency: ScheduledJobFrequency = Field(default=ScheduledJobFrequency.DAILY)
    cron_expression: str | None = Field(
        default=None,
        description=(
            "Standard 5-field cron expression (minute hour dom month dow). "
            "When set, takes precedence over ``frequency``. "
            "Example: ``0 9 * * 1-5`` for weekdays at 09:00 UTC."
        ),
        max_length=128,
    )
    timezone: str = Field(
        default="UTC",
        description="IANA timezone for cron scheduling (default UTC).",
        max_length=64,
    )
    last_run_at: str | None = Field(None, max_length=64)

    # Job template (snapshot of a JobCreate payload)
    job_name: str = Field(..., description="Name pattern for generated jobs", max_length=255)
    mode: ScrapeMode = Field(ScrapeMode.MANUAL)
    urls: list[str] = Field(default_factory=list, max_length=100, description="Target URLs for manual-mode jobs")
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
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat(), max_length=64)
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat(), max_length=64)

    # Statistics
    total_executions: int = Field(0, ge=0)
    successful_executions: int = Field(0, ge=0)


class ScheduledJobChangesResponse(BaseModel):
    """Response model for GET /api/scheduled/{job_id}/changes."""

    job_id: str
    job_name: str
    target_url: str
    frequency: str
    changes_detected: bool
    last_run_at: str
    last_status: str
    previous_status: str
    last_records_count: int
    previous_records_count: int
    record_count_delta: int
    status_changed: bool
    frequency_met: bool | None = None
    summary_count: int
    message: str


# ─── Notification Channels ────────────────────────────────────────────────


class NotificationChannelCreate(BaseModel):
    """Request body to create a notification channel."""

    type: str = Field(..., max_length=32, description="Channel type: slack, teams, discord, email")
    webhook_url: str = Field(..., max_length=2048, description="Webhook URL for the channel")
    events: list[str] = Field(default_factory=lambda: ["completed"], description="Events to notify on")


class NotificationChannelUpdate(BaseModel):
    """Request body to update a notification channel."""

    webhook_url: str | None = Field(default=None, max_length=2048)
    events: list[str] | None = None
    enabled: bool | None = None


class NotificationChannel(BaseModel):
    """A notification channel for a job."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=64)
    job_id: str = Field("", max_length=64)
    type: str = Field("", max_length=32)
    webhook_url: str = Field("", max_length=2048)
    events: list[str] = Field(default_factory=list)
    enabled: bool = True
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat(), max_length=64)
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat(), max_length=64)


# ─── Extraction Templates ──────────────────────────────────────────────────


class ExtractionTemplateCreate(BaseModel):
    """Request body to create a new extraction template."""

    name: str = Field(..., max_length=255, description="Template name")
    config: dict[str, Any] = Field(default_factory=dict, description="Extraction configuration overrides")
    schema_fields: list[SchemaField] = Field(default_factory=list, max_length=50)
    selectors_map: dict[str, Any] = Field(default_factory=dict)


class ExtractionTemplateUpdate(BaseModel):
    """Request body to update an extraction template."""

    name: str | None = Field(default=None, max_length=255)
    config: dict[str, Any] | None = None
    schema_fields: list[SchemaField] | None = None
    selectors_map: dict[str, Any] | None = None


class ExtractionTemplate(BaseModel):
    """A reusable extraction template."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=64)
    name: str = Field("", max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)
    schema_fields: list[SchemaField] = Field(default_factory=list)
    selectors_map: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat(), max_length=64)
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat(), max_length=64)
