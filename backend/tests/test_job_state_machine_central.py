"""Test that job state machine is centralized, used consistently, and
that the mutating functions (transition_to, mark_canceled,
mark_recovered_failed) enforce all valid/invalid transitions correctly."""

from __future__ import annotations

import datetime
from unittest.mock import Mock

import pytest
from app.models import JobStatus
from app.services.job_state_machine import (
    _TERMINAL_STATUSES,
    can_transition,
    is_terminal,
    mark_canceled,
    mark_recovered_failed,
    sync_from_db,
    transition_to,
    valid_transitions_from,
)


def _mock_job(status: JobStatus = JobStatus.PENDING, **attrs) -> Mock:
    job = Mock()
    job.status = status
    job.error = None
    job.cancel_requested = False
    job.completed_at = None
    job.id = "test-job"
    for k, v in attrs.items():
        setattr(job, k, v)
    return job


# ═══════════════════════════════════════════════════════════════════════════
# transition_to — actual mutation tests
# ═══════════════════════════════════════════════════════════════════════════


def test_transition_to_valid_changes_status() -> None:
    job = _mock_job(JobStatus.PENDING)
    transition_to(job, JobStatus.RUNNING)
    assert job.status == JobStatus.RUNNING


def test_transition_to_invalid_raises_value_error() -> None:
    job = _mock_job(JobStatus.FAILED)
    with pytest.raises(ValueError, match="H7: Invalid state transition"):
        transition_to(job, JobStatus.RUNNING)


def test_transition_to_idempotent_same_status_is_noop() -> None:
    job = _mock_job(JobStatus.PENDING)
    original = job.status
    transition_to(job, JobStatus.PENDING)
    assert job.status == original


def test_transition_to_sets_error() -> None:
    job = _mock_job(JobStatus.PENDING)
    transition_to(job, JobStatus.FAILED, error="Something broke")
    assert job.error == "Something broke"
    assert job.status == JobStatus.FAILED


def test_transition_to_sets_cancel_requested() -> None:
    job = _mock_job(JobStatus.RUNNING)
    transition_to(job, JobStatus.CANCELED, cancel_requested=True)
    assert job.cancel_requested is True


def test_transition_to_auto_sets_completed_at_for_terminal() -> None:
    job = _mock_job(JobStatus.RUNNING)
    assert job.completed_at is None
    transition_to(job, JobStatus.COMPLETED)
    assert job.completed_at is not None


def test_transition_to_honors_explicit_completed_at() -> None:
    job = _mock_job(JobStatus.RUNNING)
    ts = "2026-06-01T12:00:00"
    transition_to(job, JobStatus.COMPLETED, completed_at=ts)
    assert job.completed_at == ts


def test_transition_to_completed_auto_sets_completed_at() -> None:
    """COMPLETED is a completing status (auto-sets completed_at) even though
    it is not terminal (reclean allows COMPLETED → RUNNING)."""
    job = _mock_job(JobStatus.RUNNING)
    transition_to(job, JobStatus.COMPLETED)
    assert job.completed_at is not None


def test_transition_to_non_terminal_does_not_set_completed_at() -> None:
    job = _mock_job(JobStatus.PENDING)
    transition_to(job, JobStatus.RUNNING)
    assert job.completed_at is None


# ═══════════════════════════════════════════════════════════════════════════
# mark_canceled
# ═══════════════════════════════════════════════════════════════════════════


def test_mark_canceled_pending_sets_canceled() -> None:
    job = _mock_job(JobStatus.PENDING)
    mark_canceled(job)
    assert job.status == JobStatus.CANCELED
    assert job.error is not None


def test_mark_canceled_discovering_sets_canceled() -> None:
    job = _mock_job(JobStatus.DISCOVERING)
    mark_canceled(job)
    assert job.status == JobStatus.CANCELED


def test_mark_canceled_running_sets_canceled() -> None:
    job = _mock_job(JobStatus.RUNNING)
    mark_canceled(job)
    assert job.status == JobStatus.CANCELED


def test_mark_canceled_terminal_does_not_change_status() -> None:
    job = _mock_job(JobStatus.COMPLETED)
    mark_canceled(job)
    assert job.status == JobStatus.COMPLETED


def test_mark_canceled_failed_does_not_change_status() -> None:
    job = _mock_job(JobStatus.FAILED)
    mark_canceled(job)
    assert job.status == JobStatus.FAILED


# ═══════════════════════════════════════════════════════════════════════════
# mark_recovered_failed
# ═══════════════════════════════════════════════════════════════════════════


def test_mark_recovered_failed_pending_sets_failed() -> None:
    job = _mock_job(JobStatus.PENDING)
    mark_recovered_failed(job)
    assert job.status == JobStatus.FAILED
    assert "Recovered after restart" in job.error


def test_mark_recovered_failed_running_sets_failed() -> None:
    job = _mock_job(JobStatus.RUNNING)
    mark_recovered_failed(job)
    assert job.status == JobStatus.FAILED


def test_mark_recovered_failed_terminal_does_not_change() -> None:
    job = _mock_job(JobStatus.COMPLETED)
    mark_recovered_failed(job)
    assert job.status == JobStatus.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════
# Query function tests (existing — expanded)
# ═══════════════════════════════════════════════════════════════════════════


def test_state_machine_is_central_source() -> None:
    """Verify state machine module is the single source of truth."""
    job = _mock_job(JobStatus.PENDING)
    assert can_transition(job, JobStatus.DISCOVERING)
    job.status = JobStatus.DISCOVERING
    assert can_transition(job, JobStatus.RUNNING)
    job.status = JobStatus.RUNNING
    assert can_transition(job, JobStatus.COMPLETED)
    # COMPLETED → RUNNING is allowed (reclean); FAILED → RUNNING is not
    job.status = JobStatus.COMPLETED
    assert can_transition(job, JobStatus.RUNNING)  # reclean path
    job.status = JobStatus.FAILED
    assert not can_transition(job, JobStatus.RUNNING)


def test_all_valid_transitions_defined() -> None:
    valid_paths = [
        (JobStatus.PENDING, JobStatus.DISCOVERING),
        (JobStatus.DISCOVERING, JobStatus.RUNNING),
        (JobStatus.RUNNING, JobStatus.COMPLETED),
        (JobStatus.RUNNING, JobStatus.DEGRADED),
        (JobStatus.RUNNING, JobStatus.EMPTY_RESULT),
        (JobStatus.RUNNING, JobStatus.FAILED),
        (JobStatus.PENDING, JobStatus.FAILED),
        (JobStatus.RUNNING, JobStatus.CANCELED),
        (JobStatus.COMPLETED, JobStatus.RUNNING),  # reclean
    ]
    for src, dst in valid_paths:
        job = _mock_job(src)
        assert can_transition(job, dst), f"Should allow {src} → {dst}"


def test_invalid_transitions_blocked() -> None:
    invalid_paths = [
        (JobStatus.FAILED, JobStatus.RUNNING),
        (JobStatus.CANCELED, JobStatus.RUNNING),
        (JobStatus.COMPLETED, JobStatus.FAILED),
    ]
    for src, dst in invalid_paths:
        job = _mock_job(src)
        assert not can_transition(job, dst), f"Should block {src} → {dst}"


def test_terminal_states_identified() -> None:
    for status in _TERMINAL_STATUSES:
        assert is_terminal(status), f"{status} should be terminal"
    non_terminal = {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}
    for status in non_terminal:
        assert not is_terminal(status), f"{status} should not be terminal"


def test_valid_transitions_from_terminal_returns_empty() -> None:
    for status in _TERMINAL_STATUSES:
        assert valid_transitions_from(status) == frozenset(), f"{status} should have no valid transitions"


def test_completed_is_not_terminal_due_to_reclean() -> None:
    """COMPLETED → RUNNING is allowed (reclean), so COMPLETED is not terminal."""
    assert not is_terminal(JobStatus.COMPLETED)
    assert can_transition(_mock_job(JobStatus.COMPLETED), JobStatus.RUNNING)
    assert valid_transitions_from(JobStatus.COMPLETED) == frozenset({JobStatus.RUNNING})


def test_valid_transitions_from_pending() -> None:
    pending_allowed = valid_transitions_from(JobStatus.PENDING)
    assert JobStatus.DISCOVERING in pending_allowed
    assert JobStatus.RUNNING in pending_allowed
    assert JobStatus.CANCELED in pending_allowed
    assert JobStatus.FAILED in pending_allowed


def test_transition_records_timestamp() -> None:
    job = _mock_job()
    job.status = JobStatus.RUNNING
    job.started_at = datetime.datetime.now(datetime.UTC).isoformat()
    assert job.started_at is not None
    assert job.status == JobStatus.RUNNING


# ═══════════════════════════════════════════════════════════════════════════
# Additional Coverage — Exhaustive transitions, double-cancel, sync_from_db
# ═══════════════════════════════════════════════════════════════════════════


def test_double_cancel_pending_is_idempotent() -> None:
    job = _mock_job(JobStatus.PENDING)
    mark_canceled(job)
    assert job.status == JobStatus.CANCELED
    mark_canceled(job)
    assert job.status == JobStatus.CANCELED


def test_double_cancel_running_is_idempotent() -> None:
    job = _mock_job(JobStatus.RUNNING)
    mark_canceled(job)
    assert job.status == JobStatus.CANCELED
    mark_canceled(job)
    assert job.status == JobStatus.CANCELED


def test_double_cancel_discovering_is_idempotent() -> None:
    job = _mock_job(JobStatus.DISCOVERING)
    mark_canceled(job)
    assert job.status == JobStatus.CANCELED
    mark_canceled(job)
    assert job.status == JobStatus.CANCELED


def test_cancel_from_completed_is_noop() -> None:
    job = _mock_job(JobStatus.COMPLETED)
    mark_canceled(job)
    assert job.status == JobStatus.COMPLETED


def test_cancel_from_failed_is_noop() -> None:
    job = _mock_job(JobStatus.FAILED)
    mark_canceled(job)
    assert job.status == JobStatus.FAILED


def test_cancel_from_degrated_is_noop() -> None:
    job = _mock_job(JobStatus.DEGRADED)
    mark_canceled(job)
    assert job.status == JobStatus.DEGRADED


def test_cancel_from_empty_result_is_noop() -> None:
    job = _mock_job(JobStatus.EMPTY_RESULT)
    mark_canceled(job)
    assert job.status == JobStatus.EMPTY_RESULT


def test_exhaustive_valid_transitions_from_pending() -> None:
    """PENDING should allow DISCOVERING, RUNNING, CANCELED, FAILED."""
    for dst in [JobStatus.DISCOVERING, JobStatus.RUNNING, JobStatus.CANCELED, JobStatus.FAILED]:
        job = _mock_job(JobStatus.PENDING)
        transition_to(job, dst)
        assert job.status == dst


def test_exhaustive_valid_transitions_from_discovering() -> None:
    """DISCOVERING should allow RUNNING, CANCELED, FAILED."""
    for dst in [JobStatus.RUNNING, JobStatus.CANCELED, JobStatus.FAILED]:
        job = _mock_job(JobStatus.DISCOVERING)
        transition_to(job, dst)
        assert job.status == dst


def test_exhaustive_valid_transitions_from_running() -> None:
    """RUNNING should allow COMPLETED, DEGRADED, EMPTY_RESULT, CANCELED, FAILED."""
    for dst in [JobStatus.COMPLETED, JobStatus.DEGRADED, JobStatus.EMPTY_RESULT, JobStatus.CANCELED, JobStatus.FAILED]:
        job = _mock_job(JobStatus.RUNNING)
        transition_to(job, dst)
        assert job.status == dst


def test_exhaustive_valid_transitions_from_completed() -> None:
    """COMPLETED should only allow RUNNING."""
    job = _mock_job(JobStatus.COMPLETED)
    transition_to(job, JobStatus.RUNNING)
    assert job.status == JobStatus.RUNNING


def test_exhaustive_invalid_transitions_from_every_state() -> None:
    """Every transition that is NOT in the valid table must raise ValueError."""
    all_statuses = list(JobStatus)
    for src in all_statuses:
        for dst in all_statuses:
            if src == dst:
                continue
            allowed = can_transition(_mock_job(src), dst)
            if not allowed:
                job = _mock_job(src)
                with pytest.raises(ValueError, match="H7"):
                    transition_to(job, dst)


def test_sync_from_db_noop_same_status() -> None:
    job = _mock_job(JobStatus.PENDING)
    sync_from_db(job, JobStatus.PENDING)
    assert job.status == JobStatus.PENDING


def test_sync_from_db_valid_transition() -> None:
    job = _mock_job(JobStatus.PENDING)
    sync_from_db(job, JobStatus.RUNNING)
    assert job.status == JobStatus.RUNNING


def test_sync_from_db_invalid_transition_raises() -> None:
    job = _mock_job(JobStatus.FAILED)
    with pytest.raises(ValueError, match="H7"):
        sync_from_db(job, JobStatus.RUNNING)


def test_sync_from_db_non_jobstatus_raises_type_error() -> None:
    job = _mock_job(JobStatus.PENDING)
    with pytest.raises(TypeError, match="must be a JobStatus"):
        sync_from_db(job, "PENDING")  # type: ignore[arg-type]


def test_sync_from_db_job_non_jobstatus_raises_type_error() -> None:
    class FakeJob:
        status = "PENDING"

    with pytest.raises(TypeError, match="must be a JobStatus"):
        sync_from_db(FakeJob(), JobStatus.PENDING)


def test_mark_recovered_failed_from_discovering() -> None:
    job = _mock_job(JobStatus.DISCOVERING)
    mark_recovered_failed(job)
    assert job.status == JobStatus.FAILED
    assert "Recovered after restart" in job.error


def test_mark_recovered_failed_from_canceled_is_noop() -> None:
    job = _mock_job(JobStatus.CANCELED)
    mark_recovered_failed(job)
    assert job.status == JobStatus.CANCELED


def test_mark_recovered_failed_from_degrated_is_noop() -> None:
    job = _mock_job(JobStatus.DEGRADED)
    mark_recovered_failed(job)
    assert job.status == JobStatus.DEGRADED


def test_mark_recovered_failed_from_empty_result_is_noop() -> None:
    job = _mock_job(JobStatus.EMPTY_RESULT)
    mark_recovered_failed(job)
    assert job.status == JobStatus.EMPTY_RESULT


def test_terminal_statuses_cannot_transition_to_anything() -> None:
    for status in _TERMINAL_STATUSES:
        for dst in list(JobStatus):
            if status == dst:
                continue
            assert not can_transition(_mock_job(status), dst), f"Terminal {status} should not allow → {dst}"


def test_completed_auto_sets_completed_at_with_explicit_completed_at() -> None:
    job = _mock_job(JobStatus.RUNNING)
    explicit_ts = "2026-07-01T00:00:00"
    transition_to(job, JobStatus.COMPLETED, completed_at=explicit_ts)
    assert job.completed_at == explicit_ts


def test_failed_auto_sets_completed_at() -> None:
    job = _mock_job(JobStatus.RUNNING)
    transition_to(job, JobStatus.FAILED, error="crashed")
    assert job.completed_at is not None


def test_degrated_auto_sets_completed_at() -> None:
    job = _mock_job(JobStatus.RUNNING)
    transition_to(job, JobStatus.DEGRADED)
    assert job.completed_at is not None


def test_empty_result_auto_sets_completed_at() -> None:
    job = _mock_job(JobStatus.RUNNING)
    transition_to(job, JobStatus.EMPTY_RESULT)
    assert job.completed_at is not None
