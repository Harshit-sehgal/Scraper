from __future__ import annotations

import pytest
from app.config import settings
from app.models import Job, JobStatus
from app.services.finalization import run_finalization
from app.utils.usage_ledger import UsageType, get_usage_ledger, reset_usage_ledger


@pytest.fixture(autouse=True)
def _reset_usage():
    reset_usage_ledger()
    yield


class TestCostTracking:
    @pytest.mark.asyncio
    async def test_finalization_calculates_cost(self) -> None:
        async def fake_persist_fn():
            pass

        job = Job(
            name="cost-test",
            mode="manual",
            urls=["https://example.com"],
        )
        job.status = JobStatus.RUNNING
        job.total_llm_calls = 10
        job.progress_total = 5

        await run_finalization(
            job,
            all_raw_results=[{"record": 1}],
            urls_with_records=1,
            persist_fn=fake_persist_fn,
        )

        expected = round(
            10 * settings.COST_PER_LLM_CALL + 5 * settings.COST_PER_URL_SCRAPE,
            4,
        )
        assert job.estimated_cost_usd == expected
        assert job.estimated_cost_usd > 0

    @pytest.mark.asyncio
    async def test_cost_scales_with_llm_calls(self) -> None:
        async def fake_persist_fn():
            pass

        job1 = Job(name="j1", mode="manual", urls=["https://a.com"])
        job1.status = JobStatus.RUNNING
        job1.total_llm_calls = 1
        job1.progress_total = 0

        job5 = Job(name="j5", mode="manual", urls=["https://b.com"])
        job5.status = JobStatus.RUNNING
        job5.total_llm_calls = 5
        job5.progress_total = 0

        await run_finalization(job1, all_raw_results=[{"r": 1}], urls_with_records=1, persist_fn=fake_persist_fn)
        await run_finalization(job5, all_raw_results=[{"r": 1}], urls_with_records=1, persist_fn=fake_persist_fn)

        assert job5.estimated_cost_usd > job1.estimated_cost_usd

    def test_job_model_has_cost_field(self) -> None:
        job = Job(name="test", mode="manual", urls=[])
        assert hasattr(job, "estimated_cost_usd")
        assert job.estimated_cost_usd == 0.0

    def test_usage_ledger_records_usage(self) -> None:
        ledger = get_usage_ledger()
        ledger.record_usage("user1", UsageType.API_REQUEST, quantity=1)
        summary = ledger.get_usage_summary("user1")
        assert summary is not None
        assert summary["user_id"] == "user1"

    def test_usage_ledger_tracks_multiple_types(self) -> None:
        ledger = get_usage_ledger()
        ledger.record_usage("user1", UsageType.API_REQUEST, quantity=1)
        ledger.record_usage("user1", UsageType.JOB_COMPLETED, quantity=1)
        summary = ledger.get_usage_summary("user1")
        assert summary is not None
        assert UsageType.API_REQUEST.value in summary["usage"]
        assert UsageType.JOB_COMPLETED.value in summary["usage"]
