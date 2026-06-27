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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

logger = logging.getLogger(__name__)


def _default_schedule_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task | None:
    """Default implementation — schedule a coroutine as a background task.

    Falls back to the FastAPI lifespan :func:`schedule_background_task` which
    wraps :func:`asyncio.create_task` with error logging.
    """
    try:
        from app.lifespan import schedule_background_task

        return schedule_background_task(coro)
    except ImportError as exc:
        logger.debug("Could not import schedule_background_task: %s", exc)
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            return loop.create_task(coro)
    except RuntimeError as exc:
        logger.debug("No running event loop for background task: %s", exc)
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
    schedule_task_fn = schedule if schedule is not None else _default_schedule_task
    run_job_coro_fn = run_job if run_job is not None else _default_run_job


# ── Runtime dependency checks ────────────────────────────────────────────

# Required packages — the application will not start if any are missing.
REQUIRED_PACKAGES: list[tuple[str, str]] = [
    ("pydantic", "pydantic"),
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("httpx", "httpx"),
    ("bs4", "beautifulsoup4"),
]

# Optional packages — the application logs a warning if missing but continues.
OPTIONAL_PACKAGES: list[tuple[str, str]] = [
    ("playwright", "playwright"),
    ("aiosqlite", "aiosqlite"),
    ("psycopg2", "psycopg2-binary"),
    ("psycopg", "psycopg[binary,pool]"),
]


def check_runtime_deps(fail_on_missing: bool = True) -> dict[str, list[str]]:
    """Verify that required and optional Python packages are importable.

    Returns a dict with keys ``"missing_required"`` and ``"missing_optional"``,
    each containing a list of pip package names that could not be imported.

    Args:
        fail_on_missing: If True (default), raise ``RuntimeError`` when any
            required package is missing. Set False for a soft check (e.g. in
            health endpoints).
    """
    missing_required: list[str] = []
    missing_optional: list[str] = []

    for module_name, pip_name in REQUIRED_PACKAGES:
        try:
            __import__(module_name)
        except ImportError:
            missing_required.append(pip_name)

    for module_name, pip_name in OPTIONAL_PACKAGES:
        try:
            __import__(module_name)
        except ImportError:
            missing_optional.append(pip_name)

    if missing_optional:
        logger.warning(
            "Optional packages not installed: %s. Some features may be unavailable.",
            ", ".join(missing_optional),
        )

    if missing_required and fail_on_missing:
        msg = f"Missing required packages: {', '.join(missing_required)}. Install them with: pip install " + " ".join(
            missing_required
        )
        raise RuntimeError(msg)

    return {"missing_required": missing_required, "missing_optional": missing_optional}
