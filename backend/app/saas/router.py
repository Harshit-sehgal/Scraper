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
import re
import sqlite3
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.audit_logger import log_job_event
from app.plan_enforcer import get_plan_limits, get_user_tier
from app.rate_limiter import SlidingWindowCounter
from app.saas import CURRENT_AUP_VERSION  # re-exported from app.saas.__init__
from app.saas.identity_store import IdentityStoreError, get_identity_store

# Models & services
from app.saas.models import (
    Membership,
    MembershipRole,
    Organization,
    Project,
)
from app.saas.service import SignupService
from app.utils.aup import require_aup_accepted
from app.utils.rbac import UserRole, require_principal, require_role_with_user
from app.utils.usage_ledger import UsageType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/saas", tags=["saas"])

# ═══════════════════════════════════════════════════════════════════════
# AUP (Acceptable Use Policy)
# ═══════════════════════════════════════════════════════════════════════


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


def _get_aup_user_or_none(user_id: str) -> Any | None:
    try:
        return get_identity_store().get_user(user_id)
    except (IdentityStoreError, sqlite3.Error) as exc:
        logger.debug("AUP user lookup failed for %s: %s", user_id, exc)
        return None


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
    user = _get_aup_user_or_none(user_id)
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
    user = _get_aup_user_or_none(user_id)
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
async def signup(body: SignupRequest, request: Request) -> SignupResponse:
    """Create a new user with a default organization and project.

    Rate-limited to 3 signups per 5 minutes per IP address to prevent
    account creation spam.
    """
    # Rate limit: 3 signups per 5 minutes per IP
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(_SIGNUP_LIMITERS, client_ip, max_requests=3, window_seconds=300.0, action="signup")

    # Validate password strength
    _validate_password(body.password)

    svc = SignupService()
    # Validate email format
    validated_email = _validate_email(body.email)

    try:
        result = svc.signup(
            email=validated_email,
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

    @field_validator("name")
    @classmethod
    def _validate_org_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "Organization name must not be blank"
            raise ValueError(msg)
        if len(stripped) < 1 or len(stripped) > 120:
            msg = "Organization name must be between 1 and 120 characters"
            raise ValueError(msg)
        return stripped


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

    # Existence before permission so a request for a missing org returns
    # 404 consistently, even when the caller is not a member.
    org = get_identity_store().get_organization(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="organization not found")

    # Verify membership
    if not get_identity_store().is_org_member(user_id, org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    return OrgResponse(
        id=org.id,
        name=org.name,
        created_by_user_id=org.created_by_user_id,
        created_at=org.created_at,
    )


@router.delete("/orgs/{org_id}", status_code=204)
async def delete_organization(
    org_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> None:
    """Permanently delete an organization and all its resources.

    Cascading deletion removes all memberships, projects, API keys,
    and user_selections associated with the org. Only the org owner
    or an env-backed admin/operator may delete an org.

    This is a destructive operation and cannot be undone.
    """
    role, user_id, _org_id, _project_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    store = get_identity_store()
    org = store.get_organization(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="organization not found")

    # Enforce ownership: env-backed admins/operators retain all-access;
    # SaaS-scoped keys must be the org creator.
    if (role not in (UserRole.ADMIN, UserRole.OPERATOR) or _org_id) and org.created_by_user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Only the organization owner can delete it",
        )

    store.delete_organization(org_id)

    log_job_event(
        actor=user_id,
        action="org_delete",
        job_id="saas",
        outcome="success",
        details={"org_id": org_id, "org_name": org.name},
    )


# ═══════════════════════════════════════════════════════════════════════
# Project Management
# ═══════════════════════════════════════════════════════════════════════


class ProjectCreateRequest(BaseModel):
    """Request to create a new project within an organization."""

    org_id: str = Field(..., description="Parent organization ID")
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

    store.delete_project(project_id)

    log_job_event(
        actor=user_id,
        action="project_delete",
        job_id="saas",
        outcome="success",
        details={"project_id": project_id, "org_id": project.org_id, "project_name": project.name},
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
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> None:
    """Remove a member from an organization (admin/operator only).

    The caller must be a member of the target membership's organization.
    Env-backed admins and env-backed operators (no org scope) retain
    all-access, matching the ``can_access_scoped_resource`` bypass.
    Without this check, a persistent WRITE key from Org A could remove
    any member from Org B by guessing/obtaining a ``membership_id``.
    """
    role, user_id, org_id, _project_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    membership = get_identity_store().get_membership(membership_id)
    if not membership:
        raise HTTPException(status_code=404, detail="membership not found")

    # Env-backed admins and operators retain all-access (no org scope).
    # For SaaS-scoped keys, the caller MUST be a member of the target
    # membership's org.
    if (
        role != UserRole.ADMIN
        and (role != UserRole.OPERATOR or org_id)
        and not get_identity_store().is_org_member(user_id, membership.org_id)
    ):
        log_job_event(
            actor=user_id,
            action="member_remove",
            job_id="saas",
            outcome="denied",
            details={
                "membership_id": membership_id,
                "org_id": membership.org_id,
                "reason": "not_org_member",
            },
        )
        raise HTTPException(status_code=403, detail="not a member of this organization")

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
# Email Verification
# ═══════════════════════════════════════════════════════════════════════


class EmailVerificationSendResponse(BaseModel):
    """Response for requesting email verification."""

    message: str = "Verification email sent. Check your inbox."
    user_id: str


class EmailVerifyRequest(BaseModel):
    """Request body for verifying an email address."""

    token: str = Field(..., description="Verification token (from email link)")


class EmailVerifyResponse(BaseModel):
    """Response after successful email verification."""

    verified: bool
    message: str


class EmailVerificationStatusResponse(BaseModel):
    """Email verification status for the authenticated user."""

    email: str
    email_verified: bool
    email_verified_at: str | None


@router.post("/email-verification/send", status_code=200)
async def send_email_verification(
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> EmailVerificationSendResponse:
    """Create an email verification token for the authenticated user.

    In the current MVP the token is logged rather than sent via SMTP.
    A real email-sending integration (SendGrid, SES, etc.) will replace
    this when the project's email transport is wired in.

    Rate-limited to 3 requests per 5 minutes per user to prevent abuse.
    """
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    # Rate limit: 3 email verification sends per 5 minutes
    _check_rate_limit(
        _EMAIL_VERIFICATION_LIMITERS, user_id, max_requests=3, window_seconds=300.0, action="email verification send"
    )

    store = get_identity_store()
    user = store.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if user.email_verified_at is not None:
        return EmailVerificationSendResponse(
            message="Email is already verified.",
            user_id=user_id,
        )

    store.create_email_verification_token(user_id)
    logger.debug("Email verification token created for %s", user.email)

    log_job_event(
        actor=user_id,
        action="email_verification_sent",
        job_id="saas",
        outcome="success",
        details={"email": user.email},
    )

    return EmailVerificationSendResponse(user_id=user_id)


@router.post("/email-verification/verify", status_code=200)
async def verify_email(
    body: EmailVerifyRequest,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
    request: Request,
) -> EmailVerifyResponse:
    """Verify an email address using a verification token.

    Rate-limited to 5 attempts per 5 minutes per IP address to prevent
    brute-force guessing of verification tokens.
    """
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    # Rate limit: 5 email verification attempts per 5 minutes per IP
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(
        _EMAIL_VERIFICATION_CONFIRM_LIMITERS, client_ip, max_requests=5, window_seconds=300.0, action="email verification"
    )

    store = get_identity_store()
    user = store.verify_email_token(body.token)
    if user is None:
        log_job_event(
            actor=user_id,
            action="email_verification_failed",
            job_id="saas",
            outcome="failure",
            details={"reason": "invalid_or_expired_token"},
        )
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    log_job_event(
        actor=user_id,
        action="email_verified",
        job_id="saas",
        outcome="success",
    )

    return EmailVerifyResponse(verified=True, message="Email verified successfully")


@router.get("/email-verification/status", response_model=EmailVerificationStatusResponse)
async def email_verification_status(
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> EmailVerificationStatusResponse:
    """Return the email verification status for the authenticated user."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    store = get_identity_store()
    user = store.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    return EmailVerificationStatusResponse(
        email=user.email,
        email_verified=user.email_verified_at is not None,
        email_verified_at=user.email_verified_at,
    )


# ═══════════════════════════════════════════════════════════════════════
# Password Reset
# ═══════════════════════════════════════════════════════════════════════


class PasswordResetRequest(BaseModel):
    """Request body to initiate a password reset."""

    email: str = Field(..., description="Email address for the account to reset")


class PasswordResetResponse(BaseModel):
    """Response after a password reset request."""

    message: str = "If that email exists, a reset link has been sent."


class PasswordResetConfirmRequest(BaseModel):
    """Request body to confirm a password reset with a new password."""

    token: str = Field(..., description="Reset token (from email link)")
    new_password: str = Field(..., min_length=8, description="New password (min 8 characters)")


class PasswordResetConfirmResponse(BaseModel):
    """Response after a successful password reset."""

    message: str = "Password has been reset successfully."


# Rate-limit state for password reset endpoints (in-memory, per-IP).
# Uses a dict of per-IP counters so one user's burst cannot block others.
# ─── Email validation (lightweight, no external dependency) ────────────
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)


def _validate_email(email: str) -> str:
    """Validate and normalize an email address.

    Returns the stripped, lowercased email if valid.
    Raises HTTPException 422 if invalid.
    """
    stripped = email.strip().lower()
    if not stripped or len(stripped) > 254:
        raise HTTPException(status_code=422, detail="Invalid email address")
    if not _EMAIL_RE.match(stripped):
        raise HTTPException(status_code=422, detail="Invalid email address format")
    return stripped


# Rate-limit state for password reset endpoints (in-memory, per-IP).
# Uses a dict of per-IP counters so one user's burst cannot block others.
_PASSWORD_RESET_REQUEST_LIMITERS: dict[str, SlidingWindowCounter] = {}
_PASSWORD_RESET_CONFIRM_LIMITERS: dict[str, SlidingWindowCounter] = {}

# Rate-limit state for email verification (per-user, because the caller
# is authenticated). Prevents a user from spamming the send endpoint.
_EMAIL_VERIFICATION_LIMITERS: dict[str, SlidingWindowCounter] = {}

# Rate-limit state for invitation creation (per-user).
_INVITATION_CREATE_LIMITERS: dict[str, SlidingWindowCounter] = {}

# Rate-limit state for email verification confirm (per-IP, to prevent token brute-forcing).
_EMAIL_VERIFICATION_CONFIRM_LIMITERS: dict[str, SlidingWindowCounter] = {}

# Rate-limit state for signup (per-IP, to prevent account creation spam).
_SIGNUP_LIMITERS: dict[str, SlidingWindowCounter] = {}


def reset_rate_limiters() -> None:
    """Clear all in-memory rate limiter state.

    Called by test fixtures between test runs to prevent rate-limit
    carryover from one test to the next. Not intended for production use.
    """
    _PASSWORD_RESET_REQUEST_LIMITERS.clear()
    _PASSWORD_RESET_CONFIRM_LIMITERS.clear()
    _EMAIL_VERIFICATION_LIMITERS.clear()
    _INVITATION_CREATE_LIMITERS.clear()
    _EMAIL_VERIFICATION_CONFIRM_LIMITERS.clear()
    _SIGNUP_LIMITERS.clear()


# Password strength validation
_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]).{8,128}$")


def _validate_password(password: str) -> str:
    """Validate password strength.

    Requirements:
    - 8-128 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Returns the password if valid.
    Raises HTTPException 422 if invalid.
    """
    if not password or len(password) < 8:
        raise HTTPException(
            status_code=422,
            detail="Password must be at least 8 characters",
        )
    if len(password) > 128:
        raise HTTPException(
            status_code=422,
            detail="Password must be 128 characters or fewer",
        )
    if not _PASSWORD_RE.match(password):
        raise HTTPException(
            status_code=422,
            detail="Password must include uppercase, lowercase, digit, and special character",
        )
    return password


def _check_rate_limit(
    limiters: dict[str, SlidingWindowCounter],
    key: str,
    max_requests: int = 5,
    window_seconds: float = 300.0,
    action: str = "request",
) -> None:
    """Check rate limit for an action by key (IP address or user ID).

    Args:
        limiters: Dict mapping keys to sliding-window counters.
        key: Identifier to rate-limit by (IP address or user ID).
        max_requests: Maximum allowed requests in the window.
        window_seconds: Duration of the sliding window in seconds.
        action: Human-readable action name for log/error messages.

    Raises HTTPException 429 if the limit is exceeded.
    Returns None on success.
    """
    counter = limiters.get(key)
    if counter is None:
        counter = SlidingWindowCounter(max_requests=max_requests, window_seconds=window_seconds)
        limiters[key] = counter
    elif counter.is_expired():
        # Prune expired counters to prevent unbounded memory growth
        del limiters[key]
        counter = SlidingWindowCounter(max_requests=max_requests, window_seconds=window_seconds)
        limiters[key] = counter

    if not counter.allow():
        logger.warning("Rate limit exceeded for %s: key=%s", action, key)
        raise HTTPException(
            status_code=429,
            detail=f"Too many {action}s. Please try again later.",
        )


@router.post("/password-reset/request", status_code=200)
async def request_password_reset(
    body: PasswordResetRequest,
    request: Request,
) -> PasswordResetResponse:
    """Request a password reset token for the given email.

    Always returns 200 to prevent email enumeration. If the email exists,
    a reset token is created and logged.

    Rate-limited to 5 requests per 5 minutes per IP address.
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(
        _PASSWORD_RESET_REQUEST_LIMITERS, client_ip, max_requests=5, window_seconds=300.0, action="password reset request"
    )

    validated_email = _validate_email(body.email)

    store = get_identity_store()
    user = store.get_user_by_email(validated_email)
    if user is not None:
        store.create_password_reset_token(user.id)
        logger.debug("Password reset token created for %s", body.email)
        log_job_event(
            actor=user.id,
            action="password_reset_requested",
            job_id="saas",
            outcome="success",
            details={"email": body.email},
        )
    else:
        logger.info("Password reset requested for unknown email: %s", body.email)

    return PasswordResetResponse()


@router.post("/password-reset/reset", status_code=200)
async def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    request: Request,
) -> PasswordResetConfirmResponse:
    """Confirm a password reset using the token and set a new password.

    Rate-limited to 10 attempts per 5 minutes per IP address to prevent
    brute-force guessing of reset tokens.
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(
        _PASSWORD_RESET_CONFIRM_LIMITERS, client_ip, max_requests=10, window_seconds=300.0, action="password reset confirmation"
    )

    # Validate new password strength
    _validate_password(body.new_password)

    from app.saas.service import hash_password

    store = get_identity_store()
    new_hash = hash_password(body.new_password)
    success = store.consume_password_reset_token(body.token, new_hash)
    if not success:
        log_job_event(
            actor="unknown",
            action="password_reset_failed",
            job_id="saas",
            outcome="failure",
            details={"reason": "invalid_or_expired_token"},
        )
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    log_job_event(
        actor="resolved-from-token",
        action="password_reset_completed",
        job_id="saas",
        outcome="success",
    )

    return PasswordResetConfirmResponse()


# ═══════════════════════════════════════════════════════════════════════
# Team Invitations
# ═══════════════════════════════════════════════════════════════════════


class InvitationCreateRequest(BaseModel):
    """Request to invite a user to an organization."""

    email: str = Field(..., description="Email address to invite")
    role: str = Field("member", description="Role to assign (member/admin/viewer)")


class InvitationResponse(BaseModel):
    """Invitation details."""

    id: str
    org_id: str
    invited_email: str
    invited_by_user_id: str
    role: str
    status: str
    created_at: str
    expires_at: str


class InvitationListResponse(BaseModel):
    """List of invitations."""

    items: list[InvitationResponse]
    total: int


class InvitationRespondRequest(BaseModel):
    """Request to accept or decline an invitation."""

    accept: bool = Field(..., description="True to accept, False to decline")


class InvitationRespondResponse(BaseModel):
    """Response after responding to an invitation."""

    id: str
    status: str
    message: str


class PendingInvitationResponse(BaseModel):
    """Pending invitation details (returned to the invited user)."""

    id: str
    org_id: str
    invited_email: str
    role: str
    created_at: str
    expires_at: str


@router.post("/orgs/{org_id}/invitations", status_code=201, response_model=InvitationResponse)
async def create_invitation(
    org_id: str,
    body: InvitationCreateRequest,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> InvitationResponse:
    """Create a team invitation for an organization.

    Requires admin/operator role in the org.
    Rate-limited to 10 invitations per 5 minutes per user to prevent spam.
    """
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    # Rate limit: 10 invitation creates per 5 minutes per user
    _check_rate_limit(_INVITATION_CREATE_LIMITERS, user_id, max_requests=10, window_seconds=300.0, action="invitation creation")

    # Validate email format
    validated_email = _validate_email(body.email)

    store = get_identity_store()

    # Verify the caller is a member of the org
    if not store.is_org_member(user_id, org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    # Verify the org exists
    org = store.get_organization(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="organization not found")

    invitation = store.create_team_invitation(
        org_id=org_id,
        invited_email=validated_email,
        invited_by_user_id=user_id,
        role=body.role,
    )

    log_job_event(
        actor=user_id,
        action="invitation_created",
        job_id="saas",
        outcome="success",
        details={"org_id": org_id, "invited_email": validated_email, "role": body.role},
    )

    return InvitationResponse(**invitation)


@router.get("/orgs/{org_id}/invitations", response_model=InvitationListResponse)
async def list_org_invitations(
    org_id: str,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    status: str | None = None,
) -> InvitationListResponse:
    """List invitations for an organization."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    store = get_identity_store()

    if not store.is_org_member(user_id, org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    invitations = store.list_org_invitations(org_id, status=status)
    return InvitationListResponse(
        items=[InvitationResponse(**inv) for inv in invitations],
        total=len(invitations),
    )


@router.post("/invitations/{invitation_id}/respond", response_model=InvitationRespondResponse)
async def respond_to_invitation(
    invitation_id: str,
    body: InvitationRespondRequest,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> InvitationRespondResponse:
    """Accept or decline a team invitation."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    store = get_identity_store()
    result = store.respond_to_invitation(invitation_id, accept=body.accept)
    if result is None:
        raise HTTPException(status_code=404, detail="Invitation not found or already responded to")

    status = "accepted" if body.accept else "declined"
    log_job_event(
        actor=user_id,
        action=f"invitation_{status}",
        job_id="saas",
        outcome="success",
        details={"invitation_id": invitation_id, "org_id": result["org_id"]},
    )

    return InvitationRespondResponse(
        id=invitation_id,
        status=result["status"],
        message=f"Invitation {result['status']}.",
    )


@router.get("/invitations/pending", response_model=list[PendingInvitationResponse])
async def get_pending_invitations(
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> list[PendingInvitationResponse]:
    """Return pending invitations for the authenticated user's email."""
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    store = get_identity_store()
    user = store.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    invitation = store.get_pending_invitation_by_email(user.email)
    if invitation is None:
        return []

    return [
        PendingInvitationResponse(
            id=invitation["id"],
            org_id=invitation["org_id"],
            invited_email=invitation["invited_email"],
            role=invitation["role"],
            created_at=invitation["created_at"],
            expires_at=invitation["expires_at"],
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════
# Plan & Limits — informational view of the caller's tier. Enforcement
# of tier limits lives in ``app.plan_enforcer`` (wired into job creation
# and other metered routes via ``require_plan_limit``); this endpoint
# only reports the current tier and its derived limits to the UI.
# ═══════════════════════════════════════════════════════════════════════


class PlanTier(str):
    """Subscription plan tiers."""

    __slots__ = ()

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# Per-tier feature flags and teammate/project caps. Usage limits
# (jobs/pages/scheduled/api) are sourced from ``app.plan_enforcer`` so
# there is a single source of truth for the numeric limits.
_TIER_FEATURES: dict[str, list[str]] = {
    "free": ["basic_scraping", "scheduled_jobs", "aup_compliance"],
    "starter": ["basic_scraping", "scheduled_jobs", "aup_compliance", "csv_export", "json_export"],
    "pro": [
        "basic_scraping",
        "scheduled_jobs",
        "aup_compliance",
        "csv_export",
        "json_export",
        "excel_export",
        "workflow_replay",
        "auth_profiles",
    ],
    "enterprise": [
        "basic_scraping",
        "scheduled_jobs",
        "aup_compliance",
        "csv_export",
        "json_export",
        "excel_export",
        "workflow_replay",
        "auth_profiles",
        "priority_support",
        "custom_retention",
    ],
}

_TIER_TEAMMATES: dict[str, int] = {
    "free": 2,
    "starter": 5,
    "pro": 25,
    "enterprise": -1,
}

_TIER_PROJECTS: dict[str, int] = {
    "free": 2,
    "starter": 10,
    "pro": 100,
    "enterprise": -1,
}


# Maximum API-key scope grantable per org membership role. Used by
# ``create_api_key`` to enforce the privilege boundary: a viewer-level
# member must not be able to mint an admin-scope key (which maps to
# ``UserRole.ADMIN`` → global all-access). Kept at module level so the
# policy is testable in isolation.
_MAX_KEY_SCOPE_FOR_ROLE: dict[str, str] = {
    "owner": "admin",
    "admin": "admin",
    "member": "write",
    "viewer": "read",
}

# Rank order for scope comparison (higher = more privileged).
_SCOPE_RANK: dict[str, int] = {
    "read": 0,
    "write": 1,
    "admin": 2,
}


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
    scope: Literal["read", "write", "admin"] = Field(
        "read",
        description="Key scope: read, write, or admin",
    )


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
    # ``body.scope`` is constrained to Literal["read","write","admin"] so
    # the lookup is always success; the surrounding code is kept defensive
    # in case the validator is ever loosened.
    raw_scope = body.scope.lower()
    scope = scope_map[raw_scope]

    # Privilege boundary: the granted key scope MUST NOT exceed the
    # caller's own membership role in the target org. Without this, a
    # viewer-level member who holds a WRITE key (→ OPERATOR) could
    # issue an admin-scope key for any project in the org, and because
    # UserRole.ADMIN maps to global all-access, that key would grant
    # access to every tenant's data.
    _caller_memberships = get_identity_store().list_user_memberships(user_id)
    _caller_role_in_org = next(
        (m.role for m in _caller_memberships if m.org_id == project.org_id and m.is_active()),
        None,
    )
    if _caller_role_in_org is None and not _caller_memberships:
        logger.warning(
            "create_api_key: caller=%s has zero memberships — env-backed admin or identity-store issue",
            user_id,
        )
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


@router.get("/plan", response_model=PlanInfoResponse)
async def get_plan_info(
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> PlanInfoResponse:
    """Return the current user's plan and limits.

    Looks up the caller's tier via the billing service (falling back to
    ``free`` when billing is unconfigured) and derives the usage limits
    from the same ``app.plan_enforcer`` source of truth that enforces
    them at job-creation time, so the informational view and the
    enforcement gate can never drift.
    """
    _role, user_id = auth
    tier = get_user_tier(user_id) if user_id else "free"
    limits = get_plan_limits(tier)
    return PlanInfoResponse(
        tier=tier,
        max_jobs=limits.get(UsageType.JOB_CREATED.value, 10),
        max_scrapes=limits.get(UsageType.PAGE_FETCHED.value, 1000),
        max_teammates=_TIER_TEAMMATES.get(tier, 2),
        max_projects=_TIER_PROJECTS.get(tier, 2),
        features=_TIER_FEATURES.get(tier, _TIER_FEATURES["free"]),
    )


class UsageSummaryResponse(BaseModel):
    """Current usage summary for the authenticated user."""

    jobs_created: int = 0
    pages_fetched: int = 0
    scheduled_jobs: int = 0
    ai_structuring: int = 0
    api_requests: int = 0


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage_summary(
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> UsageSummaryResponse:
    """Return current usage counters for the authenticated user.

    Used by the frontend billing page to show how much of the plan
    quota has been consumed (e.g. "3 of 10 jobs used this month").
    """
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    try:
        from app.utils.usage_ledger import UsageType, get_usage_ledger

        ledger = get_usage_ledger()
        jobs_usage = ledger.get_usage(user_id, UsageType.JOB_CREATED)
        pages_usage = ledger.get_usage(user_id, UsageType.PAGE_FETCHED)
        scheduled_usage = ledger.get_usage(user_id, UsageType.SCHEDULED_JOB)
        ai_usage = ledger.get_usage(user_id, UsageType.AI_STRUCTURING)
        api_usage = ledger.get_usage(user_id, UsageType.API_REQUEST)

        return UsageSummaryResponse(
            jobs_created=sum(r.quantity for r in jobs_usage),
            pages_fetched=sum(r.quantity for r in pages_usage),
            scheduled_jobs=sum(r.quantity for r in scheduled_usage),
            ai_structuring=sum(r.quantity for r in ai_usage),
            api_requests=sum(r.quantity for r in api_usage),
        )
    except (ImportError, RuntimeError, ValueError) as exc:
        logger.warning("Failed to read usage summary: %s", exc)
        return UsageSummaryResponse()
