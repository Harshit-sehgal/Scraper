"""Role-Based Access Control (RBAC) Module — DataForge Scraper.

Enforces administrative, operator, and user privilege boundaries.
"""

import hashlib
import logging
import secrets
import sqlite3
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
    """Authenticated request principal resolved from one shared decision path.

    `org_id` and `project_id` are populated for persistent API keys (the
    SaaS identity model in ``app.saas``). Env-backed API keys (legacy)
    and dev bypass have empty values; ownership enforcement in routers
    must fall back to ``user_id`` / ``created_by`` for those.
    """

    role: UserRole
    user_id: str
    source: Literal["api_key", "session", "dev"]
    org_id: str = ""
    project_id: str = ""


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


def _resolve_persistent_api_key_context(raw_key: str) -> AuthContext | None:
    """Look up a raw API key in the persistent SaaS identity store.

    Returns ``None`` if the key is empty, the store is unavailable, or
    the key has not been issued. Successful lookups return an
    ``AuthContext`` with ``user_id``, ``org_id``, and ``project_id``
    populated from the issued key + project.

    The role is derived from the key's scope: ``ADMIN`` → admin,
    ``READ`` → user, ``WRITE`` → operator. ``user_id`` is the
    key-issuing user so audit trails can attribute writes to the
    human who created the key, not the project.
    """
    if not raw_key:
        return None
    try:
        from app.saas.identity_store import get_identity_store
        from app.saas.models import ApiKeyScope
        from app.saas.service import ApiKeyService, hash_api_key
    except ImportError:
        return None
    try:
        store = get_identity_store()
        service = ApiKeyService(store=store)
        record = service.authenticate(raw_key)
    except (RuntimeError, ValueError, TypeError, sqlite3.Error) as e:
        logger.debug("Persistent API key lookup failed: %s", e)
        return None
    if record is None:
        return None
    role = {
        ApiKeyScope.ADMIN: UserRole.ADMIN,
        ApiKeyScope.WRITE: UserRole.OPERATOR,
        ApiKeyScope.READ: UserRole.USER,
    }.get(record.scope, UserRole.USER)
    user_id = record.user_id or hash_api_key(record.key_hash)[:16]
    return AuthContext(
        role=role,
        user_id=user_id,
        source="api_key",
        org_id=(record.project_id and _project_org(store, record.project_id)) or "",
        project_id=record.project_id,
    )


def _project_org(store, project_id: str) -> str:
    """Tiny helper to look up an org id for a project (lazy import)."""
    try:
        proj = store.get_project(project_id)
    except (RuntimeError, ValueError, TypeError):
        return ""
    return proj.org_id if proj else ""


def _resolve_api_key_context(request: Request) -> AuthContext | None:
    from app.config import settings

    api_key_header = request.headers.get("X-API-Key", "")
    admin_key_header = request.headers.get("X-Admin-Key", "")
    bearer_token = _extract_bearer_token(request)
    operator_key = getattr(settings, "OPERATOR_API_KEY", "")

    # 1. Try the persistent SaaS identity store first. This is the
    #    forward path; env keys remain for self-hosted/internal mode.
    for raw_key in (api_key_header, bearer_token, admin_key_header):
        ctx = _resolve_persistent_api_key_context(raw_key)
        if ctx is not None:
            return ctx

    # 2. Fall back to env-backed API keys (legacy / self-hosted).
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


def _auth_was_attempted(request: Request) -> bool:
    """Return True if the request carries any auth signals (attempted auth)."""
    if request.headers.get("X-API-Key"):
        return True
    if request.headers.get("X-Admin-Key"):
        return True
    if request.headers.get("Authorization"):
        return True
    try:
        if request.cookies.get("dataforge_session"):
            return True
    except (AttributeError, TypeError):
        pass
    return False


def resolve_auth_context(request: Request, *, allow_cookie: bool = True) -> AuthContext:
    """Resolve API-key, bearer, session-cookie, or explicit dev auth.

    This is the single authentication decision engine used by middleware
    and route-level RBAC dependencies. Authorization checks should consume
    the returned role/user identity rather than re-reading headers.

    Security invariant: dev auth is NEVER used as a fallback when the
    client has already presented credentials. This prevents the dev
    fallback from silently granting admin access to requests with
    invalid (but present) keys or expired sessions.
    """
    cached = getattr(getattr(request, "state", None), "auth_context", None)
    if cached is not None and (allow_cookie or cached.source != "session"):
        return cached

    context = _resolve_api_key_context(request)
    if context is None and allow_cookie:
        context = _resolve_session_context(request)

    # If no auth was even attempted, we may fall through to the insecure
    # dev bypass.  If a key / cookie / bearer token was present but
    # failed to validate, we MUST NOT grant admin via dev auth.
    if context is None and not _auth_was_attempted(request):
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


def require_principal(allowed_roles: list[UserRole]):
    """FastAPI route guard that returns the full P0-SAAS-001 principal.

    Returns a 4-tuple ``(role, user_id, org_id, project_id)``. Use this
    dependency on routes that need to enforce org/project ownership.
    Env-backed API keys and dev bypass return empty ``org_id`` and
    ``project_id`` so the caller falls back to the legacy
    ``created_by``-based ownership check.
    """

    async def dependency(request: Request):
        context = resolve_auth_context(request)
        if context.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied. Required roles: {[r.value for r in allowed_roles]}. Your role: {context.role.value}.",
            )
        return context.role, context.user_id, context.org_id, context.project_id

    return dependency


def can_access_scoped_resource(
    role: UserRole,
    user_id: str,
    org_id: str = "",
    project_id: str = "",
    *,
    resource_owner_id: str | None = "",
    resource_org_id: str | None = "",
    resource_project_id: str | None = "",
) -> bool:
    """Return whether an authenticated principal can access a scoped resource.

    Admins can access all resources. Env-backed operators also retain
    all-access because they have no org/project scope. Persistent SaaS WRITE
    keys map to operator but carry org/project ids, so they remain scoped.
    """
    if role == UserRole.ADMIN:
        return True
    if role == UserRole.OPERATOR and not org_id and not project_id:
        return True

    owner = str(resource_owner_id or "")
    resource_org = str(resource_org_id or "")
    resource_project = str(resource_project_id or "")

    if project_id and resource_project:
        return project_id == resource_project
    if org_id and resource_org:
        return org_id == resource_org
    return bool(owner) and owner == user_id
