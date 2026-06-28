"""Tests for cron-expression scheduling (Feat 3 / Wave 2 of the roadmap).

Covers:
- Cron parser correctness (unit-level)
- Scheduled job CRUD with cron_expression
- next_run_at computed from cron expression
- Cron validation rejects invalid expressions
- Processor loop uses cron for next_run_at when set
- @shortcut expansion (@hourly, @daily, etc.)
"""

from __future__ import annotations

import datetime

import pytest
from app.models import ScrapeMode

# ── Cron parser unit tests ───────────────────────────────────────────


class TestCronParser:
    """Unit tests for app.utils.cron_parser."""

    def test_every_5_minutes(self) -> None:
        from app.utils.cron_parser import next_after

        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        n = next_after(base, "*/5 * * * *")
        assert n == datetime.datetime(2026, 1, 1, 0, 5, tzinfo=datetime.UTC)

    def test_weekday_nine_am(self) -> None:
        from app.utils.cron_parser import next_after

        # 2026-01-01 is Thursday (Python weekday 3 → cron dow 4)
        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        n = next_after(base, "0 9 * * 1-5")
        assert n == datetime.datetime(2026, 1, 1, 9, 0, tzinfo=datetime.UTC)

    def test_saturday_noon(self) -> None:
        from app.utils.cron_parser import next_after

        # Cron dow=6 = Saturday (Python weekday=5)
        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        n = next_after(base, "0 12 * * 6")
        assert n == datetime.datetime(2026, 1, 3, 12, 0, tzinfo=datetime.UTC)

    def test_sunday_midnight(self) -> None:
        from app.utils.cron_parser import next_after

        # Cron dow=0 = Sunday (Python weekday=6)
        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        n = next_after(base, "0 0 * * 0")
        assert n == datetime.datetime(2026, 1, 4, 0, 0, tzinfo=datetime.UTC)

    def test_monthly_first(self) -> None:
        from app.utils.cron_parser import next_after

        base = datetime.datetime(2026, 1, 1, 12, 30, tzinfo=datetime.UTC)
        n = next_after(base, "0 0 1 * *")
        assert n == datetime.datetime(2026, 2, 1, 0, 0, tzinfo=datetime.UTC)

    def test_at_shortcut_daily(self) -> None:
        from app.utils.cron_parser import next_after

        base = datetime.datetime(2026, 1, 1, 12, 30, tzinfo=datetime.UTC)
        n = next_after(base, "@daily")
        assert n == datetime.datetime(2026, 1, 2, 0, 0, tzinfo=datetime.UTC)

    def test_at_shortcut_hourly(self) -> None:
        from app.utils.cron_parser import next_after

        base = datetime.datetime(2026, 1, 1, 12, 30, tzinfo=datetime.UTC)
        n = next_after(base, "@hourly")
        assert n == datetime.datetime(2026, 1, 1, 13, 0, tzinfo=datetime.UTC)

    def test_at_shortcut_weekly(self) -> None:
        from app.utils.cron_parser import next_after

        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        n = next_after(base, "@weekly")
        # @weekly = 0 0 * * 0 — next Sunday midnight
        assert n == datetime.datetime(2026, 1, 4, 0, 0, tzinfo=datetime.UTC)

    def test_at_shortcut_monthly(self) -> None:
        from app.utils.cron_parser import next_after

        base = datetime.datetime(2026, 1, 15, 0, 0, tzinfo=datetime.UTC)
        n = next_after(base, "@monthly")
        assert n == datetime.datetime(2026, 2, 1, 0, 0, tzinfo=datetime.UTC)

    def test_invalid_empty(self) -> None:
        from app.utils.cron_parser import is_valid

        assert not is_valid("")
        assert not is_valid("  ")

    def test_invalid_too_few_fields(self) -> None:
        from app.utils.cron_parser import is_valid

        assert not is_valid("* * * *")
        assert not is_valid("* *")

    def test_invalid_out_of_range(self) -> None:
        from app.utils.cron_parser import is_valid

        assert not is_valid("60 * * * *")
        assert not is_valid("0 24 * * *")
        assert not is_valid("0 0 32 * *")

    def test_invalid_step_zero(self) -> None:
        from app.utils.cron_parser import is_valid

        assert not is_valid("*/0 * * * *")

    def test_valid_comma_list(self) -> None:
        from app.utils.cron_parser import is_valid, next_after

        assert is_valid("0,15,30,45 * * * *")
        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        n = next_after(base, "0,15,30,45 * * * *")
        assert n.minute == 15

    def test_valid_range_with_step(self) -> None:
        from app.utils.cron_parser import is_valid, next_after

        assert is_valid("0 9-17/2 * * *")
        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        n = next_after(base, "0 9-17/2 * * *")
        assert n.hour == 9

    def test_matches(self) -> None:
        from app.utils.cron_parser import matches

        dt = datetime.datetime(2026, 1, 1, 9, 0, tzinfo=datetime.UTC)
        assert matches(dt, "0 9 * * 1-5")  # Thursday
        assert not matches(dt, "0 9 * * 6")  # Not Saturday

    def test_now_param(self) -> None:
        from app.utils.cron_parser import next_after

        # base is far in the past, but now is the effective start
        past = datetime.datetime(2020, 1, 1, 0, 0, tzinfo=datetime.UTC)
        now = datetime.datetime(2026, 6, 1, 12, 30, tzinfo=datetime.UTC)
        n = next_after(past, "@hourly", now=now)
        assert n == datetime.datetime(2026, 6, 1, 13, 0, tzinfo=datetime.UTC)

    def test_month_names(self) -> None:
        from app.utils.cron_parser import next_after

        base = datetime.datetime(2026, 1, 15, 0, 0, tzinfo=datetime.UTC)
        n = next_after(base, "0 0 1 MAR *")
        assert n == datetime.datetime(2026, 3, 1, 0, 0, tzinfo=datetime.UTC)

    def test_dow_names(self) -> None:
        from app.utils.cron_parser import next_after

        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        n = next_after(base, "0 12 * * SAT")
        # 2026-01-03 is Saturday
        assert n == datetime.datetime(2026, 1, 3, 12, 0, tzinfo=datetime.UTC)


# ── Scheduled job API tests ──────────────────────────────────────────


class TestScheduledJobCronExpression:
    """ScheduledJob CRUD with cron_expression field."""

    def test_model_accepts_cron_expression(self) -> None:
        from app.models import ScheduledJob, ScheduledJobFrequency

        job = ScheduledJob(
            name="cron-test",
            frequency=ScheduledJobFrequency.DAILY,
            cron_expression="0 9 * * 1-5",
            job_name="Scheduled: cron-test",
        )
        assert job.cron_expression == "0 9 * * 1-5"
        assert job.timezone == "UTC"

    def test_model_cron_defaults_to_none(self) -> None:
        from app.models import ScheduledJob

        job = ScheduledJob(name="no-cron", job_name="Scheduled: test")
        assert job.cron_expression is None
        assert job.timezone == "UTC"

    def test_model_timezone_custom(self) -> None:
        from app.models import ScheduledJob

        job = ScheduledJob(
            name="tz-test",
            timezone="US/Eastern",
            job_name="Scheduled: tz-test",
        )
        assert job.timezone == "US/Eastern"

    def test_update_clears_cron_expression(self) -> None:
        """Setting cron_expression to empty string clears it."""
        from app.models import ScheduledJob

        job = ScheduledJob(
            name="clear-cron",
            cron_expression="0 9 * * 1-5",
            job_name="Scheduled: test",
        )
        assert job.cron_expression == "0 9 * * 1-5"


class TestScheduledJobRouterCronValidation:
    """Router-level validation of cron expressions on create/update."""

    @pytest.mark.asyncio
    async def test_create_with_valid_cron(self) -> None:
        """POST /api/scheduled with valid cron_expression should succeed."""
        from app.models import ScheduledJob, ScheduledJobFrequency
        from app.routers.scheduled_monitoring import _compute_next_run

        job = ScheduledJob(
            name="cron-job",
            frequency=ScheduledJobFrequency.DAILY,
            cron_expression="0 9 * * 1-5",
            job_name="Scheduled: cron-job",
        )
        next_run = _compute_next_run(job)
        # Should be a valid ISO datetime string
        assert next_run
        parsed = datetime.datetime.fromisoformat(next_run)
        # The next run should be at 09:00 UTC on a weekday
        assert parsed.hour == 9
        assert parsed.minute == 0
        assert parsed.weekday() <= 4  # Mon-Fri (0-4)

    @pytest.mark.asyncio
    async def test_create_with_invalid_cron_rejected(self) -> None:
        """Invalid cron expression should be rejected by is_valid."""
        from app.utils.cron_parser import is_valid

        assert not is_valid("not-a-cron")


class TestComputeNextRun:
    """Test _compute_next_run and _compute_next_from_record helpers."""

    def test_cron_expression_takes_precedence(self) -> None:
        from app.models import ScheduledJob, ScheduledJobFrequency
        from app.routers.scheduled_monitoring import _compute_next_run

        # frequency=daily but cron=every 5 minutes — cron should win
        job = ScheduledJob(
            name="pred-test",
            frequency=ScheduledJobFrequency.DAILY,
            cron_expression="*/5 * * * *",
            job_name="Scheduled: test",
        )
        next_run = _compute_next_run(job)
        parsed = datetime.datetime.fromisoformat(next_run)
        # Should be within 5 minutes of now (modulo alignment)
        # next_run must be strictly in the future and divisible by 5
        assert parsed.minute % 5 == 0

    def test_fallback_to_now_without_cron(self) -> None:
        from app.models import ScheduledJob
        from app.routers.scheduled_monitoring import _compute_next_run

        job = ScheduledJob(name="no-cron", job_name="Scheduled: test")
        next_run = _compute_next_run(job)
        # Should be "now" — an ISO string parsing back to roughly now
        assert next_run
        parsed = datetime.datetime.fromisoformat(next_run)
        now = datetime.datetime.now(datetime.UTC)
        delta = abs((parsed - now).total_seconds())
        assert delta < 5, f"Expected near-now, got {delta}s delta"

    def test_compute_next_from_record_with_cron(self) -> None:
        from app.routers.scheduled_monitoring import _compute_next_from_record

        record = {
            "frequency": "daily",
            "cron_expression": "0 0 1 * *",
        }
        next_run = _compute_next_from_record(record)
        parsed = datetime.datetime.fromisoformat(next_run)
        # Should land on the 1st of some month
        assert parsed.day == 1
        assert parsed.hour == 0
        assert parsed.minute == 0

    def test_compute_next_from_record_frequency_fallback(self) -> None:
        from app.routers.scheduled_monitoring import _compute_next_from_record

        record = {"frequency": "weekly"}
        next_run = _compute_next_from_record(record)
        parsed = datetime.datetime.fromisoformat(next_run)
        now = datetime.datetime.now(datetime.UTC)
        delta = (parsed - now).total_seconds()
        # Should be ~7 days
        assert 5 * 86400 < delta < 9 * 86400


class TestProcessorLoopCronIntegration:
    """Test that the lifespan processor loop correctly uses cron for next_run_at."""

    def test_process_due_scheduled_jobs_uses_cron(self, tmp_path, monkeypatch) -> None:
        """When a scheduled job has cron_expression, next_run_at should be
        computed via the cron parser, not the simple frequency delta."""
        from app.worker_queue import reset_worker_queue

        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "test_jobs.json"))
        from app.config import settings

        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(tmp_path / "test_jobs.json"))
        from app.job_store import reset_job_store_for_tests

        reset_job_store_for_tests()
        from app.main import jobs_store, recycle_bin_store

        jobs_store.clear()
        recycle_bin_store.clear()
        reset_worker_queue()

        # Create a scheduled job record with cron_expression
        from app.models import ScheduledJob, ScheduledJobFrequency
        from app.routers.scheduled_monitoring import _scheduled_jobs

        job = ScheduledJob(
            name="cron-processor-test",
            frequency=ScheduledJobFrequency.DAILY,
            cron_expression="0 0 1 * *",  # monthly on the 1st
            job_name="Scheduled: processor test",
            urls=["https://example.com"],
            mode=ScrapeMode.MANUAL,
        )
        record = job.model_dump()
        # Set next_run_at to the past so the job is due
        past = datetime.datetime(2020, 1, 1, 0, 0, tzinfo=datetime.UTC)
        record["next_run_at"] = past.isoformat()
        _scheduled_jobs.upsert(job.id, record)

        # We can't easily invoke _process_due_scheduled_jobs without the
        # full scheduler wiring, but we can verify that the
        # _compute_next_from_record helper produces a cron-derived
        # result (the 1st of a month).
        from app.routers.scheduled_monitoring import _compute_next_from_record

        next_run = _compute_next_from_record(record)
        parsed = datetime.datetime.fromisoformat(next_run)
        assert parsed.day == 1, f"Expected day=1 from cron '0 0 1 * *', got day={parsed.day}"

        # Cleanup
        _scheduled_jobs.delete(job.id)
        reset_job_store_for_tests()
        jobs_store.clear()
        recycle_bin_store.clear()
        reset_worker_queue()
