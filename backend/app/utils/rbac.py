"""Role-Based Access Control (RBAC) Module — DataForge Scraper.

Enforces administrative, operator, and user privilege boundaries.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"


@dataclass(frozen=True)
class AuthContext:
    """Authenticated request principal resolved from one shared decision path."""

    role: UserRole
    user_id: str
    source: Literal["api_key", "session", "dev"]


def _fingerprint_key(key: str) -> str:
    """Derive a stable, non-reversible user identity from an API key.

    Uses SHA-256 to produce a fingerprint that can be used as a user ID
    without exposing the raw key. The fingerprint is deterministic — the
    same key always produces the same identity.
    """
    if not key:
        return ""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _is_match(provided: str, expected: str) -> bool:
    if not expected or not provided:
        return False
    return secrets.compare_digest(provided, expected)


def _configured_user_id_for_role(role: UserRole) -> str:
    from app.config import settings

    if role == UserRole.ADMIN:
        return _fingerprint_key(settings.ADMIN_API_KEY)
    if role == UserRole.OPERATOR:
        return _fingerprint_key(getattr(settings, "OPERATOR_API_KEY", ""))
    return _fingerprint_key(settings.API_KEY)


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    auth_scheme, _, auth_token = auth_header.partition(" ")
    if auth_scheme.lower() == "bearer":
        return auth_token.strip()
    return ""


def _resolve_api_key_context(request: Request) -> AuthContext | None:
    from app.config import settings

    api_key_header = request.headers.get("X-API-Key", "")
    admin_key_header = request.headers.get("X-Admin-Key", "")
    bearer_token = _extract_bearer_token(request)
    operator_key = getattr(settings, "OPERATOR_API_KEY", "")

    if (
        _is_match(api_key_header, settings.ADMIN_API_KEY)
        or _is_match(bearer_token, settings.ADMIN_API_KEY)
        or _is_match(admin_key_header, settings.ADMIN_API_KEY)
    ):
        return AuthContext(
            role=UserRole.ADMIN,
            user_id=_fingerprint_key(settings.ADMIN_API_KEY),
            source="api_key",
        )
    if _is_match(api_key_header, operator_key) or _is_match(bearer_token, operator_key):
        return AuthContext(
            role=UserRole.OPERATOR,
            user_id=_fingerprint_key(operator_key),
            source="api_key",
        )
    if _is_match(api_key_header, settings.API_KEY) or _is_match(bearer_token, settings.API_KEY):
        return AuthContext(
            role=UserRole.USER,
            user_id=_fingerprint_key(settings.API_KEY),
            source="api_key",
        )
    return None


def _resolve_session_context(request: Request) -> AuthContext | None:
    from app.auth.session import get_session_payload

    cookies = getattr(request, "cookies", {}) or {}
    cookie = cookies.get("dataforge_session")
    if not cookie:
        return None

    payload = get_session_payload(request)
    if payload is None:
        raise HTTPException(status_code=403, detail="Invalid or expired session")

    try:
        role = UserRole(str(payload["role"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=403, detail="Invalid or expired session") from exc

    user_id = str(payload.get("user_id") or "") or _configured_user_id_for_role(role)
    if not user_id:
        raise HTTPException(status_code=403, detail="Invalid or expired session")
    return AuthContext(role=role, user_id=user_id, source="session")


def _resolve_dev_context() -> AuthContext | None:
    from app.config import settings

    if settings.ALLOW_INSECURE_DEV_AUTH and settings.ENV.lower() in {"development", "test"}:
        return AuthContext(role=UserRole.ADMIN, user_id="dev-admin", source="dev")
    return None


def resolve_auth_context(request: Request, *, allow_cookie: bool = True) -> AuthContext:
    """Resolve API-key, bearer, session-cookie, or explicit dev auth.

    This is the single authentication decision engine used by middleware
    and route-level RBAC dependencies. Authorization checks should consume
    the returned role/user identity rather than re-reading headers.
    """
    cached = getattr(getattr(request, "state", None), "auth_context", None)
    if cached is not None and (allow_cookie or cached.source != "session"):
        return cached

    context = _resolve_api_key_context(request)
    if context is None and allow_cookie:
        context = _resolve_session_context(request)
    if context is None:
        context = _resolve_dev_context()

    if context is None:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing authentication. Provide X-API-Key, Authorization Bearer token, or a valid session.",
        )

    state = getattr(request, "state", None)
    if state is not None:
        state.auth_context = context
    return context


def get_current_user(request: Request) -> tuple[UserRole, str]:
    """Extract role and user identity from the request.

    Returns a tuple of (role, user_id) where user_id is a fingerprint
    of the API key used for authentication. This enables data isolation
    by allowing jobs to be scoped to the creating user.
    """
    context = resolve_auth_context(request)
    return context.role, context.user_id


def get_current_role(request: Request) -> UserRole:
    """FastAPI dependency to retrieve and authenticate the active role from request headers.

    Supports standard X-API-Key and Bearer token mappings.
    """
    role, _user_id = get_current_user(request)
    return role


def require_role(allowed_roles: list[UserRole]):
    """FastAPI route guard dependency to enforce role permission boundaries."""

    async def dependency(request: Request):
        role = get_current_role(request)
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied. Required roles: {[r.value for r in allowed_roles]}. Your role: {role.value}.",
            )
        return role

    return dependency


def require_role_with_user(allowed_roles: list[UserRole]):
    """FastAPI route guard that returns both role and user identity.

    Use this dependency when the route needs to enforce data isolation
    by knowing which user created a resource.
    """

    async def dependency(request: Request):
        role, user_id = get_current_user(request)
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied. Required roles: {[r.value for r in allowed_roles]}. Your role: {role.value}.",
            )
        return role, user_id

    return dependency
