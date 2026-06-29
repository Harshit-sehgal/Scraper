"""Tests for run_scraping_phase cancel-poll deadline timeout.

Verifies that the safety-net deadline prevents the worker from wedging
indefinitely when scrape tasks hang beyond the per-URL timeout and no
cancel signal is propagating.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models import Job, JobStatus


@pytest.mark.asyncio
async def test_cancel_poll_deadline_force_cancels_wedged_tasks(monkeypatch) -> None:
    """When tasks hang past the deadline, force-cancellation must fire."""
    from app.services.scraping import run_scraping_phase

    monkeypatch.setenv("DATAFORGE_CANCEL_POLL_DEADLINE", "0.1")

    async def hang_forever(*args, **kwargs):
        await asyncio.sleep(3600)

    monkeypatch.setattr("app.services.job_runner.scrape_url_with_recovery", AsyncMock(side_effect=hang_forever))

    mock_policy = MagicMock()
    mock_policy.can_fetch.return_value = True
    mock_policy.get_or_create.return_value = MagicMock(max_parallel=1)
    monkeypatch.setattr("app.domain_runtime_policy.get_domain_runtime_policy", lambda: mock_policy)

    async def no_cancel() -> bool:
        return False

    job = Job(
        id="cancel-deadline-job",
        name="cancel-deadline-test",
        created_by="test-user",
        urls=["https://example.com/slow1", "https://example.com/slow2"],
        status=JobStatus.RUNNING,
        schema_fields=[],
    )

    with patch("app.services.scraping._record_page_fetch", return_value=True):
        with patch("app.services.scraping._record_page_fetch_duration_metric"):
            all_raw, urls_with_records, warnings, scraped = await run_scraping_phase(
                job,
                max_job_runtime_seconds=60,
                per_url_scrape_timeout_seconds=10,
                persist_fn=lambda: None,
                cancel_check=no_cancel,
            )

    assert urls_with_records == 0
    assert isinstance(all_raw, list)


@pytest.mark.asyncio
async def test_cancel_poll_deadline_custom_env_var(monkeypatch) -> None:
    """DATAFORGE_CANCEL_POLL_DEADLINE env var must be read and honoured."""
    from app.services.scraping import run_scraping_phase

    monkeypatch.setenv("DATAFORGE_CANCEL_POLL_DEADLINE", "0.05")

    async def hang_forever(*args, **kwargs):
        await asyncio.sleep(3600)

    monkeypatch.setattr("app.services.job_runner.scrape_url_with_recovery", AsyncMock(side_effect=hang_forever))

    mock_policy = MagicMock()
    mock_policy.can_fetch.return_value = True
    mock_policy.get_or_create.return_value = MagicMock(max_parallel=1)
    monkeypatch.setattr("app.domain_runtime_policy.get_domain_runtime_policy", lambda: mock_policy)

    async def no_cancel() -> bool:
        return False

    job = Job(
        id="custom-deadline-job",
        name="custom-deadline-test",
        created_by="test-user",
        urls=["https://example.com/hang"],
        status=JobStatus.RUNNING,
        schema_fields=[],
    )

    with patch("app.services.scraping._record_page_fetch", return_value=True):
        with patch("app.services.scraping._record_page_fetch_duration_metric"):
            all_raw, urls_with_records, warnings, scraped = await run_scraping_phase(
                job,
                max_job_runtime_seconds=60,
                per_url_scrape_timeout_seconds=10,
                persist_fn=lambda: None,
                cancel_check=no_cancel,
            )

    assert urls_with_records == 0


@pytest.mark.asyncio
async def test_cancel_poll_deadline_does_not_break_normal_completion(monkeypatch) -> None:
    """When all tasks complete quickly, the deadline must not fire."""
    from app.services.scraping import run_scraping_phase

    monkeypatch.setenv("DATAFORGE_CANCEL_POLL_DEADLINE", "0.3")

    mock_results = [{"name": "Test Inc"}]
    monkeypatch.setattr(
        "app.services.job_runner.scrape_url_with_recovery",
        AsyncMock(return_value=(mock_results, {"recovery_attempts": 0, "acquisition_lineage": {}})),
    )

    mock_policy = MagicMock()
    mock_policy.can_fetch.return_value = True
    mock_policy.get_or_create.return_value = MagicMock(max_parallel=1)
    monkeypatch.setattr("app.domain_runtime_policy.get_domain_runtime_policy", lambda: mock_policy)

    async def no_cancel() -> bool:
        return False

    job = Job(
        id="fast-no-break",
        name="fast-no-break-test",
        created_by="test-user",
        urls=["https://example.com/ok"],
        status=JobStatus.RUNNING,
        schema_fields=[],
        intent="test",
    )

    with patch("app.services.scraping._record_page_fetch", return_value=True):
        with patch("app.services.scraping._record_page_fetch_duration_metric"):
            with patch("app.semantic_world_state.get_world_state"):
                with patch("app.discovery.infer_source_metadata", return_value={}):
                    with patch("app.utils.quality.safe_score", return_value=0.5):
                        with patch("app.services.scraping.get_llm_call_count", return_value=0):
                            all_raw, urls_with_records, warnings, scraped = await run_scraping_phase(
                                job,
                                max_job_runtime_seconds=60,
                                per_url_scrape_timeout_seconds=10,
                                persist_fn=lambda: None,
                                cancel_check=no_cancel,
                            )

    assert urls_with_records == 1
