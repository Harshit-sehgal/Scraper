"""
RBAC — simple role-based access control for the product kernel.

Uses API keys as the authentication mechanism for operator/admin roles.
"""

from __future__ import annotations

import enum
import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from forge_kernel.config import settings

_bearer = HTTPBearer(auto_error=False)


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


def _resolve_role(api_key: str) -> UserRole | None:
    """Resolve a role from an API key. Returns None if key is invalid."""
    sec = settings.security
    if not api_key:
        return None
    if sec.ADMIN_API_KEY and secrets.compare_digest(api_key, sec.ADMIN_API_KEY):
        return UserRole.ADMIN
    if sec.OPERATOR_API_KEY and secrets.compare_digest(api_key, sec.OPERATOR_API_KEY):
        return UserRole.OPERATOR
    if sec.API_KEY and secrets.compare_digest(api_key, sec.API_KEY):
        return UserRole.VIEWER
    return None


def get_current_role(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserRole | None:
    """Extract the current user role from the request (API key or Bearer token)."""
    # Check X-API-Key header first
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        role = _resolve_role(api_key)
        if role:
            return role

    # Fall back to Bearer token
    if credentials:
        role = _resolve_role(credentials.credentials)
        if role:
            return role

    return None


def require_role(allowed_roles: list[UserRole]):
    """FastAPI dependency that requires one of the specified roles."""

    def _check(role: UserRole | None = Depends(get_current_role)) -> UserRole:
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Provide X-API-Key or Authorization: Bearer header.",
            )
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role.value}' is not authorized for this endpoint.",
            )
        return role

    return _check
