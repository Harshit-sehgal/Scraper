"""Mutable runtime dependency container for route handlers.

Routes reference ``schedule_task_fn`` and ``run_job_coro_fn`` through this
module instead of capturing them as closure variables. Tests can swap
implementations via :func:`set_deps` to avoid real background job execution.

Usage in production::

    import app.runtime_deps
    app.runtime_deps.set_deps(
        schedule=_schedule_background_task,
        run_job=_run_job_wrapper,
    )

Usage in tests::

    import app.runtime_deps

    async def fake_run_job(job_id: str) -> None:
        await asyncio.sleep(0.01)

    app.runtime_deps.set_deps(schedule=fake_schedule, run_job=fake_run_job)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)


def _default_schedule_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task | None:
    """Default implementation — schedule a coroutine as a background task.

    Falls back to the FastAPI lifespan :func:`schedule_background_task` which
    wraps :func:`asyncio.create_task` with error logging.
    """
    try:
        from app.lifespan import schedule_background_task

        return schedule_background_task(coro)
    except ImportError:
        pass
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            return loop.create_task(coro)
    except RuntimeError:
        pass
    return None


async def _default_run_job(job_id: str) -> None:
    """Default implementation — delegate to the standard job runner."""
    from app.lifespan import run_job_wrapper

    await run_job_wrapper(job_id)


# ── Mutable module-level references ───────────────────────────────────
# Routes import these directly. Tests swap them via set_deps().
schedule_task_fn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task | None] = _default_schedule_task
run_job_coro_fn: Callable[[str], Coroutine[Any, Any, None]] = _default_run_job


def set_deps(
    schedule: Callable[[Coroutine[Any, Any, Any]], asyncio.Task | None] | None = None,
    run_job: Callable[[str], Coroutine[Any, Any, None]] | None = None,
) -> None:
    """Swap runtime dependency implementations.

    Pass ``None`` to leave that dependency unchanged. Tests should call
    ``set_deps(schedule=fake_schedule, run_job=fake_run_job)`` before
    creating the test app so route handlers immediately see the new
    implementations.

    The call is idempotent and safe to call multiple times. Pass
    ``None`` to leave a dependency unchanged, or omit both arguments
    to restore both defaults.
    """
    global schedule_task_fn, run_job_coro_fn
    if schedule is not None:
        schedule_task_fn = schedule
    else:
        schedule_task_fn = _default_schedule_task
    if run_job is not None:
        run_job_coro_fn = run_job
    else:
        run_job_coro_fn = _default_run_job
