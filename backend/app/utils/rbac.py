"""
Role-Based Access Control (RBAC) Module — DataForge Scraper.
Enforces administrative, operator, and user privilege boundaries.
"""

from enum import Enum
import logging
import secrets
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"


def get_current_role(request: Request) -> UserRole:
    """
    FastAPI dependency to retrieve and authenticate the active role from request headers.
    Supports standard X-API-Key and Bearer token mappings.
    """
    from app.config import settings

    # 1. Read headers
    api_key_header = request.headers.get("X-API-Key", "")
    auth_header = request.headers.get("Authorization", "")

    provided_token = ""
    if auth_header.startswith("Bearer "):
        provided_token = auth_header[7:]

    # Helper to check if a key matches safely
    def is_match(provided: str, expected: str) -> bool:
        if not expected or not provided:
            return False
        return secrets.compare_digest(provided, expected)

    # 2. Match Admin Role
    # Check X-Admin-Key (legacy operator router compatibility) or X-API-Key or
    # Bearer token
    admin_key_header = request.headers.get("X-Admin-Key", "")
    if (
        is_match(api_key_header, settings.ADMIN_API_KEY)
        or is_match(provided_token, settings.ADMIN_API_KEY)
        or is_match(admin_key_header, settings.ADMIN_API_KEY)
    ):
        return UserRole.ADMIN

    # 3. Match Operator Role
    # operator_api_key defaults to a dedicated operator config if declared,
    # fallback to general API_KEY
    operator_key = getattr(settings, "OPERATOR_API_KEY", "")
    if is_match(api_key_header, operator_key) or is_match(provided_token, operator_key):
        return UserRole.OPERATOR

    # 4. Match User Role
    if is_match(api_key_header, settings.API_KEY) or is_match(provided_token, settings.API_KEY):
        return UserRole.USER

    # 5. In development with no configured keys, allow full access (Admin)
    if settings.ENV.lower() == "development" and not settings.API_KEY and not settings.ADMIN_API_KEY:
        return UserRole.ADMIN

    # 6. Fallback / Unauthenticated
    raise HTTPException(
        status_code=403, detail="Invalid or missing API credentials. Provide X-API-Key or Authorization Bearer token."
    )


def require_role(allowed_roles: list[UserRole]):
    """
    FastAPI route guard dependency to enforce role permission boundaries.
    """

    async def dependency(request: Request):
        role = get_current_role(request)
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Permission denied. Required roles: {
                    [
                        r.value for r in allowed_roles]}. Your role: {
                    role.value}.")
        return role

    return dependency
