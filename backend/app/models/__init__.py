"""Pydantic models for the scraper API.

This package splits the original monolithic ``models.py`` into domain-specific
sub-modules while maintaining full backward compatibility.  All public symbols
are re-exported here so that ``from app.models import X`` continues to work
exactly as before.

Sub-modules:
    scraping   — FieldType, SchemaField, FilterRule, ScrapeMode, etc.
    jobs       — Job, JobCreate, JobStatus, job update/response models
    workflow   — Workflow, WorkflowCreate, WorkflowStep, etc.
    auth       — AuthProfile, ScheduledJob, NotificationChannel, etc.
    session    — Session create/destroy/me response models
    system     — StatusResponse, AuditLogResponse, scraper router responses
"""

# Shared types and constants
# Auth / scheduling domain
from app.models.auth import (
    AuthProfile,
    AuthProfileStatus,
    ExtractionTemplate,
    ExtractionTemplateCreate,
    ExtractionTemplateUpdate,
    NotificationChannel,
    NotificationChannelCreate,
    NotificationChannelUpdate,
    ScheduledJob,
    ScheduledJobChangesResponse,
    ScheduledJobFrequency,
)

# Job domain
from app.models.jobs import (
    BatchSubmitRequest,
    BatchSubmitResponse,
    ClearTerminalResponse,
    DeleteMyDataResponse,
    EmailDeliveryRequest,
    FetchStrategyUpdate,
    Job,
    JobCloneRequest,
    JobCreate,
    JobCreateResponse,
    JobEventsResponse,
    JobExtractionUpdate,
    JobExtractionUpdateResponse,
    JobHeadersUpdate,
    JobQualityResponse,
    JobQualityTrendsResponse,
    JobResultsResponse,
    JobStatus,
    JobStrategyUpdate,
    JobUserAgentUpdate,
    JobWaitConditionsUpdate,
    JobWebhookUpdate,
    LogEntry,
    UsageRecord,
)
from app.models.scraping import (
    RESERVED_FIELD_NAMES,
    DiscoveryRequest,
    FieldType,
    FilterOperator,
    FilterRule,
    SchemaField,
    SchemaSuggestionRequest,
    ScrapeMode,
    ScraperDiagnosticsRequest,
    SelectorMap,
    SourcePolicy,
)

# Session domain
from app.models.session import (
    SessionCreateResponse,
    SessionDestroyResponse,
    SessionMeResponse,
)

# System domain
from app.models.system import (
    AuditLogResponse,
    DomainConfidenceResponse,
    LowConfidenceSelectorItem,
    LowConfidenceSelectorsResponse,
    PreviewResponse,
    RegressionGenerateAllResponse,
    RegressionTestGenerateResponse,
    RemoveDenylistResponse,
    ScraperConfigResponse,
    ScraperStatsResponse,
    SelectorCleanupResponse,
    SelectorMemoryFullStatsResponse,
    SelectorMemoryStatsResponse,
    StatusResponse,
)

# Workflow domain
from app.models.workflow import (
    Workflow,
    WorkflowCreate,
    WorkflowPaginationConfig,
    WorkflowRunQueuedResponse,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepType,
    WorkflowUpdate,
)

__all__ = [
    "RESERVED_FIELD_NAMES",
    # System
    "AuditLogResponse",
    # Auth
    "AuthProfile",
    "AuthProfileStatus",
    # Jobs
    "BatchSubmitRequest",
    "BatchSubmitResponse",
    "ClearTerminalResponse",
    "DeleteMyDataResponse",
    # Shared types
    "DiscoveryRequest",
    "DomainConfidenceResponse",
    "EmailDeliveryRequest",
    "ExtractionTemplate",
    "ExtractionTemplateCreate",
    "ExtractionTemplateUpdate",
    "FetchStrategyUpdate",
    "FieldType",
    "FilterOperator",
    "FilterRule",
    "Job",
    "JobCloneRequest",
    "JobCreate",
    "JobCreateResponse",
    "JobEventsResponse",
    "JobExtractionUpdate",
    "JobExtractionUpdateResponse",
    "JobHeadersUpdate",
    "JobQualityResponse",
    "JobQualityTrendsResponse",
    "JobResultsResponse",
    "JobStatus",
    "JobStrategyUpdate",
    "JobUserAgentUpdate",
    "JobWaitConditionsUpdate",
    "JobWebhookUpdate",
    "LogEntry",
    "LowConfidenceSelectorItem",
    "LowConfidenceSelectorsResponse",
    "NotificationChannel",
    "NotificationChannelCreate",
    "NotificationChannelUpdate",
    "PreviewResponse",
    "RegressionGenerateAllResponse",
    "RegressionTestGenerateResponse",
    "RemoveDenylistResponse",
    "ScheduledJob",
    "ScheduledJobChangesResponse",
    "ScheduledJobFrequency",
    "SchemaField",
    "SchemaSuggestionRequest",
    "ScrapeMode",
    "ScraperConfigResponse",
    "ScraperDiagnosticsRequest",
    "ScraperStatsResponse",
    "SelectorCleanupResponse",
    "SelectorMap",
    "SelectorMemoryFullStatsResponse",
    "SelectorMemoryStatsResponse",
    # Session
    "SessionCreateResponse",
    "SessionDestroyResponse",
    "SessionMeResponse",
    "SourcePolicy",
    "StatusResponse",
    "UsageRecord",
    # Workflow
    "Workflow",
    "WorkflowCreate",
    "WorkflowPaginationConfig",
    "WorkflowRunQueuedResponse",
    "WorkflowStatus",
    "WorkflowStep",
    "WorkflowStepType",
    "WorkflowUpdate",
]
