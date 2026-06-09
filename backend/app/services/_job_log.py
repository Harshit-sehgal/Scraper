"""Shared ``_log`` helper for job log entries.

Consolidates the identical ``_log`` function previously duplicated across
``discovery.py``, ``post_processing.py``, ``insight.py``, and
``finalization.py``.

Usage::

    from app.services._job_log import log_job_message  # or shorter alias

    log_job_message(job, "message")
    log_job_message(job, "warning", level="warning", persist_fn=my_fn)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


def log_job_message(job: Any, message: str, level: str = "info", persist_fn: Callable | None = None) -> None:
    """Append a log entry to a job and optionally persist.

    Args:
        job: The job object (must have a ``logs`` list).
        message: The log message text.
        level: Log level (``info``, ``warning``, ``error``).
        persist_fn: Optional zero-arg callable to persist state after logging.

    """
    from app.models import LogEntry

    job.logs.append(LogEntry(message=message, level=level))
    if persist_fn:
        persist_fn()
