"""Workflow domain models — workflows, steps, pagination config."""

import datetime
import uuid
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.scraping import SchemaField

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
    """Type of action in a workflow step.

    Members are explicit aliases for historically-used names (OPEN→GOTO,
    WAIT_FOR_TIMEOUT_LIMITED→WAIT); all aliases are first-class — both names
    resolve to the same string value and both appear in ``list(``cls``)``.
    """

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
    stop_condition: str = Field(
        "none", description="Stop condition: none, no_more_records, duplicate_threshold, custom", max_length=64
    )
    selector: str = Field("", description="Selector for next button or page links", max_length=500)


class Workflow(BaseModel):
    """A saved scraping workflow that can be replayed."""

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=64)
    name: str = Field(..., description="Human-readable workflow name", max_length=255)
    description: str = Field("", description="Optional workflow description", max_length=1000)

    # Ownership
    user_id: str = Field(default="", description="Creator user ID", max_length=128)
    org_id: str = Field(default="", description="Organization ID for multi-tenant isolation", max_length=128)
    project_id: str = Field(default="", description="Project ID for grouping", max_length=128)

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
    pagination_config: WorkflowPaginationConfig = Field(default_factory=WorkflowPaginationConfig)  # type: ignore[arg-type]

    # Status
    status: WorkflowStatus = Field(default=WorkflowStatus.DRAFT, description="Current workflow status")
    version: int = Field(1, ge=1, description="Workflow version for change tracking")

    # Timestamps
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat(), max_length=64)
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat(), max_length=64)
    last_run_at: str | None = Field(default=None, description="When this workflow was last executed", max_length=64)
    last_success_at: str | None = Field(default=None, description="When this workflow last completed successfully", max_length=64)
    last_failure_reason: str | None = Field(default=None, description="Last workflow failure reason", max_length=4096)
    last_run_job_id: str | None = Field(default=None, description="ID of the last job created from this workflow", max_length=64)

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
    pagination_config: WorkflowPaginationConfig = Field(default_factory=WorkflowPaginationConfig)  # type: ignore[arg-type]

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


class WorkflowRunQueuedResponse(BaseModel):
    """Response model for POST /api/workflows/{workflow_id}/run."""

    workflow_id: str
    job_id: str
    run_id: str
    status: str
    message: str
