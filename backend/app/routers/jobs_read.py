"""Read-only job routes — ``GET`` endpoints for jobs, results, events, and recycle bin.

Extracted from ``routers/jobs.py`` during the router refactoring to separate
read routes from write/mutation routes.

All routes are registered by ``register_jobs_read_routes(router, manager)``
which is called from ``app.routers.jobs.create_jobs_router``.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.audit_logger import log_rbac_event
from app.models import JobStatus
from app.routers.jobs_state import JobStoreManager, is_worker_mode
from app.storage_interface import get_job_repository
from app.utils.rbac import UserRole, require_principal

logger = logging.getLogger(__name__)


def _can_access_owner(role: UserRole, user_id: str, owner_id: str | None) -> bool:
    """Legacy ``created_by``-based check used by env-backed API keys.

    P0-SAAS-001 prefers ``_can_access_principal`` for persistent API keys
    but this helper remains for backward compatibility with test fixtures
    that only set ``created_by``.
    """
    if role in {UserRole.ADMIN, UserRole.OPERATOR}:
        return True
    return bool(owner_id) and owner_id == user_id


def _can_access_principal(
    role: UserRole,
    user_id: str,
    org_id: str,
    job_org_id: str,
    job_owner_id: str | None,
) -> bool:
    """P0-SAAS-001 ownership predicate.

    Policy:
      * Admin role always has all-access.
      * Operator role has all-access ONLY when the caller is an
        env-backed operator (no ``org_id``). Project-scoped SaaS
        keys that map to OPERATOR (WRITE scope) are still subject
        to org_id enforcement, because the role only grants the
        write capability within the key's own org.
      * User role sees a job if either:
          - the job's ``org_id`` matches the user's authenticated org, OR
          - the job's legacy ``created_by`` fingerprint matches the
            user's ``user_id`` (env-backed keys have no org scope).
    """
    if role == UserRole.ADMIN:
        return True
    if role == UserRole.OPERATOR and not org_id:
        return True
    if org_id and job_org_id and org_id == job_org_id:
        return True
    return bool(job_owner_id) and job_owner_id == user_id


def _summary_visible(summary: dict, role: UserRole, user_id: str, org_id: str) -> bool:
    return _can_access_principal(
        role,
        user_id,
        org_id,
        str(summary.get("org_id") or ""),
        str(summary.get("created_by") or ""),
    )


def _public_summary(summary: dict) -> dict:
    return {key: value for key, value in summary.items() if key != "created_by"}


def _ensure_job_access(job, role: UserRole, user_id: str, org_id: str, action: str) -> None:
    if _can_access_principal(
        role,
        user_id,
        org_id,
        getattr(job, "org_id", ""),
        getattr(job, "created_by", ""),
    ):
        return
    log_rbac_event(
        actor=user_id,
        action=action,
        resource=f"job:{job.id}",
        role=role.value,
        outcome="denied",
        details={
            "owner_id": getattr(job, "created_by", ""),
            "org_id": getattr(job, "org_id", ""),
            "policy": "mvp_created_by_owner_or_saas_org",
        },
    )
    raise HTTPException(status_code=404, detail="Job not found")


def _auth_tuple(auth) -> tuple:
    """Normalise the ``require_role_with_user`` dependency result.

    Returns ``(role, user_id, org_id, project_id)``. The legacy
    ``require_role_with_user`` returns a 2-tuple; the new SaaS path
    returns a 4-tuple. The two coexist until all routes are migrated.
    """
    if len(auth) == 4:
        return auth
    role, user_id = auth
    return role, user_id, "", ""


def register_jobs_read_routes(router: APIRouter, manager: JobStoreManager) -> None:
    """Register all read-only job endpoints on the given router."""

    @router.get("/api/jobs")
    async def list_jobs(
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
        ],
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        cursor: Annotated[str | None, Query()] = None,
    ):
        """List job summaries.

        Supports keyset pagination via ``limit`` and ``cursor`` (an
        ISO-8601 ``created_at`` timestamp). The response shape is
        additive: callers that ignore ``next_cursor`` see the same
        data they always have. When more results are available the
        field contains the ``created_at`` of the last returned item;
        when the result set is exhausted it is ``None``.
        """
        role, user_id, org_id, _project_id = _auth_tuple(auth)
        # In worker mode, refresh from repo using a summary projection.
        if is_worker_mode():
            try:
                repo = get_job_repository()
                summaries = await run_in_threadpool(
                    repo.list_job_summaries,
                    limit,
                    cursor,
                )
                summaries = [s for s in summaries if _summary_visible(s, role, user_id, org_id)]
                next_cursor = summaries[-1]["created_at"] if len(summaries) == limit else None
                with manager.lock:
                    summary_ids = {s["id"] for s in summaries}
                    for s in summaries:
                        if s["id"] in manager.jobs_store:
                            cached = manager.jobs_store[s["id"]]
                            cached.status = JobStatus(s["status"])
                            cached.completed_at = s["completed_at"]  # type: ignore[assignment]
                    stale_ids = [jid for jid in manager.jobs_store if jid not in summary_ids]
                    for jid in stale_ids:
                        manager.jobs_store.pop(jid, None)
                    return {"jobs": [_public_summary(s) for s in summaries], "next_cursor": next_cursor}
            except (AttributeError, ImportError, RuntimeError):
                logger.debug("Failed to refresh jobs list from repo")

        with manager.lock:
            ordered = [
                job
                for job in sorted(manager.jobs_store.values(), key=lambda j: j.created_at, reverse=True)
                if _can_access_principal(role, user_id, org_id, job.org_id, job.created_by)
            ]
            if cursor:
                ordered = [j for j in ordered if (j.created_at or "") < cursor]
            ordered = ordered[:limit]
            summaries = []
            for job in ordered:
                dumped = job.model_dump()
                summaries.append(
                    {
                        "id": dumped["id"],
                        "name": dumped["name"],
                        "mode": dumped["mode"],
                        "urls": dumped["urls"],
                        "topic": dumped.get("topic", ""),
                        "status": dumped["status"],
                        "created_at": dumped["created_at"],
                        "started_at": dumped.get("started_at"),
                        "completed_at": dumped.get("completed_at"),
                        "total_records": dumped.get("total_records", 0),
                        "filtered_records": dumped.get("filtered_records", 0),
                        "progress_current": dumped.get("progress_current", 0),
                        "progress_total": dumped.get("progress_total", 0),
                        "error": dumped.get("error"),
                    },
                )
            next_cursor = summaries[-1]["created_at"] if len(summaries) == limit else None
            return {"jobs": summaries, "next_cursor": next_cursor}

    @router.get("/api/jobs/{job_id}")
    async def get_job(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
        ],
        include_results: Annotated[bool, Query()] = False,
    ):
        role, user_id, org_id, _project_id = _auth_tuple(auth)
        job = await run_in_threadpool(manager.get_job, job_id)
        _ensure_job_access(job, role, user_id, org_id, "read_job")

        results_list = []
        if include_results:
            results_list = list(job.results)
            if job.results_on_disk:
                from app.utils.job_results_store import load_job_results_from_disk

                results_list = await run_in_threadpool(load_job_results_from_disk, job.id, job.results_file_path)

        dumped = job.model_dump()
        dumped.pop("results_file_path", None)
        dumped["results"] = results_list
        return dumped

    @router.get("/api/jobs/{job_id}/results")
    async def get_job_results(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
        ],
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        """Return a paginated slice of job results.

        When results live on disk (large jobs), we read the JSONL
        file directly via ``load_paginated_job_results_from_disk``.
        Otherwise we prefer the ``job_results`` companion table
        (storage-split v4) and only fall back to ``job.results``
        for back-compat with v3 deployments.
        """
        role, user_id, org_id, _project_id = _auth_tuple(auth)
        job = await run_in_threadpool(manager.get_job, job_id)
        _ensure_job_access(job, role, user_id, org_id, "read_job_results")

        if job.results_on_disk:
            from app.utils.job_results_store import load_paginated_job_results_from_disk

            page, total = await run_in_threadpool(
                load_paginated_job_results_from_disk,
                job.id,
                limit=limit,
                offset=offset,
                file_path=job.results_file_path,
            )
        else:
            repo = get_job_repository()
            # Fetch only the requested page from the persistent store. The
            # previous implementation asked for ``limit + offset`` rows and
            # used the count as ``total``, which always yielded
            # ``next_offset = None`` because the cap and the requested count
            # were the same value (``limit < limit`` is always False).
            results_list = await run_in_threadpool(repo.read_results, job.id, limit, offset)
            if results_list or getattr(repo, "backend", "sqlite") != "sqlite":
                # Prefer the authoritative COUNT(*) when the storage backend
                # supports it; fall back to the in-memory list otherwise.
                try:
                    total = await run_in_threadpool(repo.count_results, job.id)
                except (AttributeError, NotImplementedError):
                    total = len(list(job.results))
                page = list(results_list)
            else:
                results_list = list(job.results)
                total = len(results_list)
                page = results_list[offset : offset + limit]

        next_offset = offset + limit if (offset + limit) < total else None

        return {
            "job_id": job_id,
            "results": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset,
            "returned": len(page),
        }

    @router.get("/api/jobs/{job_id}/events")
    async def get_job_events(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
        ],
        limit: Annotated[int, Query(ge=1, le=1000)] = 200,
        offset: Annotated[int, Query(ge=0)] = 0,
        level: Annotated[str | None, Query()] = None,
    ):
        """Return a paginated, filterable view of a job's lifecycle events.

        Events are read from the dedicated ``job_events`` companion
        table when the repository supports it (storage split, v4+);
        otherwise we fall back to ``Job.logs`` for back-compat. The
        response shape is stable for clients that poll a long-running
        job for progress.
        """
        role, user_id, org_id, _project_id = _auth_tuple(auth)
        job = await run_in_threadpool(manager.get_job, job_id)
        _ensure_job_access(job, role, user_id, org_id, "read_job_events")

        events: list[dict] = []
        try:
            repo = get_job_repository()
            events = await run_in_threadpool(
                repo.read_events,
                job_id,
                limit,
                offset,
                level,
            )
        except (AttributeError, RuntimeError):
            events = []

        if not events:
            for entry in job.logs or []:
                try:
                    payload = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
                except (AttributeError, TypeError, ValueError):
                    payload = {"timestamp": "", "level": "info", "message": str(entry)}
                events.append(
                    {
                        "timestamp": payload.get("timestamp") or "",
                        "level": payload.get("level") or "info",
                        "message": payload.get("message") or "",
                    },
                )
            status_ts = job.completed_at or job.started_at or job.created_at or ""
            if status_ts:
                events.append(
                    {
                        "timestamp": status_ts,
                        "level": "info",
                        "message": f"status: {job.status}",
                    },
                )
            events.sort(key=lambda e: e.get("timestamp") or "")
            if level:
                lvl = level.lower()
                events = [e for e in events if (e.get("level") or "").lower().startswith(lvl)]

        total = len(events)
        page = events[offset : offset + limit]
        next_offset = offset + limit if (offset + limit) < total else None

        return {
            "job_id": job_id,
            "status": job.status,
            "events": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset,
        }

    @router.get("/api/recycle_bin")
    async def list_recycle_bin(
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
        ],
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        cursor: str | None = None,
    ):
        role, user_id, org_id, _project_id = _auth_tuple(auth)
        if is_worker_mode():
            repo = get_job_repository()
            summaries = await run_in_threadpool(
                repo.list_recycle_summaries,
                limit=limit,
                cursor=cursor,
            )
            summaries = [s for s in summaries if _summary_visible(s, role, user_id, org_id)]
            return {"jobs": [_public_summary(s) for s in summaries]}

        with manager.lock:
            ordered = [
                job
                for job in sorted(manager.recycle_bin_store.values(), key=lambda j: j.created_at, reverse=True)
                if _can_access_principal(role, user_id, org_id, job.org_id, job.created_by)
            ]
            summaries = []
            for job in ordered:
                dumped = job.model_dump()
                summaries.append(
                    {
                        "id": dumped["id"],
                        "name": dumped["name"],
                        "mode": dumped["mode"],
                        "urls": dumped["urls"],
                        "topic": dumped.get("topic", ""),
                        "status": dumped["status"],
                        "created_at": dumped["created_at"],
                        "started_at": dumped.get("started_at"),
                        "completed_at": dumped.get("completed_at"),
                        "total_records": dumped.get("total_records", 0),
                        "filtered_records": dumped.get("filtered_records", 0),
                        "progress_current": dumped.get("progress_current", 0),
                        "progress_total": dumped.get("progress_total", 0),
                        "error": dumped.get("error"),
                    },
                )
            return {"jobs": summaries}
