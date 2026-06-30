"""AUP (Acceptable Use Policy) acceptance endpoints."""

from __future__ import annotations

import logging
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.audit_logger import log_job_event
from app.saas import CURRENT_AUP_VERSION
from app.saas.identity_store import IdentityStoreError, get_identity_store
from app.utils.log_redaction import redact_pii
from app.utils.rbac import UserRole, require_role_with_user

logger = logging.getLogger(__name__)

router = APIRouter()


class AupAcceptRequest(BaseModel):
    """Request body for recording AUP acceptance."""

    aup_version: str = Field(
        CURRENT_AUP_VERSION,
        max_length=64,
        description="AUP version the user accepted (defaults to the current version).",
    )


class AupStatusResponse(BaseModel):
    """Response body for AUP status / acceptance."""

    user_id: str = Field(max_length=64)
    aup_accepted_at: str | None = Field(default=None, max_length=64)
    aup_version_accepted: str | None = Field(default=None, max_length=64)
    requires_acceptance: bool
    current_aup_version: str = Field(max_length=64)


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
        logger.debug("AUP user lookup failed for %s: %s", redact_pii(str(user_id)), exc)
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
