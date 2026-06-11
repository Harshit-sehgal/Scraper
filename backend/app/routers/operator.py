"""Operator Router — operational intelligence endpoints (RESERVED).

All former routes (operator mode switching, governance dashboard, degradation
predictions, system health overview) were backed by research-shell modules
(visualization, domain_health_alerts, trend_analyzer, degradation_predictor).
They have been quarantined to ``routers/experimental.py`` and require
``DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true`` to mount.

This router hosts the **P1-COMPLIANCE-001 admin domain denylist** —
the only product-kernel operator endpoint that has shipped so far.
The denylist is a persistent, auditable allow/deny control that the
URL-safety check consults before every scrape.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.admin_denylist import DenylistEntry, get_denylist
from app.audit_logger import log_admin_action
from app.utils.rbac import UserRole, require_role_with_user

router = APIRouter(prefix="/api/operator", tags=["operator"])


class DenylistAddRequest(BaseModel):
    """Request body for adding an entry to the admin domain denylist."""

    domain: str = Field(..., min_length=1, max_length=253, description="Hostname to block (e.g. 'example.com')")
    reason: str = Field("", max_length=512, description="Human-readable reason (visible to operators)")
    path_prefix: str = Field("", max_length=512, description="Optional path prefix to scope the block (e.g. '/private')")


class DenylistRemoveRequest(BaseModel):
    """Request body for removing an entry from the admin domain denylist."""

    domain: str = Field(..., min_length=1, max_length=253, description="Hostname to unblock")
    path_prefix: str = Field("", max_length=512, description="Path prefix used when the entry was added (empty = whole domain)")


class DenylistEntryResponse(BaseModel):
    """One denylist row, as returned by the admin endpoints."""

    domain: str
    reason: str
    added_by: str
    added_at: str
    path_prefix: str = ""


def _to_response(entry: DenylistEntry) -> DenylistEntryResponse:
    return DenylistEntryResponse(
        domain=entry.domain,
        reason=entry.reason,
        added_by=entry.added_by,
        added_at=entry.added_at,
        path_prefix=entry.path_prefix,
    )


@router.get("/denylist", response_model=list[DenylistEntryResponse])
async def list_denylist(
    _auth: Annotated[tuple[UserRole, str], Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR]))],
) -> list[DenylistEntryResponse]:
    """Return all admin-domain-denylist entries (admin or operator)."""
    return [_to_response(e) for e in get_denylist().list()]


@router.post("/denylist", response_model=DenylistEntryResponse, status_code=201)
async def add_denylist_entry(
    body: DenylistAddRequest,
    auth: Annotated[tuple[UserRole, str], Depends(require_role_with_user([UserRole.ADMIN]))],
) -> DenylistEntryResponse:
    """Add (or update) an entry in the admin domain denylist. Admin only."""
    _role, user_id = auth
    try:
        entry = get_denylist().add(
            body.domain,
            reason=body.reason,
            added_by=user_id,
            path_prefix=body.path_prefix,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_admin_action(
        actor=user_id,
        action="denylist_add",
        resource=f"domain:{entry.domain}{':' + entry.path_prefix if entry.path_prefix else ''}",
        details={"reason": entry.reason, "path_prefix": entry.path_prefix},
    )
    # ``added_at`` is set by SQLite; reload the canonical row.
    stored = get_denylist().get(entry.domain)
    persisted = next((e for e in stored if e.path_prefix == entry.path_prefix), entry)
    return _to_response(persisted)


@router.delete("/denylist", status_code=200)
async def remove_denylist_entry(
    body: DenylistRemoveRequest,
    auth: Annotated[tuple[UserRole, str], Depends(require_role_with_user([UserRole.ADMIN]))],
) -> dict[str, Any]:
    """Remove an entry from the admin domain denylist. Admin only."""
    _role, user_id = auth
    removed = get_denylist().remove(body.domain, path_prefix=body.path_prefix)
    if not removed:
        raise HTTPException(status_code=404, detail="Denylist entry not found")
    log_admin_action(
        actor=user_id,
        action="denylist_remove",
        resource=f"domain:{body.domain.lower()}{':' + body.path_prefix if body.path_prefix else ''}",
        details={"path_prefix": body.path_prefix},
    )
    return {"message": "Denylist entry removed", "domain": body.domain.lower(), "path_prefix": body.path_prefix}
