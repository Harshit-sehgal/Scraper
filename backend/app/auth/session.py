"""Session-based authentication for DataForge SaaS.

Stateless session management using HMAC-signed cookies.
Exchanges a valid API key for an HTTP-only session cookie,
removing the need for the browser to hold the raw API key in memory.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from fastapi import Request, Response

logger = logging.getLogger(__name__)

SESSION_COOKIE = "dataforge_session"
SESSION_MAX_AGE = 86400  # 24 hours


def _derive_secret() -> bytes:
    """Derive a deterministic signing key from the configured secret or a default.

    In production, operators MUST set ``DATAFORGE_SESSION_SECRET`` to a
    unique, unpredictable value. The default fallback is derived from
    the admin API key so that two deployments with different admin keys
    get different signing keys — but this is NOT a substitute for an
    explicit secret.
    """
    raw = (settings.SESSION_SECRET or settings.ADMIN_API_KEY or "dataforge-insecure-dev-default").encode("utf-8")
    return hashlib.sha256(raw).digest()


_SIGNING_KEY = _derive_secret()


def _sign(payload: str) -> str:
    """Return an HMAC-SHA256 signature (hex-encoded) for *payload*."""
    return hmac.new(_SIGNING_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _unsign(signed: str) -> str | None:
    """Verify and return the payload from a signed cookie value, or None on failure."""
    try:
        payload, sig = signed.rsplit(".", 1)
    except (ValueError, AttributeError):
        return None
    expected = _sign(payload)
    if not hmac.compare_digest(sig, expected):
        return None
    return payload


def create_session_cookie(role: str) -> str:
    """Create a signed session cookie value embedding the authenticated role."""
    data = json.dumps({"role": role, "iat": int(time.time()), "max_age": SESSION_MAX_AGE}, separators=(",", ":"))
    payload = base64.urlsafe_b64encode(data.encode("utf-8")).decode("ascii").rstrip("=")
    sig = _sign(payload)
    return f"{payload}.{sig}"


def verify_session_cookie(cookie_value: str) -> str | None:
    """Verify a signed session cookie and return the embedded role, or None.

    Also rejects expired sessions.
    """
    payload = _unsign(cookie_value)
    if payload is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(payload + "==")  # padding may have been stripped
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return None

    role: str = data.get("role", "")
    iat: int = data.get("iat", 0)
    max_age: int = data.get("max_age", SESSION_MAX_AGE)

    if not role or time.time() > iat + max_age:
        return None
    return role


def set_session_cookie(response: Response, role: str) -> None:
    """Set the session cookie on *response* for the authenticated *role*."""
    cookie_value = create_session_cookie(role)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=cookie_value,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=settings.ENV.lower() == "production",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Clear the session cookie on *response*."""
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="strict",
        secure=settings.ENV.lower() == "production",
    )


def get_session_role(request: Request) -> str | None:
    """Extract the authenticated role from the session cookie, if valid."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    return verify_session_cookie(cookie)
