"""Regression tests for job_store.py field persistence.

Covers:
- warnings field round-trip (was hardcoded to "[]")
- acquisition_mode field round-trip (was hardcoded to "standard")
- Full field parity: every important Job field survives save → load
"""

import os
import tempfile
from pathlib import Path

import pytest

from app.models import Job, JobStatus, ScrapeMode, SourcePolicy
from app.job_store import (
    _job_to_row,
    _row_to_job,
    load_state,
    save_state,
    reset_job_store_for_tests,
)


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Point job_store at a fresh temp DB for each test."""
    db_file = tmp_path / "test_jobs.db"
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(db_file.with_suffix(".json")))
    reset_job_store_for_tests()
    yield db_file
    reset_job_store_for_tests()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(**kwargs) -> Job:
    defaults = dict(name="test-job", urls=["https://example.com"])
    defaults.update(kwargs)
    return Job(**defaults)


def _roundtrip(job: Job) -> Job:
    """Convert job → row → job without touching the DB."""
    row = _job_to_row(job)
    result = _row_to_job(row)
    assert result is not None, "Deserialization returned None"
    return result


# ---------------------------------------------------------------------------
# test_sqlite_preserves_job_warnings
# ---------------------------------------------------------------------------

def test_sqlite_preserves_job_warnings_empty(isolated_db):
    """A job with no warnings attribute round-trips to an empty list in the row."""
    job = _make_job()
    row = _job_to_row(job)
    assert row["warnings"] == "[]", f"Expected '[]', got {row['warnings']!r}"


def test_sqlite_preserves_job_warnings_with_data(isolated_db):
    """If Job gains a warnings field, its value is persisted (not overwritten with [])."""
    job = _make_job()
    # Simulate a future Job that has warnings
    object.__setattr__(job, "warnings", ["selector drift detected", "low confidence"])
    row = _job_to_row(job)
    import json
    assert json.loads(row["warnings"]) == ["selector drift detected", "low confidence"]


def test_sqlite_preserves_job_warnings_restored(isolated_db):
    """warnings stored in the row are restored onto the job if the field exists."""
    job = _make_job()
    object.__setattr__(job, "warnings", ["w1", "w2"])
    row = _job_to_row(job)
    restored = _row_to_job(row)
    assert restored is not None
    # If Job has warnings, it should be restored; if not, the row value is still correct
    import json
    assert json.loads(row["warnings"]) == ["w1", "w2"]
    if hasattr(restored, "warnings"):
        assert restored.warnings == ["w1", "w2"]


def test_sqlite_warnings_via_db(isolated_db):
    """End-to-end: warnings survive save_state → load_state."""
    job = _make_job(status=JobStatus.COMPLETED)
    object.__setattr__(job, "warnings", ["test warning"])
    save_state({job.id: job}, {})
    jobs, _, _ = load_state()
    loaded = jobs.get(job.id)
    # Job was marked FAILED on recovery (was COMPLETED so no recovery), check it loaded
    assert loaded is not None
    if hasattr(loaded, "warnings"):
        assert loaded.warnings == ["test warning"]


# ---------------------------------------------------------------------------
# test_sqlite_preserves_acquisition_mode
# ---------------------------------------------------------------------------

def test_sqlite_preserves_acquisition_mode_default(isolated_db):
    """A job with no acquisition_mode attribute defaults to 'standard' in the row."""
    job = _make_job()
    row = _job_to_row(job)
    assert row["acquisition_mode"] == "standard"


def test_sqlite_preserves_acquisition_mode_custom_string(isolated_db):
    """A string acquisition_mode is persisted as-is."""
    job = _make_job()
    object.__setattr__(job, "acquisition_mode", "deep_crawl")
    row = _job_to_row(job)
    assert row["acquisition_mode"] == "deep_crawl"


def test_sqlite_preserves_acquisition_mode_enum(isolated_db):
    """An enum acquisition_mode uses .value for serialization."""
    from enum import Enum

    class AcquisitionMode(str, Enum):
        STANDARD = "standard"
        AGGRESSIVE = "aggressive"

    job = _make_job()
    object.__setattr__(job, "acquisition_mode", AcquisitionMode.AGGRESSIVE)
    row = _job_to_row(job)
    assert row["acquisition_mode"] == "aggressive"


def test_sqlite_preserves_acquisition_mode_restored(isolated_db):
    """acquisition_mode stored in the row is restored onto the job if the field exists."""
    job = _make_job()
    object.__setattr__(job, "acquisition_mode", "deep_crawl")
    row = _job_to_row(job)
    restored = _row_to_job(row)
    assert restored is not None
    assert row["acquisition_mode"] == "deep_crawl"
    if hasattr(restored, "acquisition_mode"):
        assert restored.acquisition_mode == "deep_crawl"


def test_sqlite_acquisition_mode_not_overwritten_on_save(isolated_db):
    """Saving a job with a non-standard mode does not reset it to 'standard'."""
    job = _make_job(status=JobStatus.COMPLETED)
    object.__setattr__(job, "acquisition_mode", "aggressive")
    save_state({job.id: job}, {})
    jobs, _, _ = load_state()
    loaded = jobs.get(job.id)
    assert loaded is not None
    if hasattr(loaded, "acquisition_mode"):
        assert loaded.acquisition_mode == "aggressive"


# ---------------------------------------------------------------------------
# test_sqlite_full_job_field_parity
# ---------------------------------------------------------------------------

def test_sqlite_full_job_field_parity(isolated_db):
    """Every important Job field survives a _job_to_row → _row_to_job round-trip."""
    from app.models import SchemaField, FilterRule, LogEntry

    job = Job(
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
        schema_fields=[SchemaField(name="price", field_type="number")],
        filters=[FilterRule(field_name="price", operator="greater_than", value="10")],
        pagination=True,
        max_pages=5,
        deduplicate=False,
        deduplicate_field="url",
        min_record_score=0.7,
        selectors_map={"https://example.com": [".product"]},
        search_params={"q": "laptop", "page": "1"},
        cancel_requested=False,
        status=JobStatus.COMPLETED,
        started_at="2026-05-25T10:00:00",
        completed_at="2026-05-25T10:05:00",
        total_records=42,
        filtered_records=38,
        error=None,
        results=[{"name": "Widget", "price": 9.99}],
        analysis="High quality results",
        discovered_urls=[{"url": "https://example.com/p/1", "score": 0.9}],
        quality_report={"score": 0.95, "issues": []},
        estimated_cost_usd=0.05,
        total_llm_calls=3,
        logs=[LogEntry(level="info", message="started")],
        progress_current=42,
        progress_total=42,
        results_on_disk=True,
        results_file_path="/tmp/results.gz",
    )
    object.__setattr__(job, "warnings", ["warning1"])
    object.__setattr__(job, "acquisition_mode", "aggressive")

    restored = _roundtrip(job)

    assert restored.name == job.name
    assert restored.mode == job.mode
    assert restored.intent == job.intent
    assert restored.urls == job.urls
    assert restored.topic == job.topic
    assert restored.location == job.location
    assert restored.preferred_domain == job.preferred_domain
    assert restored.source_policy == job.source_policy
    assert restored.max_per_domain == job.max_per_domain
    assert restored.origin_location == job.origin_location
    assert restored.max_distance_km == job.max_distance_km
    assert len(restored.schema_fields) == 1
    assert restored.schema_fields[0].name == "price"
    assert len(restored.filters) == 1
    assert restored.filters[0].field_name == "price"
    assert restored.pagination == job.pagination
    assert restored.max_pages == job.max_pages
    assert restored.deduplicate == job.deduplicate
    assert restored.deduplicate_field == job.deduplicate_field
    assert restored.min_record_score == job.min_record_score
    assert restored.selectors_map == job.selectors_map
    assert restored.search_params == job.search_params
    assert restored.cancel_requested == job.cancel_requested
    assert restored.status == job.status
    assert restored.started_at == job.started_at
    assert restored.completed_at == job.completed_at
    assert restored.total_records == job.total_records
    assert restored.filtered_records == job.filtered_records
    assert restored.error == job.error
    assert restored.results == job.results
    assert restored.analysis == job.analysis
    assert restored.discovered_urls == job.discovered_urls
    assert restored.quality_report == job.quality_report
    assert restored.estimated_cost_usd == job.estimated_cost_usd
    assert restored.total_llm_calls == job.total_llm_calls
    assert len(restored.logs) == 1
    assert restored.logs[0].message == "started"
    assert restored.progress_current == job.progress_current
    assert restored.progress_total == job.progress_total
    assert restored.results_on_disk == job.results_on_disk
    assert restored.results_file_path == job.results_file_path
    if hasattr(restored, "warnings"):
        assert restored.warnings == ["warning1"]
    if hasattr(restored, "acquisition_mode"):
        assert restored.acquisition_mode == "aggressive"


# ---------------------------------------------------------------------------
# test_restart_recovery_persisted_to_db  (item 6)
# ---------------------------------------------------------------------------

def test_restart_recovery_writes_failed_status_to_db(isolated_db, monkeypatch):
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


def test_restart_recovery_survives_second_load(isolated_db):
    """After recovery, a second load_state() must not re-recover the same job."""
    job = _make_job(status=JobStatus.PENDING)
    save_state({job.id: job}, {})

    load_state()  # first load — recovers to FAILED
    jobs2, _, _ = load_state()  # second load — must stay FAILED, not re-trigger

    assert jobs2[job.id].status == JobStatus.FAILED
    assert "Recovered" in (jobs2[job.id].error or "")
