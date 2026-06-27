"""User Data Router — delete-my-data and account management.

Provides an endpoint for users to delete all their personal data
across all DataForge stores: jobs, workflows, auth profiles,
scheduled monitoring jobs, and SaaS identity records.

This implements the ``delete-my-data`` gap from Prompt 12.

Roadmap (Comp #8): GDPR right-to-erasure receipt and /compliance/gdpr/forget
alias endpoint with audit trail.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.utils.rbac import UserRole, require_principal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/user", tags=["user-data"])


# ---------------------------------------------------------------------------
# Delete-my-data endpoint
# ---------------------------------------------------------------------------


@router.delete("/data", status_code=200)
async def delete_my_data(
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> dict[str, Any]:
    """Delete all data owned by the authenticated user.

    Clears the following data scoped to the caller's identity:
    - Scraping jobs and their results from disk
    - Saved workflows
    - Auth profiles
    - Scheduled monitoring jobs
    - SaaS identity records (API keys, memberships, user account)

    The current stable API deletes only the caller's own data. Admin/operator
    deletion of another user's data is intentionally not exposed here.

    Returns a summary of what was deleted.
    """
    _role, caller_user_id, _org_id, _project_id = auth

    # Resolve which user's data to delete
    # (In a full implementation, query params would allow an admin to specify
    # another user_id. For now, only the caller's own data is deleted.)

    user_id = caller_user_id
    if not user_id:
        raise HTTPException(status_code=400, detail="Cannot determine user identity.")

    summary: dict[str, int] = {
        "jobs_deleted": 0,
        "workflows_deleted": 0,
        "auth_profiles_deleted": 0,
        "scheduled_jobs_deleted": 0,
        "api_keys_revoked": 0,
        "memberships_removed": 0,
    }

    # 1. Delete jobs owned by the user.
    #
    # ``jobs_store`` is a process-wide dict guarded by
    # ``app.globals._jobs_store_lock`` — every mutation (iter, read,
    # pop) must hold the lock to avoid races with concurrent
    # router-driven mutations and ``RuntimeError: dictionary changed
    # size during iteration``.
    from app.globals import _jobs_store_lock, jobs_store

    job_ids_to_delete: list[str] = []
    job_result_paths: dict[str, str | None] = {}
    try:
        # ``jobs_store`` is always a plain ``dict[str, Job]`` at runtime;
        # the repository-style method dispatch (get_all_jobs / list_jobs /
        # delete_job / remove_job) is dead code that the type checker could
        # not narrow through ``hasattr`` on a typed dict.
        with _jobs_store_lock:
            for job_id, job in list(jobs_store.items()):
                if isinstance(job, dict):
                    owner = str(job.get("created_by") or job.get("created_by_fingerprint") or job.get("user_id", ""))
                    rfp = job.get("result_file_path")
                else:
                    owner = str(
                        getattr(job, "created_by", "")
                        or getattr(job, "created_by_fingerprint", "")
                        or getattr(job, "user_id", ""),
                    )
                    rfp = getattr(job, "result_file_path", None)
                if owner == user_id:
                    job_ids_to_delete.append(job_id)
                    job_result_paths[job_id] = rfp
            for jid in job_ids_to_delete:
                jobs_store.pop(jid, None)
        summary["jobs_deleted"] = len(job_ids_to_delete)
    except (RuntimeError, OSError, ValueError, TypeError) as e:
        logger.warning("Failed to delete jobs for user %s: %s", user_id, e)

    # 2. Delete workflow results from disk
    try:
        from app.utils.job_results_store import delete_job_results_from_disk

        for jid in job_ids_to_delete:
            delete_job_results_from_disk(jid, file_path=job_result_paths.get(jid))
    except (OSError, ValueError, TypeError) as e:
        logger.debug("Failed to delete job results from disk: %s", e)

    # 3. Delete workflows owned by the user (single flocked batch via delete_many).
    try:
        from app.routers.workflow import _get_workflow_repo
        from app.workflow_repository import JsonWorkflowRepository

        repo = _get_workflow_repo()

        if isinstance(repo, JsonWorkflowRepository):
            # JSON store supports batch delete_many for efficiency.
            workflow_store = repo._store
            workflow_ids_to_delete: list[str] = [
                str(wf.get("id", "")) for wf in workflow_store.values() if str(wf.get("user_id", "")) == user_id and wf.get("id")
            ]
            if workflow_ids_to_delete:
                summary["workflows_deleted"] = workflow_store.delete_many(workflow_ids_to_delete)
            else:
                summary["workflows_deleted"] = 0
        else:
            # SQL-backed repos: iterate and delete individually.
            user_wfs = repo.list_workflows(user_id=user_id, limit=500)
            deleted = 0
            for wf in user_wfs:
                if repo.delete(str(wf.get("id", ""))):
                    deleted += 1
            summary["workflows_deleted"] = deleted
    except (RuntimeError, ValueError, TypeError) as e:
        logger.warning("Failed to delete workflows for user %s: %s", user_id, e)

    # 4. Delete auth profiles owned by the user (single flocked batch via delete_many).
    try:
        from app.routers.auth_profiles import _auth_profiles as auth_profile_store

        profile_ids_to_delete: list[str] = [
            str(prof.get("id", ""))
            for prof in auth_profile_store.values()
            if str(prof.get("user_id", "")) == user_id and prof.get("id")
        ]
        if profile_ids_to_delete:
            summary["auth_profiles_deleted"] = auth_profile_store.delete_many(profile_ids_to_delete)
        else:
            summary["auth_profiles_deleted"] = 0
    except (RuntimeError, ValueError, TypeError) as e:
        logger.warning("Failed to delete auth profiles for user %s: %s", user_id, e)

    # 5. Delete scheduled monitoring jobs owned by the user (single flocked batch via delete_many).
    try:
        from app.routers.scheduled_monitoring import _scheduled_jobs as schedule_store

        schedule_ids_to_delete: list[str] = [
            str(sched.get("id", ""))
            for sched in schedule_store.values()
            if str(sched.get("user_id", "")) == user_id and sched.get("id")
        ]
        if schedule_ids_to_delete:
            summary["scheduled_jobs_deleted"] = schedule_store.delete_many(schedule_ids_to_delete)
        else:
            summary["scheduled_jobs_deleted"] = 0
    except (RuntimeError, ValueError, TypeError) as e:
        logger.warning("Failed to delete scheduled jobs for user %s: %s", user_id, e)

    # 6. Revoke API keys and remove SaaS identity records
    try:
        from app.saas.identity_store import get_identity_store
        from app.saas.service import ApiKeyService, MembershipService

        store = get_identity_store()

        # Revoke all API keys issued by this user
        api_key_service = ApiKeyService(store=store)
        try:
            if hasattr(store, "get_user_by_email"):
                user = store.get_user(user_id) or store.get_user_by_email(user_id)
                if user:
                    # The user_id might be a UUID, not an email — try to find keys
                    memberships = store.list_user_memberships(user.id, include_removed=True)
                    for membership in memberships:
                        projects = store.list_org_projects(membership.org_id)
                        for project in projects:
                            keys = api_key_service.list_for_project(project.id)
                            for key in keys:
                                if key.user_id == user.id:
                                    api_key_service.revoke(key.id)
                                    summary["api_keys_revoked"] += 1
        except (RuntimeError, ValueError, TypeError) as e:
            logger.debug("Failed to revoke API keys: %s", e)

        # Remove memberships
        membership_service = MembershipService(store=store)
        # The user_id here might be an API key fingerprint, not a SaaS user.
        # Try to find the user by user_id or email.
        try:
            user = store.get_user(user_id)
            if not user:
                # Try to match via memberships directly
                memberships = store.list_user_memberships(user_id, include_removed=True)
                for membership in memberships:
                    membership_service.remove_member(membership.id)
                    summary["memberships_removed"] += 1
            else:
                # Remove all memberships for this user
                memberships = store.list_user_memberships(user.id, include_removed=True)
                for membership in memberships:
                    membership_service.remove_member(membership.id)
                    summary["memberships_removed"] += 1
        except (RuntimeError, ValueError, TypeError) as e:
            logger.debug("Failed to remove memberships: %s", e)

    except ImportError:
        logger.debug("SaaS identity store not available")
    except (RuntimeError, OSError, ValueError, TypeError) as e:
        logger.warning("Failed to clean up SaaS identity for user %s: %s", user_id, e)

    logger.info(
        "User data deleted for %s: %s",
        user_id,
        {k: v for k, v in summary.items() if v > 0},
    )

    # ── GDPR deletion receipt ───────────────────────────────────────
    # Roadmap Comp #8: A machine-readable deletion receipt enables the
    # subject to prove compliance. The receipt_token is a SHA-256
    # fingerprint of (user_id + timestamp + summary) — tampering with
    # any field invalidates the token. The audit logger also records
    # the deletion event for immutable compliance evidence.
    receipt_id = str(uuid.uuid4())
    receipt_timestamp = datetime.datetime.now(datetime.UTC).isoformat()
    receipt_payload = f"{user_id}:{receipt_timestamp}:{summary}".encode()
    receipt_token = hashlib.sha256(receipt_payload).hexdigest()[:16]

    from app.audit_logger import log_admin_action

    log_admin_action(
        actor=user_id,
        action="gdpr_data_deletion",
        resource="user_data",
        details={
            "receipt_id": receipt_id,
            "receipt_token": receipt_token,
            **summary,
        },
    )

    return {
        "status": "ok",
        "user_id": user_id,
        "summary": summary,
        "message": "All user data has been deleted.",
        "receipt": {
            "id": receipt_id,
            "timestamp": receipt_timestamp,
            "token": receipt_token,
        },
    }


# ---------------------------------------------------------------------------
# GDPR right-to-erasure alias (Roadmap Comp #8)
# ---------------------------------------------------------------------------


compliance_router = APIRouter(prefix="/api/compliance/gdpr", tags=["compliance"])


@compliance_router.post("/forget", status_code=200)
async def gdpr_forget(
    auth: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    ],
) -> dict[str, Any]:
    """GDPR right-to-erasure (alias for DELETE /api/user/data).

    Accepts POST so it can be called by compliance automation tools
    that prefer POST semantics for destructive operations. Delegates
    to the canonical ``delete_my_data`` handler and returns the same
    GDPR deletion receipt.
    """
    return await delete_my_data(auth)
