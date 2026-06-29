"""Regression test for selector_memory _save() debounce.

Pins the contract that ``record_success`` and ``record_failure`` use a
debounced ``_maybe_save()`` instead of an immediate ``_save()`` on every
call.  The old code flushed the entire JSON dict to disk (tempfile + fsync +
atomic-rename) after *every single event* — under failure storms this
produced O(N) fsyncs where N = concurrent URLs x recovery attempts.

The debounce batches up to ``_save_threshold`` (default 8) events before
flushing.  Destructive operations (``invalidate_domain``,
``force_cleanup_for``, ``_auto_cleanup``) still flush immediately because
they represent user-visible state deletions that must be durable ASAP.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.selector_memory import SelectorMemory


@pytest.fixture
def _mem(tmp_path: Path) -> SelectorMemory:
    """Return a SelectorMemory backed by a temp directory."""
    path = tmp_path / "test_memory.json"
    return SelectorMemory(storage_path=str(path))


class TestMaybeSaveDebounce:
    """``_maybe_save`` batches writes; ``_save`` always writes."""

    def test_record_success_does_not_save_on_every_call(self, _mem: SelectorMemory) -> None:
        """record_success should NOT persist on every single call.

        With the default threshold of 8, the first 7 calls should not
        trigger _save().
        """
        save_mock = MagicMock()
        with patch.object(_mem, "_save", save_mock):
            for i in range(7):
                _mem.record_success(
                    f"https://example.com/page{i}",
                    {"title": f"h{i}"},
                )
        # _save should NOT have been called — threshold (8) not reached
        assert save_mock.call_count == 0

    def test_record_success_saves_after_threshold(self, _mem: SelectorMemory) -> None:
        """record_success must flush once the pending-write threshold is hit."""
        save_mock = MagicMock()
        with patch.object(_mem, "_save", save_mock):
            for i in range(8):
                _mem.record_success(
                    f"https://example.com/page{i}",
                    {"title": f"h{i}"},
                )
        # Exactly 1 _save() call after 8 events
        assert save_mock.call_count == 1

    def test_record_failure_does_not_save_on_every_call(self, _mem: SelectorMemory) -> None:
        """record_failure should NOT persist on every single call."""
        # Pre-populate so record_failure has an entry to increment
        _mem.record_success("https://example.com/test", {"title": "h1"})
        _mem._pending_writes = 0  # reset counter from the pre-seed

        save_mock = MagicMock()
        with patch.object(_mem, "_save", save_mock):
            for i in range(7):
                _mem.record_failure("https://example.com/test")
        assert save_mock.call_count == 0

    def test_record_failure_saves_after_threshold(self, _mem: SelectorMemory) -> None:
        """record_failure must flush once the pending-write threshold is hit."""
        _mem.record_success("https://example.com/test", {"title": "h1"})
        # Reset pending_writes
        _mem._pending_writes = 0

        save_mock = MagicMock()
        with patch.object(_mem, "_save", save_mock):
            for i in range(8):
                _mem.record_failure("https://example.com/test")
        assert save_mock.call_count == 1

    def test_invalidate_domain_always_saves_immediately(self, _mem: SelectorMemory) -> None:
        """invalidate_domain is destructive — bypasses debounce and saves immediately."""
        _mem.record_success("https://example.com/test", {"title": "h1"})
        _mem._pending_writes = 0
        _mem._save()  # ensure persisted

        save_mock = MagicMock()
        with patch.object(_mem, "_save", save_mock):
            _mem.invalidate_domain("https://example.com/test")
        # Must call _save() directly, not _maybe_save()
        assert save_mock.call_count == 1

    def test_force_cleanup_for_saves_immediately(self, _mem: SelectorMemory) -> None:
        """force_cleanup_for is destructive — bypasses debounce."""
        _mem.record_success("https://very-bad.com/page", {"title": "h1"})
        # Make confidence very low by adding many failures
        for _ in range(20):
            _mem.record_failure("https://very-bad.com/page")
        _mem._save()  # force persist

        save_mock = MagicMock()
        with patch.object(_mem, "_save", save_mock):
            _mem.force_cleanup_for("https://very-bad.com/page")
        assert save_mock.call_count == 1

    def test_threshold_resets_after_flush(self, _mem: SelectorMemory) -> None:
        """After a flush, the pending-writes counter resets to 0."""
        save_mock = MagicMock()
        with patch.object(_mem, "_save", save_mock):
            for i in range(16):
                _mem.record_success(
                    f"https://example.com/reset{i}",
                    {"title": f"h{i}"},
                )
        # 16 events / threshold 8 = 2 flushes
        assert save_mock.call_count == 2

    def test_mixed_success_failure_accumulates_toward_threshold(self, _mem: SelectorMemory) -> None:
        """Success + failure events share the same pending-write counter."""
        _mem.record_success("https://example.com/a", {"title": "h1"})
        _mem._pending_writes = 0

        save_mock = MagicMock()
        with patch.object(_mem, "_save", save_mock):
            _mem.record_success("https://example.com/a", {"title": "h1"})
            _mem.record_failure("https://example.com/a")
            _mem.record_failure("https://example.com/a")
            # 3 events — below threshold of 8
        assert save_mock.call_count == 0


class TestPendingWritesThreadSafety:
    """Verify _pending_writes increment is safe under the self._lock."""

    def test_concurrent_increments_no_lost_updates(self, _mem: SelectorMemory) -> None:
        """_pending_writes += 1 inside _maybe_save must not lose increments.

        With a threshold of 50 and 160 total events, the counter should
        end at ``160 mod 50 = 10`` — that proves all events were counted
        (any loss would tip it below 10).
        """
        _mem._save_threshold = 50  # prevent flush during test
        _mem.record_success("https://concurrent.test/p", {"title": "h"})

        n_threads = 16
        n_per_thread = 10
        barrier = threading.Barrier(n_threads)

        def _worker() -> None:
            barrier.wait()
            for _ in range(n_per_thread):
                _mem.record_failure("https://concurrent.test/p")

        threads = [threading.Thread(target=_worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 161 events total (1 init success + 160 failures);
        # threshold 50 → 3 flushes + 11 remaining.
        # If _pending_writes were below 11, that means events were lost.
        assert _mem._pending_writes == 11, (
            f"expected 11 remainder (161 events, threshold 50), got {_mem._pending_writes} — possible lost increments"
        )
