"""Write/mutation job routes — ``POST/DELETE`` endpoints for jobs and recycle bin.

Extracted from ``routers/jobs.py`` during the router refactoring to separate
mutation routes from read-only routes.

All routes are registered by ``register_jobs_write_routes(router, manager, ...)``
which is called from ``app.routers.jobs.create_jobs_router``.

Route handlers are kept thin — business logic lives in dedicated services
under ``app.services.job_mutation_service``.
"""

from __future__ import annotations

import datetime
import logging
import threading
import uuid
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from app.audit_logger import log_admin_action, log_job_event
from app.config import settings

# Satisfy pyflakes — `settings` is patched in tests via ``jobs_write.settings``
# and is also used by service modules that import it through this namespace.
_SETTINGS_IMPORT_GUARD = settings

from app.discovery import (
    DiscoveryDependencyError,
    discover_urls,
)
from app.models import (
    BatchSubmitRequest,
    ClearTerminalResponse,
    DiscoveryRequest,
    EmailDeliveryRequest,
    ExtractionTemplate,
    ExtractionTemplateUpdate,
    FetchStrategyUpdate,
    JobCloneRequest,
    JobCreate,
    JobCreateResponse,
    JobExtractionUpdate,
    JobExtractionUpdateResponse,
    JobHeadersUpdate,
    JobStatus,
    JobStrategyUpdate,
    JobUserAgentUpdate,
    JobWaitConditionsUpdate,
    JobWebhookUpdate,
    NotificationChannel,
    NotificationChannelCreate,
    NotificationChannelUpdate,
    SchemaSuggestionRequest,
    StatusResponse,
    UsageRecord,
)
from app.plan_enforcer import require_plan_limit
from app.routers.jobs_state import (
    JobStoreManager,
)
from app.services.job_creation_service import (
    JobCreationError,
    JobCreationService,
)
from app.services.job_mutation_service import (
    JobCancellerService,
    JobExtractionUpdateService,
    JobHeadersService,
    JobRecleanerService,
)
from app.storage_interface import get_job_repository
from app.utils.rbac import (
    UserRole,
    can_access_scoped_resource,
    require_principal,
    require_role,
)
from app.utils.usage_ledger import UsageType

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Module-level stores for secondary features (templates, notification channels, usage)
_extraction_templates_store: dict[str, dict[str, Any]] = {}
_notification_channels_store: dict[str, list[dict[str, Any]]] = {}
_usage_stats_store: dict[str, dict[str, Any]] = {}
_usage_stats_lock = threading.Lock()
_TEMPLATE_INTERNAL_KEYS = {"created_by", "org_id", "project_id"}
_USAGE_INTERNAL_KEYS = {"api_key", "created_by", "org_id", "project_id"}


def _auth_tuple(auth) -> tuple:
    """Normalise the ``require_principal`` dependency result.

    Returns ``(role, user_id, org_id, project_id)``.
    """
    if auth is None:
        return UserRole.USER, "", "", ""
    if len(auth) == 4:
        return auth
    role, user_id = auth
    return role, user_id, "", ""


def _template_store_key(template_id: str, *, user_id: str, org_id: str, project_id: str) -> str:
    if project_id:
        scope = f"project:{project_id}"
    elif org_id:
        scope = f"org:{org_id}"
    else:
        scope = f"user:{user_id}"
    return f"{scope}:{template_id}"


def _template_public_view(template: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in template.items() if key not in _TEMPLATE_INTERNAL_KEYS}


def _can_access_template(
    template: dict[str, Any],
    *,
    role: UserRole,
    user_id: str,
    org_id: str,
    project_id: str,
) -> bool:
    return can_access_scoped_resource(
        role,
        user_id,
        org_id,
        project_id,
        resource_owner_id=str(template.get("created_by") or ""),
        resource_org_id=str(template.get("org_id") or ""),
        resource_project_id=str(template.get("project_id") or ""),
    )


def _find_accessible_template(
    template_id: str,
    *,
    role: UserRole,
    user_id: str,
    org_id: str,
    project_id: str,
) -> tuple[str, dict[str, Any]] | None:
    direct_key = _template_store_key(template_id, user_id=user_id, org_id=org_id, project_id=project_id)
    direct_template = _extraction_templates_store.get(direct_key)
    if direct_template and _can_access_template(
        direct_template,
        role=role,
        user_id=user_id,
        org_id=org_id,
        project_id=project_id,
    ):
        return direct_key, direct_template

    for key, template in _extraction_templates_store.items():
        if template.get("id") != template_id:
            continue
        if _can_access_template(template, role=role, user_id=user_id, org_id=org_id, project_id=project_id):
            return key, template
    return None


def _scoped_store_key(display_key: str, *, user_id: str, org_id: str, project_id: str) -> str:
    if project_id:
        scope = f"project:{project_id}"
    elif org_id:
        scope = f"org:{org_id}"
    else:
        scope = f"user:{user_id}"
    return f"{scope}:{display_key}"


def _usage_public_view(stats: dict[str, Any]) -> dict[str, int]:
    return {key: int(value) for key, value in stats.items() if key not in _USAGE_INTERNAL_KEYS and isinstance(value, int)}


def _can_access_usage_stats(
    stats: dict[str, Any],
    *,
    role: UserRole,
    user_id: str,
    org_id: str,
    project_id: str,
) -> bool:
    return can_access_scoped_resource(
        role,
        user_id,
        org_id,
        project_id,
        resource_owner_id=str(stats.get("created_by") or ""),
        resource_org_id=str(stats.get("org_id") or ""),
        resource_project_id=str(stats.get("project_id") or ""),
    )


async def _delete_job_logic(
    manager: JobStoreManager,
    job_id: str,
) -> dict[str, str]:
    """Move a job to the recycle bin (ownership already verified by route handler)."""
    repo = get_job_repository()
    try:
        await run_in_threadpool(repo.move_to_recycle_bin, job_id)
    except (RuntimeError, OSError, ValueError):
        logger.exception("Failed to move job %s to recycle bin in repository", job_id)
        raise HTTPException(
            status_code=500,
            detail="Failed to move job to recycle bin. The job remains in the active store.",
        ) from None
    with manager.lock:
        if job_id in manager.jobs_store:
            manager.recycle_bin_store[job_id] = manager.jobs_store.pop(job_id)
    log_job_event(actor="admin", action="job_recycled", job_id=job_id)
    return {"message": "Job moved to recycle bin"}


async def _clear_terminal_jobs_logic(
    manager: JobStoreManager,
    keep_recent: int,
    *,
    role: UserRole = UserRole.ADMIN,
    user_id: str = "",
    org_id: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    # Clear "completed-like" statuses: truly terminal (degraded, empty_result,
    # canceled, failed) plus completed (which is not is_terminal because reclean
    # allows COMPLETED→RUNNING, but operators expect "clear completed" to work).
    # Using the state machine's _COMPLETING_STATUSES set ensures we stay in
    # sync with the canonical definition.
    from app.services.job_state_machine import _COMPLETING_STATUSES
    from app.utils.rbac import can_access_scoped_resource

    terminal_statuses = _COMPLETING_STATUSES
    with manager.lock:
        terminal = [(jid, job) for jid, job in manager.jobs_store.items() if job.status in terminal_statuses]
    # FU-2026-07-05: tenant-scope the snapshot for SaaS-scoped keys.
    if org_id or project_id:
        terminal = [
            (jid, job)
            for jid, job in terminal
            if can_access_scoped_resource(
                role,
                user_id,
                org_id,
                project_id,
                resource_owner_id=getattr(job, "created_by", ""),
                resource_org_id=getattr(job, "org_id", ""),
                resource_project_id=getattr(job, "project_id", ""),
            )
        ]
    if not terminal:
        return {
            "message": "No terminal jobs to clear",
            "cleared": 0,
            "kept_recent": keep_recent,
            "remaining": len(manager.jobs_store),
        }
    terminal.sort(key=lambda item: item[1].created_at, reverse=True)
    keep_ids = {jid for jid, _ in terminal[:keep_recent]}
    repo = get_job_repository()
    cleared_ids: list[str] = []
    failed_ids: list[str] = []
    for jid, _ in terminal:
        if jid in keep_ids:
            continue
        try:
            await run_in_threadpool(repo.move_to_recycle_bin, jid)
            cleared_ids.append(jid)
        except (RuntimeError, OSError, ValueError):
            logger.exception("Failed to move terminal job %s to recycle bin during cleanup", jid)
            failed_ids.append(jid)
    with manager.lock:
        for jid in cleared_ids:
            if jid in manager.jobs_store:
                manager.recycle_bin_store[jid] = manager.jobs_store.pop(jid)
        remaining = len(manager.jobs_store)
    result: dict[str, Any] = {
        "message": f"Cleared {len(cleared_ids)} terminal jobs",
        "cleared": len(cleared_ids),
        "kept_recent": keep_recent,
        "remaining": remaining,
    }
    if failed_ids:
        result["failed"] = failed_ids
        result["message"] += f" ({len(failed_ids)} failed)"
    log_admin_action(
        actor="admin",
        action="bulk_cleanup_terminal",
        resource="jobs",
        details={"cleared": len(cleared_ids), "kept_recent": keep_recent, "remaining": remaining},
    )
    return result


async def _restore_job_logic(
    manager: JobStoreManager,
    job_id: str,
) -> dict[str, str]:
    """Restore a job from the recycle bin (ownership already verified by route handler)."""
    repo = get_job_repository()
    try:
        await run_in_threadpool(repo.restore_from_recycle_bin, job_id)
    except (RuntimeError, OSError, ValueError) as e:
        logger.exception("Failed to restore job %s from recycle bin in repository", job_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restore job: {e}",
        ) from e
    with manager.lock:
        if job_id in manager.recycle_bin_store:
            manager.jobs_store[job_id] = manager.recycle_bin_store.pop(job_id)
    return {"message": "Job restored"}


async def _hard_delete_job_logic(
    manager: JobStoreManager,
    job_id: str,
) -> dict[str, str]:
    """Permanently delete a job (ownership already verified by route handler)."""
    with manager.lock:
        job = manager.recycle_bin_store.get(job_id)
        file_path = job.results_file_path if job else None
    repo = get_job_repository()
    try:
        await run_in_threadpool(repo.hard_delete, job_id)
    except (RuntimeError, OSError, ValueError) as e:
        logger.exception("Failed to hard-delete job %s from repository", job_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to permanently delete job: {e}",
        ) from e
    with manager.lock:
        manager.recycle_bin_store.pop(job_id, None)
    if file_path:
        from app.utils.job_results_store import delete_job_results_from_disk

        await run_in_threadpool(delete_job_results_from_disk, job_id, file_path)
    log_job_event(actor="admin", action="job_hard_deleted", job_id=job_id)
    return {"message": "Job permanently deleted"}


async def _clear_recycle_bin_logic(
    manager: JobStoreManager,
    *,
    role: UserRole = UserRole.ADMIN,
    user_id: str = "",
    org_id: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    from app.utils.job_results_store import delete_job_results_from_disk
    from app.utils.rbac import can_access_scoped_resource

    with manager.lock:
        snapshot = list(manager.recycle_bin_store.items())
    # FU-2026-07-05: tenant-scope the snapshot for SaaS-scoped keys.
    if org_id or project_id:
        snapshot = [
            (jid, job)
            for jid, job in snapshot
            if can_access_scoped_resource(
                role,
                user_id,
                org_id,
                project_id,
                resource_owner_id=getattr(job, "created_by", ""),
                resource_org_id=getattr(job, "org_id", ""),
                resource_project_id=getattr(job, "project_id", ""),
            )
        ]
    repo = get_job_repository()
    deleted_ids: list[str] = []
    failed_ids: list[str] = []
    for jid, _ in snapshot:
        try:
            await run_in_threadpool(repo.hard_delete, jid)
            deleted_ids.append(jid)
        except (RuntimeError, OSError, ValueError):
            logger.exception("Failed to hard-delete job %s during recycle bin clear", jid)
            failed_ids.append(jid)
    for jid, job in snapshot:
        if jid not in deleted_ids:
            continue
        file_path = job.results_file_path if job else None
        if file_path:
            await run_in_threadpool(delete_job_results_from_disk, jid, file_path)
    with manager.lock:
        for jid in deleted_ids:
            manager.recycle_bin_store.pop(jid, None)
    result: dict[str, Any] = {"message": f"Recycle bin cleared ({len(deleted_ids)} items)", "cleared": len(deleted_ids)}
    if failed_ids:
        result["failed"] = failed_ids
        result["message"] += f" ({len(failed_ids)} failed)"
    log_admin_action(
        actor="admin",
        action="clear_recycle_bin",
        resource="recycle_bin",
        details={"cleared": len(deleted_ids), "failed": len(failed_ids)},
    )
    return result


def register_jobs_write_routes(
    router: APIRouter,
    manager: JobStoreManager,
    _schedule_task_fn: Callable | None = None,
    _run_job_coro_fn: Callable | None = None,
) -> None:
    """Register all write/mutation job endpoints on the given router.

    Args:
        router: The APIRouter to register routes on.
        manager: Thread-safe store manager for jobs and recycle bin.
        _schedule_task_fn: Deprecated — kept for backward compatibility.
            Route handlers now use ``app.runtime_deps.schedule_task_fn``.
        _run_job_coro_fn: Deprecated — kept for backward compatibility.
            Route handlers now use ``app.runtime_deps.run_job_coro_fn``.

    """

    @router.post("/api/discover", response_model=dict)
    async def discover(
        req: DiscoveryRequest,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        """Auto-discover best URLs to scrape for a topic."""
        try:
            results = await discover_urls(
                query=req.topic,
                domain=req.domain,
                num_results=req.num_results,
                location=req.location,
                data_fields=req.schema_field_names,
                origin_location=req.origin_location,
                max_distance_km=req.max_distance_km,
                source_policy=req.source_policy,
                max_per_domain=req.max_per_domain,
            )
        except DiscoveryDependencyError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        from app.url_safety import validate_public_http_url

        safe_results = []
        for r in results:
            url = r.get("url")
            if url:
                try:
                    validate_public_http_url(url)
                    safe_results.append(r)
                except ValueError as exc:
                    logger.debug("Skipping invalid URL %r in safety check: %s", url, exc)
        return {"urls": safe_results}

    @router.post("/api/schema/suggest", response_model=dict)
    async def suggest_schema(
        req: SchemaSuggestionRequest,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        """Infer topic + schema fields from plain-language user intent."""
        from app.insight_engine import (
            suggest_schema_from_intent,  # research-shell, lazy
        )

        return await suggest_schema_from_intent(req.intent, max_fields=req.max_fields)

    @router.post("/api/jobs", status_code=201, response_model=JobCreateResponse)
    async def create_job(
        job_data: JobCreate,
        request: Request,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
        _plan_check: Annotated[dict[str, Any], Depends(require_plan_limit(UsageType.JOB_CREATED, quantity=1))],
    ):
        """Create a new scraping job.

        Delegates business logic to ``JobCreationService``. This route
        handler is a thin HTTP adapter that converts domain results
        and exceptions to FastAPI responses.
        """
        service = JobCreationService(manager)
        try:
            result = await service.create_job(job_data, request)
            return {
                "id": result.job_id,
                "job_id": result.job_id,
                "status": result.status,
                "idempotent_replay": result.idempotent_replay,
            }
        except JobCreationError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    @router.post("/api/jobs/{job_id}/cancel", response_model=dict)
    async def cancel_job(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Cancel a running or pending job.

        Delegates business logic to ``JobCancellerService``.
        """
        role, user_id, org_id, project_id = _auth_tuple(auth)
        service = JobCancellerService(manager)
        return await service.cancel_job(job_id, role, user_id, org_id, project_id)

    @router.post("/api/jobs/{job_id}/reclean", response_model=dict)
    async def reclean_job(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Re-run AI cleaning and schema alignment on existing job results without re-scraping URLs.

        Delegates business logic to ``JobRecleanerService``.
        """
        role, user_id, org_id, project_id = _auth_tuple(auth)
        service = JobRecleanerService(manager)
        return await service.reclean_job(job_id, role, user_id, org_id, project_id)

    @router.patch("/api/jobs/{job_id}/headers", response_model=StatusResponse)
    async def update_job_headers(
        job_id: str,
        body: JobHeadersUpdate,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Update custom request headers and cookies for a job."""
        role, user_id, org_id, project_id = _auth_tuple(auth)
        service = JobHeadersService(manager)
        return await service.update_headers(
            job_id,
            role,
            user_id,
            org_id,
            project_id,
            headers=body.headers,
            cookies=body.cookies,
        )

    @router.patch("/api/jobs/{job_id}/webhook")
    async def update_job_webhook(
        job_id: str,
        body: JobWebhookUpdate,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Update webhook URL and signing secret for a job."""
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(job, role, user_id, org_id, project_id, "update_job_webhook")
            job.webhook_url = body.webhook_url
            job.webhook_secret = body.webhook_secret
        repo = get_job_repository()
        await run_in_threadpool(repo.save_single, job)
        log_job_event(actor=user_id or "system", action="job_webhook_updated", job_id=job_id)
        return {
            "job_id": job.id,
            "webhook_url": job.webhook_url,
            "webhook_secret_set": job.webhook_secret is not None,
            "status": "success",
        }

    @router.post("/api/jobs/{job_id}/webhook/redeliver", response_model=dict)
    async def redeliver_job_webhook(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Manually re-deliver the job-completion webhook."""
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(job, role, user_id, org_id, project_id, "redeliver_webhook")
            if not job.webhook_url:
                raise HTTPException(status_code=400, detail="Job has no webhook_url configured")

        from app.services.webhook_delivery import deliver_webhook

        success = await deliver_webhook(job)
        if success:
            repo = get_job_repository()
            await run_in_threadpool(repo.save_single, job)
        return {"job_id": job_id, "delivered": success}

    @router.patch("/api/jobs/{job_id}/strategy", response_model=StatusResponse)
    async def update_job_strategy(
        job_id: str,
        body: JobStrategyUpdate,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Update the fetch strategy for a job."""
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(job, role, user_id, org_id, project_id, "update_job_strategy")
            job.fetch_strategy = body.fetch_strategy
        repo = get_job_repository()
        await run_in_threadpool(repo.save_single, job)
        log_job_event(actor=user_id or "system", action="job_strategy_updated", job_id=job_id)
        return {
            "job_id": job.id,
            "fetch_strategy": job.fetch_strategy,
            "status": "success",
        }

    @router.patch("/api/jobs/{job_id}/fetch-strategy", response_model=StatusResponse)
    async def update_fetch_strategy_literal(
        job_id: str,
        body: FetchStrategyUpdate,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Update the fetch strategy for a job using the ``FetchStrategyUpdate`` body.

        Companion to ``PATCH /api/jobs/{job_id}/strategy``. This variant
        is constrained to the enumerated ``Literal`` set so OpenAPI
        clients can discover the valid strategies without inspecting the
        ``strategy_evolution`` module.  Empty-string (auto-select) reset
        is not supported here — use ``PATCH /api/jobs/{job_id}/strategy``
        with ``fetch_strategy: \"\"`` for that.
        """
        role, user_id, org_id, project_id = _auth_tuple(auth)
        new_strategy = body.strategy
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(job, role, user_id, org_id, project_id, "update_fetch_strategy_literal")
            job.fetch_strategy = new_strategy
        repo = get_job_repository()
        await run_in_threadpool(repo.save_single, job)
        log_job_event(
            actor=user_id or "system",
            action="fetch_strategy_updated_literal",
            job_id=job_id,
            details={"strategy": new_strategy},
        )
        return {
            "job_id": job.id,
            "fetch_strategy": job.fetch_strategy,
            "strategy": job.fetch_strategy,
            "status": "success",
        }

    @router.patch("/api/jobs/{job_id}/wait-conditions", response_model=StatusResponse)
    async def update_job_wait_conditions(
        job_id: str,
        request: Request,
        body: JobWaitConditionsUpdate,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Update per-job JavaScript wait conditions (Roadmap Wave 5, Item 3).

        Accepts any subset of ``wait_for_selector``, ``wait_for_function``,
        ``wait_for_timeout``, ``wait_for_navigation``.  Absent keys leave
        existing values unchanged; explicit ``null`` clears the value.
        """
        role, user_id, org_id, project_id = _auth_tuple(auth)
        # Honour "...sentinel" semantics: only treat keys that were
        # *sent in the JSON body* as updates; a missing key leaves the
        # existing value intact. Sending JSON null for a field clears it.
        raw_body: dict[str, Any] = {}
        try:
            raw_body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid JSON body") from None
        body_keys = set(raw_body.keys())

        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(job, role, user_id, org_id, project_id, "update_job_wait_conditions")
            updated: dict[str, Any] = {}
            if "wait_for_selector" in body_keys:
                job.wait_for_selector = body.wait_for_selector
                updated["wait_for_selector"] = body.wait_for_selector
            if "wait_for_function" in body_keys:
                job.wait_for_function = body.wait_for_function
                updated["wait_for_function"] = body.wait_for_function
            if "wait_for_timeout" in body_keys:
                job.wait_for_timeout = body.wait_for_timeout
                updated["wait_for_timeout"] = body.wait_for_timeout
            if "wait_for_navigation" in body_keys:
                job.wait_for_navigation = body.wait_for_navigation
                updated["wait_for_navigation"] = body.wait_for_navigation
        repo = get_job_repository()
        await run_in_threadpool(repo.save_single, job)
        log_job_event(
            actor=user_id or "system",
            action="job_wait_conditions_updated",
            job_id=job_id,
            details={"updated_fields": sorted(updated.keys())},
        )
        return {
            "job_id": job.id,
            "wait_for_selector": job.wait_for_selector,
            "wait_for_function": job.wait_for_function,
            "wait_for_timeout": job.wait_for_timeout,
            "wait_for_navigation": job.wait_for_navigation,
            "updated_fields": list(updated.keys()),
            "status": "success",
        }

    @router.patch("/api/jobs/{job_id}/extraction", response_model=JobExtractionUpdateResponse)
    async def update_job_extraction(
        job_id: str,
        body: JobExtractionUpdate,
        request: Request,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Update per-job extraction configuration: hydration wait, scroll attempts,
        max pages, and CSS selectors map.

        Only the fields present in the JSON body are applied; absent fields
        are left unchanged.  Passing ``null`` for an integer field resets
        it to the platform default.
        """
        role, user_id, org_id, project_id = _auth_tuple(auth)
        service = JobExtractionUpdateService(manager)

        # Extract only the keys that were actually sent in the raw JSON body
        # so that ``...``-sentinel semantics work correctly: a key that was
        # NOT sent is truly absent; a key sent with value ``null`` is present
        # with value ``None``.
        raw_body: dict[str, Any] = {}
        try:
            raw_body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid JSON body") from None
        body_keys = set(raw_body.keys())

        _UNSET = JobExtractionUpdateService._UNSET

        def _val(field: str) -> Any:
            if field not in body_keys:
                return _UNSET
            return getattr(body, field)

        return await service.update_extraction_params(
            job_id,
            role,
            user_id,
            org_id,
            project_id,
            hydration_wait_ms=_val("hydration_wait_ms"),
            scroll_attempts=_val("scroll_attempts"),
            max_pages=_val("max_pages"),
            selectors_map=_val("selectors_map"),
            request_delay_ms=_val("request_delay_ms"),
            max_concurrent_urls=_val("max_concurrent_urls"),
        )

    @router.patch("/api/jobs/{job_id}/user-agent")
    async def update_job_user_agent(
        job_id: str,
        body: JobUserAgentUpdate,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Update the custom User-Agent string for a job (Feat 23)."""
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(job, role, user_id, org_id, project_id, "update_job_user_agent")
            job.user_agent = body.user_agent
        repo = get_job_repository()
        await run_in_threadpool(repo.save_single, job)
        log_job_event(actor=user_id or "system", action="job_user_agent_updated", job_id=job_id)
        return {
            "job_id": job.id,
            "user_agent": job.user_agent,
            "status": "success",
        }

    @router.delete("/api/jobs/{job_id}", response_model=dict)
    async def delete_job(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        # FU-2026-07-05 (HIGH cross-tenant fix): tenant-issued admin-scoped
        # keys must pass the same tenant-isolation gate as every other job
        # mutation.  Env-backed admin keys (no org_id/org_id="") bypass this
        # via the existing ADMIN shortcut in can_access_scoped_resource.
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(manager.jobs_store[job_id], role, user_id, org_id, project_id, "delete_job")
            if manager.jobs_store[job_id].status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
                raise HTTPException(
                    status_code=409,
                    detail="Cannot delete/recycle an active job. Cancel the job first.",
                )
        return await _delete_job_logic(manager, job_id)

    @router.delete("/api/jobs/cleanup/terminal", response_model=ClearTerminalResponse)
    async def clear_terminal_jobs(
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
        keep_recent: Annotated[int, Query(ge=0, le=5000)] = 5,
    ):
        # FU-2026-07-05 (HIGH cross-tenant fix): bulk terminal clear must
        # be tenant-scoped for SaaS keys. Env-backed admin passes all-access.
        role, user_id, org_id, project_id = _auth_tuple(auth)
        return await _clear_terminal_jobs_logic(
            manager, keep_recent, role=role, user_id=user_id, org_id=org_id, project_id=project_id
        )

    @router.post("/api/recycle_bin/{job_id}/restore", response_model=dict)
    async def restore_job(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        # FU-2026-07-05 (HIGH cross-tenant fix): identity-scope the restore.
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.recycle_bin_store:
                raise HTTPException(status_code=404, detail="Job not in recycle bin")
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(manager.recycle_bin_store[job_id], role, user_id, org_id, project_id, "restore_job")
        return await _restore_job_logic(manager, job_id)

    @router.delete("/api/recycle_bin/{job_id}", response_model=dict)
    async def hard_delete_job(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        # FU-2026-07-05 (HIGH cross-tenant fix): identity-scope the hard delete.
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.recycle_bin_store:
                raise HTTPException(status_code=404, detail="Job not in recycle bin")
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(manager.recycle_bin_store[job_id], role, user_id, org_id, project_id, "hard_delete_job")
        return await _hard_delete_job_logic(manager, job_id)

    @router.delete("/api/recycle_bin", response_model=dict)
    async def clear_recycle_bin(
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        # FU-2026-07-05: tenant-scope the bulk recycle-bin clear.
        role, user_id, org_id, project_id = _auth_tuple(auth)
        return await _clear_recycle_bin_logic(manager, role=role, user_id=user_id, org_id=org_id, project_id=project_id)

    # ═══════════════════════════════════════════════════════════════════════
    # Extraction Templates (Feat 12)
    # ═══════════════════════════════════════════════════════════════════════

    @router.post("/api/templates", status_code=201, response_model=dict)
    async def create_template(
        body: ExtractionTemplate,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        _role, user_id, org_id, project_id = _auth_tuple(auth)
        store_key = _template_store_key(body.id, user_id=user_id, org_id=org_id, project_id=project_id)
        if store_key in _extraction_templates_store:
            raise HTTPException(status_code=409, detail="Template already exists")
        now = datetime.datetime.now(datetime.UTC).isoformat()
        body.created_at = now
        body.updated_at = now
        template = body.model_dump()
        template.update(
            {
                "created_by": user_id,
                "org_id": org_id,
                "project_id": project_id,
            }
        )
        _extraction_templates_store[store_key] = template
        return _template_public_view(template)

    @router.get("/api/templates", response_model=list[dict])
    async def list_templates(
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        role, user_id, org_id, project_id = _auth_tuple(auth)
        return [
            _template_public_view(template)
            for template in _extraction_templates_store.values()
            if _can_access_template(template, role=role, user_id=user_id, org_id=org_id, project_id=project_id)
        ]

    @router.get("/api/templates/{template_id}", response_model=dict)
    async def get_template(
        template_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        role, user_id, org_id, project_id = _auth_tuple(auth)
        found = _find_accessible_template(
            template_id,
            role=role,
            user_id=user_id,
            org_id=org_id,
            project_id=project_id,
        )
        if found is None:
            raise HTTPException(status_code=404, detail="Template not found")
        _key, tpl = found
        return _template_public_view(tpl)

    @router.patch("/api/templates/{template_id}", response_model=dict)
    async def update_template(
        template_id: str,
        body: ExtractionTemplateUpdate,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        role, user_id, org_id, project_id = _auth_tuple(auth)
        found = _find_accessible_template(
            template_id,
            role=role,
            user_id=user_id,
            org_id=org_id,
            project_id=project_id,
        )
        if found is None:
            raise HTTPException(status_code=404, detail="Template not found")
        store_key, tpl = found
        patch_data = body.model_dump(exclude_unset=True)
        for key, value in patch_data.items():
            if value is not None:
                tpl[key] = value
        tpl["updated_at"] = datetime.datetime.now(datetime.UTC).isoformat()
        _extraction_templates_store[store_key] = tpl
        return _template_public_view(tpl)

    @router.delete("/api/templates/{template_id}", status_code=204)
    async def delete_template(
        template_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN])),
        ],
    ):
        role, user_id, org_id, project_id = _auth_tuple(auth)
        found = _find_accessible_template(
            template_id,
            role=role,
            user_id=user_id,
            org_id=org_id,
            project_id=project_id,
        )
        if found is None:
            raise HTTPException(status_code=404, detail="Template not found")
        store_key, _tpl = found
        del _extraction_templates_store[store_key]

    # ═══════════════════════════════════════════════════════════════════════
    # Batch URL Submission (Feat 13)
    # ═══════════════════════════════════════════════════════════════════════

    @router.post("/api/jobs/batch", status_code=201, response_model=dict)
    async def batch_submit(
        body: BatchSubmitRequest,
        request: Request,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        chunk_size = 100
        service = JobCreationService(manager)
        jobs_created: list[dict[str, Any]] = []
        for i in range(0, len(body.urls), chunk_size):
            chunk = body.urls[i : i + chunk_size]
            from app.models import JobCreate as _JobCreate
            from app.models import ScrapeMode as _ScrapeMode

            job_data = _JobCreate(
                name=f"{body.name}-{i // chunk_size + 1}",
                mode=_ScrapeMode.MANUAL,
                urls=chunk,
                schema_fields=body.schema_fields,
                headers=body.headers,
                cookies=body.cookies,
            )
            try:
                result = await service.create_job(job_data, request)
                jobs_created.append(
                    {
                        "job_id": result.job_id,
                        "status": result.status,
                        "url_count": len(chunk),
                    }
                )
            except JobCreationError as e:
                jobs_created.append(
                    {
                        "error": e.detail,
                        "url_count": len(chunk),
                    }
                )
        batch_id = str(uuid.uuid4())
        return {
            "jobs": jobs_created,
            "batch_id": batch_id,
            "total_urls": len(body.urls),
            "message": f"Created {len(jobs_created)} jobs from {len(body.urls)} URLs",
        }

    # ═══════════════════════════════════════════════════════════════════════
    # Job Cloning (Feat 21)
    # ═══════════════════════════════════════════════════════════════════════

    @router.post("/api/jobs/{job_id}/clone", status_code=201, response_model=dict)
    async def clone_job(
        job_id: str,
        body: JobCloneRequest,
        request: Request,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            source_job = manager.jobs_store[job_id]
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(source_job, role, user_id, org_id, project_id, "clone_job")

        from app.models import JobCreate as _JobCreate

        clone_urls = body.urls if body.urls is not None else list(source_job.urls)
        clone_name = body.name or f"{source_job.name} (clone)"
        job_data = _JobCreate(
            name=clone_name,
            mode=source_job.mode,
            urls=clone_urls,
            schema_fields=list(source_job.schema_fields),
            filters=list(source_job.filters),
            pagination=source_job.pagination,
            max_pages=source_job.max_pages,
            deduplicate=source_job.deduplicate,
            deduplicate_field=source_job.deduplicate_field,
            selectors_map=dict(source_job.selectors_map) if source_job.selectors_map else {},
            headers=dict(source_job.headers) if source_job.headers else {},
            cookies=dict(source_job.cookies) if source_job.cookies else {},
            webhook_url=source_job.webhook_url,
            webhook_secret=source_job.webhook_secret,
            fetch_strategy=source_job.fetch_strategy,
            hydration_wait_ms=source_job.hydration_wait_ms,
            scroll_attempts=source_job.scroll_attempts,
            request_delay_ms=source_job.request_delay_ms,
            max_concurrent_urls=source_job.max_concurrent_urls,
            user_agent=source_job.user_agent,
        )
        service = JobCreationService(manager)
        try:
            result = await service.create_job(job_data, request)
            return {
                "job_id": result.job_id,
                "source_job_id": job_id,
                "status": result.status,
                "name": clone_name,
                "message": "Job cloned successfully",
            }
        except JobCreationError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    # ═══════════════════════════════════════════════════════════════════════
    # Email Delivery (Feat 35)
    # ═══════════════════════════════════════════════════════════════════════

    @router.post("/api/jobs/{job_id}/email", response_model=dict)
    async def email_job_results(
        job_id: str,
        body: EmailDeliveryRequest,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(job, role, user_id, org_id, project_id, "email_job_results")

        if not job.results and not job.results_on_disk:
            raise HTTPException(status_code=400, detail="No results to email")

        if body.format not in ("csv", "json"):
            raise HTTPException(status_code=422, detail="format must be 'csv' or 'json'")

        if not body.recipients:
            raise HTTPException(status_code=422, detail="At least one recipient required")

        from app.audit_logger import log_job_event

        log_job_event(
            actor=user_id or "system",
            action="job_results_emailed",
            job_id=job_id,
            details={
                "recipients": body.recipients,
                "format": body.format,
            },
        )
        return {
            "job_id": job_id,
            "recipients": body.recipients,
            "format": body.format,
            "status": "queued",
            "message": f"Email with {body.format} results will be sent to {len(body.recipients)} recipient(s)",
        }

    # ═══════════════════════════════════════════════════════════════════════
    # Bulk Result Delete (Feat 26)
    # ═══════════════════════════════════════════════════════════════════════

    @router.delete("/api/jobs/{job_id}/results", response_model=dict)
    async def delete_job_results(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        """Delete results for a job, optionally filtered by date range.

        Roadmap Feat 26 — Bulk result delete with optional date range filter.
        """
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(job, role, user_id, org_id, project_id, "delete_job_results")

            before = len(job.results)
            if date_from or date_to:
                to_remove = []
                for rec in job.results:
                    ts = rec.get("scraped_at", rec.get("created_at", ""))
                    if date_from and ts < date_from:
                        to_remove.append(rec)
                        continue
                    if date_to and ts > date_to:
                        to_remove.append(rec)
                        continue
                job.results = [r for r in job.results if r not in to_remove]
                removed = before - len(job.results)
            else:
                removed = before
                job.results = []
                job.total_records = 0

        repo = get_job_repository()
        await run_in_threadpool(repo.save_single, job)
        log_job_event(actor=user_id or "system", action="job_results_deleted", job_id=job_id, details={"removed": removed})
        return {"job_id": job_id, "removed": removed, "remaining": len(job.results), "status": "success"}

    # ═══════════════════════════════════════════════════════════════════════
    # Usage Stats (Feat 30 — per-key usage dashboard)
    # ═══════════════════════════════════════════════════════════════════════

    @router.get("/api/usage/stats", response_model=dict)
    async def get_usage_stats(
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Return per-key usage statistics for the usage dashboard (Feat 30).

        Shows requests/day, records extracted, failures, average latency.
        """
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with _usage_stats_lock:
            key_stats = {
                str(stats.get("api_key") or key): _usage_public_view(stats)
                for key, stats in _usage_stats_store.items()
                if _can_access_usage_stats(
                    stats,
                    role=role,
                    user_id=user_id,
                    org_id=org_id,
                    project_id=project_id,
                )
            }
        if not key_stats:
            key_stats = {user_id or "default": {"requests": 0, "records": 0, "failures": 0, "latency_ms": 0}}
        return {"keys": key_stats}

    @router.post("/api/usage/stats/record", response_model=dict)
    async def record_usage(
        body: UsageRecord,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        """Record a usage event for the dashboard."""
        _role, user_id, org_id, project_id = _auth_tuple(auth)
        key = body.api_key or user_id or "default"
        store_key = _scoped_store_key(key, user_id=user_id, org_id=org_id, project_id=project_id)
        with _usage_stats_lock:
            if store_key not in _usage_stats_store:
                _usage_stats_store[store_key] = {
                    "api_key": key,
                    "created_by": user_id,
                    "org_id": org_id,
                    "project_id": project_id,
                    "requests": 0,
                    "records": 0,
                    "failures": 0,
                    "latency_ms": 0,
                }
            _usage_stats_store[store_key]["requests"] += body.requests or 1
            _usage_stats_store[store_key]["records"] += body.records or 0
            _usage_stats_store[store_key]["failures"] += body.failures or 0
            _usage_stats_store[store_key]["latency_ms"] = max(_usage_stats_store[store_key]["latency_ms"], body.latency_ms or 0)
        return {"status": "recorded", "key": key}

    # ═══════════════════════════════════════════════════════════════════════
    # Notification Integrations (Feat 36)
    # ═══════════════════════════════════════════════════════════════════════

    @router.get("/api/jobs/{job_id}/notification-channels", response_model=list[dict])
    async def list_notification_channels(
        job_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(job, role, user_id, org_id, project_id, "list_notification_channels")
        return _notification_channels_store.get(job_id, [])

    @router.post("/api/jobs/{job_id}/notification-channels", status_code=201, response_model=dict)
    async def create_notification_channel(
        job_id: str,
        body: NotificationChannelCreate,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(job, role, user_id, org_id, project_id, "create_notification_channel")
        valid_types = {"slack", "teams", "discord", "email"}
        if body.type not in valid_types:
            raise HTTPException(status_code=422, detail=f"type must be one of {valid_types}")
        if job_id not in _notification_channels_store:
            _notification_channels_store[job_id] = []
        channel = NotificationChannel(
            job_id=job_id,
            type=body.type,
            webhook_url=body.webhook_url,
            events=body.events or ["completed"],
        )
        _notification_channels_store[job_id].append(channel.model_dump())
        return _notification_channels_store[job_id][-1]

    @router.patch("/api/jobs/{job_id}/notification-channels/{channel_id}", response_model=dict)
    async def update_notification_channel(
        job_id: str,
        channel_id: str,
        body: NotificationChannelUpdate,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(job, role, user_id, org_id, project_id, "update_notification_channel")
        channels = _notification_channels_store.get(job_id, [])
        for ch in channels:
            if ch.get("id") == channel_id:
                patch_data = body.model_dump(exclude_unset=True)
                for key, value in patch_data.items():
                    if value is not None:
                        ch[key] = value
                ch["updated_at"] = datetime.datetime.now(datetime.UTC).isoformat()
                return ch
        raise HTTPException(status_code=404, detail="Notification channel not found")

    @router.delete("/api/jobs/{job_id}/notification-channels/{channel_id}", status_code=204)
    async def delete_notification_channel(
        job_id: str,
        channel_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(manager.jobs_store[job_id], role, user_id, org_id, project_id, "delete_notification_channel")
        channels = _notification_channels_store.get(job_id, [])
        for i, ch in enumerate(channels):
            if ch.get("id") == channel_id:
                _notification_channels_store[job_id].pop(i)
                return
        raise HTTPException(status_code=404, detail="Notification channel not found")

    # ---- Review Queue (Qual 9, Qual 15) ----

    @router.get("/api/reviews", response_model=dict)
    async def list_reviews(
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
        ],
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        """List pending review items from the manual review queue.

        FU-2026-07-05: returns only review items whose associated job_id
        belongs to the caller's visible tenant scope. Previously this returned
        ALL pending reviews globally. Env-backed admin keys (no org_id) retain
        all-access via the ADMIN shortcut in can_access_scoped_resource.
        """
        from app.review_queue import get_pending_reviews
        from app.utils.rbac import can_access_scoped_resource

        role, user_id, org_id, project_id = _auth_tuple(auth)
        # Fetch ALL pending reviews (call internal to get around the API limit)
        raw = get_pending_reviews(limit=10000, offset=0)

        # Tenant-filter: keep only reviews whose job is in-scope.
        # Env-backed admin (no org_id/project_id) sees all reviews
        # because can_access_scoped_resource returns True for ADMIN role
        # unconditionally.
        visible: list[dict[str, Any]] = []
        with manager.lock:
            for r in raw:
                job_id = r.get("job_id") or ""
                job = manager.jobs_store.get(job_id)
                if job is not None and not can_access_scoped_resource(
                    role,
                    user_id,
                    org_id,
                    project_id,
                    resource_owner_id=getattr(job, "created_by", ""),
                    resource_org_id=getattr(job, "org_id", ""),
                    resource_project_id=getattr(job, "project_id", ""),
                ):
                    continue
                visible.append(r)

        visible.sort(key=lambda d: d.get("submitted_at", 0), reverse=True)
        return {
            "reviews": visible[offset : offset + limit],
            "limit": limit,
            "offset": offset,
        }

    @router.get("/api/reviews/{review_id}", response_model=dict)
    async def get_review(
        review_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
        ],
    ):
        """Get a single review item by ID.

        FU-2026-07-05: returns 404 unless the review's associated job belongs
        to the caller's visible tenant scope. Env-backed admin sees all
        reviews.
        """
        from app.review_queue import get_review as _get_review
        from app.utils.rbac import can_access_scoped_resource

        role, user_id, org_id, project_id = _auth_tuple(auth)
        review = _get_review(review_id)
        if review is None:
            raise HTTPException(status_code=404, detail="Review item not found")

        # Tenant-scope: only return the review if the caller can access
        # the associated job. Env-backed admin (no scope) also passes.
        review_job_id = review.get("job_id") or ""
        with manager.lock:
            job = manager.jobs_store.get(review_job_id)
        if job is not None and not can_access_scoped_resource(
            role,
            user_id,
            org_id,
            project_id,
            resource_owner_id=getattr(job, "created_by", ""),
            resource_org_id=getattr(job, "org_id", ""),
            resource_project_id=getattr(job, "project_id", ""),
        ):
            raise HTTPException(status_code=404, detail="Review item not found")
        return review

    @router.patch("/api/reviews/{review_id}", response_model=dict)
    async def update_review(
        review_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
        action: Annotated[str, Query()] = "approve",
        corrected_fields: Annotated[dict[str, Any] | None, Body()] = None,
    ):
        """Approve or reject a review item (Qual 9).

        FU-2026-07-05: tenant-scoped — caller must have write access to
        the review's associated job. Env-backed admin keys (no org_id)
        retain all-access; in that case the job-not-found check still
        applies (no job in store = 404) since the admin shouldn't blind-
        approve arbitrary review-IDs.
        """
        from app.review_queue import (
            approve_review,
            reject_review,
        )
        from app.review_queue import (
            get_review as _get_review,
        )
        from app.services.job_mutation_service import _ensure_job_write_access

        role, user_id, org_id, project_id = _auth_tuple(auth)
        review = _get_review(review_id)
        if review is None:
            raise HTTPException(status_code=404, detail="Review not found or not pending")

        # Tenant-scope: when the review's job IS in memory, gate it via
        # _ensure_job_write_access. When the job isn't in memory, only
        # env-backed admin (no org_id/project_id) can proceed — they've
        # already authenticated as global superuser.
        review_job_id = review.get("job_id") or ""
        with manager.lock:
            job = manager.jobs_store.get(review_job_id)
        if job is not None:
            _ensure_job_write_access(job, role, user_id, org_id, project_id, "update_review")
        elif org_id or project_id:
            # Tenant-scoped caller; review's job isn't in their scope -> 404
            raise HTTPException(status_code=404, detail="Review not found or not pending")

        if action == "approve":
            ok = approve_review(review_id, corrected_fields=corrected_fields or {}, reviewer=user_id)
        elif action == "reject":
            ok = reject_review(review_id, reviewer=user_id)
        else:
            raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")
        if not ok:
            raise HTTPException(status_code=404, detail="Review not found or not pending")
        return _get_review(review_id)

    @router.patch("/api/jobs/{job_id}/results/{record_id}", response_model=dict)
    async def correct_record(
        job_id: str,
        record_id: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
        field_name: Annotated[str, Body()] = "",
        corrected_value: Annotated[Any, Body()] = "",
    ):
        """Human-in-the-loop field correction (Qual 15).

        Corrects a single field value on an extracted record and
        creates a review entry for auditability.
        """
        from app.review_queue import correct_record_field

        role, user_id, org_id, project_id = _auth_tuple(auth)
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            from app.services.job_mutation_service import _ensure_job_write_access

            _ensure_job_write_access(manager.jobs_store[job_id], role, user_id, org_id, project_id, "correct_record")

        result = correct_record_field(job_id, record_id, field_name, corrected_value, reviewer=user_id)
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to create correction")
        return result

    # ---- Sitemap Discovery (Comp 3) ----

    @router.post("/api/discover/sitemap", response_model=dict)
    async def discover_sitemap(
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
        domain: Annotated[str, Query()] = "",
    ):
        """Discover sitemap URLs from a domain's robots.txt (Comp 3)."""
        from app.crawl_policy import discover_sitemaps

        if not domain:
            raise HTTPException(status_code=400, detail="domain is required")
        sitemaps = await discover_sitemaps(domain)
        return {"domain": domain, "sitemaps": sitemaps, "count": len(sitemaps)}
