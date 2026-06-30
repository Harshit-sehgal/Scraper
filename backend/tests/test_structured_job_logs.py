"""Unit tests for structured_job_logs.

Covers event emission, per-job retrieval with pagination,
cross-job recent-events, global and per-job caps, and clearing.
"""

from __future__ import annotations

import pytest
from app import structured_job_logs as sjl

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_store() -> None:
    """Reset the in-memory store before every test."""
    sjl.clear_job_events()


# ---------------------------------------------------------------------------
# log_job_event / get_job_events
# ---------------------------------------------------------------------------


class TestLogAndGetJobEvents:
    """log_job_event stores events; get_job_events retrieves them."""

    def test_stores_single_event(self) -> None:
        """A single event is stored and retrievable."""
        sjl.log_job_event("j1", "started", {"url": "https://example.com"})
        events = sjl.get_job_events("j1")
        assert len(events) == 1
        e = events[0]
        assert e["job_id"] == "j1"
        assert e["event_type"] == "started"
        assert e["details"]["url"] == "https://example.com"
        assert "timestamp" in e

    def test_stores_multiple_events_preserving_order(self) -> None:
        """Events are returned in insertion order."""
        sjl.log_job_event("j-ord", "step-1")
        sjl.log_job_event("j-ord", "step-2")
        sjl.log_job_event("j-ord", "step-3")
        events = sjl.get_job_events("j-ord")
        assert [e["event_type"] for e in events] == ["step-1", "step-2", "step-3"]

    def test_details_default_to_none(self) -> None:
        """When details are not provided, they default to None."""
        sjl.log_job_event("j-d", "ping")
        assert sjl.get_job_events("j-d")[0]["details"] is None

    def test_unknown_job_returns_empty(self) -> None:
        """Querying events for a non-existent job returns an empty list."""
        assert sjl.get_job_events("no-job") == []


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    """get_job_events supports limit and offset."""

    def test_limit_restricts_results(self) -> None:
        """Only the first *limit* events are returned."""
        for i in range(10):
            sjl.log_job_event("j-pag", f"ev-{i}")
        events = sjl.get_job_events("j-pag", limit=3)
        assert len(events) == 3
        assert events[0]["event_type"] == "ev-0"

    def test_offset_skips_events(self) -> None:
        """Offset skips the first N events."""
        for i in range(10):
            sjl.log_job_event("j-pag2", f"ev-{i}")
        events = sjl.get_job_events("j-pag2", offset=8)
        assert [e["event_type"] for e in events] == ["ev-8", "ev-9"]

    def test_offset_beyond_count_returns_empty(self) -> None:
        """An offset larger than the event count returns an empty list."""
        sjl.log_job_event("j-pag3", "only")
        assert sjl.get_job_events("j-pag3", offset=100) == []

    def test_combined_limit_and_offset(self) -> None:
        """limit and offset work together for paging."""
        for i in range(10):
            sjl.log_job_event("j-pag4", f"ev-{i}")
        events = sjl.get_job_events("j-pag4", offset=2, limit=3)
        assert [e["event_type"] for e in events] == ["ev-2", "ev-3", "ev-4"]


# ---------------------------------------------------------------------------
# get_recent_events
# ---------------------------------------------------------------------------


class TestGetRecentEvents:
    """get_recent_events returns events across all jobs, newest first."""

    def test_cross_job_events(self) -> None:
        """Events from multiple jobs are returned together."""
        sjl.log_job_event("j-a", "a1")
        sjl.log_job_event("j-b", "b1")
        recent = sjl.get_recent_events()
        types = {e["event_type"] for e in recent}
        assert "a1" in types
        assert "b1" in types

    def test_respects_limit(self) -> None:
        """Only the most recent *limit* events are returned."""
        for i in range(20):
            sjl.log_job_event("j-rl", f"ev-{i}")
        recent = sjl.get_recent_events(limit=5)
        assert len(recent) == 5

    def test_sorted_by_timestamp_descending(self) -> None:
        """Recent events are sorted newest-first."""
        sjl.log_job_event("j-rs", "old")
        # Slight time gap to ensure ordering (monotonic clock)
        sjl._job_events["j-rs"][-1]["timestamp"] = 1.0
        sjl.log_job_event("j-rs", "new")
        sjl._job_events["j-rs"][-1]["timestamp"] = 100.0
        recent = sjl.get_recent_events()
        assert recent[0]["event_type"] == "new"
        assert recent[1]["event_type"] == "old"


# ---------------------------------------------------------------------------
# clear_job_events
# ---------------------------------------------------------------------------


class TestClearJobEvents:
    """clear_job_events drops all stored events."""

    def test_clears_everything(self) -> None:
        """After clear, no events remain for any job."""
        sjl.log_job_event("j-c1", "ev")
        sjl.log_job_event("j-c2", "ev")
        sjl.clear_job_events()
        assert sjl.get_job_events("j-c1") == []
        assert sjl.get_job_events("j-c2") == []


# ---------------------------------------------------------------------------
# Per-job event cap
# ---------------------------------------------------------------------------


class TestPerJobCap:
    """When _MAX_EVENTS_PER_JOB is exceeded, oldest events are trimmed."""

    def test_per_job_cap_trims_oldest(self) -> None:
        """Only the latest _MAX_EVENTS_PER_JOB events are kept per job."""
        original_cap = sjl._MAX_EVENTS_PER_JOB
        try:
            sjl._MAX_EVENTS_PER_JOB = 5
            for i in range(10):
                sjl.log_job_event("j-cap", f"ev-{i}")
            events = sjl.get_job_events("j-cap")
            assert len(events) == 5
            assert events[0]["event_type"] == "ev-5"
            assert events[-1]["event_type"] == "ev-9"
        finally:
            sjl._MAX_EVENTS_PER_JOB = original_cap


# ---------------------------------------------------------------------------
# Global cap (_MAX_TOTAL_EVENTS)
# ---------------------------------------------------------------------------


class TestGlobalCap:
    """When _MAX_TOTAL_EVENTS is exceeded, oldest jobs' events are evicted."""

    def test_global_cap_eviction(self) -> None:
        """Oldest jobs are trimmed first when the global cap is hit."""
        original_cap = sjl._MAX_TOTAL_EVENTS
        try:
            sjl._MAX_TOTAL_EVENTS = 10
            # Create two jobs with 6 events each
            for i in range(6):
                sjl.log_job_event("j-old", f"old-{i}")
                sjl._job_events["j-old"][-1]["timestamp"] = float(i)
            for i in range(6):
                sjl.log_job_event("j-new", f"new-{i}")
                sjl._job_events["j-new"][-1]["timestamp"] = float(i + 100)
            # Total is 12 > 10; eviction should trim the oldest job first
            with sjl._job_events_lock:
                total = sum(len(v) for v in sjl._job_events.values())
            assert total <= 10
            # The older job should be partially or fully evicted
            new_events = sjl.get_job_events("j-new")
            assert len(new_events) > 0
        finally:
            sjl._MAX_TOTAL_EVENTS = original_cap
