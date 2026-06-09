"""Role-Based Access Control (RBAC) Module — DataForge Scraper.

Enforces administrative, operator, and user privilege boundaries.
"""

import hashlib
import logging
import secrets
from enum import StrEnum

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"


def _fingerprint_key(key: str) -> str:
    """Derive a stable, non-reversible user identity from an API key.

    Uses SHA-256 to produce a fingerprint that can be used as a user ID
    without exposing the raw key. The fingerprint is deterministic — the
    same key always produces the same identity.
    """
    if not key:
        return ""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def get_current_user(request: Request) -> tuple[UserRole, str]:
    """Extract role and user identity from the request.

    Returns a tuple of (role, user_id) where user_id is a fingerprint
    of the API key used for authentication. This enables data isolation
    by allowing jobs to be scoped to the creating user.
    """
    from app.config import settings

    # 1. Read headers
    api_key_header = request.headers.get("X-API-Key", "")
    auth_header = request.headers.get("Authorization", "")

    provided_token = ""  # nosec B105
    if auth_header.startswith("Bearer "):
        provided_token = auth_header[7:]

    # Helper to check if a key matches safely
    def is_match(provided: str, expected: str) -> bool:
        if not expected or not provided:
            return False
        return secrets.compare_digest(provided, expected)

    # 2. Match Admin Role
    admin_key_header = request.headers.get("X-Admin-Key", "")
    if (
        is_match(api_key_header, settings.ADMIN_API_KEY)
        or is_match(provided_token, settings.ADMIN_API_KEY)
        or is_match(admin_key_header, settings.ADMIN_API_KEY)
    ):
        return UserRole.ADMIN, _fingerprint_key(settings.ADMIN_API_KEY)

    # 3. Match Operator Role
    operator_key = getattr(settings, "OPERATOR_API_KEY", "")
    if is_match(api_key_header, operator_key) or is_match(provided_token, operator_key):
        return UserRole.OPERATOR, _fingerprint_key(operator_key)

    # 4. Match User Role
    if is_match(api_key_header, settings.API_KEY) or is_match(provided_token, settings.API_KEY):
        return UserRole.USER, _fingerprint_key(settings.API_KEY)

    # 5. In development with no configured keys, allow full access (Admin) if explicitly permitted
    if (
        settings.ENV.lower() == "development"
        and settings.ALLOW_INSECURE_DEV_AUTH
        and not settings.API_KEY
        and not settings.ADMIN_API_KEY
    ):
        return UserRole.ADMIN, "dev-admin"

    # 6. Fallback / Unauthenticated
    raise HTTPException(
        status_code=403,
        detail="Invalid or missing API credentials. Provide X-API-Key or Authorization Bearer token.",
    )


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
