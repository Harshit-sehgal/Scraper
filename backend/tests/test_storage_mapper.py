"""Direct unit tests for storage_mapper — the canonical Job ↔ row
serialization shared by SQLite and Postgres backends."""

from __future__ import annotations

import json

from app.models import Job, JobStatus, ScrapeMode, SourcePolicy
from app.storage_mapper import job_to_row, row_to_job

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _minimal_job(**overrides) -> Job:
    """Return a Job with only the required fields set — everything else
    uses its default value."""
    kwargs = {"name": "test-job"} | overrides
    return Job(**kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# job_to_row — field preservation
# ═══════════════════════════════════════════════════════════════════════════


def test_job_to_row_preserves_required_fields() -> None:
    job = _minimal_job(id="abc-123", name="my-job")
    row = job_to_row(job)
    assert row["id"] == "abc-123"
    assert row["name"] == "my-job"


def test_job_to_row_preserves_enum_status() -> None:
    job = _minimal_job(status=JobStatus.RUNNING)
    row = job_to_row(job)
    assert row["status"] == "running"


def test_job_to_row_preserves_enum_mode() -> None:
    job = _minimal_job(mode=ScrapeMode.AUTO)
    row = job_to_row(job)
    assert row["mode"] == "auto"


def test_job_to_row_preserves_source_policy() -> None:
    job = _minimal_job(source_policy=SourcePolicy.OFFICIAL_ONLY)
    row = job_to_row(job)
    assert row["source_policy"] == "official_only"


def test_job_to_row_ownership_fields() -> None:
    job = _minimal_job(created_by="user-x", org_id="org-1", project_id="proj-42")
    row = job_to_row(job)
    assert row["created_by"] == "user-x"
    assert row["org_id"] == "org-1"
    assert row["project_id"] == "proj-42"


def test_job_to_row_ownership_defaults_empty() -> None:
    job = _minimal_job()
    row = job_to_row(job)
    assert row["created_by"] == ""
    assert row["org_id"] == ""
    assert row["project_id"] == ""


def test_job_to_row_boolean_cancel_requested() -> None:
    job = _minimal_job(cancel_requested=True)
    row = job_to_row(job)
    assert row["cancel_requested"] is True


def test_job_to_row_boolean_pagination() -> None:
    job = _minimal_job(pagination=True)
    row = job_to_row(job)
    assert row["pagination"] is True


def test_job_to_row_boolean_deduplicate_default_true() -> None:
    job = _minimal_job()
    row = job_to_row(job)
    assert row["deduplicate"] is True


def test_job_to_row_boolean_results_on_disk_default_false() -> None:
    job = _minimal_job()
    row = job_to_row(job)
    assert row["results_on_disk"] is False


def test_job_to_row_json_urls() -> None:
    job = _minimal_job(urls=["https://a.com", "https://b.com"])
    row = job_to_row(job)
    assert json.loads(row["urls"]) == ["https://a.com", "https://b.com"]


def test_job_to_row_json_urls_default() -> None:
    job = _minimal_job()
    row = job_to_row(job)
    assert json.loads(row["urls"]) == []


def test_job_to_row_json_warnings() -> None:
    job = _minimal_job(warnings=["low quality", "timeout"])
    row = job_to_row(job)
    assert json.loads(row["warnings"]) == ["low quality", "timeout"]


def test_job_to_row_json_search_params() -> None:
    job = _minimal_job(search_params={"q": "test"})
    row = job_to_row(job)
    assert json.loads(row["search_params"]) == {"q": "test"}


def test_job_to_row_json_schema_fields() -> None:
    from app.models import FieldType, SchemaField

    fields = [SchemaField(name="title", field_type=FieldType.STRING)]
    job = _minimal_job(schema_fields=fields)
    row = job_to_row(job)
    parsed = json.loads(row["schema_fields"])
    assert len(parsed) == 1
    assert parsed[0]["name"] == "title"


def test_job_to_row_numeric_defaults() -> None:
    job = _minimal_job()
    row = job_to_row(job)
    assert row["total_records"] == 0
    assert row["max_per_domain"] == 4
    assert row["min_record_score"] == 0.35
    assert row["estimated_cost_usd"] == 0.0


def test_job_to_row_error_none_becomes_empty() -> None:
    job = _minimal_job(error=None)
    row = job_to_row(job)
    assert row["error"] == ""


def test_job_to_row_error_set() -> None:
    job = _minimal_job(error="something broke")
    row = job_to_row(job)
    assert row["error"] == "something broke"


def test_job_to_row_completed_at_none_becomes_empty() -> None:
    job = _minimal_job(completed_at=None)
    row = job_to_row(job)
    assert row["completed_at"] == ""


def test_job_to_row_max_distance_km_none() -> None:
    job = _minimal_job(max_distance_km=None)
    row = job_to_row(job)
    assert row["max_distance_km"] is None


def test_job_to_row_acquisition_mode_default() -> None:
    job = _minimal_job()
    row = job_to_row(job)
    assert row["acquisition_mode"] == "standard"


# ═══════════════════════════════════════════════════════════════════════════
# row_to_job — deserialization
# ═══════════════════════════════════════════════════════════════════════════


def test_row_to_job_minimal_row() -> None:
    row = {"id": "x", "name": "j", "status": "pending"}
    job = row_to_job(row)
    assert job is not None
    assert job.id == "x"
    assert job.name == "j"
    assert job.status == JobStatus.PENDING


def test_row_to_job_returns_none_for_missing_id() -> None:
    row = {"status": "pending"}  # no "id" key
    assert row_to_job(row) is None


def test_row_to_job_returns_none_for_invalid_json() -> None:
    row = {"id": "x", "name": "j", "status": "pending", "urls": "not json"}
    assert row_to_job(row) is None


def test_row_to_job_round_trip() -> None:
    original = _minimal_job(
        id="roundtrip-1",
        urls=["https://example.com/data"],
        status=JobStatus.RUNNING,
        mode=ScrapeMode.AUTO,
        error=None,
    )
    row = job_to_row(original)
    restored = row_to_job(row)
    assert restored is not None
    assert restored.id == original.id
    assert restored.status == original.status
    assert restored.urls == original.urls


def test_row_to_job_full_round_trip() -> None:
    original = _minimal_job(
        id="full-rt",
        name="full-test",
        status=JobStatus.COMPLETED,
        mode=ScrapeMode.AUTO,
        created_by="user-1",
        org_id="org-1",
        project_id="proj-1",
        urls=["https://example.com"],
        error="something went wrong",
        total_records=42,
        cancel_requested=False,
        pagination=True,
        deduplicate=False,
        min_record_score=0.5,
        acquisition_mode="deep_scan",
    )
    row = job_to_row(original)
    restored = row_to_job(row)
    assert restored is not None
    assert restored.id == original.id
    assert restored.name == original.name
    assert restored.status == original.status
    assert restored.mode == original.mode
    assert restored.created_by == original.created_by
    assert restored.org_id == original.org_id
    assert restored.project_id == original.project_id
    assert restored.urls == original.urls
    assert restored.error == original.error
    assert restored.total_records == original.total_records
    assert restored.cancel_requested == original.cancel_requested
    assert restored.pagination == original.pagination
    assert restored.deduplicate == original.deduplicate
    assert restored.min_record_score == original.min_record_score
    assert restored.acquisition_mode == original.acquisition_mode


def test_row_to_job_source_policy_invalid_falls_back() -> None:
    row = {"id": "x", "name": "j", "status": "pending", "source_policy": "bogus_value"}
    job = row_to_job(row)
    assert job is not None
    assert job.source_policy == SourcePolicy.ALL_SOURCES


def test_row_to_job_cancel_requested_string_true() -> None:
    row = {"id": "x", "name": "j", "status": "pending", "cancel_requested": "1"}
    job = row_to_job(row)
    assert job is not None
    assert job.cancel_requested is True


def test_row_to_job_completed_at_restored() -> None:
    row = {"id": "x", "name": "j", "status": "completed", "completed_at": "2026-06-01T12:00:00"}
    job = row_to_job(row)
    assert job is not None
    assert job.completed_at == "2026-06-01T12:00:00"


def test_row_to_job_warnings_restored() -> None:
    row = {"id": "x", "name": "j", "status": "completed", "warnings": '["warn1"]'}
    job = row_to_job(row)
    assert job is not None
    assert job.warnings == ["warn1"]


def test_row_to_job_search_params_json_restored() -> None:
    row = {"id": "x", "name": "j", "status": "pending", "search_params": '{"q":"test"}'}
    job = row_to_job(row)
    assert job is not None
    assert job.search_params == {"q": "test"}


def test_row_to_job_search_params_none_becomes_none() -> None:
    row = {"id": "x", "name": "j", "status": "pending", "search_params": "{}"}
    job = row_to_job(row)
    assert job is not None
    assert job.search_params is None


def test_row_to_job_ownership_restored() -> None:
    row = {"id": "x", "name": "j", "status": "completed", "created_by": "a", "org_id": "b", "project_id": "c"}
    job = row_to_job(row)
    assert job is not None
    assert job.created_by == "a"
    assert job.org_id == "b"
    assert job.project_id == "c"


def test_row_to_job_results_on_disk_restored() -> None:
    row = {"id": "x", "name": "j", "status": "completed", "results_on_disk": True, "results_file_path": "/tmp/results.json"}
    job = row_to_job(row)
    assert job is not None
    assert job.results_on_disk is True
    assert job.results_file_path == "/tmp/results.json"


def test_row_to_job_empty_fields_default() -> None:
    row = {"id": "x", "name": "j", "status": "pending"}
    job = row_to_job(row)
    assert job is not None
    assert job.created_by == ""
    assert job.org_id == ""
    assert job.project_id == ""
    assert job.acquisition_mode == "standard"
    assert job.source_policy == SourcePolicy.ALL_SOURCES
    assert job.deduplicate is True
    assert job.pagination is False


def test_row_to_job_mode_defaults_to_manual() -> None:
    row = {"id": "x", "name": "j", "status": "pending"}
    job = row_to_job(row)
    assert job is not None
    assert job.mode == ScrapeMode.MANUAL
