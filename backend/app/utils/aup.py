"""AUP (Acceptable Use Policy) enforcement utilities.

Provides a FastAPI dependency that checks whether the authenticated
user has accepted the current AUP version before allowing protected
actions. This is the enforcement counterpart to the AUP acceptance
endpoints in ``app.saas.router``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request

from app.saas import CURRENT_AUP_VERSION
from app.saas.identity_store import get_identity_store
from app.utils.rbac import UserRole, resolve_auth_context

logger = logging.getLogger(__name__)


async def require_aup_accepted(request: Request) -> dict[str, Any]:
    """FastAPI dependency that enforces AUP acceptance.

    Usage::

        @router.post("/api/jobs")
        async def create_job(
            ...,
            _aup: dict = Depends(require_aup_accepted),
        ):
            ...

    Raises:
        HTTPException(403): if the user has not accepted the current AUP.
        HTTPException(401): if the user is not authenticated.

    Silent passthrough for env-backed admin/operator keys (no AUP required).
    """
    try:
        ctx = resolve_auth_context(request)
        user_id = ctx.user_id
        role = ctx.role
    except HTTPException:
        # If auth hasn't resolved yet, skip AUP check (the route's own
        # auth dependency will handle it)
        return {"skipped": True}

    # Env-backed admins and operators bypass AUP enforcement
    # (they are infra/ops, not end-users). Session-cookie admins are
    # real SaaS users (an admin role within a persistent identity)
    # and must accept the policy like any other end-user.
    if role in (UserRole.ADMIN, UserRole.OPERATOR) and not ctx.org_id and ctx.source != "session":
        return {"skipped": True, "role": role.value, "user_id": user_id}

    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required for AUP check.")

    # Fetch the user's AUP status from the identity store.
    user = get_identity_store().get_user(user_id)

    if user is None:
        # Shadow user (API key without SaaS account) — skip AUP
        return {"skipped": True, "user_id": user_id, "role": role.value}

    accepted_at = user.aup_accepted_at
    accepted_version = user.aup_version_accepted

    requires_acceptance = accepted_at is None or accepted_version != CURRENT_AUP_VERSION

    if requires_acceptance:
        logger.warning(
            "AUP not accepted: user=%s role=%s accepted=%s version=%s current=%s",
            user_id,
            role.value,
            accepted_at,
            accepted_version,
            CURRENT_AUP_VERSION,
        )
        raise HTTPException(
            status_code=403,
            detail=(
                f"You must accept the Acceptable Use Policy (version {CURRENT_AUP_VERSION}) "
                "before performing this action. "
                "Use POST /api/saas/aup/accept to accept."
            ),
        )

    return {
        "accepted": True,
        "user_id": user_id,
        "role": role.value,
        "aup_version": accepted_version,
    }
