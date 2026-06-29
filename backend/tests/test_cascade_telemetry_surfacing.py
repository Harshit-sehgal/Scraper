"""Tests for cascade_telemetry surfacing on the Job model.

Verifies that the new ``cascade_telemetry`` and ``quality_score_summary``
fields round-trip through Job creation and ``model_dump()`` so they are
available in the get_job API response.
"""

from __future__ import annotations

import pytest
from app.models import Job, JobStatus


def _job(**overrides) -> Job:
    """Build a Job with optional overrides for telemetry fields."""
    defaults: dict = {
        "name": "test-job",
        "urls": ["https://example.com/a"],
    }
    defaults.update(overrides)
    return Job(**defaults)


def test_job_has_cascade_telemetry_field() -> None:
    """The cascade_telemetry field exists and defaults to empty dict."""
    job = _job()
    assert hasattr(job, "cascade_telemetry")
    assert job.cascade_telemetry == {}
    assert isinstance(job.cascade_telemetry, dict)


def test_job_has_quality_score_summary_field() -> None:
    """The quality_score_summary field exists and defaults to 0.0."""
    job = _job()
    assert hasattr(job, "quality_score_summary")
    assert job.quality_score_summary == 0.0


def test_cascade_telemetry_round_trips_through_model_dump() -> None:
    """Populating cascade_telemetry survives a model_dump round-trip."""
    job = _job(
        cascade_telemetry={
            "https://example.com/a": {
                "layer": "regex_v2",
                "score": 0.92,
                "duration_ms": 145,
                "quality_score": 0.85,
            }
        },
    )
    dumped = job.model_dump()
    assert dumped["cascade_telemetry"]["https://example.com/a"]["layer"] == "regex_v2"
    assert dumped["cascade_telemetry"]["https://example.com/a"]["duration_ms"] == 145


def test_quality_score_summary_round_trips() -> None:
    """Populating quality_score_summary survives a model_dump round-trip."""
    job = _job(quality_score_summary=0.87)
    dumped = job.model_dump()
    assert dumped["quality_score_summary"] == 0.87


def test_cascade_telemetry_keys_by_url() -> None:
    """Each URL gets its own telemetry block — no cross-talk."""
    job = _job(
        urls=["https://example.com/a", "https://example.com/b"],
        cascade_telemetry={
            "https://example.com/a": {"layer": "regex", "score": 0.9, "duration_ms": 100},
            "https://example.com/b": {"layer": "llm", "score": 0.7, "duration_ms": 1200},
        },
    )
    dumped = job.model_dump()
    layers = {url: data["layer"] for url, data in dumped["cascade_telemetry"].items()}
    assert layers["https://example.com/a"] == "regex"
    assert layers["https://example.com/b"] == "llm"


def test_empty_cascade_telemetry_for_pending_job() -> None:
    """A job that hasn't run yet has no telemetry keys."""
    job = _job()
    assert job.status == JobStatus.PENDING
    assert job.cascade_telemetry == {}
    assert job.quality_score_summary == 0.0


def test_quality_score_summary_bounded_zero_to_one() -> None:
    """quality_score_summary must be in [0.0, 1.0] — pydantic enforces this."""
    # Valid values
    _job(quality_score_summary=0.0)
    _job(quality_score_summary=0.5)
    _job(quality_score_summary=1.0)

    # Out-of-bounds values should be rejected
    with pytest.raises(ValueError):
        _job(quality_score_summary=-0.1)
    with pytest.raises(ValueError):
        _job(quality_score_summary=1.5)


def test_cascade_telemetry_omitted_when_not_provided() -> None:
    """When the API caller doesn't supply cascade_telemetry, the field defaults to {}."""
    job = Job(name="x", urls=["https://example.com"])
    dumped = job.model_dump()
    assert "cascade_telemetry" in dumped
    assert dumped["cascade_telemetry"] == {}
