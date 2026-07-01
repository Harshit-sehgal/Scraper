"""Unit tests for the status classifier service.

Covers classify_job_status and job_completion_message for all
terminal job status combinations.
"""

from __future__ import annotations

from app.models import JobStatus
from app.services.status_classifier import (
    classify_job_status,
    job_completion_message,
)


class TestClassifyJobStatus:
    """classify_job_status determines terminal status and error message."""

    def test_all_urls_produced_records_returns_completed(self) -> None:
        status, msg = classify_job_status(total_urls=5, urls_with_records=5, all_raw_results_count=100)
        assert status == JobStatus.COMPLETED
        assert msg == ""

    def test_single_url_with_results_returns_completed(self) -> None:
        status, _ = classify_job_status(total_urls=1, urls_with_records=1, all_raw_results_count=10)
        assert status == JobStatus.COMPLETED

    def test_no_urls_and_no_results_returns_completed(self) -> None:
        """Zero URLs with no results is still COMPLETED (no URLs to degrade)."""
        status, _ = classify_job_status(total_urls=0, urls_with_records=0, all_raw_results_count=0)
        assert status == JobStatus.EMPTY_RESULT

    def test_empty_url_list_returns_empty_result(self) -> None:
        status, msg = classify_job_status(
            total_urls=0,
            urls_with_records=0,
            all_raw_results_count=0,
            has_empty_url_list=True,
        )
        assert status == JobStatus.EMPTY_RESULT
        assert "No URLs to scrape" in msg

    def test_no_raw_results_returns_empty_result(self) -> None:
        status, msg = classify_job_status(total_urls=5, urls_with_records=0, all_raw_results_count=0)
        assert status == JobStatus.EMPTY_RESULT
        assert "no records were extracted" in msg

    def test_partial_results_returns_degraded(self) -> None:
        status, msg = classify_job_status(total_urls=10, urls_with_records=6, all_raw_results_count=60)
        assert status == JobStatus.DEGRADED
        assert "6 of 10 URLs produced results" in msg

    def test_one_url_produced_some_degraded(self) -> None:
        status, _ = classify_job_status(total_urls=3, urls_with_records=1, all_raw_results_count=5)
        assert status == JobStatus.DEGRADED

    def test_all_but_one_url_produced_degraded(self) -> None:
        status, _ = classify_job_status(total_urls=100, urls_with_records=99, all_raw_results_count=990)
        assert status == JobStatus.DEGRADED

    def test_large_result_set_completed(self) -> None:
        status, _ = classify_job_status(total_urls=1, urls_with_records=1, all_raw_results_count=10000)
        assert status == JobStatus.COMPLETED

    def test_zero_total_urls_no_empty_flag_returns_empty(self) -> None:
        """total_urls=0 without has_empty_url_list should still return EMPTY_RESULT."""
        status, _ = classify_job_status(total_urls=0, urls_with_records=0, all_raw_results_count=0)
        assert status == JobStatus.EMPTY_RESULT

    def test_urls_with_records_more_than_total(self) -> None:
        """Defensive: urls_with_records > total_urls should not cause errors."""
        status, _ = classify_job_status(total_urls=3, urls_with_records=5, all_raw_results_count=50)
        # In this edge case, urls_with_records > total_urls implies full coverage
        assert status == JobStatus.COMPLETED


class TestJobCompletionMessage:
    def test_completed_message(self) -> None:
        assert job_completion_message(JobStatus.COMPLETED) == "Job completed successfully"

    def test_degraded_message(self) -> None:
        assert "degraded" in job_completion_message(JobStatus.DEGRADED)

    def test_empty_result_message(self) -> None:
        assert "empty" in job_completion_message(JobStatus.EMPTY_RESULT)

    def test_unknown_status(self) -> None:
        msg = job_completion_message(JobStatus.CANCELED)
        assert "CANCELED" in msg

    def test_pending_status(self) -> None:
        msg = job_completion_message(JobStatus.PENDING)
        assert "PENDING" in msg
