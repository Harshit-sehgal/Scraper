"""Self-service user signup and password reset endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.audit_logger import log_job_event
from app.saas.identity_store import IdentityStoreError, get_identity_store
from app.saas.service import SignupService
from app.utils.log_redaction import redact_pii

from ._common import (
    _PASSWORD_RESET_CONFIRM_LIMITERS,
    _PASSWORD_RESET_REQUEST_LIMITERS,
    _SIGNUP_LIMITERS,
    _check_rate_limit,
    _validate_email,
    _validate_password,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class SignupRequest(BaseModel):
    """Request body for self-service user signup."""

    email: str = Field(..., max_length=320, description="User email (becomes login)")
    password: str = Field(..., min_length=8, max_length=128, description="Minimum 8 characters")
    display_name: str = Field("", max_length=255, description="Optional human-readable name")
    org_name: str | None = Field(None, max_length=255, description="Optional organization name")
    project_name: str | None = Field(None, max_length=255, description="Optional project name")


class SignupResponse(BaseModel):
    """Response after successful signup."""

    user_id: str = Field(max_length=64)
    email: str = Field(max_length=320)
    organization_id: str = Field(max_length=64)
    project_id: str = Field(max_length=64)
    message: str = Field(default="Account created successfully. Please accept the AUP.", max_length=1024)


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
        # FU-2026-07-05 (F-DISC-002 email enumeration): IdentityStoreError
        # carries the raw email in its message ("user with email '...'
        # already exists"), and surfacing that in a 409 response lets an
        # attacker harvest registered email addresses. Instead return a
        # generic conflict that discloses nothing about which email is
        # already registered. Rate-limiting (3/5min per IP) is a
        # backstop but not sufficient — a distributed enumeration
        # campaign with many rotating IPs needs zero signal, not a slow
        # one.
        logger.debug("Signup conflict for email=%r", redact_pii(validated_email))
        raise HTTPException(
            status_code=409,
            detail="Cannot complete signup at this time. Please try a different email address or contact support.",
        ) from exc
    except ValueError as exc:
        logger.info("Signup validation failed: %s", exc)
        raise HTTPException(status_code=422, detail="Invalid signup information") from exc

    log_job_event(
        actor=result.user.id,
        action="user_signup",
        job_id="signup",
        outcome="success",
        details={"email": redact_pii(result.user.email), "org_id": result.organization.id, "project_id": result.project.id},
    )

    return SignupResponse(
        user_id=result.user.id,
        email=result.user.email,
        organization_id=result.organization.id,
        project_id=result.project.id,
    )


# ═══════════════════════════════════════════════════════════════════════
# Password Reset
# ═══════════════════════════════════════════════════════════════════════


class PasswordResetRequest(BaseModel):
    """Request body to initiate a password reset."""

    email: str = Field(..., max_length=320, description="Email address for the account to reset")


class PasswordResetResponse(BaseModel):
    """Response after a password reset request."""

    message: str = Field(default="If that email exists, a reset link has been sent.", max_length=1024)


class PasswordResetConfirmRequest(BaseModel):
    """Request body to confirm a password reset with a new password."""

    token: str = Field(..., max_length=512, description="Reset token (from email link)")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password (min 8 characters)")


class PasswordResetConfirmResponse(BaseModel):
    """Response after a successful password reset."""

    message: str = Field(default="Password has been reset successfully.", max_length=1024)


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
        logger.debug("Password reset token created for %s", redact_pii(body.email))
        log_job_event(
            actor=user.id,
            action="password_reset_requested",
            job_id="saas",
            outcome="success",
            details={"email": redact_pii(body.email)},
        )
    else:
        # Avoid logging the user-supplied email at INFO — it lands in
        # aggregators, SIEM, and long-lived backups as PII.  The
        # audit log_job_event above also deliberately omits the email.
        logger.info("Password reset requested for unknown account")

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
