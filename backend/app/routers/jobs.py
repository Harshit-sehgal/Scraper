"""Job routes — factory combining read-only and write/mutation sub-routers.

This module is the public entry point for the jobs router. It creates a
``JobStoreManager`` instance from the caller-provided stores, then composes
two sub-routers:

- **Read routes** (``GET``) — ``app.routers.jobs_read``
- **Write routes** (``POST/DELETE``) — ``app.routers.jobs_write``

Keeps backward-compatible exports so existing imports in ``main.py``,
tests, and scripts continue to work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.routers.jobs_read import register_jobs_read_routes
from app.routers.jobs_state import JobStoreManager
from app.routers.jobs_write import register_jobs_write_routes
from fastapi import APIRouter

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.models import Job


def create_jobs_router(
    jobs_store: dict[str, Job],
    recycle_bin_store: dict[str, Job],
    persist_state_fn: Callable | None = None,  # noqa: ARG001, RUF100
    schedule_task_fn: Callable | None = None,
    run_job_coro_fn: Callable | None = None,
    config: dict | None = None,  # noqa: ARG001, RUF100
) -> APIRouter:
    """Create and return an APIRouter with all job-related endpoints.

    The factory accepts the same signature as before so existing callers
    in ``main.py`` continue to work. The ``persist_state_fn`` and
    ``config`` parameters are preserved for backward compatibility (they
    are no longer used internally — state persistence is handled through
    the repository interface).

    Args:
        jobs_store: Shared in-memory jobs dict (from app.globals).
        recycle_bin_store: Shared in-memory recycle-bin dict (from app.globals).
        persist_state_fn: Legacy — kept for backward compatibility.
        schedule_task_fn: Callable to schedule a background task.
        run_job_coro_fn: Callable that returns a coroutine to run a job by ID.
        config: Legacy — kept for backward compatibility.

    Returns:
        APIRouter with all job endpoints registered.
    """
    manager = JobStoreManager(jobs_store, recycle_bin_store)
    router = APIRouter(tags=["jobs"])

    register_jobs_read_routes(router, manager)

    if schedule_task_fn is not None and run_job_coro_fn is not None:
        register_jobs_write_routes(router, manager, schedule_task_fn, run_job_coro_fn)

    return router
