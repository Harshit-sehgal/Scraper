"""User profile and email verification endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.audit_logger import log_job_event
from app.saas.identity_store import get_identity_store
from app.utils.log_redaction import redact_pii
from app.utils.rbac import UserRole, require_role_with_user

from ._common import (
    _EMAIL_VERIFICATION_CONFIRM_LIMITERS,
    _EMAIL_VERIFICATION_LIMITERS,
    _check_rate_limit,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
# User Profile
# ═══════════════════════════════════════════════════════════════════════


class UserProfileResponse(BaseModel):
    """Public view of a user's profile."""

    user_id: str = Field(max_length=64)
    email: str = Field(max_length=320)
    display_name: str = Field(max_length=255)
    status: str = Field(max_length=32)
    aup_accepted_at: str | None = Field(default=None, max_length=64)
    aup_version_accepted: str | None = Field(default=None, max_length=64)


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
# Email Verification
# ═══════════════════════════════════════════════════════════════════════


class EmailVerificationSendResponse(BaseModel):
    """Response for requesting email verification."""

    message: str = Field(default="Verification email sent. Check your inbox.", max_length=1024)
    user_id: str = Field(max_length=64)


class EmailVerifyRequest(BaseModel):
    """Request body for verifying an email address."""

    token: str = Field(..., max_length=512, description="Verification token (from email link)")


class EmailVerifyResponse(BaseModel):
    """Response after successful email verification."""

    verified: bool
    message: str = Field(max_length=1024)


class EmailVerificationStatusResponse(BaseModel):
    """Email verification status for the authenticated user."""

    email: str = Field(max_length=320)
    email_verified: bool
    email_verified_at: str | None = Field(default=None, max_length=64)


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
    logger.debug("Email verification token created for %s", redact_pii(user.email))

    log_job_event(
        actor=user_id,
        action="email_verification_sent",
        job_id="saas",
        outcome="success",
        details={"email": redact_pii(user.email)},
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
