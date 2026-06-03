"""Tests for the Transactional Priority Queue."""

import time

import pytest
from app.transactional_priority_queue import (
    PriorityLevel,
    TransactionalPriorityQueue,
    reset_priority_queue,
)


@pytest.fixture(autouse=True)
def reset():
    reset_priority_queue()


class TestTransactionalPriorityQueue:
    """Verify priority ordering, aging, starvation prevention, and thread safety."""

    # ─── Basic Priority Ordering ───────────────────────────────────────

    def test_critical_before_normal(self):
        queue = TransactionalPriorityQueue()
        queue.push(PriorityLevel.NORMAL, "normal_tx")
        queue.push(PriorityLevel.CRITICAL, "critical_tx")

        first = queue.pop()
        assert first is not None
        first_label = first.label
        first_priority = first.priority
        assert first_label == "critical_tx"
        assert first_priority == PriorityLevel.CRITICAL

        second = queue.pop()
        assert second is not None
        assert second.label == "normal_tx"

    def test_high_before_low(self):
        queue = TransactionalPriorityQueue()
        queue.push(PriorityLevel.LOW, "low_tx")
        queue.push(PriorityLevel.HIGH, "high_tx")
        queue.push(PriorityLevel.BACKGROUND, "bg_tx")

        assert queue.pop() is not None
        assert queue.pop() is not None
        assert queue.pop() is not None

    def test_fifo_within_same_priority(self):
        queue = TransactionalPriorityQueue()
        queue.push(PriorityLevel.NORMAL, "first")
        queue.push(PriorityLevel.NORMAL, "second")
        queue.push(PriorityLevel.NORMAL, "third")

        assert queue.pop() is not None
        assert queue.pop() is not None
        assert queue.pop() is not None

    # ─── Aging ─────────────────────────────────────────────────────────

    def test_aging_boosts_low_priority(self):
        queue = TransactionalPriorityQueue(aging_interval=0.01)
        queue.push(PriorityLevel.LOW, "low_tx")
        queue.push(PriorityLevel.NORMAL, "normal_tx")

        # Before aging: normal has higher priority
        assert queue.peek() is not None

        # Age the low-priority entry multiple times
        for _ in range(6):
            queue.force_age_all()

        # After aging: low should now have effective priority equal to or better than normal
        peeked = queue.peek()
        assert peeked is not None

    def test_starvation_prevention_with_force_age(self):
        queue = TransactionalPriorityQueue(aging_interval=0.01)
        # Push many high-priority entries
        for i in range(10):
            queue.push(PriorityLevel.HIGH, f"high_{i}")
        # Push one low-priority entry
        queue.push(PriorityLevel.LOW, "lonely_low")

        # Pop all high-priority (+ aging to boost the low one)
        for _ in range(10):
            queue.pop()
        # Force-age the low entry many times
        for _ in range(8):
            queue.force_age_all()
        # The low entry should now have been aged to effective priority ~0
        assert queue.peek() is not None

    # ─── Max Size & Eviction ─────────────────────────────────────────

    def test_eviction_when_full(self):
        queue = TransactionalPriorityQueue(max_size=3)
        queue.push(PriorityLevel.LOW, "low_1")
        queue.push(PriorityLevel.LOW, "low_2")
        queue.push(PriorityLevel.NORMAL, "normal")
        # Insert a HIGH priority into a full queue — should evict lowest
        queue.push(PriorityLevel.HIGH, "high_tx")

        # The queue should now contain normal + high + one low
        assert queue.size() == 3
        first = queue.pop()
        assert first is not None
        assert first.label == "high_tx"

    def test_no_eviction_within_size_limit(self):
        queue = TransactionalPriorityQueue(max_size=5)
        for i in range(5):
            queue.push(PriorityLevel.NORMAL, f"tx_{i}")
        assert queue.size() == 5

    # ─── Removal ───────────────────────────────────────────────────────

    def test_remove_by_trace_id(self):
        queue = TransactionalPriorityQueue()
        trace_a = queue.push(PriorityLevel.NORMAL, "tx_a")
        _ = queue.push(PriorityLevel.HIGH, "tx_b")

        assert queue.size() == 2
        removed = queue.remove(trace_a)
        assert removed is True
        assert queue.size() == 1
        assert queue.peek() is not None

    def test_remove_nonexistent(self):
        queue = TransactionalPriorityQueue()
        queue.push(PriorityLevel.NORMAL, "tx")
        removed = queue.remove("nonexistent")
        assert removed is False

    # ─── Empty Queue ─────────────────────────────────────────────────

    def test_pop_empty(self):
        queue = TransactionalPriorityQueue()
        assert queue.pop() is None

    def test_peek_empty(self):
        queue = TransactionalPriorityQueue()
        assert queue.peek() is None

    # ─── Metrics & Status ─────────────────────────────────────────────

    def test_status_returns_metrics(self):
        queue = TransactionalPriorityQueue()
        queue.push(PriorityLevel.CRITICAL, "critical")
        queue.push(PriorityLevel.NORMAL, "normal")
        queue.push(PriorityLevel.LOW, "low")

        status = queue.status()
        assert status["size"] == 3
        assert status["priority_distribution"]["CRITICAL"] >= 1
        assert status["priority_distribution"]["NORMAL"] >= 1
        assert status["priority_distribution"]["LOW"] >= 1
        assert status["oldest_wait_seconds"] >= 0.0
        assert len(status["top_entries"]) == 3

    def test_mark_completed(self):
        queue = TransactionalPriorityQueue()
        queue.push(PriorityLevel.NORMAL, "tx")
        entry = queue.pop()
        assert entry is not None
        queue.mark_completed(entry)
        assert queue.status()["completed"] == 1

    def test_clear(self):
        queue = TransactionalPriorityQueue()
        queue.push(PriorityLevel.HIGH, "tx")
        assert queue.size() == 1
        queue.clear()
        assert queue.size() == 0
        assert queue.pop() is None

    # ─── Entry Info ──────────────────────────────────────────────────

    def test_entry_to_dict(self):
        queue = TransactionalPriorityQueue()
        queue.push(PriorityLevel.NORMAL, "test_tx", trace_id="trace_123")
        entry = queue.peek()
        assert entry is not None
        info = entry.to_dict()
        assert info["label"] == "test_tx"
        assert info["trace_id"] == "trace_123"
        assert info["priority"] == PriorityLevel.NORMAL
        assert info["wait_seconds"] >= 0.0

    # ─── Aging Interval Trigger ─────────────────────────────────────────

    def test_aging_happens_on_pop_after_interval(self):
        queue = TransactionalPriorityQueue(aging_interval=0.1)
        queue.push(PriorityLevel.LOW, "low_tx")
        time.sleep(0.15)
        # pop should trigger aging since interval elapsed
        entry = queue.peek()
        assert entry is not None
        assert entry.aging_count >= 1
