"""SaaS identity router — thin FastAPI adapter over the identity store.

Hosts endpoints for:
- AUP (Acceptable Use Policy) acceptance
- Self-service user signup
- Organization management
- Project management
- User profile
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.audit_logger import log_job_event
from app.saas.identity_store import IdentityStoreError, get_identity_store

# Models & services
from app.saas.models import (
    Membership,
    MembershipRole,
    Organization,
    Project,
)
from app.saas.service import SignupService
from app.utils.rbac import UserRole, require_role_with_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/saas", tags=["saas"])

# ═══════════════════════════════════════════════════════════════════════
# AUP (Acceptable Use Policy)
# ═══════════════════════════════════════════════════════════════════════

CURRENT_AUP_VERSION = "2026-06-11-v1"


class AupAcceptRequest(BaseModel):
    """Request body for recording AUP acceptance."""

    aup_version: str = Field(
        CURRENT_AUP_VERSION,
        max_length=64,
        description="AUP version the user accepted (defaults to the current version).",
    )


class AupStatusResponse(BaseModel):
    """Response body for AUP status / acceptance."""

    user_id: str
    aup_accepted_at: str | None
    aup_version_accepted: str | None
    requires_acceptance: bool
    current_aup_version: str


AupAcceptResponse = AupStatusResponse


def _aup_response_for(
    user_id: str,
    accepted_at: str | None,
    accepted_version: str | None,
) -> AupStatusResponse:
    return AupStatusResponse(
        user_id=user_id,
        aup_accepted_at=accepted_at,
        aup_version_accepted=accepted_version,
        requires_acceptance=accepted_at is None or accepted_version != CURRENT_AUP_VERSION,
        current_aup_version=CURRENT_AUP_VERSION,
    )


@router.post("/aup/accept", response_model=AupStatusResponse)
async def accept_aup(
    body: AupAcceptRequest,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> AupStatusResponse:
    """Record that the authenticated user accepted the AUP.

    Idempotent: re-acceptance keeps the first acceptance timestamp.
    """
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")
    user = get_identity_store().get_user(user_id)
    if user is None:
        log_job_event(
            actor=user_id,
            action="aup_accept",
            job_id="aup",
            outcome="success",
            details={"aup_version": body.aup_version, "shadow_user": True},
        )
        return _aup_response_for(user_id=user_id, accepted_at=None, accepted_version=None)
    updated = get_identity_store().mark_aup_accepted(user_id, aup_version=body.aup_version)
    if updated is None:
        raise HTTPException(status_code=500, detail="failed to record AUP acceptance")
    log_job_event(
        actor=user_id,
        action="aup_accept",
        job_id="aup",
        outcome="success",
        details={"aup_version": body.aup_version, "previous": user.aup_accepted_at},
    )
    return _aup_response_for(
        user_id=user_id,
        accepted_at=updated.aup_accepted_at,
        accepted_version=updated.aup_version_accepted,
    )


@router.get("/aup/status", response_model=AupStatusResponse)
async def get_aup_status(
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> AupStatusResponse:
    """Return the authenticated user's current AUP acceptance state."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")
    user = get_identity_store().get_user(user_id)
    if user is None:
        return _aup_response_for(user_id=user_id, accepted_at=None, accepted_version=None)
    return _aup_response_for(
        user_id=user_id,
        accepted_at=user.aup_accepted_at,
        accepted_version=user.aup_version_accepted,
    )


# ═══════════════════════════════════════════════════════════════════════
# Self-service Signup
# ═══════════════════════════════════════════════════════════════════════


class SignupRequest(BaseModel):
    """Request body for self-service user signup."""

    email: str = Field(..., description="User email (becomes login)")
    password: str = Field(..., min_length=8, description="Minimum 8 characters")
    display_name: str = Field("", description="Optional human-readable name")
    org_name: str | None = Field(None, description="Optional organization name")
    project_name: str | None = Field(None, description="Optional project name")


class SignupResponse(BaseModel):
    """Response after successful signup."""

    user_id: str
    email: str
    organization_id: str
    project_id: str
    message: str = "Account created successfully. Please accept the AUP."


@router.post("/signup", status_code=201)
async def signup(body: SignupRequest) -> SignupResponse:
    """Create a new user with a default organization and project."""
    svc = SignupService()
    try:
        result = svc.signup(
            email=body.email,
            password=body.password,
            display_name=body.display_name or "",
            org_name=body.org_name,
            project_name=body.project_name,
        )
    except IdentityStoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    log_job_event(
        actor=result.user.id,
        action="user_signup",
        job_id="signup",
        outcome="success",
        details={"email": result.user.email, "org_id": result.organization.id, "project_id": result.project.id},
    )

    return SignupResponse(
        user_id=result.user.id,
        email=result.user.email,
        organization_id=result.organization.id,
        project_id=result.project.id,
    )


# ═══════════════════════════════════════════════════════════════════════
# User Profile
# ═══════════════════════════════════════════════════════════════════════


class UserProfileResponse(BaseModel):
    """Public view of a user's profile."""

    user_id: str
    email: str
    display_name: str
    status: str
    aup_accepted_at: str | None
    aup_version_accepted: str | None


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> UserProfileResponse:
    """Return the current user's profile."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")
    user = get_identity_store().get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return UserProfileResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status.value,
        aup_accepted_at=user.aup_accepted_at,
        aup_version_accepted=user.aup_version_accepted,
    )


# ═══════════════════════════════════════════════════════════════════════
# Organization Management
# ═══════════════════════════════════════════════════════════════════════


class OrgCreateRequest(BaseModel):
    """Request to create a new organization."""

    name: str = Field(..., min_length=1, max_length=120, description="Organization name")


class OrgResponse(BaseModel):
    """Organization details."""

    id: str
    name: str
    created_by_user_id: str
    created_at: str


class OrgListResponse(BaseModel):
    """List of organizations the user belongs to."""

    items: list[OrgResponse]
    total: int


@router.post("/orgs", status_code=201, response_model=OrgResponse)
async def create_organization(
    body: OrgCreateRequest,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> OrgResponse:
    """Create a new organization. Caller becomes owner."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    org = Organization(
        name=body.name.strip(),
        created_by_user_id=user_id,
    )
    org = get_identity_store().create_organization(org)

    # Auto-add creator as owner
    membership = Membership(user_id=user_id, org_id=org.id, role=MembershipRole.OWNER)
    get_identity_store().create_membership(membership)

    log_job_event(
        actor=user_id,
        action="org_create",
        job_id="saas",
        outcome="success",
        details={"org_id": org.id, "org_name": org.name},
    )

    return OrgResponse(
        id=org.id,
        name=org.name,
        created_by_user_id=org.created_by_user_id,
        created_at=org.created_at,
    )


@router.get("/orgs", response_model=OrgListResponse)
async def list_my_organizations(
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> OrgListResponse:
    """List all organizations the current user is a member of."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    orgs = get_identity_store().list_user_organizations(user_id)
    return OrgListResponse(
        items=[
            OrgResponse(
                id=org.id,
                name=org.name,
                created_by_user_id=org.created_by_user_id,
                created_at=org.created_at,
            )
            for org in orgs
        ],
        total=len(orgs),
    )


@router.get("/orgs/{org_id}", response_model=OrgResponse)
async def get_organization(
    org_id: str,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> OrgResponse:
    """Get a single organization by ID."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    # Verify membership
    if not get_identity_store().is_org_member(user_id, org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    org = get_identity_store().get_organization(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="organization not found")

    return OrgResponse(
        id=org.id,
        name=org.name,
        created_by_user_id=org.created_by_user_id,
        created_at=org.created_at,
    )


# ═══════════════════════════════════════════════════════════════════════
# Project Management
# ═══════════════════════════════════════════════════════════════════════


class ProjectCreateRequest(BaseModel):
    """Request to create a new project within an organization."""

    org_id: str = Field(..., description="Parent organization ID")
    name: str = Field(..., min_length=1, max_length=120, description="Project name")


class ProjectResponse(BaseModel):
    """Project details."""

    id: str
    org_id: str
    name: str
    created_by_user_id: str
    created_at: str


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
) -> ProjectResponse:
    """Create a new project within an organization."""
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
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> ProjectListResponse:
    """List all projects within an organization."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

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
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> ProjectResponse:
    """Get a single project by ID."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    project = get_identity_store().get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")

    # Verify user is a member of the project org
    if not get_identity_store().is_org_member(user_id, project.org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    return ProjectResponse(
        id=project.id,
        org_id=project.org_id,
        name=project.name,
        created_by_user_id=project.created_by_user_id,
        created_at=project.created_at,
    )


# ═══════════════════════════════════════════════════════════════════════
# Membership / Team Management
# ═══════════════════════════════════════════════════════════════════════


class MemberInviteRequest(BaseModel):
    """Request to invite a user to an organization."""

    org_id: str = Field(..., description="Organization ID")
    email: str = Field(..., description="Email of the user to invite")
    role: str = Field("member", description="Role to assign (owner/admin/member/viewer)")


class MembershipResponse(BaseModel):
    """Membership details."""

    membership_id: str
    user_id: str
    org_id: str
    role: str
    created_at: str


@router.get("/orgs/{org_id}/members", response_model=list[MembershipResponse])
async def list_org_members(
    org_id: str,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> list[MembershipResponse]:
    """List all active members of an organization."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    # Verify membership
    if not get_identity_store().is_org_member(user_id, org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    members = get_identity_store().list_org_memberships(org_id)
    return [
        MembershipResponse(
            membership_id=m.id,
            user_id=m.user_id,
            org_id=m.org_id,
            role=m.role.value,
            created_at=m.created_at,
        )
        for m in members
        if m.is_active()
    ]


@router.delete("/memberships/{membership_id}", status_code=204)
async def remove_member(
    membership_id: str,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> None:
    """Remove a member from an organization (admin/operator only)."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    membership = get_identity_store().get_membership(membership_id)
    if not membership:
        raise HTTPException(status_code=404, detail="membership not found")

    # Cannot remove self if the last owner
    if membership.role == MembershipRole.OWNER and membership.user_id == user_id:
        # Check if there's another owner
        all_members = get_identity_store().list_org_memberships(membership.org_id)
        owners = [m for m in all_members if m.role == MembershipRole.OWNER and m.id != membership_id]
        if not owners:
            raise HTTPException(status_code=409, detail="cannot remove the last owner")

    get_identity_store().remove_membership(membership_id)
    log_job_event(
        actor=user_id,
        action="member_remove",
        job_id="saas",
        outcome="success",
        details={"membership_id": membership_id, "org_id": membership.org_id},
    )


# ═══════════════════════════════════════════════════════════════════════
# Plan & Limits (stub — records tier, does not enforce)
# ═══════════════════════════════════════════════════════════════════════


class PlanTier(str):
    """Subscription plan tiers."""

    __slots__ = ()

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class PlanInfoResponse(BaseModel):
    """Current plan information for the user."""

    tier: str = "free"
    max_jobs: int = 10
    max_scrapes: int = 1000
    max_teammates: int = 2
    max_projects: int = 2
    features: list[str]


# ═══════════════════════════════════════════════════════════════════════
# API Key Management
# ═══════════════════════════════════════════════════════════════════════


class ApiKeyCreateRequest(BaseModel):
    """Request to create a new API key for a project."""

    name: str = Field(..., min_length=1, max_length=120, description="Key name")
    scope: str = Field("read", description="Key scope: read, write, or admin")


class ApiKeyResponse(BaseModel):
    """API key metadata (raw key only shown once at creation)."""

    id: str
    project_id: str
    name: str
    scope: str
    key_prefix: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None


class ApiKeyListResponse(BaseModel):
    """List of API keys for a project."""

    items: list[ApiKeyResponse]
    total: int


class ApiKeyCreateResponse(BaseModel):
    """Response after creating an API key — raw key shown only here."""

    id: str
    project_id: str
    name: str
    scope: str
    raw_key: str  # ⚠️ Shown once — never stored in plain text
    key_prefix: str
    created_at: str


@router.post("/projects/{project_id}/keys", status_code=201, response_model=ApiKeyCreateResponse)
async def create_api_key(
    project_id: str,
    body: ApiKeyCreateRequest,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> ApiKeyCreateResponse:
    """Create a new API key for a project.

    The raw key is returned **only once** in this response. It is hashed
    before storage and cannot be retrieved later.
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
    scope = scope_map.get(body.scope.lower(), ApiKeyScope.READ)

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


@router.get("/plan", response_model=PlanInfoResponse)
async def get_plan_info(
    _auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> PlanInfoResponse:
    """Return the current user's plan and limits.

    Stub — returns free tier defaults. Future: lookup from a billing table.
    """
    return PlanInfoResponse(
        tier="free",
        max_jobs=10,
        max_scrapes=1000,
        max_teammates=2,
        max_projects=2,
        features=["basic_scraping", "scheduled_jobs", "aup_compliance"],
    )
