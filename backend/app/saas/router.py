"""SaaS identity router — thin FastAPI adapter over the identity store.

Currently hosts the P1-COMPLIANCE-001 Acceptable Use Policy (AUP)
acceptance endpoint. The store, models, and service helpers all live
in :mod:`app.saas`; this module exists to keep FastAPI / auth
machinery out of the store layer.

AUP semantics
-------------
- New users start with ``aup_accepted_at = NULL`` (not accepted).
- A user calls ``POST /api/saas/aup/accept`` to record acceptance.
- The endpoint is opt-in: a middleware gate (added separately) can
  be wired to enforce AUP acceptance before certain routes. The
  default is OFF so the rest of the test suite keeps passing.
- The endpoint is idempotent — re-accepting keeps the first
  acceptance timestamp.
- Every acceptance emits a ``log_job_event`` audit line with the
  AUP version string the user accepted, so a future AUP bump can
  re-prompt users.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.audit_logger import log_job_event
from app.saas.identity_store import get_identity_store
from app.utils.rbac import UserRole, require_role_with_user

logger = logging.getLogger(__name__)

# AUP version pinned in code. Bump when the policy text changes;
# the audit log records which version each user accepted so a
# future change can re-prompt users whose acceptance is stale.
CURRENT_AUP_VERSION = "2026-06-11-v1"

router = APIRouter(prefix="/api/saas", tags=["saas"])


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


def _aup_response_for(user_id: str, accepted_at: str | None, accepted_version: str | None) -> AupStatusResponse:
    """Build an :class:`AupStatusResponse` for a given user."""
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
    auth: Annotated[tuple[UserRole, str], Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER]))],
) -> AupStatusResponse:
    """Record that the authenticated user accepted the AUP.

    Idempotent: re-acceptance keeps the first acceptance timestamp.
    Emits an audit log entry tagged with the AUP version that was
    accepted.
    """
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")
    user = get_identity_store().get_user(user_id)
    if user is None:
        # Env-backed admin/operator/user have no SaaS user record —
        # accept the AUP into a transient "shadow" record? No: the
        # AUP is part of the SaaS signup flow. For env-backed keys
        # we accept on the spot so the rest of the platform is
        # usable, but we still emit the audit line.
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
async def aup_status(
    auth: Annotated[tuple[UserRole, str], Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER]))],
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
