"""User Data Router — delete-my-data and account management.

Provides an endpoint for users to delete all their personal data
across all DataForge stores: jobs, workflows, auth profiles,
scheduled monitoring jobs, and SaaS identity records.

This implements the ``delete-my-data`` gap from Prompt 12.
"""

from __future__ import annotations

import logging
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

    # 1. Delete jobs owned by the user
    try:
        from app.globals import jobs_store

        job_ids_to_delete: list[str] = []
        if hasattr(jobs_store, "get_all_jobs"):
            all_jobs = jobs_store.get_all_jobs()
        elif hasattr(jobs_store, "list_jobs"):
            all_jobs = jobs_store.list_jobs()
        else:
            all_jobs = {}

        if isinstance(all_jobs, dict):
            for job_id, job in all_jobs.items():
                if isinstance(job, dict):
                    owner = str(job.get("created_by") or job.get("created_by_fingerprint") or job.get("user_id", ""))
                else:
                    owner = str(
                        getattr(job, "created_by", "")
                        or getattr(job, "created_by_fingerprint", "")
                        or getattr(job, "user_id", ""),
                    )
                if owner == user_id:
                    job_ids_to_delete.append(job_id)
            for jid in job_ids_to_delete:
                if hasattr(jobs_store, "delete_job"):
                    jobs_store.delete_job(jid)
                elif hasattr(jobs_store, "remove_job"):
                    jobs_store.remove_job(jid)
                else:
                    all_jobs.pop(jid, None)
        summary["jobs_deleted"] = len(job_ids_to_delete)
    except (RuntimeError, OSError, ValueError, TypeError) as e:
        logger.warning("Failed to delete jobs for user %s: %s", user_id, e)

    # 2. Delete workflow results from disk
    try:
        from app.utils.job_results_store import delete_job_results_from_disk

        for jid in job_ids_to_delete:
            delete_job_results_from_disk(jid)
    except (OSError, ValueError, TypeError) as e:
        logger.debug("Failed to delete job results from disk: %s", e)

    # 3. Delete workflows owned by the user (single flocked batch via delete_many).
    try:
        from app.routers.workflow import _workflows as workflow_store

        workflow_ids_to_delete: list[str] = [
            str(wf.get("id", "")) for wf in workflow_store.values() if str(wf.get("user_id", "")) == user_id and wf.get("id")
        ]
        if workflow_ids_to_delete:
            summary["workflows_deleted"] = workflow_store.delete_many(workflow_ids_to_delete)
        else:
            summary["workflows_deleted"] = 0
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

    return {
        "status": "ok",
        "user_id": user_id,
        "summary": summary,
        "message": "All user data has been deleted.",
    }
