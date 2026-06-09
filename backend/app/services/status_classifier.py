"""Status classifier service — extracted from ``job_runner.run_job``.

This module encapsulates the final status determination phase of the
job pipeline. It classifies a completed job as COMPLETED, DEGRADED,
or EMPTY_RESULT based on scrape results, and generates appropriate
error messages and completion timestamps.

This is the third extraction from the ``run_job`` monolith as part
of the L1 strangler refactor (Phase 9 of 9). See
``docs/RUN_JOB_CHARACTERIZATION.md`` for the full extraction plan.
"""

from __future__ import annotations

from app.models import JobStatus


def classify_job_status(
    total_urls: int,
    urls_with_records: int,
    all_raw_results_count: int,
    has_empty_url_list: bool = False,
) -> tuple[JobStatus, str]:
    """Determine the terminal status and error message for a completed job.

    Args:
        total_urls: Total number of URLs in the job URL list.
        urls_with_records: Number of URLs that produced at least one record.
        all_raw_results_count: Total number of raw results collected.
        has_empty_url_list: Whether the URL list was empty before scraping.

    Returns:
        Tuple of ``(status, error_message)`` where:
        - ``COMPLETED``: All URLs produced results (or no URLs listed).
        - ``DEGRADED``: Some URLs produced results, but not all.
        - ``EMPTY_RESULT``: No URLs or no records extracted at all.
    """
    if has_empty_url_list or total_urls == 0:
        return (
            JobStatus.EMPTY_RESULT,
            "No URLs to scrape (empty URL list).",
        )

    if all_raw_results_count == 0:
        return (
            JobStatus.EMPTY_RESULT,
            (
                "The job completed but no records were extracted. "
                "This may be due to a session-bound URL, empty response, anti-bot block, "
                "JavaScript-rendered results, or missing search-form replay."
            ),
        )

    if urls_with_records > 0 and urls_with_records < total_urls:
        return (
            JobStatus.DEGRADED,
            (
                f"{urls_with_records} of {total_urls} URLs produced results. "
                "Some pages may have anti-bot protection, expired sessions, "
                "or require JavaScript rendering."
            ),
        )

    return JobStatus.COMPLETED, ""


def job_completion_message(status: JobStatus) -> str:
    """Return a human-readable completion log message for the given status."""
    if status == JobStatus.COMPLETED:
        return "Job completed successfully"
    if status == JobStatus.DEGRADED:
        return "Job completed with degraded results"
    if status == JobStatus.EMPTY_RESULT:
        return "Job completed with empty result"
    return f"Job completed with status {status.value}"
