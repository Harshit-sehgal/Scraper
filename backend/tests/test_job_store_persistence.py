"""Regression tests for job_store.py field persistence.

Covers:
- warnings field round-trip (fully typed Pydantic field)
- acquisition_mode field round-trip (fully typed Pydantic field)
- Full field parity: every important Job field survives save → load
"""

import enum
import json

import pytest
from app.job_store import (
    _job_to_row,
    _row_to_job,
    load_state,
    reset_job_store_for_tests,
    save_state,
)
from app.models import Job, JobStatus, ScrapeMode, SourcePolicy


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point job_store at a fresh temp DB for each test."""
    from app.config import settings

    db_file = tmp_path / "test_jobs.db"
    state_file = db_file.with_suffix(".json")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(state_file))
    monkeypatch.setattr(settings, "STATE_FILE_PATH", str(state_file))
    reset_job_store_for_tests()
    yield db_file
    reset_job_store_for_tests()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(**kwargs) -> Job:
    defaults = {"name": "test-job", "urls": ["https://example.com"]}
    defaults.update(kwargs)
    return Job(**defaults)


def _roundtrip(job: Job) -> Job:
    """Convert job → row → job without touching the DB."""
    row = _job_to_row(job)
    result = _row_to_job(row)
    assert result is not None, "Deserialization returned None"
    return result


def _make_parity_job() -> Job:
    from app.models import FilterRule, LogEntry, SchemaField

    return Job(
        id="job-field-parity",
        name="parity-test",
        mode=ScrapeMode.AUTO,
        intent="find all products",
        urls=["https://example.com/products", "https://example.com/shop"],
        topic="e-commerce products",
        location="New York",
        preferred_domain="example.com",
        source_policy=SourcePolicy.ALL_SOURCES,
        max_per_domain=3,
        origin_location="40.7128,-74.0060",
        max_distance_km=50.0,
        schema_fields=[SchemaField(name="price", field_type="number", description="", required=False)],
        filters=[FilterRule(field_name="price", operator="greater_than", value="10", origin_address="", distance_unit="km")],
        pagination=True,
        max_pages=5,
        deduplicate=False,
        deduplicate_field="url",
        min_record_score=0.7,
        selectors_map={"https://example.com": [".product"]},
        search_params={"q": "laptop", "page": "1"},
        cancel_requested=True,
        status=JobStatus.DEGRADED,
        created_at="2026-05-25T09:59:00",
        started_at="2026-05-25T10:00:00",
        completed_at="2026-05-25T10:05:00",
        total_records=42,
        filtered_records=38,
        error="partial scrape warning",
        results=[{"name": "Widget", "price": 9.99}],
        analysis="High quality results",
        discovered_urls=[{"url": "https://example.com/p/1", "score": 0.9}],
        quality_report={"score": 0.95, "issues": []},
        estimated_cost_usd=0.05,
        total_llm_calls=3,
        logs=[
            LogEntry(
                timestamp="2026-05-25T10:00:01",
                level="info",
                message="started",
            ),
        ],
        progress_current=42,
        progress_total=42,
        results_on_disk=True,
        results_file_path="/tmp/results.gz",  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        warnings=["warning1"],
        acquisition_mode="aggressive",
    )


def _assert_job_field_parity(restored: Job, expected: Job) -> None:
    assert restored.model_dump(mode="json") == expected.model_dump(mode="json")


# ---------------------------------------------------------------------------
# test_sqlite_preserves_job_warnings
# ---------------------------------------------------------------------------


def test_sqlite_preserves_job_warnings_empty(isolated_db) -> None:
    """A job with no warnings attribute round-trips to an empty list in the row."""
    job = _make_job()
    row = _job_to_row(job)
    assert row["warnings"] == "[]", f"Expected '[]', got {row['warnings']!r}"


def test_sqlite_preserves_job_warnings_with_data(isolated_db) -> None:
    """Warnings field value is persisted (not overwritten with [])."""
    job = _make_job(warnings=["selector drift detected", "low confidence"])
    row = _job_to_row(job)
    assert json.loads(row["warnings"]) == ["selector drift detected", "low confidence"]


def test_sqlite_preserves_job_warnings_restored(isolated_db) -> None:
    """Warnings stored in the row are restored onto the job."""
    job = _make_job(warnings=["w1", "w2"])
    row = _job_to_row(job)
    restored = _row_to_job(row)
    assert restored is not None
    assert json.loads(row["warnings"]) == ["w1", "w2"]
    assert restored.warnings == ["w1", "w2"]


def test_sqlite_warnings_via_db(isolated_db) -> None:
    """End-to-end: warnings survive save_state → load_state."""
    job = _make_job(status=JobStatus.COMPLETED, warnings=["test warning"])
    save_state({job.id: job}, {})
    jobs, _, _ = load_state()
    loaded = jobs.get(job.id)
    assert loaded is not None
    assert loaded.warnings == ["test warning"]


# ---------------------------------------------------------------------------
# test_sqlite_preserves_acquisition_mode
# ---------------------------------------------------------------------------


def test_sqlite_preserves_acquisition_mode_default(isolated_db) -> None:
    """A job with no acquisition_mode attribute defaults to 'standard' in the row."""
    job = _make_job()
    row = _job_to_row(job)
    assert row["acquisition_mode"] == "standard"


def test_sqlite_preserves_acquisition_mode_custom_string(isolated_db) -> None:
    """A string acquisition_mode is persisted as-is."""
    job = _make_job(acquisition_mode="deep_crawl")
    row = _job_to_row(job)
    assert row["acquisition_mode"] == "deep_crawl"


def test_sqlite_preserves_acquisition_mode_enum(isolated_db) -> None:
    """An enum acquisition_mode uses .value for serialization."""

    class AcquisitionMode(enum.StrEnum):
        STANDARD = "standard"
        AGGRESSIVE = "aggressive"

    job = _make_job(acquisition_mode=AcquisitionMode.AGGRESSIVE)
    row = _job_to_row(job)
    assert row["acquisition_mode"] == "aggressive"


def test_sqlite_preserves_acquisition_mode_restored(isolated_db) -> None:
    """acquisition_mode stored in the row is restored onto the job."""
    job = _make_job(acquisition_mode="deep_crawl")
    row = _job_to_row(job)
    restored = _row_to_job(row)
    assert restored is not None
    assert row["acquisition_mode"] == "deep_crawl"
    assert restored.acquisition_mode == "deep_crawl"


def test_sqlite_acquisition_mode_not_overwritten_on_save(isolated_db) -> None:
    """Saving a job with a non-standard mode does not reset it to 'standard'."""
    job = _make_job(status=JobStatus.COMPLETED, acquisition_mode="aggressive")
    save_state({job.id: job}, {})
    jobs, _, _ = load_state()
    loaded = jobs.get(job.id)
    assert loaded is not None
    assert loaded.acquisition_mode == "aggressive"


# ---------------------------------------------------------------------------
# test_sqlite_full_job_field_parity
# ---------------------------------------------------------------------------


def test_sqlite_full_job_field_parity(isolated_db) -> None:
    """Every important Job field survives a _job_to_row → _row_to_job round-trip."""
    job = _make_parity_job()
    restored = _roundtrip(job)
    _assert_job_field_parity(restored, job)


def test_sqlite_full_job_field_parity_via_db(isolated_db) -> None:
    """Every important Job field survives a real save_state → load_state round-trip."""
    job = _make_parity_job()

    save_state({job.id: job}, {})
    jobs, _, _ = load_state()

    restored = jobs.get(job.id)
    assert restored is not None
    _assert_job_field_parity(restored, job)
    assert restored.warnings == ["warning1"]
    assert restored.acquisition_mode == "aggressive"


# ---------------------------------------------------------------------------
# test_restart_recovery_persisted_to_db  (item 6)
# ---------------------------------------------------------------------------


def test_restart_recovery_writes_failed_status_to_db(isolated_db, monkeypatch) -> None:
    """load_state() must write FAILED back to SQLite, not just return it in-memory.

    Regression guard: if the DB write is removed, the next load_state() call
    would return the job as RUNNING again instead of FAILED.
    """
    import sqlite3 as _sqlite3

    # Seed a RUNNING job directly into the DB (simulates ungraceful shutdown)
    job = _make_job(status=JobStatus.RUNNING)
    save_state({job.id: job}, {})

    # First load_state() — should recover the job to FAILED and write it back
    jobs, _, _ = load_state()
    assert jobs[job.id].status == JobStatus.FAILED

    # Now read the DB row directly — must also be FAILED, not RUNNING
    from app.job_store import _get_db_path

    conn = _sqlite3.connect(str(_get_db_path()))
    row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job.id,)).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "failed", f"DB row still has status={row[0]!r}, expected 'failed'"


def test_load_state_can_skip_restart_recovery_for_worker_reads(isolated_db) -> None:
    """Worker hot-path reads must not mark active jobs as restart-recovered."""
    import sqlite3 as _sqlite3

    job = _make_job(status=JobStatus.RUNNING)
    save_state({job.id: job}, {})

    jobs, _, _ = load_state(recover_in_progress=False)
    assert jobs[job.id].status == JobStatus.RUNNING
    assert jobs[job.id].error in (None, "")

    from app.job_store import _get_db_path

    conn = _sqlite3.connect(str(_get_db_path()))
    row = conn.execute("SELECT status, error FROM jobs WHERE id = ?", (job.id,)).fetchone()
    conn.close()
    assert row in {("running", None), ("running", "")}


def test_restart_recovery_survives_second_load(isolated_db) -> None:
    """After recovery, a second load_state() must not re-recover the same job."""
    job = _make_job(status=JobStatus.PENDING)
    save_state({job.id: job}, {})

    load_state()  # first load — recovers to FAILED
    jobs2, _, _ = load_state()  # second load — must stay FAILED, not re-trigger

    assert jobs2[job.id].status == JobStatus.FAILED
    assert "Recovered" in (jobs2[job.id].error or "")
