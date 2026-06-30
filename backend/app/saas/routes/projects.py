"""Project CRUD and API key management endpoints."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.audit_logger import log_job_event
from app.saas.identity_store import get_identity_store
from app.saas.models import Project
from app.utils.aup import require_aup_accepted
from app.utils.rbac import UserRole, require_principal, require_role_with_user

from ._common import _MAX_KEY_SCOPE_FOR_ROLE, _SCOPE_RANK

logger = logging.getLogger(__name__)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
# Project Management
# ═══════════════════════════════════════════════════════════════════════


class ProjectCreateRequest(BaseModel):
    """Request to create a new project within an organization."""

    org_id: str = Field(..., max_length=64, description="Parent organization ID")
    name: str = Field(..., min_length=1, max_length=120, description="Project name")

    @field_validator("name")
    @classmethod
    def _validate_project_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "Project name must not be blank"
            raise ValueError(msg)
        if len(stripped) < 1 or len(stripped) > 120:
            msg = "Project name must be between 1 and 120 characters"
            raise ValueError(msg)
        return stripped


class ProjectResponse(BaseModel):
    """Project details."""

    id: str = Field(max_length=64)
    org_id: str = Field(max_length=64)
    name: str = Field(max_length=255)
    created_by_user_id: str = Field(max_length=64)
    created_at: str = Field(max_length=64)


class ProjectListResponse(BaseModel):
    """List of projects."""

    items: list[ProjectResponse]
    total: int


@router.post("/projects", status_code=201, response_model=ProjectResponse)
async def create_project(
    body: ProjectCreateRequest,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    _aup_check: Annotated[dict[str, Any], Depends(require_aup_accepted)],
) -> ProjectResponse:
    """Create a new project within an organization.

    Requires AUP acceptance.
    """
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    # Verify user is a member of the org
    if not get_identity_store().is_org_member(user_id, body.org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    project = Project(
        org_id=body.org_id,
        name=body.name.strip(),
        created_by_user_id=user_id,
    )
    project = get_identity_store().create_project(project)

    log_job_event(
        actor=user_id,
        action="project_create",
        job_id="saas",
        outcome="success",
        details={"project_id": project.id, "project_name": project.name, "org_id": body.org_id},
    )

    return ProjectResponse(
        id=project.id,
        org_id=project.org_id,
        name=project.name,
        created_by_user_id=project.created_by_user_id,
        created_at=project.created_at,
    )


@router.get("/orgs/{org_id}/projects", response_model=ProjectListResponse)
async def list_org_projects(
    org_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> ProjectListResponse:
    """List all projects within an organization."""
    _role, user_id, auth_org_id, _project_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    if auth_org_id and auth_org_id != org_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access forbidden")

    # Verify membership
    if not get_identity_store().is_org_member(user_id, org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    projects = get_identity_store().list_org_projects(org_id)
    return ProjectListResponse(
        items=[
            ProjectResponse(
                id=p.id,
                org_id=p.org_id,
                name=p.name,
                created_by_user_id=p.created_by_user_id,
                created_at=p.created_at,
            )
            for p in projects
        ],
        total=len(projects),
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> ProjectResponse:
    """Get a single project by ID."""
    role, user_id, _org_id, _project_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    project = get_identity_store().get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")

    # Verify user is a member of the project org
    if not get_identity_store().is_org_member(user_id, project.org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    # Enforce project-level scope
    from app.utils.rbac import can_access_scoped_resource

    if not can_access_scoped_resource(
        role,
        user_id,
        _org_id,
        _project_id,
        resource_owner_id=project.created_by_user_id,
        resource_org_id=project.org_id,
        resource_project_id=project.id,
    ):
        raise HTTPException(status_code=403, detail="Cross-project access forbidden")

    return ProjectResponse(
        id=project.id,
        org_id=project.org_id,
        name=project.name,
        created_by_user_id=project.created_by_user_id,
        created_at=project.created_at,
    )


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> None:
    """Permanently delete a project and all its API keys.

    Cascading deletion removes all API keys associated with the project.
    Only project members with operator-level access or env-backed
    admins/operators may delete a project.
    """
    role, user_id, _org_id, _project_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    store = get_identity_store()
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")

    # Verify caller is a member of the org
    if not store.is_org_member(user_id, project.org_id) and role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="not a member of this organization")

    # Enforce project-level scope
    from app.utils.rbac import can_access_scoped_resource

    if not can_access_scoped_resource(
        role,
        user_id,
        _org_id,
        _project_id,
        resource_owner_id=project.created_by_user_id,
        resource_org_id=project.org_id,
        resource_project_id=project.id,
    ):
        raise HTTPException(status_code=403, detail="Cross-project access forbidden")

    store.delete_project(project_id)

    log_job_event(
        actor=user_id,
        action="project_delete",
        job_id="saas",
        outcome="success",
        details={"project_id": project_id, "org_id": project.org_id, "project_name": project.name},
    )


# ═══════════════════════════════════════════════════════════════════════
# API Key Management
# ═══════════════════════════════════════════════════════════════════════


class ApiKeyCreateRequest(BaseModel):
    """Request to create a new API key for a project."""

    name: str = Field(..., min_length=1, max_length=120, description="Key name")
    scope: Literal["read", "write", "admin"] = Field(
        "read",
        max_length=32,
        description="Key scope: read, write, or admin",
    )


class ApiKeyResponse(BaseModel):
    """API key metadata (raw key only shown once at creation)."""

    id: str = Field(max_length=64)
    project_id: str = Field(max_length=64)
    name: str = Field(max_length=255)
    scope: str = Field(max_length=32)
    key_prefix: str = Field(max_length=128)
    created_at: str = Field(max_length=64)
    last_used_at: str | None = Field(default=None, max_length=64)
    revoked_at: str | None = Field(default=None, max_length=64)


class ApiKeyListResponse(BaseModel):
    """List of API keys for a project."""

    items: list[ApiKeyResponse]
    total: int


class ApiKeyCreateResponse(BaseModel):
    """Response after creating an API key — raw key shown only here."""

    id: str = Field(max_length=64)
    project_id: str = Field(max_length=64)
    name: str = Field(max_length=255)
    scope: str = Field(max_length=32)
    raw_key: str = Field(max_length=256)
    key_prefix: str = Field(max_length=128)
    created_at: str = Field(max_length=64)


@router.post("/projects/{project_id}/keys", status_code=201, response_model=ApiKeyCreateResponse)
async def create_api_key(
    project_id: str,
    body: ApiKeyCreateRequest,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    _aup_check: Annotated[dict[str, Any], Depends(require_aup_accepted)],
) -> ApiKeyCreateResponse:
    """Create a new API key for a project.

    The raw key is returned **only once** in this response. It is hashed
    before storage and cannot be retrieved later.

    Requires AUP acceptance.
    """
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    # Verify project exists and user is a member of the org
    project = get_identity_store().get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")

    if not get_identity_store().is_org_member(user_id, project.org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    from app.saas.service import ApiKeyScope, ApiKeyService

    scope_map = {
        "read": ApiKeyScope.READ,
        "write": ApiKeyScope.WRITE,
        "admin": ApiKeyScope.ADMIN,
    }
    raw_scope = body.scope.lower()
    scope = scope_map[raw_scope]

    # Privilege boundary: the granted key scope MUST NOT exceed the
    # caller's own membership role in the target org.
    _caller_memberships = get_identity_store().list_user_memberships(user_id)
    _caller_role_in_org = next(
        (m.role for m in _caller_memberships if m.org_id == project.org_id and m.is_active()),
        None,
    )
    if _caller_role_in_org is None and not _caller_memberships:
        _caller_role_value = _role.value if getattr(_role, "value", None) is not None else "viewer"
        logger.debug(
            "create_api_key: caller=%s has zero memberships — falling back to auth role=%s",
            user_id,
            _caller_role_value,
        )
    else:
        _caller_role_value = _caller_role_in_org.value if _caller_role_in_org else "viewer"
    _caller_max_scope = _MAX_KEY_SCOPE_FOR_ROLE.get(_caller_role_value, "read")
    if _SCOPE_RANK.get(raw_scope, 0) > _SCOPE_RANK.get(_caller_max_scope, 0):
        log_job_event(
            actor=user_id,
            action="api_key_create",
            job_id="saas",
            outcome="denied",
            details={
                "project_id": project_id,
                "requested_scope": body.scope,
                "caller_membership_role": _caller_role_value,
                "reason": "scope_exceeds_membership_role",
            },
        )
        raise HTTPException(
            status_code=403,
            detail=f"Cannot issue a {body.scope}-scope key: your membership role in this org does not permit it.",
        )

    svc = ApiKeyService(store=get_identity_store())
    issued = svc.issue(
        project_id=project_id,
        user_id=user_id,
        name=body.name,
        scope=scope,
    )
    api_key = issued.api_key
    raw_key = issued.raw_key

    log_job_event(
        actor=user_id,
        action="api_key_create",
        job_id="saas",
        outcome="success",
        details={"project_id": project_id, "key_id": api_key.id, "scope": body.scope},
    )

    return ApiKeyCreateResponse(
        id=api_key.id,
        project_id=api_key.project_id,
        name=api_key.name,
        scope=body.scope,
        raw_key=raw_key,
        key_prefix=api_key.key_prefix,
        created_at=api_key.created_at,
    )


@router.get("/projects/{project_id}/keys", response_model=ApiKeyListResponse)
async def list_project_api_keys(
    project_id: str,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> ApiKeyListResponse:
    """List all API keys for a project (raw key not included)."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    project = get_identity_store().get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")

    if not get_identity_store().is_org_member(user_id, project.org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    from app.saas.service import ApiKeyService

    svc = ApiKeyService(store=get_identity_store())
    keys = svc.list_for_project(project_id)

    return ApiKeyListResponse(
        items=[
            ApiKeyResponse(
                id=k.id,
                project_id=k.project_id,
                name=k.name,
                scope=k.scope.value,
                key_prefix=k.key_prefix,
                created_at=k.created_at,
                last_used_at=k.last_used_at,
                revoked_at=k.revoked_at,
            )
            for k in keys
        ],
        total=len(keys),
    )


@router.delete("/projects/{project_id}/keys/{key_id}", status_code=204)
async def revoke_api_key(
    project_id: str,
    key_id: str,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> None:
    """Revoke an API key (admin/operator only)."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    project = get_identity_store().get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")

    if not get_identity_store().is_org_member(user_id, project.org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    from app.saas.service import ApiKeyService

    svc = ApiKeyService(store=get_identity_store())
    key = svc.store.get_api_key(key_id)
    if not key or key.project_id != project_id:
        raise HTTPException(status_code=404, detail="key not found")

    svc.revoke(key_id)

    log_job_event(
        actor=user_id,
        action="api_key_revoke",
        job_id="saas",
        outcome="success",
        details={"project_id": project_id, "key_id": key_id},
    )
