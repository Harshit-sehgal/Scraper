"""Centralized Job State Machine.

Previously, job state transitions were scattered across 5+ modules
(job_runner, finalization, status_classifier, state_store, utils/job,
postgres_repository_base, routers/jobs_write).

This module provides a single source of truth for valid transitions
and safe transition functions.

Valid states (from app.models.JobStatus):
    PENDING → DISCOVERING → RUNNING → COMPLETED
                                     → DEGRADED
                                     → EMPTY_RESULT
                                     → FAILED
    PENDING → CANCELED
    DISCOVERING → CANCELED
    RUNNING → CANCELED
    RUNNING → FAILED
    PENDING → FAILED  (recovery)
    DISCOVERING → FAILED  (recovery)
    RUNNING → FAILED  (recovery)
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from app.models import JobStatus

logger = logging.getLogger(__name__)

# ── Valid transition table ─────────────────────────────────────────────
# Maps current status → set of allowed next statuses
_VALID_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING: {
        JobStatus.DISCOVERING,
        JobStatus.RUNNING,
        JobStatus.CANCELED,
        JobStatus.FAILED,  # recovery
    },
    JobStatus.DISCOVERING: {
        JobStatus.RUNNING,
        JobStatus.CANCELED,
        JobStatus.FAILED,  # recovery or error
    },
    JobStatus.RUNNING: {
        JobStatus.COMPLETED,
        JobStatus.DEGRADED,
        JobStatus.EMPTY_RESULT,
        JobStatus.CANCELED,
        JobStatus.FAILED,  # exception or recovery
    },
    JobStatus.COMPLETED: set(),  # terminal
    JobStatus.DEGRADED: set(),  # terminal
    JobStatus.EMPTY_RESULT: set(),  # terminal
    JobStatus.CANCELED: set(),  # terminal
    JobStatus.FAILED: set(),  # terminal
}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


# ── Public API ─────────────────────────────────────────────────────────


def can_transition(job: Any, new_status: JobStatus) -> bool:
    """Check whether the transition from the job's current status to
    *new_status* is allowed."""
    allowed = _VALID_TRANSITIONS.get(job.status)
    if allowed is None:
        return False
    return new_status in allowed


def transition_to(
    job: Any,
    new_status: JobStatus,
    *,
    error: str | None = None,
    cancel_requested: bool = False,
    completed_at: str | None = None,
) -> None:
    """Transition a job to a new status with validation.

    Args:
        job: The job object (must have ``.status`` attribute).
        new_status: The target status.
        error: Optional error message to set on ``job.error``.
        cancel_requested: Whether to set ``job.cancel_requested``.
        completed_at: Optional ISO timestamp for completion. Auto-set
            if the new status is terminal.

    Raises:
        ValueError: If the transition is invalid.
    """
    # Allow idempotent transitions (same status → same status)
    if job.status == new_status:
        return

    if not can_transition(job, new_status):
        valid = _VALID_TRANSITIONS.get(job.status, set())
        msg = (
            f"Invalid state transition: {job.status.value!r} → "
            f"{new_status.value!r}. "
            f"Allowed from {job.status.value!r}: "
            f"{[s.value for s in valid] or ['(none — terminal)']}"
        )
        raise ValueError(msg)

    old_status = job.status
    job.status = new_status

    if error is not None:
        job.error = error
    if cancel_requested:
        job.cancel_requested = True
    if completed_at is not None:
        job.completed_at = completed_at
    elif new_status in _TERMINAL_STATUSES:
        job.completed_at = _now_iso()

    logger.info(
        "Job %s: state transition %r → %r",
        getattr(job, "id", "?"),
        old_status.value,
        new_status.value,
    )


def mark_canceled(job: Any, reason: str = "Canceled by user") -> None:
    """Mark a job as canceled with a safe transition.

    This is the replacement for ``app.utils.job.mark_job_canceled``.
    """
    # Allow cancel from any status that supports it
    if job.status in (
        JobStatus.PENDING,
        JobStatus.DISCOVERING,
        JobStatus.RUNNING,
    ):
        transition_to(
            job,
            JobStatus.CANCELED,
            error=reason,
            cancel_requested=False,
        )
    else:
        logger.warning(
            "Cannot cancel job %s in status %r",
            getattr(job, "id", "?"),
            job.status.value,
        )


def mark_recovered_failed(job: Any) -> None:
    """Mark a job as failed after recovery from restart/crash.

    This is the replacement for the inline recovery logic in
    ``app.state_store.load_state`` and
    ``app.postgres_repository_base``.
    """
    if job.status in (
        JobStatus.PENDING,
        JobStatus.DISCOVERING,
        JobStatus.RUNNING,
    ):
        transition_to(
            job,
            JobStatus.FAILED,
            error="Recovered after restart while still in progress.",
            cancel_requested=False,
        )


# ── Internal helpers ───────────────────────────────────────────────────

_TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.DEGRADED,
        JobStatus.EMPTY_RESULT,
        JobStatus.CANCELED,
        JobStatus.FAILED,
    }
)


def is_terminal(status: JobStatus) -> bool:
    """Check if a status is terminal (no further transitions allowed)."""
    return status in _TERMINAL_STATUSES


def valid_transitions_from(status: JobStatus) -> frozenset[JobStatus]:
    """Return the set of allowed transitions from a given status."""
    return frozenset(_VALID_TRANSITIONS.get(status, set()))
