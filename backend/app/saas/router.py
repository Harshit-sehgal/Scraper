"""SaaS identity router — thin FastAPI adapter over the identity store.

Hosts endpoints for:
- AUP (Acceptable Use Policy) acceptance
- Self-service user signup
- Organization management
- Project management
- User profile
- Plan info & usage summary
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.plan_enforcer import get_plan_limits, get_user_tier
from app.saas.routes._common import _MAX_KEY_SCOPE_FOR_ROLE, _SCOPE_RANK, reset_rate_limiters
from app.saas.routes.aup import router as aup_router
from app.saas.routes.orgs import router as orgs_router
from app.saas.routes.profile import router as profile_router
from app.saas.routes.projects import router as projects_router
from app.saas.routes.signup import router as signup_router
from app.utils.log_redaction import redact_pii
from app.utils.rbac import UserRole, require_role_with_user
from app.utils.usage_ledger import UsageType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/saas", tags=["saas"])

# ─── Include sub-routers ────────────────────────────────────────────
router.include_router(aup_router)
router.include_router(signup_router)
router.include_router(profile_router)
router.include_router(orgs_router)
router.include_router(projects_router)

# ─── Re-exports for test compatibility ──────────────────────────────
# Tests import these symbols from app.saas.router directly.
__all__ = [
    "_MAX_KEY_SCOPE_FOR_ROLE",
    "_SCOPE_RANK",
    "reset_rate_limiters",
]

# ═══════════════════════════════════════════════════════════════════════
# Plan & Limits — informational view of the caller's tier. Enforcement
# of tier limits lives in ``app.plan_enforcer`` (wired into job creation
# and other metered routes via ``require_plan_limit``); this endpoint
# only reports the current tier and its derived limits to the UI.
# ═══════════════════════════════════════════════════════════════════════


class PlanTier(str):
    """Subscription plan tiers."""

    __slots__ = ()

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# Per-tier feature flags and teammate/project caps. Usage limits
# (jobs/pages/scheduled/api) are sourced from ``app.plan_enforcer`` so
# there is a single source of truth for the numeric limits.
_TIER_FEATURES: dict[str, list[str]] = {
    "free": ["basic_scraping", "scheduled_jobs", "aup_compliance"],
    "starter": ["basic_scraping", "scheduled_jobs", "aup_compliance", "csv_export", "json_export"],
    "pro": [
        "basic_scraping",
        "scheduled_jobs",
        "aup_compliance",
        "csv_export",
        "json_export",
        "excel_export",
        "workflow_replay",
        "auth_profiles",
    ],
    "enterprise": [
        "basic_scraping",
        "scheduled_jobs",
        "aup_compliance",
        "csv_export",
        "json_export",
        "excel_export",
        "workflow_replay",
        "auth_profiles",
        "priority_support",
        "custom_retention",
    ],
}

_TIER_TEAMMATES: dict[str, int] = {
    "free": 2,
    "starter": 5,
    "pro": 25,
    "enterprise": -1,
}

_TIER_PROJECTS: dict[str, int] = {
    "free": 2,
    "starter": 10,
    "pro": 100,
    "enterprise": -1,
}


class PlanInfoResponse(BaseModel):
    """Current plan information for the user."""

    tier: str = Field(default="free", max_length=32)
    max_jobs: int = 10
    max_scrapes: int = 1000
    max_teammates: int = 2
    max_projects: int = 2
    features: list[str]


@router.get("/plan", response_model=PlanInfoResponse)
async def get_plan_info(
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> PlanInfoResponse:
    """Return the current user's plan and limits.

    Looks up the caller's tier via the billing service (falling back to
    ``free`` when billing is unconfigured) and derives the usage limits
    from the same ``app.plan_enforcer`` source of truth that enforces
    them at job-creation time, so the informational view and the
    enforcement gate can never drift.
    """
    _role, user_id = auth
    tier = get_user_tier(user_id) if user_id else "free"
    limits = get_plan_limits(tier)
    return PlanInfoResponse(
        tier=tier,
        max_jobs=limits.get(UsageType.JOB_CREATED.value, 10),
        max_scrapes=limits.get(UsageType.PAGE_FETCHED.value, 1000),
        max_teammates=_TIER_TEAMMATES.get(tier, 2),
        max_projects=_TIER_PROJECTS.get(tier, 2),
        features=_TIER_FEATURES.get(tier, _TIER_FEATURES["free"]),
    )


class UsageSummaryResponse(BaseModel):
    """Current usage summary for the authenticated user."""

    jobs_created: int = 0
    pages_fetched: int = 0
    scheduled_jobs: int = 0
    ai_structuring: int = 0
    api_requests: int = 0


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage_summary(
    request: Request,
    auth: Annotated[
        tuple[UserRole, str],
        Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> UsageSummaryResponse:
    """Return current usage counters for the authenticated user.

    Used by the frontend billing page to show how much of the plan
    quota has been consumed (e.g. "3 of 10 jobs used this month").
    """
    _role, user_id = auth
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    try:
        from app.utils.rbac import resolve_auth_context

        ctx = resolve_auth_context(request)
        quota_owner = ctx.org_id or ctx.project_id or ctx.user_id
    except Exception:
        logger.debug("Quota context resolution failed; falling back to user_id: %s", redact_pii(str(user_id)))
        quota_owner = user_id

    try:
        from app.utils.usage_ledger import UsageType, get_usage_ledger

        ledger = get_usage_ledger()
        jobs_usage = ledger.get_usage(quota_owner, UsageType.JOB_CREATED)
        pages_usage = ledger.get_usage(quota_owner, UsageType.PAGE_FETCHED)
        scheduled_usage = ledger.get_usage(quota_owner, UsageType.SCHEDULED_JOB)
        ai_usage = ledger.get_usage(quota_owner, UsageType.AI_STRUCTURING)
        api_usage = ledger.get_usage(quota_owner, UsageType.API_REQUEST)

        return UsageSummaryResponse(
            jobs_created=sum(r.quantity for r in jobs_usage),
            pages_fetched=sum(r.quantity for r in pages_usage),
            scheduled_jobs=sum(r.quantity for r in scheduled_usage),
            ai_structuring=sum(r.quantity for r in ai_usage),
            api_requests=sum(r.quantity for r in api_usage),
        )
    except (ImportError, RuntimeError, ValueError) as exc:
        logger.warning("Failed to read usage summary: %s", exc)
        return UsageSummaryResponse()
