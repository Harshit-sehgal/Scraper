"""Plan enforcement — enforce SaaS tier limits before expensive operations.

This module extends the usage-leader with a small high-level guard that
routers can use as a FastAPI dependency. Example::

    @router.post("/api/jobs")
    async def create_job(
        ...,
        _check_plan: None = Depends(require_plan_limit(UsageType.JOB_CREATED, quantity=1)),
    ):
        ...

"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request

from app.utils.rbac import resolve_auth_context
from app.utils.usage_ledger import QuotaPeriod, UsageType, get_usage_ledger

logger = logging.getLogger(__name__)

_PLAN_LIMITS: dict[tuple[str, UsageType], int] = {
    # tier, usage_type -> limit
    ("free", UsageType.JOB_CREATED): 10,
    ("free", UsageType.PAGE_FETCHED): 1_000,
    ("free", UsageType.SCHEDULED_JOB): 5,
    ("free", UsageType.API_REQUEST): 10_000,
    ("starter", UsageType.JOB_CREATED): 100,
    ("starter", UsageType.PAGE_FETCHED): 10_000,
    ("starter", UsageType.SCHEDULED_JOB): 50,
    ("starter", UsageType.API_REQUEST): 100_000,
    ("pro", UsageType.JOB_CREATED): 1_000,
    ("pro", UsageType.PAGE_FETCHED): 100_000,
    ("pro", UsageType.SCHEDULED_JOB): 500,
    ("pro", UsageType.API_REQUEST): 1_000_000,
    ("enterprise", UsageType.JOB_CREATED): -1,
    ("enterprise", UsageType.PAGE_FETCHED): -1,
    ("enterprise", UsageType.SCHEDULED_JOB): -1,
    ("enterprise", UsageType.API_REQUEST): -1,
}

# Tiers the enforcement code recognises. Any other string value
# returning from the billing layer is normalised to ``"free"`` so a
# corrupted or stale billing record cannot bypass plan limits by
# carrying an unknown tier name (which would otherwise hit the
# ``limit is None`` branch in ``check_usage_limit`` and be treated as
# unlimited).
KNOWN_TIERS = frozenset({"free", "starter", "pro", "enterprise"})


def get_plan_limits(tier: str) -> dict[str, Any]:
    """Return plan limits for a tier.

    Returns a mapping of usage_type -> limit.  -1 means unlimited.
    """
    limits: dict[str, Any] = {}
    for usage_type in UsageType:
        limit = _PLAN_LIMITS.get((tier, usage_type))
        if limit is not None:
            limits[usage_type.value] = limit
    return limits


def _user_tier(user_id: str) -> str:
    """Return the user's subscription tier.

    Uses the Autumn billing service for real tier lookups. Falls back
    to ``"free"`` when billing is not configured (development mode) or
    when the billing layer returns a tier string we don't recognise
    (the unknown-tier branch fall-back exists so a corrupted or stale
    billing record cannot bypass plan enforcement).
    """
    try:
        from app.billing.service import get_user_tier_from_billing

        tier = get_user_tier_from_billing(user_id)
        # ``tier`` should be a ``PlanTierId`` enum but tolerate any
        # truthy value with a ``.value`` attribute. The ``except``
        # branches below are split so billing-layer shape regressions
        # (``AttributeError``) are surfaced at ``WARNING`` (ops-visible)
        # while ordinary billing flakiness stays at ``DEBUG``.
        tier_value = tier.value if tier else "free"
    except ImportError:
        return "free"
    except AttributeError:
        logger.warning(
            "Billing service returned a non-PlanTierId for user=%s; "
            "falling back to free. This usually indicates a "
            "billing-layer contract regression — investigate the "
            "return type of get_user_tier_from_billing.",
            user_id,
        )
        return "free"
    except (RuntimeError, ValueError, KeyError, TypeError):
        logger.debug("Failed to look up tier for %s, using free", user_id, exc_info=True)
        return "free"

    return tier_value if tier_value in KNOWN_TIERS else "free"


def _auto_set_quota(user_id: str, usage_type: UsageType) -> None:
    """Ensure the user has a quota row matching their plan tier."""
    tier = _user_tier(user_id)
    limit = _PLAN_LIMITS.get((tier, usage_type))
    if limit is None or limit < 0:
        return
    ledger = get_usage_ledger()
    existing = ledger.get_quota(user_id, usage_type)
    if existing is None:
        ledger.set_quota(user_id, usage_type, limit=limit, period=QuotaPeriod.MONTHLY)


def check_usage_limit(user_id: str, usage_type: UsageType, quantity: int = 1) -> tuple[bool, dict[str, Any]]:
    """Check if a user is within their plan limit for a given usage type.

    Returns a tuple of (allowed, details dict).  ``details`` contains:
    - ``tier``: the user's plan tier
    - ``limit``: the plan limit (-1 for unlimited)
    - ``current_usage``: current usage count
    - ``remaining``: remaining quota before hitting the limit
    - ``period``: the quota period (e.g. ``"monthly"``)
    """
    tier = _user_tier(user_id)
    limit = _PLAN_LIMITS.get((tier, usage_type))
    if limit is None or limit < 0:
        return True, {"tier": tier, "limit": -1, "current_usage": 0, "remaining": None, "period": "monthly"}

    _auto_set_quota(user_id, usage_type)
    ledger = get_usage_ledger()
    ok, quota = ledger.check_quota(user_id, usage_type, amount=quantity)
    return ok, {
        "tier": tier,
        "limit": limit,
        "current_usage": quota.current_usage if quota else 0,
        "remaining": (quota.limit - quota.current_usage) if quota else limit,
        "period": quota.period.value if quota else "monthly",
    }


def require_plan_limit(usage_type: UsageType, *, quantity: int = 1):
    """FastAPI dependency factory that enforces plan limits.

    Usage::

        @router.post("/api/jobs")
        async def create_job(
            ...,
            plan_check: dict = Depends(require_plan_limit(UsageType.JOB_CREATED)),
        ):
            ...

    Raises:
        HTTPException(429): if the user has exceeded their plan limit.
    """

    async def dependency(request: Request) -> dict[str, Any]:
        try:
            ctx = resolve_auth_context(request)
            user_id = ctx.user_id
        except HTTPException:
            # If auth hasn't resolved yet, skip plan check (the route's own
            # auth dependency will handle it)
            return {"skipped": True}

        allowed, details = check_usage_limit(user_id, usage_type, quantity)
        if not allowed:
            logger.warning(
                "Plan limit exceeded: user=%s tier=%s type=%s current=%s limit=%s",
                user_id,
                details["tier"],
                usage_type.value,
                details["current_usage"],
                details["limit"],
            )
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Plan limit exceeded for {usage_type.value}. "
                    f"Current: {details['current_usage']}, Limit: {details['limit']} "
                    f"({details['period']}). Upgrade your plan to continue."
                ),
            )
        return details

    return dependency
