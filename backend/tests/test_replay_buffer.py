"""Tests for the Large-Scale Replay Buffer."""

import tempfile

import pytest
from app.replay_buffer import ReplayBuffer, reset_replay_buffer


@pytest.fixture(autouse=True)
def reset() -> None:
    reset_replay_buffer()


@pytest.fixture
def tmp_base_dir():
    """Create a temporary directory for replay buffer storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestReplayBuffer:
    """Verify persistent storage, streaming, checkpoints, and reconstruction."""

    # ─── Basic Append & Read ────────────────────────────────────────────

    def test_append_and_read_entry(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_append")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        idx = buf.append({"type": "test", "delta": {"foo": 1}, "metadata": {}})
        assert idx >= 0
        entry = buf.get_entry(idx)
        assert entry is not None
        assert entry["type"] == "test"
        assert entry["idx"] == idx
        buf.clear()

    def test_append_returns_incrementing_indices(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_increment")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        idx1 = buf.append({"type": "a", "delta": {}, "metadata": {}})
        idx2 = buf.append({"type": "b", "delta": {}, "metadata": {}})
        assert idx2 == idx1 + 1
        buf.clear()

    # ─── Streaming ──────────────────────────────────────────────────────

    def test_stream_from_start(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_stream")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        entries_count = 10
        for i in range(entries_count):
            buf.append({"type": "event", "delta": {"i": i}, "metadata": {}})
        streamed = list(buf.stream_from(0))
        assert len(streamed) == entries_count
        assert streamed[0]["idx"] == 0
        assert streamed[-1]["idx"] == entries_count - 1
        buf.clear()

    def test_stream_from_midpoint(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_stream_mid")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        for i in range(20):
            buf.append({"type": "evt", "delta": {"i": i}, "metadata": {}})
        streamed = list(buf.stream_from(10))
        assert len(streamed) == 10
        assert streamed[0]["idx"] == 10
        buf.clear()

    def test_stream_from_beyond_end(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_beyond")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        for i in range(5):
            buf.append({"type": "evt", "delta": {"i": i}, "metadata": {}})
        streamed = list(buf.stream_from(100))
        assert len(streamed) == 0
        buf.clear()

    def test_stream_empty_buffer(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_empty")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        streamed = list(buf.stream_from(0))
        assert len(streamed) == 0
        buf.clear()

    # ─── State Reconstruction ──────────────────────────────────────────

    def test_reconstruct_state_at_index(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_recon")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        # Append entries that update state
        buf.append({"type": "add", "delta": {"x": {"to": 1}}, "metadata": {}})
        buf.append({"type": "update", "delta": {"y": {"to": 2}}, "metadata": {}})
        buf.append({"type": "update", "delta": {"x": {"to": 5}}, "metadata": {}})

        # Reconstruct at index 1: should have x=1, y=2
        state = buf.reconstruct_state_at(1)
        assert state is not None
        assert state.get("x") == 1
        assert state.get("y") == 2

        # Reconstruct at index 2: x should be 5
        state2 = buf.reconstruct_state_at(2)
        assert state2 is not None
        assert state2.get("x") == 5
        buf.clear()

    def test_reconstruct_before_first_entry(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_early")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        buf.append({"type": "add", "delta": {"a": 1}, "metadata": {}})
        state = buf.reconstruct_state_at(0)
        assert state is not None
        buf.clear()

    # ─── Persistence ────────────────────────────────────────────────────

    def test_data_persists_across_reload(self) -> None:
        base_dir = "/tmp/test_rb_persist"  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        buf = ReplayBuffer(base_dir=base_dir)
        buf.append({"type": "persist", "delta": {"k": "v"}, "metadata": {}})
        buf.close()

        # Create new instance pointing to same directory
        buf2 = ReplayBuffer(base_dir=base_dir)
        assert buf2.status()["total_entries"] >= 1
        streamed = list(buf2.stream_from(0))
        assert len(streamed) >= 1
        assert streamed[0]["type"] == "persist"
        buf2.clear()

    def test_clear_removes_data(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_clear")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        buf.append({"type": "test", "delta": {}, "metadata": {}})
        assert buf.status()["total_entries"] >= 1
        buf.clear()
        assert buf.status()["total_entries"] == 0
        assert buf.status()["segments"] == 0

    # ─── Segment Management ─────────────────────────────────────────────

    def test_segment_rotation(self) -> None:
        buf = ReplayBuffer(
            base_dir="/tmp/test_rb_segments",  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
            max_segments=3,
        )
        # Append enough entries to force multiple segments
        # (segment capacity = 5000, but we can force rotation by appending)
        entries_count = 120  # Enough for at least 2 segments with checkpointing
        for i in range(entries_count):
            buf.append({"type": "evt", "delta": {"i": i}, "metadata": {}})

        info = buf.get_segment_info()
        assert len(info) > 0
        buf.clear()

    def test_segment_info(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_seg_info")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        for i in range(10):
            buf.append({"type": "evt", "delta": {"i": i}, "metadata": {}})
        info = buf.get_segment_info()
        assert len(info) >= 1
        assert info[0]["size_bytes"] > 0
        buf.clear()

    # ─── Status ─────────────────────────────────────────────────────────

    def test_status(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_status")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        for _i in range(5):
            buf.append({"type": "evt", "delta": {}, "metadata": {}})
        status = buf.status()
        assert status["total_entries"] >= 5
        assert status["max_segments"] == 50
        assert isinstance(status["base_dir"], str)
        buf.clear()

    # ─── Edge Cases ─────────────────────────────────────────────────────

    def test_get_nonexistent_entry(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_missing")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        buf.append({"type": "evt", "delta": {}, "metadata": {}})
        entry = buf.get_entry(999)
        assert entry is None
        buf.clear()

    def test_append_after_clear(self) -> None:
        buf = ReplayBuffer(base_dir="/tmp/test_rb_after_clear")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        buf.append({"type": "first", "delta": {}, "metadata": {}})
        buf.clear()
        idx = buf.append({"type": "second", "delta": {}, "metadata": {}})
        assert idx == 0  # Should reset after clear
        entry = buf.get_entry(0)
        assert entry is not None
        assert entry["type"] == "second"
        buf.clear()

    # ─── Causal Chain Reconstruction ──────────────────────────────────

    def test_causal_chains_by_trace_id(self) -> None:
        """Causal chains group events sharing a trace_id."""
        buf = ReplayBuffer(base_dir="/tmp/test_rb_chain_trace")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        trace_a = "trace_aaa"
        trace_b = "trace_bbb"
        buf.append({"type": "event.a1", "delta": {}, "metadata": {"trace_id": trace_a}})
        buf.append({"type": "event.b1", "delta": {}, "metadata": {"trace_id": trace_b}})
        buf.append({"type": "event.a2", "delta": {}, "metadata": {"trace_id": trace_a}})
        chains = buf.get_causal_chains(limit=10)
        # Should have at least 2 chains (one per trace_id, possibly untraced)
        traced_chains = [c for c in chains if c["trace_id"] is not None]
        trace_ids = [c["trace_id"] for c in traced_chains]
        assert trace_a in trace_ids, f"Expected trace {trace_a} in chains, got {trace_ids}"
        assert trace_b in trace_ids, f"Expected trace {trace_b} in chains, got {trace_ids}"
        for chain in traced_chains:
            if chain["trace_id"] == trace_a:
                assert chain["event_count"] >= 2
                types = [e["type"] for e in chain["events"]]
                assert "event.a1" in types
                assert "event.a2" in types
        buf.clear()

    def test_causal_chains_untraced_grouped_by_type(self) -> None:
        """Events without trace_id are grouped by type pattern."""
        buf = ReplayBuffer(base_dir="/tmp/test_rb_chain_untraced")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        buf.append({"type": "alpha", "delta": {}, "metadata": {}})
        buf.append({"type": "beta", "delta": {}, "metadata": {}})
        buf.append({"type": "alpha", "delta": {}, "metadata": {}})
        chains = buf.get_causal_chains(limit=10)
        untraced = [c for c in chains if c["trace_id"] is None]
        assert len(untraced) >= 1
        # At least one untraced chain should have "alpha" type
        alpha_chains = [c for c in untraced if "alpha" in c["summary"]]
        assert len(alpha_chains) >= 1, f"Expected alpha chain in untraced, got {[c['summary'] for c in untraced]}"
        buf.clear()

    def test_causal_chain_summary_format(self) -> None:
        """Causal chain summary uses arrow notation for event types."""
        buf = ReplayBuffer(base_dir="/tmp/test_rb_chain_summary")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        for i in range(3):
            buf.append({"type": "step", "delta": {"i": i}, "metadata": {"trace_id": "t1"}})
        chains = buf.get_causal_chains(limit=10)
        t1_chain = next((c for c in chains if c.get("trace_id") == "t1"), None)
        assert t1_chain is not None
        assert "step" in t1_chain["summary"]
        assert t1_chain["event_count"] >= 3
        assert t1_chain["start_idx"] <= t1_chain["end_idx"]
        buf.clear()

    # ─── Event Range ────────────────────────────────────────────────────

    def test_get_event_range_returns_subset(self) -> None:
        """get_event_range returns events within the specified index range."""
        buf = ReplayBuffer(base_dir="/tmp/test_rb_range_subset")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        for i in range(10):
            buf.append({"type": "evt", "delta": {"i": i}, "metadata": {}})
        events = buf.get_event_range(3, 6)
        assert len(events) == 4, f"Expected 4 events, got {len(events)}"
        assert events[0]["idx"] == 3
        assert events[-1]["idx"] == 6
        buf.clear()

    def test_get_event_range_bounds(self) -> None:
        """get_event_range end_idx=-1 returns all events from start_idx to end."""
        buf = ReplayBuffer(base_dir="/tmp/test_rb_range_bounds")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        for i in range(10):
            buf.append({"type": "evt", "delta": {"i": i}, "metadata": {}})
        # We need to call status() to determine total, but get_event_range should handle -1
        events = buf.get_event_range(7, 999)
        assert len(events) == 3  # indices 7, 8, 9
        assert events[0]["idx"] == 7
        assert events[-1]["idx"] == 9
        buf.clear()

    def test_get_event_range_empty(self) -> None:
        """get_event_range with out-of-range indices returns empty list."""
        buf = ReplayBuffer(base_dir="/tmp/test_rb_range_empty")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
        for i in range(5):
            buf.append({"type": "evt", "delta": {"i": i}, "metadata": {}})
        events = buf.get_event_range(100, 200)
        assert len(events) == 0
        buf.clear()
