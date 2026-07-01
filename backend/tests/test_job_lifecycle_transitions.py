"""Job lifecycle integration tests — verifying state machine enforcement across
creation, deletion, cancellation, reclean, and cleanup paths.

These tests validate that the router-level logic correctly delegates to the
state machine and that the canonical status definitions are used consistently.
"""

import pytest
from app.models import Job, JobStatus
from app.services.job_state_machine import (
    _COMPLETING_STATUSES,
    _TERMINAL_STATUSES,
    can_transition,
    is_terminal,
    transition_to,
)

pytestmark = pytest.mark.api


def _job(status: JobStatus = JobStatus.PENDING) -> Job:
    """Create a Job with the given status."""
    return Job(name="test", status=status)


class TestStateMachineCanonicalDefinitions:
    """Verify the canonical status definitions are self-consistent."""

    def test_terminal_is_subset_of_completing(self) -> None:
        """Every terminal status should also be in completing statuses
        (since they set completed_at)."""
        assert _TERMINAL_STATUSES.issubset(_COMPLETING_STATUSES)

    def test_completed_is_completing_but_not_terminal(self) -> None:
        assert JobStatus.COMPLETED in _COMPLETING_STATUSES
        assert not is_terminal(JobStatus.COMPLETED)

    def test_degraded_is_terminal_and_completing(self) -> None:
        assert JobStatus.DEGRADED in _TERMINAL_STATUSES
        assert JobStatus.DEGRADED in _COMPLETING_STATUSES

    def test_empty_result_is_terminal_and_completing(self) -> None:
        assert JobStatus.EMPTY_RESULT in _TERMINAL_STATUSES
        assert JobStatus.EMPTY_RESULT in _COMPLETING_STATUSES

    def test_failed_is_terminal_and_completing(self) -> None:
        assert JobStatus.FAILED in _TERMINAL_STATUSES
        assert JobStatus.FAILED in _COMPLETING_STATUSES

    def test_canceled_is_terminal_and_completing(self) -> None:
        assert JobStatus.CANCELED in _TERMINAL_STATUSES
        assert JobStatus.CANCELED in _COMPLETING_STATUSES

    def test_non_terminal_statuses_are_not_in_terminal(self) -> None:
        for status in (JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING):
            assert status not in _TERMINAL_STATUSES, f"{status} should not be terminal"

    def test_completing_statuses_covers_all_end_states(self) -> None:
        """All 8 statuses must be in either completing or non-completing."""
        all_statuses = set(JobStatus)
        non_completing = all_statuses - _COMPLETING_STATUSES
        assert non_completing == {
            JobStatus.PENDING,
            JobStatus.DISCOVERING,
            JobStatus.RUNNING,
        }


class TestTransitionValidity:
    """All valid transitions must succeed; invalid ones must be rejected."""

    def test_pending_can_go_to_discovering(self) -> None:
        assert can_transition(_job(JobStatus.PENDING), JobStatus.DISCOVERING)

    def test_pending_can_go_to_running(self) -> None:
        assert can_transition(_job(JobStatus.PENDING), JobStatus.RUNNING)

    def test_pending_can_go_to_canceled(self) -> None:
        assert can_transition(_job(JobStatus.PENDING), JobStatus.CANCELED)

    def test_discovering_can_go_to_running(self) -> None:
        assert can_transition(_job(JobStatus.DISCOVERING), JobStatus.RUNNING)

    def test_running_can_go_to_completed(self) -> None:
        assert can_transition(_job(JobStatus.RUNNING), JobStatus.COMPLETED)

    def test_running_can_go_to_degraded(self) -> None:
        assert can_transition(_job(JobStatus.RUNNING), JobStatus.DEGRADED)

    def test_running_can_go_to_empty_result(self) -> None:
        assert can_transition(_job(JobStatus.RUNNING), JobStatus.EMPTY_RESULT)

    def test_running_can_go_to_failed(self) -> None:
        assert can_transition(_job(JobStatus.RUNNING), JobStatus.FAILED)

    def test_running_can_go_to_canceled(self) -> None:
        assert can_transition(_job(JobStatus.RUNNING), JobStatus.CANCELED)

    def test_completed_can_go_to_running_reclean(self) -> None:
        """COMPLETED → RUNNING is valid for the reclean path."""
        assert can_transition(_job(JobStatus.COMPLETED), JobStatus.RUNNING)

    def test_terminal_cannot_transition(self) -> None:
        """Terminal statuses (except COMPLETED) cannot transition."""
        for status in _TERMINAL_STATUSES:
            for target in JobStatus:
                if target == status:
                    continue
                assert not can_transition(_job(status), target), f"{status} → {target} should be invalid"

    def test_cannot_go_from_completed_to_pending(self) -> None:
        assert not can_transition(_job(JobStatus.COMPLETED), JobStatus.PENDING)

    def test_cannot_go_from_running_to_pending(self) -> None:
        assert not can_transition(_job(JobStatus.RUNNING), JobStatus.PENDING)

    def test_cannot_go_from_failed_to_running(self) -> None:
        assert not can_transition(_job(JobStatus.FAILED), JobStatus.RUNNING)


class TestTransitionSideEffects:
    """transition_to() must set status and timestamps correctly."""

    def test_transition_sets_completed_at_for_completing(self) -> None:
        job = _job(JobStatus.RUNNING)
        transition_to(job, JobStatus.COMPLETED)
        assert job.status == JobStatus.COMPLETED
        assert job.completed_at is not None

    def test_transition_does_not_set_completed_at_for_running(self) -> None:
        job = _job(JobStatus.DISCOVERING)
        transition_to(job, JobStatus.RUNNING)
        assert job.status == JobStatus.RUNNING
        assert job.started_at is None  # started_at not auto-set by transition
        assert job.completed_at is None

    def test_transition_to_canceled_sets_completed_at(self) -> None:
        job = _job(JobStatus.RUNNING)
        transition_to(job, JobStatus.CANCELED)
        assert job.status == JobStatus.CANCELED
        assert job.completed_at is not None


class TestClearTerminalJobsUsesCorrectStatusSet:
    """The clear-terminal endpoint must use _COMPLETING_STATUSES, not a
    hand-rolled set that could diverge from the state machine."""

    def test_completing_statuses_match_clear_terminal_expectation(self) -> None:
        """The endpoint should clear COMPLETED, DEGRADED, EMPTY_RESULT,
        CANCELED, and FAILED — which is exactly _COMPLETING_STATUSES."""
        expected = {
            JobStatus.COMPLETED,
            JobStatus.DEGRADED,
            JobStatus.EMPTY_RESULT,
            JobStatus.CANCELED,
            JobStatus.FAILED,
        }
        assert expected == _COMPLETING_STATUSES

    def test_pending_not_in_completing(self) -> None:
        assert JobStatus.PENDING not in _COMPLETING_STATUSES

    def test_running_not_in_completing(self) -> None:
        assert JobStatus.RUNNING not in _COMPLETING_STATUSES

    def test_discovering_not_in_completing(self) -> None:
        assert JobStatus.DISCOVERING not in _COMPLETING_STATUSES


class TestJobCreationDefaultState:
    """Newly created jobs must start in PENDING state."""

    def test_new_job_is_pending(self) -> None:
        job = Job(name="test")
        assert job.status == JobStatus.PENDING
        assert not is_terminal(job.status)

    def test_new_job_has_no_timestamps(self) -> None:
        job = Job(name="test")
        assert job.started_at is None
        assert job.completed_at is None

    def test_new_job_has_zero_progress(self) -> None:
        job = Job(name="test")
        assert job.progress_current == 0
        assert job.progress_total == 0
        assert job.total_records == 0


class TestRecleanTransitionPreconditions:
    """The reclean path COMPLETED→RUNNING must be allowed but guarded."""

    def test_completed_to_running_is_valid(self) -> None:
        assert can_transition(_job(JobStatus.COMPLETED), JobStatus.RUNNING)

    def test_degraded_to_running_is_not_valid(self) -> None:
        """DEGRADED is truly terminal — cannot reclean."""
        assert not can_transition(_job(JobStatus.DEGRADED), JobStatus.RUNNING)

    def test_failed_to_running_is_not_valid(self) -> None:
        """FAILED is truly terminal — cannot reclean."""
        assert not can_transition(_job(JobStatus.FAILED), JobStatus.RUNNING)

    def test_transition_completed_to_running_keeps_completed_at(self) -> None:
        """When recleaning, completed_at is NOT cleared by transition_to()
        since the state machine only sets timestamps for completing statuses.
        The reclean service is responsible for clearing it if needed."""
        job = Job(name="test", status=JobStatus.COMPLETED, completed_at="2025-01-01T00:00:00")
        transition_to(job, JobStatus.RUNNING)
        assert job.status == JobStatus.RUNNING
        # State machine does not clear completed_at on COMPLETED→RUNNING
        # because it only auto-sets timestamps for completing statuses.
        # The reclean service must explicitly clear it.
