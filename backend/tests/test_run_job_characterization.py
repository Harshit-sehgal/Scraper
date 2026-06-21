"""Characterization tests for run_job after strangler refactor (D2/L1).

These tests verify the refactored run_job still produces the same behavior
as the monolithic version.
"""

from __future__ import annotations

from typing import NoReturn
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models import JobStatus, ScrapeMode
from app.services.job_runner import run_job


def _make_job(
    *,
    mode: ScrapeMode = ScrapeMode.MANUAL,
    urls: list[str] | None = None,
    topic: str = "test",
    cancel_requested: bool = False,
    status: JobStatus = JobStatus.PENDING,
):
    job = MagicMock()
    job.id = "test-job-1"
    job.name = "Test Job"
    job.mode = mode
    job.urls = urls if urls is not None else ["https://example.com"]
    job.topic = topic
    job.schema_fields = []
    job.filters = []
    job.logs = []
    job.results = []
    job.discovered_urls = []
    job.cancel_requested = cancel_requested
    # Status starts as PENDING by default because real jobs enter ``run_job``
    # having only been persisted. ``transition_to`` is strict and rejects
    # same-state transitions, so tests must model that initial state.
    job.status = status
    job.error = ""
    job.started_at = None
    job.completed_at = None
    job.progress_total = 0
    job.progress_current = 0
    job.total_llm_calls = 0
    job.total_records = 0
    job.filtered_records = 0
    job.min_record_score = 0.0
    job.intent = None
    job.selectors_map = None
    job.search_params = None
    job.origin_location = None
    # Status starts as PENDING because real jobs enter ``run_job`` having
    # only been persisted. ``transition_to`` is strict and rejects same-state
    # transitions, so tests must model that initial state.
    job.max_distance_km = None
    job.deduplicate = False
    job.deduplicate_field = None
    job.max_pages = 10
    job.preferred_domain = None
    job.source_policy = None
    job.max_per_domain = None
    job.quality_report = {}
    job.analysis = ""
    job.estimated_cost_usd = 0.0
    job.results_on_disk = False
    job.results_file_path = ""
    return job


def _noop_persist() -> None:
    pass


@pytest.mark.asyncio
async def test_run_job_cancel_before_execution() -> None:
    """Job with cancel_requested=True is marked canceled immediately."""
    jobs_store = {}
    job = _make_job(cancel_requested=True)
    jobs_store[job.id] = job

    await run_job(
        job_id=job.id,
        jobs_store=jobs_store,
        persist_state_fn=_noop_persist,
        max_discovery_urls=10,
        max_job_runtime_seconds=600,
        per_url_scrape_timeout_seconds=30,
        ai_structuring_timeout_seconds=60,
        insight_timeout_seconds=60,
        persist_state_single_fn=_noop_persist,
        persist_state_single_critical_fn=_noop_persist,
    )

    assert job.status == JobStatus.CANCELED
    assert "Canceled before execution" in job.error


@pytest.mark.asyncio
async def test_run_job_manual_mode_no_urls() -> None:
    """Manual mode job with empty URLs ends with EMPTY_RESULT."""
    jobs_store = {}
    job = _make_job(mode=ScrapeMode.MANUAL, urls=[])
    jobs_store[job.id] = job

    await run_job(
        job_id=job.id,
        jobs_store=jobs_store,
        persist_state_fn=_noop_persist,
        max_discovery_urls=10,
        max_job_runtime_seconds=600,
        per_url_scrape_timeout_seconds=30,
        ai_structuring_timeout_seconds=60,
        insight_timeout_seconds=60,
    )

    assert job.status == JobStatus.EMPTY_RESULT
    assert "No URLs" in job.error


@pytest.mark.asyncio
async def test_run_job_auto_mode_discovery_failure() -> None:
    """Auto mode with no discovered URLs fails gracefully."""
    jobs_store = {}
    job = _make_job(mode=ScrapeMode.AUTO, urls=[])
    jobs_store[job.id] = job

    with (
        patch("app.services.job_runner.load_semantic_state"),
        patch("app.discovery.discover_urls", new_callable=AsyncMock, return_value=[]),
        patch("app.url_safety.validate_public_http_url"),
    ):
        await run_job(
            job_id=job.id,
            jobs_store=jobs_store,
            persist_state_fn=_noop_persist,
            max_discovery_urls=10,
            max_job_runtime_seconds=600,
            per_url_scrape_timeout_seconds=30,
            ai_structuring_timeout_seconds=60,
            insight_timeout_seconds=60,
        )

    assert job.status == JobStatus.FAILED
    assert "Could not discover any URLs" in job.error


@pytest.mark.asyncio
async def test_run_job_manual_mode_scrape_success() -> None:
    """Manual mode job with URLs completes successfully (mocked scrape)."""
    jobs_store = {}
    job = _make_job(mode=ScrapeMode.MANUAL, urls=["https://example.com"])
    jobs_store[job.id] = job

    mock_policy = MagicMock()
    mock_policy.can_fetch.return_value = True
    mock_policy.get_or_create.return_value = MagicMock(max_parallel=1)
    mock_ws = MagicMock()
    mock_ws.transaction.return_value.__enter__ = MagicMock()
    mock_ws.transaction.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch("app.services.job_runner.load_semantic_state"),
        patch("app.domain_runtime_policy.get_domain_runtime_policy", return_value=mock_policy),
        patch("app.semantic_world_state.get_world_state", return_value=mock_ws),
        patch(
            "app.services.job_runner.scrape_url_with_recovery",
            new_callable=AsyncMock,
            return_value=([{"name": "test"}], {"recovery_attempts": 0}),
        ),
        patch(
            "app.services.post_processing.process_results",
            new_callable=AsyncMock,
            return_value=([{"name": "test"}], 1, 1, {}),
        ),
        patch(
            "app.discovery.infer_source_metadata",
            return_value={"source_type": "web", "source_trust_score": 0.5},
        ),
        patch("app.services.job_runner.save_semantic_state"),
    ):
        await run_job(
            job_id=job.id,
            jobs_store=jobs_store,
            persist_state_fn=_noop_persist,
            max_discovery_urls=10,
            max_job_runtime_seconds=600,
            per_url_scrape_timeout_seconds=30,
            ai_structuring_timeout_seconds=60,
            insight_timeout_seconds=60,
        )

    assert job.status in (JobStatus.COMPLETED, JobStatus.DEGRADED)


@pytest.mark.asyncio
async def test_run_job_scrape_exception_empty_result() -> None:
    """Exception inside _scrape_single_url produces EMPTY_RESULT (caught internally)."""
    jobs_store = {}
    job = _make_job(mode=ScrapeMode.MANUAL, urls=["https://example.com"])
    jobs_store[job.id] = job

    mock_policy = MagicMock()
    mock_policy.can_fetch.return_value = True
    mock_policy.get_or_create.return_value = MagicMock(max_parallel=1)
    mock_ws = MagicMock()
    mock_ws.transaction.return_value.__enter__ = MagicMock()
    mock_ws.transaction.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch("app.services.job_runner.load_semantic_state"),
        patch("app.domain_runtime_policy.get_domain_runtime_policy", return_value=mock_policy),
        patch("app.semantic_world_state.get_world_state", return_value=mock_ws),
        patch(
            "app.services.job_runner.scrape_url_with_recovery",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network error"),
        ),
        patch(
            "app.services.post_processing.process_results",
            new_callable=AsyncMock,
            return_value=([], 0, 0, {}),
        ),
        patch("app.services.job_runner.save_semantic_state"),
    ):
        await run_job(
            job_id=job.id,
            jobs_store=jobs_store,
            persist_state_fn=_noop_persist,
            max_discovery_urls=10,
            max_job_runtime_seconds=600,
            per_url_scrape_timeout_seconds=30,
            ai_structuring_timeout_seconds=60,
            insight_timeout_seconds=60,
        )

    assert job.status == JobStatus.EMPTY_RESULT


@pytest.mark.asyncio
async def test_run_job_persist_called_on_empty() -> None:
    """Persist functions are called during job completion with empty URLs."""
    jobs_store = {}
    job = _make_job(mode=ScrapeMode.MANUAL, urls=[])
    jobs_store[job.id] = job
    called = {"fn": False}

    def track() -> None:
        called["fn"] = True

    await run_job(
        job_id=job.id,
        jobs_store=jobs_store,
        persist_state_fn=track,
        max_discovery_urls=10,
        max_job_runtime_seconds=600,
        per_url_scrape_timeout_seconds=30,
        ai_structuring_timeout_seconds=60,
        insight_timeout_seconds=60,
        persist_state_single_fn=track,
        persist_state_single_critical_fn=track,
    )

    assert called["fn"]


@pytest.mark.asyncio
async def test_run_job_degraded_when_partial_urls_succeed() -> None:
    """Job is DEGRADED when some but not all URLs produce results."""
    jobs_store = {}
    job = _make_job(
        mode=ScrapeMode.MANUAL,
        urls=["https://a.com", "https://b.com"],
    )
    jobs_store[job.id] = job

    mock_policy = MagicMock()
    mock_policy.can_fetch.return_value = True
    mock_policy.get_or_create.return_value = MagicMock(max_parallel=1)
    mock_ws = MagicMock()
    mock_ws.transaction.return_value.__enter__ = MagicMock()
    mock_ws.transaction.return_value.__exit__ = MagicMock(return_value=False)

    call_count = 0

    async def fake_scrape(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return ([{"name": "data"}], {"recovery_attempts": 0})
        return ([], {"recovery_attempts": 0})

    with (
        patch("app.services.job_runner.load_semantic_state"),
        patch("app.domain_runtime_policy.get_domain_runtime_policy", return_value=mock_policy),
        patch("app.semantic_world_state.get_world_state", return_value=mock_ws),
        patch(
            "app.services.job_runner.scrape_url_with_recovery",
            side_effect=fake_scrape,
        ),
        patch(
            "app.services.post_processing.process_results",
            new_callable=AsyncMock,
            return_value=([{"name": "data"}], 1, 1, {}),
        ),
        patch(
            "app.discovery.infer_source_metadata",
            return_value={"source_type": "web", "source_trust_score": 0.5},
        ),
        patch("app.services.job_runner.save_semantic_state"),
    ):
        await run_job(
            job_id=job.id,
            jobs_store=jobs_store,
            persist_state_fn=_noop_persist,
            max_discovery_urls=10,
            max_job_runtime_seconds=600,
            per_url_scrape_timeout_seconds=30,
            ai_structuring_timeout_seconds=60,
            insight_timeout_seconds=60,
        )

    assert job.status == JobStatus.DEGRADED
    assert "1 of 2 URLs produced results" in job.error


@pytest.mark.asyncio
async def test_run_job_all_urls_blocked_by_domain_policy() -> None:
    """All URLs blocked by domain policy results in EMPTY_RESULT."""
    jobs_store = {}
    job = _make_job(mode=ScrapeMode.MANUAL, urls=["https://cooldown.example"])
    jobs_store[job.id] = job

    mock_policy = MagicMock()
    mock_policy.can_fetch.return_value = False
    mock_policy.recommended_action.return_value = "wait"
    mock_policy.remaining_cooldown.return_value = 120.0
    mock_policy.get_or_create.return_value = MagicMock(max_parallel=1)
    mock_ws = MagicMock()
    mock_ws.transaction.return_value.__enter__ = MagicMock()
    mock_ws.transaction.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch("app.services.job_runner.load_semantic_state"),
        patch("app.domain_runtime_policy.get_domain_runtime_policy", return_value=mock_policy),
        patch("app.semantic_world_state.get_world_state", return_value=mock_ws),
        patch("app.services.job_runner.save_semantic_state"),
    ):
        await run_job(
            job_id=job.id,
            jobs_store=jobs_store,
            persist_state_fn=_noop_persist,
            max_discovery_urls=10,
            max_job_runtime_seconds=600,
            per_url_scrape_timeout_seconds=30,
            ai_structuring_timeout_seconds=60,
            insight_timeout_seconds=60,
        )

    assert job.status == JobStatus.EMPTY_RESULT
    assert "completed but no records" in job.error


@pytest.mark.asyncio
async def test_run_job_empty_results_no_ai_struct() -> None:
    """Empty raw results skip AI structuring phase cleanly."""
    jobs_store = {}
    job = _make_job(mode=ScrapeMode.MANUAL, urls=["https://example.com"])
    jobs_store[job.id] = job

    mock_policy = MagicMock()
    mock_policy.can_fetch.return_value = True
    mock_policy.get_or_create.return_value = MagicMock(max_parallel=1)
    mock_ws = MagicMock()
    mock_ws.transaction.return_value.__enter__ = MagicMock()
    mock_ws.transaction.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch("app.services.job_runner.load_semantic_state"),
        patch("app.domain_runtime_policy.get_domain_runtime_policy", return_value=mock_policy),
        patch("app.semantic_world_state.get_world_state", return_value=mock_ws),
        patch(
            "app.services.job_runner.scrape_url_with_recovery",
            new_callable=AsyncMock,
            return_value=([], {"recovery_attempts": 0}),
        ),
        patch(
            "app.services.post_processing.process_results",
            new_callable=AsyncMock,
            return_value=([], 0, 0, {}),
        ),
        patch("app.services.job_runner.save_semantic_state"),
    ):
        await run_job(
            job_id=job.id,
            jobs_store=jobs_store,
            persist_state_fn=_noop_persist,
            max_discovery_urls=10,
            max_job_runtime_seconds=600,
            per_url_scrape_timeout_seconds=30,
            ai_structuring_timeout_seconds=60,
            insight_timeout_seconds=60,
        )

    assert job.status == JobStatus.EMPTY_RESULT


@pytest.mark.asyncio
async def test_run_job_insight_timeout_produces_analysis() -> None:
    """Insight timeout produces a fallback analysis message."""
    jobs_store = {}
    job = _make_job(mode=ScrapeMode.MANUAL, urls=["https://example.com"])
    jobs_store[job.id] = job

    mock_policy = MagicMock()
    mock_policy.can_fetch.return_value = True
    mock_policy.get_or_create.return_value = MagicMock(max_parallel=1)
    mock_ws = MagicMock()
    mock_ws.transaction.return_value.__enter__ = MagicMock()
    mock_ws.transaction.return_value.__exit__ = MagicMock(return_value=False)

    async def timeout_insight(*args, **kwargs) -> NoReturn:
        raise TimeoutError

    with (
        patch("app.services.job_runner.load_semantic_state"),
        patch("app.domain_runtime_policy.get_domain_runtime_policy", return_value=mock_policy),
        patch("app.semantic_world_state.get_world_state", return_value=mock_ws),
        patch(
            "app.services.job_runner.scrape_url_with_recovery",
            new_callable=AsyncMock,
            return_value=([{"name": "test"}], {"recovery_attempts": 0}),
        ),
        patch(
            "app.services.post_processing.process_results",
            new_callable=AsyncMock,
            return_value=([{"name": "test"}], 1, 1, {}),
        ),
        patch(
            "app.discovery.infer_source_metadata",
            return_value={"source_type": "web", "source_trust_score": 0.5},
        ),
        patch("app.insight_engine.generate_data_insight", side_effect=timeout_insight),
        patch("app.services.job_runner.save_semantic_state"),
    ):
        await run_job(
            job_id=job.id,
            jobs_store=jobs_store,
            persist_state_fn=_noop_persist,
            max_discovery_urls=10,
            max_job_runtime_seconds=600,
            per_url_scrape_timeout_seconds=30,
            ai_structuring_timeout_seconds=1,
            insight_timeout_seconds=1,
        )

    assert job.status in (JobStatus.COMPLETED, JobStatus.DEGRADED)
    assert "timed out" in (job.analysis or "").lower()
