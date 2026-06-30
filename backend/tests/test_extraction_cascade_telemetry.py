"""Unit tests for extraction_cascade_telemetry.

Covers recording, querying, TTL eviction, hard-cap truncation,
prefix filtering, and clear behaviour.
"""

from __future__ import annotations

import time

import pytest
from app import extraction_cascade_telemetry as ect

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_store() -> None:
    """Reset the in-memory store before every test."""
    ect.clear_cascade_traces()


# ---------------------------------------------------------------------------
# record_cascade_step
# ---------------------------------------------------------------------------


class TestRecordCascadeStep:
    """record_cascade_step stores a step entry."""

    def test_stores_single_step(self) -> None:
        """A single call appends one entry for the job."""
        ect.record_cascade_step(
            "job-1",
            url="https://example.com",
            layer_name="static",
            quality_score=0.85,
            success=True,
            duration_ms=120.0,
            reason_stopped="threshold_met",
        )
        steps = ect.get_cascade_trace("job-1")
        assert len(steps) == 1
        entry = steps[0]
        assert entry["layer"] == "static"
        assert entry["url"] == "https://example.com"
        assert entry["quality_score"] == 0.85
        assert entry["success"] is True
        assert entry["duration_ms"] == 120.0
        assert entry["reason_stopped"] == "threshold_met"
        assert "timestamp" in entry

    def test_quality_score_rounded(self) -> None:
        """quality_score is rounded to 4 decimal places."""
        ect.record_cascade_step("j", quality_score=0.123456789)
        steps = ect.get_cascade_trace("j")
        assert steps[0]["quality_score"] == 0.1235

    def test_duration_ms_rounded(self) -> None:
        """duration_ms is rounded to 1 decimal place."""
        ect.record_cascade_step("j", duration_ms=123.456)
        steps = ect.get_cascade_trace("j")
        assert steps[0]["duration_ms"] == 123.5

    def test_stores_multiple_steps_preserving_order(self) -> None:
        """Multiple steps for the same job are stored in insertion order."""
        for i in range(5):
            ect.record_cascade_step("job-order", layer_name=f"layer-{i}")
        steps = ect.get_cascade_trace("job-order")
        assert len(steps) == 5
        assert [s["layer"] for s in steps] == [
            "layer-0",
            "layer-1",
            "layer-2",
            "layer-3",
            "layer-4",
        ]

    def test_separate_jobs_do_not_interfere(self) -> None:
        """Steps for different jobs are isolated."""
        ect.record_cascade_step("job-a", layer_name="A")
        ect.record_cascade_step("job-b", layer_name="B")
        assert len(ect.get_cascade_trace("job-a")) == 1
        assert len(ect.get_cascade_trace("job-b")) == 1
        assert ect.get_cascade_trace("job-a")[0]["layer"] == "A"


# ---------------------------------------------------------------------------
# get_cascade_trace
# ---------------------------------------------------------------------------


class TestGetCascadeTrace:
    """get_cascade_trace returns the ordered log for a single job."""

    def test_returns_empty_list_for_unknown_job(self) -> None:
        """An unknown job_id yields an empty list."""
        result = ect.get_cascade_trace("nonexistent")
        assert result == []

    def test_meta_attached_to_first_step(self) -> None:
        """When meta exists it is attached to the first step dict."""
        ect.record_cascade_step("job-m", layer_name="first")
        ect.set_cascade_final_status("job-m", "completed", "done")
        steps = ect.get_cascade_trace("job-m")
        assert len(steps) == 1
        assert steps[0]["_meta"]["status"] == "completed"
        assert steps[0]["_meta"]["stopped_reason"] == "done"

    def test_meta_has_running_status_after_record(self) -> None:
        """After record_cascade_step, the meta status is 'running'."""
        ect.record_cascade_step("job-run", layer_name="x")
        steps = ect.get_cascade_trace("job-run")
        assert steps[0]["_meta"]["status"] == "running"

    def test_meta_only_on_first_step(self) -> None:
        """Meta is attached only to the first step in a multi-step trace."""
        ect.record_cascade_step("job-mf", layer_name="a")
        ect.record_cascade_step("job-mf", layer_name="b")
        ect.set_cascade_final_status("job-mf", "completed")
        steps = ect.get_cascade_trace("job-mf")
        assert "_meta" in steps[0]
        assert "_meta" not in steps[1]


# ---------------------------------------------------------------------------
# set_cascade_final_status
# ---------------------------------------------------------------------------


class TestSetCascadeFinalStatus:
    """set_cascade_final_status updates meta for a job."""

    def test_updates_meta_status(self) -> None:
        """Status and stopped_reason are persisted in meta."""
        ect.record_cascade_step("job-s", layer_name="x")
        ect.set_cascade_final_status("job-s", "failed", "timeout")
        steps = ect.get_cascade_trace("job-s")
        assert steps[0]["_meta"]["status"] == "failed"
        assert steps[0]["_meta"]["stopped_reason"] == "timeout"

    def test_preserves_existing_meta_on_overwrite(self) -> None:
        """Updating status twice preserves the last_update timestamp."""
        ect.record_cascade_step("job-ov", layer_name="a")
        ect.set_cascade_final_status("job-ov", "running")
        ect.set_cascade_final_status("job-ov", "completed", "ok")
        steps = ect.get_cascade_trace("job-ov")
        assert steps[0]["_meta"]["status"] == "completed"
        assert steps[0]["_meta"]["stopped_reason"] == "ok"

    def test_final_status_without_prior_step(self) -> None:
        """Setting final status even without a recorded step creates meta."""
        ect.set_cascade_final_status("job-fs", "empty", "no_content")
        # The trace has no steps but meta exists
        steps = ect.get_cascade_trace("job-fs")
        assert steps == []
        # Verify meta is stored by checking the internal store
        with ect._cascade_traces_lock:
            assert ect._cascade_meta.get("job-fs", {}).get("status") == "empty"


# ---------------------------------------------------------------------------
# get_all_cascade_traces
# ---------------------------------------------------------------------------


class TestGetAllCascadeTraces:
    """get_all_cascade_traces returns a prefix-filtered snapshot."""

    def test_returns_all_when_no_prefix(self) -> None:
        """Without a prefix, all job traces are returned."""
        ect.record_cascade_step("job-x", layer_name="x")
        ect.record_cascade_step("job-y", layer_name="y")
        result = ect.get_all_cascade_traces()
        assert "job-x" in result
        assert "job-y" in result

    def test_prefix_filter(self) -> None:
        """Only jobs whose ID starts with the prefix are returned."""
        ect.record_cascade_step("alpha-1", layer_name="a")
        ect.record_cascade_step("alpha-2", layer_name="b")
        ect.record_cascade_step("beta-1", layer_name="c")
        result = ect.get_all_cascade_traces(prefix="alpha-")
        assert "alpha-1" in result
        assert "alpha-2" in result
        assert "beta-1" not in result

    def test_empty_result_for_nonexistent_prefix(self) -> None:
        """A prefix matching no jobs returns an empty dict."""
        ect.record_cascade_step("job-z", layer_name="z")
        result = ect.get_all_cascade_traces(prefix="zzz-")
        assert result == {}


# ---------------------------------------------------------------------------
# clear_cascade_traces
# ---------------------------------------------------------------------------


class TestClearCascadeTraces:
    """clear_cascade_traces drops all traces and meta."""

    def test_clears_everything(self) -> None:
        """After clear, no traces remain."""
        ect.record_cascade_step("job-c1", layer_name="a")
        ect.record_cascade_step("job-c2", layer_name="b")
        ect.clear_cascade_traces()
        assert ect.get_cascade_trace("job-c1") == []
        assert ect.get_cascade_trace("job-c2") == []

    def test_clear_also_resets_meta(self) -> None:
        """After clear, meta for all jobs is gone."""
        ect.record_cascade_step("job-cm", layer_name="x")
        ect.set_cascade_final_status("job-cm", "completed")
        ect.clear_cascade_traces()
        with ect._cascade_traces_lock:
            assert "job-cm" not in ect._cascade_meta


# ---------------------------------------------------------------------------
# TTL-based eviction
# ---------------------------------------------------------------------------


class TestTtlEviction:
    """_evict_stale removes entries older than _TRACE_TTL_SECONDS."""

    def test_stale_entries_evicted(self) -> None:
        """Entries with a last_update beyond the TTL are removed."""
        ect.record_cascade_step("job-stale", layer_name="x")
        # Artificially age the metadata
        with ect._cascade_traces_lock:
            ect._cascade_meta["job-stale"]["last_update"] = time.time() - ect._TRACE_TTL_SECONDS - 1
        # Trigger eviction by reading
        result = ect.get_cascade_trace("job-stale")
        assert result == []

    def test_fresh_entries_survive(self) -> None:
        """Recently-created entries are not evicted."""
        ect.record_cascade_step("job-fresh", layer_name="x")
        result = ect.get_cascade_trace("job-fresh")
        assert len(result) == 1

    def test_boundary_ttl_not_evicted(self) -> None:
        """An entry exactly at the TTL boundary is not evicted."""
        ect.record_cascade_step("job-bound", layer_name="x")
        with ect._cascade_traces_lock:
            ect._cascade_meta["job-bound"]["last_update"] = time.time() - ect._TRACE_TTL_SECONDS + 1
        result = ect.get_cascade_trace("job-bound")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Hard cap on total traces
# ---------------------------------------------------------------------------


class TestHardCap:
    """When _MAX_TRACES is exceeded, oldest entries are evicted."""

    def test_eviction_when_over_hard_cap(self) -> None:
        """Entries beyond _MAX_TRACES are dropped, oldest first."""
        original_max = ect._MAX_TRACES
        original_ttl = ect._TRACE_TTL_SECONDS
        now = time.time()
        try:
            ect._MAX_TRACES = 3
            ect._TRACE_TTL_SECONDS = 999_999  # prevent TTL eviction during test
            # Insert 5 jobs with increasing timestamps (within TTL)
            for i in range(5):
                ect.record_cascade_step(f"cap-job-{i}", layer_name=f"l{i}")
                with ect._cascade_traces_lock:
                    # Spread last_update so oldest is evicted first
                    ect._cascade_meta[f"cap-job-{i}"]["last_update"] = now - (5 - i)
            # Trigger eviction via get_all_cascade_traces
            result = ect.get_all_cascade_traces()
            # Only 3 should remain (the newest)
            assert len(result) == 3
            assert "cap-job-2" in result
            assert "cap-job-3" in result
            assert "cap-job-4" in result
            assert "cap-job-0" not in result
            assert "cap-job-1" not in result
        finally:
            ect._MAX_TRACES = original_max
            ect._TRACE_TTL_SECONDS = original_ttl
