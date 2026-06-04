"""FastAPI dependencies — RBAC, rate limiting, and shared state.

Provides dependency injection for the kernel's API layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, status

from forge_kernel.security.rate_limiter import get_global_limiter
from forge_kernel.security.rbac import UserRole, require_role

if TYPE_CHECKING:
    from forge_kernel.contracts.job import Job

# ─── Shared stores ───────────────────────────────────────────────────────
# These are the authoritative in-memory stores for the kernel.
# All mutations go through JobService.

_jobs_store: dict[str, Job] = {}
_recycle_bin_store: dict[str, Job] = {}


def get_jobs_store() -> dict[str, Job]:
    return _jobs_store


def get_recycle_bin_store() -> dict[str, Job]:
    return _recycle_bin_store


# ─── Rate limiting dependency ───────────────────────────────────────────


async def check_global_rate_limit(request: Request) -> bool:
    """FastAPI middleware/ dependency for global rate limiting."""
    limiter = get_global_limiter()
    client_ip = request.client.host if request.client else "unknown"
    result = limiter.allow(key=client_ip)
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result.reset_after:.0f}s.",
        )
    return True


# ─── Role dependencies ──────────────────────────────────────────────────

require_admin = require_role([UserRole.ADMIN])
require_operator = require_role([UserRole.ADMIN, UserRole.OPERATOR])
require_viewer = require_role([UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER])
