"""Workflow Router — CRUD and execution for saved scraping workflows.

Provides endpoints to create, list, update, delete, preview, and run
saved workflows that replay a sequence of browser steps.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.models import (
    SchemaField,
    Workflow,
    WorkflowCreate,
    WorkflowStatus,
    WorkflowUpdate,
)
from app.services.workflow_runner import (
    detect_fields_from_html,
    preview_workflow_snapshot,
    steps_from_manual_mapping,
)
from app.url_analyzer import analyze_url as analyze_guided_url
from app.url_safety import validate_public_http_url
from app.utils.json_file_store import JSONFileStore
from app.utils.rbac import UserRole, can_access_scoped_resource, require_principal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflows", tags=["workflows"])
draft_router = APIRouter(prefix="/api/workflow-drafts", tags=["workflow-drafts"])

# File-backed workflow store shared across uvicorn/gunicorn workers.
# Reads always re-read disk; writes use flock-serialised atomic rename.
_workflows = JSONFileStore(Path(__file__).resolve().parents[2] / "data" / "workflows.json")
_workflow_drafts = JSONFileStore(
    Path(__file__).resolve().parents[2] / "data" / "workflow_drafts.json",
)


class WorkflowDraftFromUrlAnalysisRequest(BaseModel):
    """Create a workflow replay draft from URL Intelligence output."""

    original_url: str = Field(..., max_length=2048)
    selected_start_url: str | None = Field(default=None, max_length=2048)
    detected_reason: str = Field(default="", max_length=500)


class WorkflowDraftFieldDetectionRequest(BaseModel):
    """Detect fields for a workflow draft from a safe local HTML snapshot."""

    html_snapshot: str = Field(default="", max_length=2_000_000)
    start_url: str | None = Field(default=None, max_length=2048)


class WorkflowManualMappingRequest(BaseModel):
    """Convert corrected manual field mapping into workflow steps."""

    name: str = Field(default="Workflow Replay Draft", max_length=255)
    description: str = Field(default="", max_length=1000)
    start_url: str | None = Field(default=None, max_length=2048)
    fields: list[dict[str, Any]] = Field(default_factory=list)
    submit_action: dict[str, Any] | None = None
    extraction_schema: list[SchemaField] = Field(default_factory=list)


class WorkflowPreviewRequest(BaseModel):
    """Preview request body for deterministic fixture-backed replay."""

    html_snapshot: str = Field(default="", max_length=2_000_000)
    sample_limit: int = Field(default=5, ge=1, le=25)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _workflow_to_dict(wf: Workflow) -> dict[str, Any]:
    """Serialize a Workflow model to a plain dict."""
    return wf.model_dump()


def _serialize_pagination_config(pc: Any) -> dict[str, Any]:
    """Serialize a pagination config to a plain dict for JSON storage."""
    if pc is None:
        return {}
    if hasattr(pc, "model_dump"):
        return pc.model_dump()
    if isinstance(pc, dict):
        return pc
    return {}


def _write_back(record: dict[str, Any]) -> None:
    """Persist a (possibly-mutated) local copy of a workflow record.

    The store returns deep copies on every read so direct mutation of the
    dict the caller holds does NOT persist; this helper is what makes
    mutations on those copies visible to subsequent reads and to sibling
    workers.
    """
    record_id = str(record.get("id") or "")
    if not record_id:
        missing_id_message = "workflow dict missing 'id' before write-back"
        raise RuntimeError(missing_id_message)
    _workflows.upsert(record_id, record)


def _can_access_workflow(item: dict[str, Any], auth: tuple[UserRole, str, str, str]) -> bool:
    role, user_id, org_id, project_id = auth
    return can_access_scoped_resource(
        role,
        user_id,
        org_id,
        project_id,
        resource_owner_id=str(item.get("user_id") or ""),
        resource_org_id=str(item.get("org_id") or ""),
        resource_project_id=str(item.get("project_id") or ""),
    )


def _get_visible_workflow(workflow_id: str, auth: tuple[UserRole, str, str, str]) -> dict[str, Any]:
    item = _workflows.get(workflow_id)
    if item is None or not _can_access_workflow(item, auth):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return item


def _can_access_draft(item: dict[str, Any], auth: tuple[UserRole, str, str, str]) -> bool:
    return _can_access_workflow(item, auth)


def _get_visible_draft(draft_id: str, auth: tuple[UserRole, str, str, str]) -> dict[str, Any]:
    item = _workflow_drafts.get(draft_id)
    if item is None or not _can_access_draft(item, auth):
        raise HTTPException(status_code=404, detail="Workflow draft not found")
    return item


def _write_back_draft(record: dict[str, Any]) -> None:
    """Persist a (possibly-mutated) draft record to the file-backed store."""
    record_id = str(record.get("id") or "")
    if not record_id:
        missing_id_message = "workflow draft dict missing 'id' before write-back"
        raise RuntimeError(missing_id_message)
    _workflow_drafts.upsert(record_id, record)


@draft_router.post("/from-url-analysis", status_code=201)
async def create_workflow_draft_from_url_analysis(
    req: WorkflowDraftFromUrlAnalysisRequest,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """Create a lightweight workflow replay draft from URL Intelligence.

    This is only the Prompt 8 entry point. It does not execute the
    workflow or attempt to reuse temporary session identifiers.
    """
    try:
        validate_public_http_url(req.original_url)
        if req.selected_start_url:
            validate_public_http_url(req.selected_start_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unsafe workflow URL: {exc}") from exc

    role, user_id, org_id, project_id = auth
    analysis = analyze_guided_url(req.original_url).to_guided_dict(safe_to_fetch=True)
    recommended_start_urls = analysis.get("suggested_start_urls", [])
    selected_start_url = req.selected_start_url or (
        recommended_start_urls[0]["url"] if recommended_start_urls else req.original_url
    )
    draft_id = str(uuid.uuid4())
    draft = {
        "id": draft_id,
        "original_url": analysis["url"],
        "recommended_start_urls": recommended_start_urls,
        "selected_start_url": selected_start_url,
        "detected_reason": req.detected_reason or analysis["user_message"],
        "initial_mode": "workflow_replay",
        "status": "draft",
        "user_id": user_id,
        "org_id": org_id,
        "project_id": project_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    _workflow_drafts.upsert(draft_id, draft)
    logger.info("Workflow draft created from URL analysis: %s role=%s", draft_id, role.value)
    return draft


@draft_router.post("/{draft_id}/detect-fields", status_code=200)
async def detect_workflow_draft_fields(
    draft_id: str,
    req: WorkflowDraftFieldDetectionRequest,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """Detect form fields for a workflow draft from a local HTML snapshot."""
    draft = _get_visible_draft(draft_id, auth)
    start_url = req.start_url or draft.get("selected_start_url") or ""
    if start_url:
        try:
            validate_public_http_url(start_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unsafe workflow start URL: {exc}") from exc
    if not req.html_snapshot:
        raise HTTPException(status_code=400, detail="html_snapshot is required for deterministic field detection.")
    fields = detect_fields_from_html(req.html_snapshot)
    draft["detected_fields"] = fields
    draft["updated_at"] = _now_iso()
    _write_back_draft(draft)
    return {
        "draft_id": draft_id,
        "start_url": start_url,
        "fields": fields,
        "field_count": len(fields),
    }


@draft_router.post("/{draft_id}/manual-mapping", status_code=201)
async def create_workflow_from_manual_mapping(
    draft_id: str,
    req: WorkflowManualMappingRequest,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """Create a saved workflow from corrected field mapping."""
    draft = _get_visible_draft(draft_id, auth)
    _role, user_id, org_id, project_id = auth
    start_url = req.start_url or draft.get("selected_start_url") or ""
    if not start_url:
        raise HTTPException(status_code=400, detail="Workflow start URL is required")
    try:
        validate_public_http_url(start_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unsafe workflow start URL: {exc}") from exc

    steps = steps_from_manual_mapping(
        start_url=start_url,
        fields=req.fields,
        submit_action=req.submit_action,
    )
    wf = Workflow(
        name=req.name.strip() or "Workflow Replay Draft",
        description=req.description,
        mode="workflow_replay",
        start_url=start_url,
        original_url=str(draft.get("original_url") or ""),
        search_params={},
        steps=steps,
        extraction_schema=req.extraction_schema,
        user_id=user_id,
        org_id=org_id,
        project_id=project_id,
        status=WorkflowStatus.DRAFT,
    )
    _workflows.upsert(wf.id, _workflow_to_dict(wf))
    draft["workflow_id"] = wf.id
    draft["updated_at"] = _now_iso()
    _write_back_draft(draft)
    return _workflow_to_dict(wf)


@router.post("", status_code=201)
async def create_workflow(
    req: WorkflowCreate,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """Create a new workflow from a template or scratch.

    Requires at least user role. Owner/org/project are populated from the
    authenticated context when available.
    """
    _role, user_id, org_id, project_id = auth
    wf = Workflow(
        name=req.name.strip(),
        description=req.description.strip() if req.description else "",
        mode=req.mode,
        start_url=req.start_url.strip() if req.start_url else "",
        original_url=req.original_url.strip() if req.original_url else "",
        search_params=req.search_params,
        steps=req.steps,
        extraction_schema=req.extraction_schema,
        auth_profile_id=req.auth_profile_id,
        pagination_config=req.pagination_config,
        user_id=user_id,
        org_id=org_id,
        project_id=project_id,
        status=WorkflowStatus.ACTIVE,
    )
    _workflows.upsert(wf.id, _workflow_to_dict(wf))
    logger.info("Workflow created: %s (%s)", wf.name, wf.id)
    return _workflow_to_dict(wf)


@router.get("", status_code=200)
async def list_workflows(
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    status: str | None = None,
    domain: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """List workflows with optional filtering.

    Supports filtering by status and domain. Results are paginated.
    """
    items = [item for item in _workflows.values() if _can_access_workflow(item, auth)]

    if status:
        items = [w for w in items if w.get("status") == status]
    if domain:
        items = [w for w in items if domain.lower() in (w.get("domain") or "").lower()]

    total = len(items)
    items = items[offset : offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


@router.get("/{workflow_id}", status_code=200)
async def get_workflow(
    workflow_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """Get a single workflow by ID."""
    return _get_visible_workflow(workflow_id, auth)


@router.put("/{workflow_id}", status_code=200)
async def update_workflow(
    workflow_id: str,
    req: WorkflowUpdate,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """Update an existing workflow. Only provided fields are changed."""
    existing = _get_visible_workflow(workflow_id, auth)
    update_data = req.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        if value is not None:
            existing[key] = value

    existing["updated_at"] = _now_iso()
    existing["version"] = existing.get("version", 1) + 1

    _write_back(existing)
    logger.info("Workflow updated: %s", workflow_id)
    return existing


@router.patch("/{workflow_id}", status_code=200)
async def patch_workflow(
    workflow_id: str,
    req: WorkflowUpdate,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """PATCH alias for partial workflow updates."""
    return await update_workflow(workflow_id, req, auth)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """Delete a workflow permanently."""
    _get_visible_workflow(workflow_id, auth)
    if _workflows.delete(workflow_id):
        logger.info("Workflow deleted: %s", workflow_id)


@router.post("/{workflow_id}/run", status_code=202)
async def run_workflow(
    workflow_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
):
    """Queue a workflow for execution and return the job ID.

    The actual execution is performed asynchronously by the job runner.
    """
    wf = _get_visible_workflow(workflow_id, auth)

    # Update run counters
    wf["total_runs"] = wf.get("total_runs", 0) + 1
    wf["last_run_at"] = _now_iso()

    # Generate a job ID for tracking
    job_id = str(uuid.uuid4())
    wf["last_run_job_id"] = job_id
    _write_back(wf)

    logger.info("Workflow queued: %s -> job %s", workflow_id, job_id)

    return {
        "workflow_id": workflow_id,
        "job_id": job_id,
        "status": "queued",
        "message": "Workflow queued for execution. Poll /api/jobs/{job_id} for status.",
    }


@router.post("/{workflow_id}/preview", status_code=200)
async def preview_workflow(
    workflow_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    req: WorkflowPreviewRequest | None = None,
):
    """Preview what a workflow would extract without running it.

    Returns the first-page extraction result or an error if the workflow
    cannot be previewed (e.g., requires auth, session expired).
    """
    wf = _get_visible_workflow(workflow_id, auth)
    preview_req = req or WorkflowPreviewRequest()
    workflow_model = Workflow.model_validate(wf)

    if not preview_req.html_snapshot:
        return {
            "workflow_id": workflow_id,
            "preview_status": "failed",
            "failure_type": "preview_input_required",
            "user_message": "Preview requires a local HTML snapshot in this deterministic runner.",
            "recommended_action": "Detect fields or provide an HTML snapshot, then preview again.",
            "timeline": [],
            "last_url": workflow_model.start_url,
            "page_title": "",
            "screenshot": None,
            "sample_rows": [],
            "warnings": ["Full browser preview is deferred behind the workflow runner boundary."],
        }

    result = await preview_workflow_snapshot(
        workflow_model,
        html_snapshot=preview_req.html_snapshot,
        sample_limit=preview_req.sample_limit,
    )
    if result.get("preview_status") == "succeeded":
        wf["last_success_at"] = _now_iso()
        wf["last_failure_reason"] = None
    else:
        wf["last_failure_reason"] = result.get("failure_type") or result.get("user_message")
    wf["last_run_at"] = _now_iso()
    _write_back(wf)
    return result
