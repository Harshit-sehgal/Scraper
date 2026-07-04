"""Organization CRUD and team management endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.audit_logger import log_job_event
from app.saas.identity_store import get_identity_store
from app.saas.models import (
    Membership,
    MembershipRole,
    Organization,
)
from app.utils.rbac import UserRole, require_principal, require_role_with_user

from ._common import (
    _INVITABLE_ROLES,
    _INVITATION_CREATE_LIMITERS,
    _check_rate_limit,
    _env_backed_all_access,
    _membership_rank,
    _validate_email,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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

    id: str = Field(max_length=64)
    name: str = Field(max_length=255)
    created_by_user_id: str = Field(max_length=64)
    created_at: str = Field(max_length=64)


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
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> OrgResponse:
    """Get a single organization by ID."""
    _role, user_id, auth_org_id, _project_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    if auth_org_id and auth_org_id != org_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access forbidden")

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

    if _org_id and _org_id != org_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access forbidden")

    store = get_identity_store()
    org = store.get_organization(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="organization not found")

    # Enforce ownership: scoped keys must be the org creator. Env-backed
    # admins/operators retain all-access ONLY when
    # ENABLE_OPERATOR_CROSS_TENANT is explicitly True (issue #135).
    if not _env_backed_all_access(role, _org_id):
        if _org_id and _org_id != org_id:
            raise HTTPException(status_code=403, detail="Cross-tenant access forbidden")
        if org.created_by_user_id != user_id:
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
# Membership / Team Management
# ═══════════════════════════════════════════════════════════════════════


class MemberInviteRequest(BaseModel):
    """Request to invite a user to an organization."""

    org_id: str = Field(..., max_length=64, description="Organization ID")
    email: str = Field(..., max_length=320, description="Email of the user to invite")
    role: str = Field("member", max_length=32, description="Role to assign (owner/admin/member/viewer)")


class MembershipResponse(BaseModel):
    """Membership details."""

    membership_id: str = Field(max_length=64)
    user_id: str = Field(max_length=64)
    org_id: str = Field(max_length=64)
    role: str = Field(max_length=32)
    created_at: str = Field(max_length=64)


@router.get("/orgs/{org_id}/members", response_model=list[MembershipResponse])
async def list_org_members(
    org_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> list[MembershipResponse]:
    """List all active members of an organization."""
    _role, user_id, auth_org_id, _project_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    if auth_org_id and auth_org_id != org_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access forbidden")

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

    # Env-backed admins and operators retain all-access ONLY when
    # ENABLE_OPERATOR_CROSS_TENANT is explicitly True (issue #135).
    # For SaaS-scoped keys, the caller MUST be a member of the target
    # membership's org.
    store = get_identity_store()
    if not _env_backed_all_access(role, org_id) and not store.is_org_member(user_id, membership.org_id):
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

    # FU-2026-07-05 (HIGH privilege-destruction fix): the caller's
    # membership rank must be >= the target's. Without this, a viewer-
    # membership OPERATOR-keyholder could remove co-org admins/owners —
    # gating on ``is_org_member`` alone isn't sufficient. Env-backed
    # all-access principals (above) are exempt.
    if not _env_backed_all_access(role, org_id):
        caller = store.get_org_membership(user_id, membership.org_id)
        caller_rank = _membership_rank(caller.role) if caller else -1
        target_rank = _membership_rank(membership.role)
        if caller_rank < target_rank:
            log_job_event(
                actor=user_id,
                action="member_remove",
                job_id="saas",
                outcome="denied",
                details={
                    "membership_id": membership_id,
                    "org_id": membership.org_id,
                    "reason": "insufficient_rank",
                    "caller_rank": caller_rank,
                    "target_rank": target_rank,
                },
            )
            raise HTTPException(
                status_code=403,
                detail="cannot remove a member whose role outranks yours",
            )

    # Cannot remove self if the last owner
    if membership.role == MembershipRole.OWNER and membership.user_id == user_id:
        # Check if there's another owner
        all_members = store.list_org_memberships(membership.org_id)
        owners = [m for m in all_members if m.role == MembershipRole.OWNER and m.id != membership_id]
        if not owners:
            raise HTTPException(status_code=409, detail="cannot remove the last owner")

    store.remove_membership(membership_id)
    log_job_event(
        actor=user_id,
        action="member_remove",
        job_id="saas",
        outcome="success",
        details={"membership_id": membership_id, "org_id": membership.org_id},
    )


# ═══════════════════════════════════════════════════════════════════════
# Team Invitations
# ═══════════════════════════════════════════════════════════════════════


class InvitationCreateRequest(BaseModel):
    """Request to invite a user to an organization."""

    email: str = Field(..., max_length=320, description="Email address to invite")
    # FU-2026-07-05 (CRITICAL org-takeover fix): ``role`` is constrained
    # to the invitable allowlist at the pydantic layer so an attacker
    # cannot pass ``"owner"`` (or any future role) through the body. The
    # route additionally checks the inviter's membership rank.
    role: str = Field("member", max_length=32, description="Role to assign (member/admin/viewer)")


class InvitationResponse(BaseModel):
    """Invitation details."""

    id: str = Field(max_length=64)
    org_id: str = Field(max_length=64)
    invited_email: str = Field(max_length=320)
    invited_by_user_id: str = Field(max_length=64)
    role: str = Field(max_length=32)
    status: str = Field(max_length=32)
    created_at: str = Field(max_length=64)
    expires_at: str = Field(max_length=64)


class InvitationListResponse(BaseModel):
    """List of invitations."""

    items: list[InvitationResponse]
    total: int


class InvitationRespondRequest(BaseModel):
    """Request to accept or decline an invitation."""

    accept: bool = Field(..., description="True to accept, False to decline")


class InvitationRespondResponse(BaseModel):
    """Response after responding to an invitation."""

    id: str = Field(max_length=64)
    status: str = Field(max_length=32)
    message: str = Field(max_length=1024)


class PendingInvitationResponse(BaseModel):
    """Pending invitation details (returned to the invited user)."""

    id: str = Field(max_length=64)
    org_id: str = Field(max_length=64)
    invited_email: str = Field(max_length=320)
    role: str = Field(max_length=32)
    created_at: str = Field(max_length=64)
    expires_at: str = Field(max_length=64)


@router.post("/orgs/{org_id}/invitations", status_code=201, response_model=InvitationResponse)
async def create_invitation(
    org_id: str,
    body: InvitationCreateRequest,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> InvitationResponse:
    """Create a team invitation for an organization.

    Requires admin/operator role in the org.
    Rate-limited to 10 invitations per 5 minutes per user to prevent spam.
    """
    _role, user_id, auth_org_id, _project_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    if auth_org_id and auth_org_id != org_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access forbidden")

    # Rate limit: 10 invitation creates per 5 minutes per user
    _check_rate_limit(_INVITATION_CREATE_LIMITERS, user_id, max_requests=10, window_seconds=300.0, action="invitation creation")

    # Validate email format
    validated_email = _validate_email(body.email)

    store = get_identity_store()

    # Verify the caller is a member of the org
    if not store.is_org_member(user_id, org_id):
        raise HTTPException(status_code=403, detail="not a member of this organization")

    # FU-2026-07-05 — CRITICAL org-takeover mitigation:
    # ``role`` from body must be on the invitable allowlist. "owner" is
    # never invitable (ownership is only established at org creation or
    # via explicit owner-transfer). A viewer/member cannot invite with
    # role="admin" — only an OWNER may grant ADMIN. Without this check a
    # viewer-membership attacker could invite their own second email as
    # "owner" and on acceptance take over the org (identity_store inserts
    # the role verbatim into memberships).
    normalised_role = (body.role or "").strip().lower()
    if normalised_role not in _INVITABLE_ROLES:
        raise HTTPException(
            status_code=422,
            detail="role must be one of member/admin/viewer",
        )

    caller_membership = store.get_org_membership(user_id, org_id)
    if caller_membership is None:
        # is_org_member passed above but get_org_membership returned None
        # (membership soft-removed between calls) — fail closed.
        raise HTTPException(status_code=403, detail="not a member of this organization")

    caller_rank = _membership_rank(caller_membership.role)
    if caller_rank < _membership_rank(MembershipRole.ADMIN):
        # members/viewers may only invite at their own tier or below;
        # admin-granting requires caller to be OWNER.
        if normalised_role == "admin":
            raise HTTPException(
                status_code=403,
                detail="only an owner may invite an admin",
            )
        # viewers/members may not invite at a tier above their own
        if _membership_rank(normalised_role) > caller_rank:
            raise HTTPException(
                status_code=403,
                detail="cannot invite a member role above your own",
            )

    # Verify the org exists
    org = store.get_organization(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="organization not found")

    invitation = store.create_team_invitation(
        org_id=org_id,
        invited_email=validated_email,
        invited_by_user_id=user_id,
        role=normalised_role,
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
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    status: str | None = None,
) -> InvitationListResponse:
    """List invitations for an organization."""
    _role, user_id, auth_org_id, _project_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    if auth_org_id and auth_org_id != org_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access forbidden")

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
    result = store.respond_to_invitation(
        invitation_id,
        accept=body.accept,
        requesting_user_id=user_id,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=("Invitation not found, expired, or not addressed to this user"),
        )

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
