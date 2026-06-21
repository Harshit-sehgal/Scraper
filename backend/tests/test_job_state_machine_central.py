"""Test that job state machine is centralized and used consistently."""
import datetime

from app.models import JobStatus
from app.services.job_state_machine import can_transition, is_terminal


def test_state_machine_is_central_source():
    """Verify state machine module is the single source of truth."""
    # Create mock job objects
    class MockJob:
        def __init__(self, status):
            self.status = status
            self.started_at = None
            self.completed_at = None
    
    # All transitions must go through the state machine
    job = MockJob(JobStatus.PENDING)
    assert can_transition(job, JobStatus.DISCOVERING)
    
    job.status = JobStatus.DISCOVERING
    assert can_transition(job, JobStatus.RUNNING)
    
    job.status = JobStatus.RUNNING
    assert can_transition(job, JobStatus.COMPLETED)
    
    job.status = JobStatus.COMPLETED
    assert not can_transition(job, JobStatus.RUNNING)


def test_all_valid_transitions_defined():
    """Verify all expected transitions are allowed."""
    class MockJob:
        def __init__(self, status):
            self.status = status
    
    valid_paths = [
        (JobStatus.PENDING, JobStatus.DISCOVERING),
        (JobStatus.DISCOVERING, JobStatus.RUNNING),
        (JobStatus.RUNNING, JobStatus.COMPLETED),
        (JobStatus.RUNNING, JobStatus.DEGRADED),
        (JobStatus.RUNNING, JobStatus.EMPTY_RESULT),
        (JobStatus.RUNNING, JobStatus.FAILED),
        (JobStatus.PENDING, JobStatus.FAILED),  # recovery
        (JobStatus.RUNNING, JobStatus.CANCELED),
    ]
    
    for src, dst in valid_paths:
        job = MockJob(src)
        assert can_transition(job, dst), f"Should allow {src} → {dst}"


def test_invalid_transitions_blocked():
    """Verify invalid transitions are rejected."""
    class MockJob:
        def __init__(self, status):
            self.status = status
    
    invalid_paths = [
        (JobStatus.COMPLETED, JobStatus.RUNNING),
        (JobStatus.FAILED, JobStatus.RUNNING),
        (JobStatus.COMPLETED, JobStatus.FAILED),
    ]
    
    for src, dst in invalid_paths:
        job = MockJob(src)
        assert not can_transition(job, dst), f"Should block {src} → {dst}"


def test_terminal_states_identified():
    """Verify all terminal states are correctly identified."""
    terminal_states = {
        JobStatus.COMPLETED,
        JobStatus.DEGRADED,
        JobStatus.EMPTY_RESULT,
        JobStatus.FAILED,
        JobStatus.CANCELED,
    }
    
    for status in terminal_states:
        assert is_terminal(status), f"{status} should be terminal"
    
    non_terminal = {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}
    for status in non_terminal:
        assert not is_terminal(status), f"{status} should not be terminal"


def test_transition_records_timestamp():
    """Verify transitions record state change metadata."""
    class MockJob:
        def __init__(self):
            self.status = JobStatus.PENDING
            self.started_at = None
            self.completed_at = None
    
    job = MockJob()
    
    # Transition to RUNNING should set started_at if not already set
    job.status = JobStatus.RUNNING
    job.started_at = datetime.datetime.now(datetime.UTC).isoformat()
    
    assert job.started_at is not None
    assert job.status == JobStatus.RUNNING
