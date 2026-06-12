"""Auth Profiles Router — manage stored browser sessions for authenticated scraping.

Provides endpoints to create, list, get, delete, and manage auth profiles.
Each profile stores an encrypted browser session (Playwright ``storage_state``)
scoped to a single domain.

The actual browser automation for login and the decryption for job execution
live in the workflow/job runner.
"""

from __future__ import annotations

import datetime
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.models import AuthProfile, AuthProfileStatus
from app.utils.encryption import decrypt as encryption_decrypt
from app.utils.encryption import encrypt as encryption_encrypt
from app.utils.rbac import UserRole, can_access_scoped_resource, require_principal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth-profiles", tags=["auth-profiles"])

# In-memory auth profile store (replace with DB in production)
_auth_profiles: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _can_access_profile(item: dict[str, Any], auth: tuple[UserRole, str, str, str]) -> bool:
    role, user_id, org_id, project_id = auth
    return can_access_scoped_resource(
        role,
        user_id,
        org_id,
        project_id,
        resource_owner_id=str(item.get("user_id") or ""),
        resource_org_id=str(item.get("org_id") or ""),
        resource_project_id=str(item.get("project_id") or ""),
    )


def _safe_profile(item: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the profile with sensitive fields removed."""
    return {k: v for k, v in item.items() if k != "encrypted_storage_state"}


def _get_visible_profile(profile_id: str, auth: tuple[UserRole, str, str, str]) -> dict[str, Any]:
    item = _auth_profiles.get(profile_id)
    if item is None or not _can_access_profile(item, auth):
        raise HTTPException(status_code=404, detail="Auth profile not found")
    return item


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_auth_profile(
    name: str,
    domain: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    description: str = "",
) -> dict[str, Any]:
    """Create a new auth profile in ``pending_login`` state.

    The operator must then complete the login flow via
    ``POST /auth-profiles/{id}/start-login``.
    """
    _role, user_id, org_id, project_id = auth
    profile = AuthProfile(
        name=name.strip(),
        description=description.strip() if description else "",
        domain=domain.strip().lower(),
        user_id=user_id,
        org_id=org_id,
        project_id=project_id,
        status=AuthProfileStatus.PENDING_LOGIN,
    )
    _auth_profiles[profile.id] = profile.model_dump()
    logger.info("Auth profile created: %s for domain %s", profile.name, profile.domain)
    return _safe_profile(profile.model_dump())


@router.get("", status_code=200)
async def list_auth_profiles(
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> dict[str, Any]:
    """List all auth profiles accessible to the caller."""
    items = [_safe_profile(item) for item in _auth_profiles.values() if _can_access_profile(item, auth)]
    return {"total": len(items), "items": items}


@router.get("/{profile_id}", status_code=200)
async def get_auth_profile(
    profile_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> dict[str, Any]:
    """Get a single auth profile by ID."""
    return _safe_profile(_get_visible_profile(profile_id, auth))


@router.delete("/{profile_id}", status_code=204)
async def delete_auth_profile(
    profile_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> None:
    """Delete an auth profile permanently."""
    _get_visible_profile(profile_id, auth)
    del _auth_profiles[profile_id]
    logger.info("Auth profile deleted: %s", profile_id)


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------


@router.post("/{profile_id}/start-login", status_code=200)
async def start_login(
    profile_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> dict[str, Any]:
    """Initiate the browser login flow for an auth profile.

    Returns a URL or token that the frontend can use to open a
    controlled browser window for the user to log in manually.
    """
    profile = _get_visible_profile(profile_id, auth)
    # In a full implementation, this would generate a temporary token
    # and return a URL to a browser automation endpoint.
    # For now, we return a placeholder indicating the flow is ready.
    return {
        "profile_id": profile_id,
        "domain": profile.get("domain"),
        "status": "ready",
        "message": "Open a controlled browser for the target domain and log in. Then call complete-login.",
    }


@router.post("/{profile_id}/complete-login", status_code=200)
async def complete_login(
    profile_id: str,
    storage_state: dict[str, Any],
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> dict[str, Any]:
    """Complete the login flow by storing the encrypted browser session.

    ``storage_state`` is the Playwright storage state (cookies + localStorage)
    captured after the user has logged in. It is encrypted before storage.
    """
    profile = _get_visible_profile(profile_id, auth)
    import json

    plaintext = json.dumps(storage_state)
    encrypted = encryption_encrypt(plaintext)

    now = _now_iso()
    profile["encrypted_storage_state"] = encrypted
    profile["status"] = AuthProfileStatus.ACTIVE.value
    profile["updated_at"] = now
    profile["last_validated_at"] = now

    logger.info("Auth profile login completed: %s for domain %s", profile_id, profile.get("domain"))
    return _safe_profile(profile)


# ---------------------------------------------------------------------------
# Validation, revoke, status
# ---------------------------------------------------------------------------


@router.post("/{profile_id}/validate", status_code=200)
async def validate_profile(
    profile_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> dict[str, Any]:
    """Validate that the stored session is still active.

    Returns the current status. If the session appears expired,
    the profile status is updated to ``expired``.
    """
    profile = _get_visible_profile(profile_id, auth)
    # In a full implementation, this would attempt a lightweight
    # request to the target domain using the stored session.
    # For now, we do a basic check on the stored state.
    has_state = bool(profile.get("encrypted_storage_state"))
    expires_at = profile.get("expires_at")

    if expires_at and _now_iso() > expires_at:
        profile["status"] = AuthProfileStatus.EXPIRED.value
        profile["updated_at"] = _now_iso()
        return {"valid": False, "status": "expired", "reason": "Session has expired.", "profile": _safe_profile(profile)}

    if not has_state:
        profile["status"] = AuthProfileStatus.FAILED.value
        profile["updated_at"] = _now_iso()
        return {"valid": False, "status": "failed", "reason": "No stored session state.", "profile": _safe_profile(profile)}

    # If we had a real browser, we'd test the session here.
    profile["last_validated_at"] = _now_iso()
    return {"valid": True, "status": "active", "profile": _safe_profile(profile)}


@router.post("/{profile_id}/revoke", status_code=200)
async def revoke_profile(
    profile_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
) -> dict[str, Any]:
    """Revoke an auth profile, invalidating its stored session.

    The profile is marked as ``revoked`` and the encrypted storage state
    is cleared. This does not invalidate the session on the target site,
    but prevents DataForge from using it.
    """
    profile = _get_visible_profile(profile_id, auth)
    profile["status"] = AuthProfileStatus.REVOKED.value
    profile["encrypted_storage_state"] = ""
    profile["updated_at"] = _now_iso()
    logger.info("Auth profile revoked: %s", profile_id)
    return _safe_profile(profile)


# ---------------------------------------------------------------------------
# Internal helpers for job runner
# ---------------------------------------------------------------------------


def get_decrypted_storage_state(profile_id: str, expected_domain: str) -> dict[str, Any]:
    """Decrypt and return the storage state for a profile.

    Raises:
        HTTPException: 404 if profile not found, 403 if domain mismatch.
        DecryptionError: If decryption fails.
    """
    profile = _auth_profiles.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Auth profile not found")

    stored_domain = str(profile.get("domain") or "").lower()
    if stored_domain != expected_domain.lower():
        raise HTTPException(
            status_code=403,
            detail=f"Domain mismatch: profile is for {stored_domain}, requested {expected_domain}",
        )

    status_val = profile.get("status")
    if status_val == AuthProfileStatus.REVOKED.value:
        raise HTTPException(status_code=403, detail="Auth profile has been revoked")
    if status_val == AuthProfileStatus.EXPIRED.value:
        raise HTTPException(status_code=403, detail="Auth profile has expired. Please reconnect.")
    if status_val != AuthProfileStatus.ACTIVE.value:
        raise HTTPException(status_code=403, detail="Auth profile is not active")

    encrypted = profile.get("encrypted_storage_state")
    if not encrypted:
        raise HTTPException(status_code=403, detail="No stored session state")

    import json

    plaintext = encryption_decrypt(encrypted)
    # Update usage stats
    profile["last_used_at"] = _now_iso()
    profile["usage_count"] = profile.get("usage_count", 0) + 1
    return json.loads(plaintext)
