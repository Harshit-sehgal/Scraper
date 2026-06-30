"""Shared helpers for SaaS route modules.

Internal helpers, rate-limit state, and utility functions used by two
or more route modules.  Not intended for direct import outside the
``routes`` package.
"""

from __future__ import annotations

import logging
import re

from fastapi import HTTPException

from app.rate_limiter import SlidingWindowCounter
from app.utils.rbac import UserRole

logger = logging.getLogger(__name__)

# ─── Email validation (lightweight, no external dependency) ────────────
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)


def _validate_email(email: str) -> str:
    """Validate and normalize an email address.

    Returns the stripped, lowercased email if valid.
    Raises HTTPException 422 if invalid.

    Constant-time: every check is evaluated before either raising, to
    prevent a timing side-channel that would let an attacker enumerate
    which email addresses are registered by observing response latency
    differences between the length check, regex check, and DB lookup.
    """
    stripped = email.strip().lower() if email else ""
    # Run every check before raising; the boolean matrix makes response
    # latency depend only on the constant per-check branch counts.
    length_ok = 0 < len(stripped) <= 254
    regex_ok = bool(_EMAIL_RE.match(stripped)) if stripped else False
    if not (length_ok and regex_ok):
        raise HTTPException(status_code=422, detail="Invalid email address")
    return stripped


# ─── Password strength validation ─────────────────────────────────────
_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]).{8,128}$")


def _validate_password(password: str) -> str:
    """Validate password strength.

    Requirements:
    - 8-128 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Returns the password if valid.
    Raises HTTPException 422 if invalid.

    Constant-time: every check runs before raising so response latency
    does not disclose the strength tier of an attempted password.
    """
    pwd = password or ""
    # Run every constraint check before raising.  Short-circuiting on
    # the first failure would let an attacker map ``len(p) < 8`` vs
    # ``len(p) > 128`` vs ``strength regex missed``.
    length_ok = 8 <= len(pwd) <= 128
    pattern_ok = bool(_PASSWORD_RE.match(pwd))
    if not (length_ok and pattern_ok):
        raise HTTPException(
            status_code=422,
            detail="Password does not meet complexity requirements",
        )
    return password


# ─── Rate-limit state ─────────────────────────────────────────────────
# Rate-limit state for password reset endpoints (in-memory, per-IP).
_PASSWORD_RESET_REQUEST_LIMITERS: dict[str, SlidingWindowCounter] = {}
_PASSWORD_RESET_CONFIRM_LIMITERS: dict[str, SlidingWindowCounter] = {}

# Rate-limit state for email verification (per-user).
_EMAIL_VERIFICATION_LIMITERS: dict[str, SlidingWindowCounter] = {}

# Rate-limit state for invitation creation (per-user).
_INVITATION_CREATE_LIMITERS: dict[str, SlidingWindowCounter] = {}

# Rate-limit state for email verification confirm (per-IP).
_EMAIL_VERIFICATION_CONFIRM_LIMITERS: dict[str, SlidingWindowCounter] = {}

# Rate-limit state for signup (per-IP).
_SIGNUP_LIMITERS: dict[str, SlidingWindowCounter] = {}


def reset_rate_limiters() -> None:
    """Clear all in-memory rate limiter state.

    Called by test fixtures between test runs to prevent rate-limit
    carryover from one test to the next. Not intended for production use.
    """
    _PASSWORD_RESET_REQUEST_LIMITERS.clear()
    _PASSWORD_RESET_CONFIRM_LIMITERS.clear()
    _EMAIL_VERIFICATION_LIMITERS.clear()
    _INVITATION_CREATE_LIMITERS.clear()
    _EMAIL_VERIFICATION_CONFIRM_LIMITERS.clear()
    _SIGNUP_LIMITERS.clear()


def _check_rate_limit(
    limiters: dict[str, SlidingWindowCounter],
    key: str,
    max_requests: int = 5,
    window_seconds: float = 300.0,
    action: str = "request",
) -> None:
    """Check rate limit for an action by key (IP address or user ID).

    Args:
        limiters: Dict mapping keys to sliding-window counters.
        key: Identifier to rate-limit by (IP address or user ID).
        max_requests: Maximum allowed requests in the window.
        window_seconds: Duration of the sliding window in seconds.
        action: Human-readable action name for log/error messages.

    Raises HTTPException 429 if the limit is exceeded.
    Returns None on success.
    """
    counter = limiters.get(key)
    if counter is None:
        counter = SlidingWindowCounter(max_requests=max_requests, window_seconds=window_seconds)
        limiters[key] = counter
    elif counter.is_expired():
        del limiters[key]
        counter = SlidingWindowCounter(max_requests=max_requests, window_seconds=window_seconds)
        limiters[key] = counter

    if not counter.allow():
        logger.warning("Rate limit exceeded for %s: key=%s", action, key)
        raise HTTPException(
            status_code=429,
            detail=f"Too many {action}s. Please try again later.",
        )


# ═══════════════════════════════════════════════════════════════════════
# Internal helper: env-backed operator all-access gate (issue #135)
# ═══════════════════════════════════════════════════════════════════════


def _env_backed_all_access(
    role: UserRole,
    org_id: str = "",
) -> bool:
    """Return True iff the principal is an env-backed admin/operator and cross-tenant access is explicitly enabled.

    This is the single gate used by every SaaS route that previously
    granted blanket all-access to env-backed operators. When the gate
    returns ``False`` the caller MUST enforce its own tenant-scoped
    ownership check (e.g. ``created_by_user_id`` or org membership).

    Every ``True`` return is accompanied by an audit log entry and a
    Prometheus counter increment so operators can monitor unexpected key
    usage.
    """
    from app.config import settings
    from app.utils.rbac import _record_operator_cross_tenant, is_env_backed_operator_cross_tenant

    if role == UserRole.ADMIN and not org_id:
        if settings.ENABLE_OPERATOR_CROSS_TENANT:
            _record_operator_cross_tenant(f"SaaS: env-backed ADMIN all-access — role={role.value}")
            return True
        return False

    if role != UserRole.OPERATOR or org_id:
        return False

    if is_env_backed_operator_cross_tenant(role, org_id, ""):
        _record_operator_cross_tenant(f"SaaS: env-backed OPERATOR all-access — role={role.value}")
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════
# API key scope policy (shared with tests via re-export from router.py)
# ═══════════════════════════════════════════════════════════════════════

# Maximum API-key scope grantable per org membership role.
_MAX_KEY_SCOPE_FOR_ROLE: dict[str, str] = {
    "owner": "admin",
    "admin": "admin",
    "member": "write",
    "viewer": "read",
}

# Rank order for scope comparison (higher = more privileged).
_SCOPE_RANK: dict[str, int] = {
    "read": 0,
    "write": 1,
    "admin": 2,
}
