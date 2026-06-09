"""Session management router for DataForge SaaS auth.

Provides an API-key-to-session-cookie exchange flow so browsers
never need to hold the raw API key in JavaScript memory.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Request, Response
from fastapi.security import APIKeyHeader

from app.auth.session import (
    clear_session_cookie,
    get_session_role,
    set_session_cookie,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


@router.post("/api/session")
async def create_session(
    response: Response,
    request: Request,
    _api_key: Annotated[str | None, API_KEY_HEADER] = None,
):
    """Create a session cookie by exchanging a valid API key.

    On success, sets an HTTP-only ``dataforge_session`` cookie and returns
    the authenticated role.  The cookie is automatically sent on subsequent
    requests, removing the need for the ``X-API-Key`` header in browser clients.

    The API key can also be provided via the ``Authorization: Bearer`` header
    or the ``X-Admin-Key`` header (for admin-level sessions).
    """
    from app.utils.rbac import get_current_role

    role = get_current_role(request)
    set_session_cookie(response, role.value)

    return {
        "status": "ok",
        "role": role.value,
        "message": "Session cookie set. Future requests will use the cookie automatically.",
    }


@router.delete("/api/session")
async def destroy_session(response: Response):
    """Clear the session cookie, effectively logging out."""
    clear_session_cookie(response)
    return {"status": "ok", "message": "Session cookie cleared."}


@router.get("/api/session/me")
async def get_session(request: Request):
    """Return the current session role if authenticated via cookie."""
    role = get_session_role(request)
    if role is None:
        return {"authenticated": False}
    return {"authenticated": True, "role": role}
