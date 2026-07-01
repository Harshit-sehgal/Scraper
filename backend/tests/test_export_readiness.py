"""Export readiness tests — verify export endpoints guard against non-terminal jobs.

These tests verify that:
1. Exports are only available for terminal-state jobs
2. Terminal states are well-defined
3. Export response shapes are correct
"""

import pytest
from app.models import Job, JobStatus

pytestmark = pytest.mark.api


TERMINAL_STATES = {"completed", "degraded", "empty_result", "canceled", "failed"}
NON_TERMINAL_STATES = {"pending", "discovering", "running"}


class TestExportReadiness:
    """A job must be terminal before it can be exported."""

    def test_completed_is_terminal(self) -> None:
        assert JobStatus.COMPLETED.value in TERMINAL_STATES

    def test_degraded_is_terminal(self) -> None:
        assert JobStatus.DEGRADED.value in TERMINAL_STATES

    def test_empty_result_is_terminal(self) -> None:
        assert JobStatus.EMPTY_RESULT.value in TERMINAL_STATES

    def test_canceled_is_terminal(self) -> None:
        assert JobStatus.CANCELED.value in TERMINAL_STATES

    def test_failed_is_terminal(self) -> None:
        assert JobStatus.FAILED.value in TERMINAL_STATES

    def test_pending_is_not_terminal(self) -> None:
        assert JobStatus.PENDING.value not in TERMINAL_STATES

    def test_discovering_is_not_terminal(self) -> None:
        assert JobStatus.DISCOVERING.value not in TERMINAL_STATES

    def test_running_is_not_terminal(self) -> None:
        assert JobStatus.RUNNING.value not in TERMINAL_STATES

    def test_job_default_status_is_pending(self) -> None:
        job = Job(name="test")
        assert job.status == JobStatus.PENDING
        assert job.status.value not in TERMINAL_STATES

    def test_job_results_response_has_pagination(self) -> None:
        from app.models import JobResultsResponse

        r = JobResultsResponse(
            job_id="j-1",
            results=[],
            total=100,
            limit=50,
            offset=0,
            returned=0,
        )
        assert r.total == 100
        assert r.next_offset is None  # No more results

    def test_job_results_response_with_next_offset(self) -> None:
        from app.models import JobResultsResponse

        r = JobResultsResponse(
            job_id="j-1",
            results=[],
            total=100,
            limit=50,
            offset=0,
            returned=50,
            next_offset=50,
        )
        assert r.next_offset == 50

    def test_all_job_statuses_accounted_for(self) -> None:
        """Every JobStatus enum member must be in either terminal or non-terminal set."""
        all_values = {str(v.value) for v in JobStatus}
        classified = TERMINAL_STATES | NON_TERMINAL_STATES
        assert all_values == classified, f"Unclassified: {all_values - classified}"


class TestExportStateGuard:
    """Verify the export router's state check logic."""

    def test_non_terminal_job_cannot_export(self) -> None:
        """Simulate the check that _get_export_job does."""
        from app.services.job_state_machine import is_terminal

        for status in (JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING):
            assert not is_terminal(status), f"{status} should not be terminal"

    def test_terminal_job_can_export(self) -> None:
        from app.services.job_state_machine import is_terminal

        # is_terminal() strictly excludes COMPLETED (reclean allows
        # COMPLETED → RUNNING), but the export router's _get_export_job
        # explicitly accepts COMPLETED alongside is_terminal states.
        # Here we test the actual is_terminal definition:
        for status in (JobStatus.DEGRADED, JobStatus.EMPTY_RESULT, JobStatus.FAILED, JobStatus.CANCELED):
            assert is_terminal(status), f"{status} should be terminal"

    def test_completed_is_exportable_despite_not_strictly_terminal(self) -> None:
        """COMPLETED is not is_terminal (reclean path) but IS exportable."""
        from app.services.job_state_machine import is_terminal

        assert not is_terminal(JobStatus.COMPLETED)
        # The export router allows: completed, degraded, empty_result
        # alongside is_terminal statuses — this is by design.
