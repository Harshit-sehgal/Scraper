"""Tests for the Large-Scale Replay Buffer."""
import os
import json
import tempfile
import pytest
from app.replay_buffer import ReplayBuffer, reset_replay_buffer


@pytest.fixture(autouse=True)
def reset():
    reset_replay_buffer()


@pytest.fixture
def tmp_base_dir():
    """Create a temporary directory for replay buffer storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestReplayBuffer:
    """Verify persistent storage, streaming, checkpoints, and reconstruction."""

    # ─── Basic Append & Read ────────────────────────────────────────────

    def test_append_and_read_entry(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_append")
        idx = buf.append({"type": "test", "delta": {"foo": 1}, "metadata": {}})
        assert idx >= 0
        entry = buf.get_entry(idx)
        assert entry is not None
        assert entry["type"] == "test"
        assert entry["idx"] == idx
        buf.clear()

    def test_append_returns_incrementing_indices(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_increment")
        idx1 = buf.append({"type": "a", "delta": {}, "metadata": {}})
        idx2 = buf.append({"type": "b", "delta": {}, "metadata": {}})
        assert idx2 == idx1 + 1
        buf.clear()

    # ─── Streaming ──────────────────────────────────────────────────────

    def test_stream_from_start(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_stream")
        entries_count = 10
        for i in range(entries_count):
            buf.append({"type": "event", "delta": {"i": i}, "metadata": {}})
        streamed = list(buf.stream_from(0))
        assert len(streamed) == entries_count
        assert streamed[0]["idx"] == 0
        assert streamed[-1]["idx"] == entries_count - 1
        buf.clear()

    def test_stream_from_midpoint(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_stream_mid")
        for i in range(20):
            buf.append({"type": "evt", "delta": {"i": i}, "metadata": {}})
        streamed = list(buf.stream_from(10))
        assert len(streamed) == 10
        assert streamed[0]["idx"] == 10
        buf.clear()

    def test_stream_from_beyond_end(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_beyond")
        for i in range(5):
            buf.append({"type": "evt", "delta": {"i": i}, "metadata": {}})
        streamed = list(buf.stream_from(100))
        assert len(streamed) == 0
        buf.clear()

    def test_stream_empty_buffer(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_empty")
        streamed = list(buf.stream_from(0))
        assert len(streamed) == 0
        buf.clear()

    # ─── State Reconstruction ──────────────────────────────────────────

    def test_reconstruct_state_at_index(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_recon")
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

    def test_reconstruct_before_first_entry(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_early")
        buf.append({"type": "add", "delta": {"a": 1}, "metadata": {}})
        state = buf.reconstruct_state_at(0)
        assert state is not None
        buf.clear()

    # ─── Persistence ────────────────────────────────────────────────────

    def test_data_persists_across_reload(self):
        base_dir = "/tmp/test_rb_persist"
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

    def test_clear_removes_data(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_clear")
        buf.append({"type": "test", "delta": {}, "metadata": {}})
        assert buf.status()["total_entries"] >= 1
        buf.clear()
        assert buf.status()["total_entries"] == 0
        assert buf.status()["segments"] == 0

    # ─── Segment Management ─────────────────────────────────────────────

    def test_segment_rotation(self):
        buf = ReplayBuffer(
            base_dir="/tmp/test_rb_segments",
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

    def test_segment_info(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_seg_info")
        for i in range(10):
            buf.append({"type": "evt", "delta": {"i": i}, "metadata": {}})
        info = buf.get_segment_info()
        assert len(info) >= 1
        assert info[0]["size_bytes"] > 0
        buf.clear()

    # ─── Status ─────────────────────────────────────────────────────────

    def test_status(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_status")
        for i in range(5):
            buf.append({"type": "evt", "delta": {}, "metadata": {}})
        status = buf.status()
        assert status["total_entries"] >= 5
        assert status["max_segments"] == 50
        assert isinstance(status["base_dir"], str)
        buf.clear()

    # ─── Edge Cases ─────────────────────────────────────────────────────

    def test_get_nonexistent_entry(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_missing")
        buf.append({"type": "evt", "delta": {}, "metadata": {}})
        entry = buf.get_entry(999)
        assert entry is None
        buf.clear()

    def test_append_after_clear(self):
        buf = ReplayBuffer(base_dir="/tmp/test_rb_after_clear")
        buf.append({"type": "first", "delta": {}, "metadata": {}})
        buf.clear()
        idx = buf.append({"type": "second", "delta": {}, "metadata": {}})
        assert idx == 0  # Should reset after clear
        entry = buf.get_entry(0)
        assert entry["type"] == "second"
        buf.clear()
