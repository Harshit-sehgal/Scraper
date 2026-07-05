from __future__ import annotations

import time

from app.transactional_priority_queue import (
    PriorityLevel,
    PriorityQueueEntry,
    TransactionalPriorityQueue,
)


class TestTransactionalPriorityQueue:
    def test_push_pop_returns_highest_priority(self) -> None:
        q = TransactionalPriorityQueue(max_size=100)
        q.push(PriorityLevel.LOW, "low task", trace_id="low1")
        q.push(PriorityLevel.HIGH, "high task", trace_id="high1")
        q.push(PriorityLevel.CRITICAL, "critical task", trace_id="crit1")

        first = q.pop()
        assert first is not None
        assert first.trace_id == "crit1"
        second = q.pop()
        assert second is not None
        assert second.trace_id == "high1"
        third = q.pop()
        assert third is not None
        assert third.trace_id == "low1"

    def test_empty_queue_returns_none(self) -> None:
        q = TransactionalPriorityQueue()
        assert q.pop() is None

    def test_peek_returns_without_removing(self) -> None:
        q = TransactionalPriorityQueue()
        q.push(PriorityLevel.HIGH, "task1", trace_id="t1")
        seen = q.peek()
        assert seen is not None
        assert seen.trace_id == "t1"
        assert q.size() == 1

    def test_remove_by_trace_id(self) -> None:
        q = TransactionalPriorityQueue()
        q.push(PriorityLevel.NORMAL, "task1", trace_id="t1")
        q.push(PriorityLevel.NORMAL, "task2", trace_id="t2")
        assert q.size() == 2
        assert q.remove("t1") is True
        assert q.size() == 1
        entry = q.pop()
        assert entry is not None
        assert entry.trace_id == "t2"

    def test_aging_prevents_starvation(self, monkeypatch) -> None:
        q = TransactionalPriorityQueue(max_size=100, aging_interval=0.01)
        q.push(PriorityLevel.BACKGROUND, "bg1", trace_id="bg1")
        q.push(PriorityLevel.CRITICAL, "crit1", trace_id="crit1")
        q.push(PriorityLevel.BACKGROUND, "bg2", trace_id="bg2")
        # Deterministic clock advance instead of time.sleep(0.05). The
        # aging_interval is 0.01s — the slack is plenty, but skip the
        # real sleep for speed and to be robust to CI load spikes.
        original_time = time.time
        monkeypatch.setattr("time.time", lambda: original_time() + 0.05)
        q._maybe_age()
        q._maybe_age()
        q._maybe_age()
        first = q.pop()
        assert first is not None
        assert first.trace_id == "crit1"
        second = q.pop()
        assert second is not None

    def test_max_size_eviction(self) -> None:
        q = TransactionalPriorityQueue(max_size=3)
        q.push(PriorityLevel.HIGH, "a", trace_id="a")
        q.push(PriorityLevel.HIGH, "b", trace_id="b")
        q.push(PriorityLevel.HIGH, "c", trace_id="c")
        q.push(PriorityLevel.NORMAL, "d", trace_id="d")
        assert q.size() <= 3

    def test_priority_entry_effective_priority(self) -> None:
        e = PriorityQueueEntry(PriorityLevel.BACKGROUND, "test", "t1")
        assert e.effective_priority == 4.0
        e.age()
        assert e.effective_priority == 3.5
