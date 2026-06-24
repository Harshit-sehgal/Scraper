"""Auth Profiles Router — manage stored browser sessions for authenticated scraping.

Provides endpoints to create, list, get, delete, and manage auth profiles.
Each profile stores an encrypted browser session (Playwright ``storage_state``)
scoped to a single domain.

The actual browser automation for login and the decryption for job execution
live in the workflow/job runner.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.audit_logger import log_admin_action, log_rbac_event
from app.config import settings
from app.models import AuthProfile, AuthProfileStatus
from app.url_safety import validate_public_domain
from app.utils.auth_profile_store import AuthProfileStore
from app.utils.encryption import decrypt as encryption_decrypt
from app.utils.encryption import encrypt as encryption_encrypt
from app.utils.rbac import UserRole, can_access_scoped_resource, require_principal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth-profiles", tags=["auth-profiles"])

# File-backed auth profile store shared across uvicorn/gunicorn workers.
_auth_profiles = AuthProfileStore()


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
    if item is None:
        raise HTTPException(status_code=404, detail="Auth profile not found")
    if not _can_access_profile(item, auth):
        _role, user_id, _org_id, _project_id = auth
        log_rbac_event(
            actor=user_id,
            action="get_auth_profile",
            resource=f"auth-profile:{profile_id}",
            role=_role.value,
            outcome="denied",
            details={
                "owner_id": item.get("user_id", ""),
                "org_id": item.get("org_id", ""),
                "project_id": item.get("project_id", ""),
                "policy": "scoped_resource_or_saas_org_project",
            },
        )
        raise HTTPException(status_code=404, detail="Auth profile not found")
    return item


def _write_back(profile: dict[str, Any]) -> None:
    """Persist a (possibly-mutated) local copy of a profile record.

    The store returns deep copies on every read so direct mutation
    of the dict the caller holds does NOT persist; this helper is
    what makes mutations on those copies visible to subsequent
    reads and to sibling workers.
    """
    profile_id = str(profile.get("id") or "")
    if not profile_id:
        msg = "auth profile dict missing 'id' before write-back"
        raise RuntimeError(msg)
    _auth_profiles.upsert(profile_id, profile)


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
    # SSRF guard: validate the target domain is a public host before
    # storing it. Without this, an operator could store
    # ``domain="localhost"`` and later trigger a server-side fetch
    # (``_try_live_session_check``) against an internal service with
    # the profile's attached cookies.
    try:
        validate_public_domain(domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    profile = AuthProfile(
        name=name.strip(),
        description=description.strip() if description else "",
        domain=domain.strip().lower(),
        user_id=user_id,
        org_id=org_id,
        project_id=project_id,
        status=AuthProfileStatus.PENDING_LOGIN,
    )
    _auth_profiles.upsert(profile.id, profile.model_dump())
    logger.info("Auth profile created: %s for domain %s", profile.name, profile.domain)
    log_admin_action(
        actor=user_id,
        action="auth_profile_created",
        resource=f"auth-profile:{profile.id}",
        details={"name": profile.name, "domain": profile.domain},
    )
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
    profile = _get_visible_profile(profile_id, auth)
    deleted = _auth_profiles.delete(profile_id)
    if deleted:
        logger.info("Auth profile deleted: %s", profile_id)
        log_admin_action(
            actor=auth[1],
            action="auth_profile_deleted",
            resource=f"auth-profile:{profile_id}",
            details={"domain": profile.get("domain"), "name": profile.get("name")},
        )


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

    H12: Use per-user encryption key derived from user_id.
    """
    profile = _get_visible_profile(profile_id, auth)
    plaintext = json.dumps(storage_state)
    _, _, user_id, _ = auth  # H12: Extract user_id from auth tuple
    encrypted = encryption_encrypt(plaintext, user_id=user_id)

    now = _now_iso()
    profile["encrypted_storage_state"] = encrypted
    # Record the user_id used at encrypt-time so the matching decrypt can
    # re-derive the same per-user key. The actor may differ from the
    # profile owner across sessions; this field pins which key was used.
    profile["encrypted_by_user_id"] = user_id
    profile["status"] = AuthProfileStatus.ACTIVE.value
    profile["updated_at"] = now
    profile["last_validated_at"] = now
    _write_back(profile)

    logger.info("Auth profile login completed: %s for domain %s", profile_id, profile.get("domain"))
    return _safe_profile(profile)


# ---------------------------------------------------------------------------
# Validation, revoke, status
# ---------------------------------------------------------------------------


async def _try_live_session_check(profile: dict[str, Any]) -> dict[str, Any] | None:
    """Attempt a live HTTP check against the profile's target domain.

    Uses the stored cookies (from Playwright storage_state) to make
    a lightweight GET request to the target domain. If the request
    succeeds without redirect to a login page, the session is
    considered valid.

    Returns a result dict with ``valid``, ``status``, and ``reason``
    keys, or ``None`` if the check could not be performed (no state,
    network error, etc.).
    """
    encrypted = profile.get("encrypted_storage_state", "")
    if not encrypted:
        return None

    domain = str(profile.get("domain", ""))
    if not domain:
        return None

    try:
        plaintext = encryption_decrypt(
            encrypted,
            user_id=str(profile.get("encrypted_by_user_id") or profile.get("user_id") or ""),
        )
        storage_state = json.loads(plaintext)
    except (ValueError, TypeError):
        logger.debug("Could not decrypt storage state for live check", exc_info=True)
        return None

    # Extract cookies from Playwright storage state
    cookies = storage_state.get("cookies", []) if isinstance(storage_state, dict) else []
    if not cookies:
        logger.debug("No cookies in storage state for live check")
        return None

    # Build a target URL from the domain
    target_url = f"https://{domain}/"

    try:
        import httpx

        # Build cookie jar from stored cookies
        cookie_dict: dict[str, str] = {}
        for c in cookies:
            name = c.get("name", "")
            value = c.get("value", "")
            if name and value:
                cookie_dict[name] = value

        async with httpx.AsyncClient(
            cookies=cookie_dict,
            follow_redirects=True,
            timeout=15.0,
            verify=settings.VERIFY_SSL if hasattr(settings, "VERIFY_SSL") else True,
        ) as client:
            response = await client.get(
                target_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )

            status_code = response.status_code
            final_url = str(response.url)
            content_lower = response.text[:2000].lower() if response.text else ""

            # Detect login page redirects or login form indicators
            login_keywords = ["login", "sign in", "log in", "signin", "auth", "authenticate", "session expired"]
            redirected_to_login = any(kw in final_url.lower() for kw in login_keywords)
            page_has_login_form = any(kw in content_lower for kw in login_keywords[:3])

            if status_code == 200 and not redirected_to_login and not page_has_login_form:
                return {"valid": True, "status": "active", "reason": "Live HTTP check passed."}
            if status_code in (301, 302, 303, 307, 308) and redirected_to_login:
                return {"valid": False, "status": "expired", "reason": f"Redirected to login page: {final_url}"}
            if page_has_login_form:
                return {"valid": False, "status": "expired", "reason": "Response contains login form — session expired."}
            if status_code in (401, 403):
                return {"valid": False, "status": "expired", "reason": f"HTTP {status_code} — authentication required."}
            if status_code >= 500:
                logger.debug("Live session check got %d for %s, treating as inconclusive", status_code, target_url)
                return None

            # Fall back to treating non-200 as inconclusive
            logger.debug("Live session check got status %d for %s", status_code, target_url)
            return None

    except httpx.ConnectError:
        logger.debug("Could not connect to %s for live session check", target_url)
        return None
    except httpx.TimeoutException:
        logger.debug("Timeout connecting to %s for live session check", target_url)
        return None
    except (RuntimeError, ValueError, TypeError):
        logger.debug("Live session check failed for %s", target_url, exc_info=True)
        return None


@router.post("/{profile_id}/validate", status_code=200)
async def validate_profile(
    profile_id: str,
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
    ],
    live: bool = True,
) -> dict[str, Any]:
    """Validate that the stored session is still active.

    By default, performs a local check on the stored state and
    expiration timestamp. When ``live=true`` is set, also attempts
    an actual HTTP request to the target domain using the stored
    cookies to verify the session is still valid.

    If the session appears expired or the live check fails,
    the profile status is updated accordingly.
    """
    profile = _get_visible_profile(profile_id, auth)
    has_state = bool(profile.get("encrypted_storage_state"))
    expires_at = profile.get("expires_at")

    if expires_at and _now_iso() > expires_at:
        profile["status"] = AuthProfileStatus.EXPIRED.value
        profile["updated_at"] = _now_iso()
        _write_back(profile)
        return {"valid": False, "status": "expired", "reason": "Session has expired.", "profile": _safe_profile(profile)}

    if not has_state:
        profile["status"] = AuthProfileStatus.FAILED.value
        profile["updated_at"] = _now_iso()
        _write_back(profile)
        return {"valid": False, "status": "failed", "reason": "No stored session state.", "profile": _safe_profile(profile)}

    # Optional live HTTP check
    if live and profile.get("status") == AuthProfileStatus.ACTIVE.value:
        live_result = await _try_live_session_check(profile)
        if live_result is not None:
            if not live_result["valid"]:
                profile["status"] = AuthProfileStatus.EXPIRED.value
                profile["updated_at"] = _now_iso()
                _write_back(profile)
                return {
                    "valid": False,
                    "status": "expired",
                    "reason": live_result["reason"],
                    "profile": _safe_profile(profile),
                }
            # Live check confirmed valid
            profile["last_validated_at"] = _now_iso()
            _write_back(profile)
            return {"valid": True, "status": "active", "reason": "Live HTTP check passed.", "profile": _safe_profile(profile)}

    # Local-only check passed
    profile["last_validated_at"] = _now_iso()
    _write_back(profile)
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
    _write_back(profile)
    logger.info("Auth profile revoked: %s", profile_id)
    log_admin_action(
        actor=auth[1],
        action="auth_profile_revoked",
        resource=f"auth-profile:{profile_id}",
        details={"domain": profile.get("domain")},
    )
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

    plaintext = encryption_decrypt(
        encrypted,
        user_id=str(profile.get("encrypted_by_user_id") or profile.get("user_id") or ""),
    )
    # Update usage stats
    profile["last_used_at"] = _now_iso()
    profile["usage_count"] = int(profile.get("usage_count", 0) or 0) + 1
    _write_back(profile)
    return json.loads(plaintext)
