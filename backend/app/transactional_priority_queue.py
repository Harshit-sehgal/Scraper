"""Transactional Priority Queue — prevents transaction starvation under load.

Priority levels:
- CRITICAL (0): Governance, immune responses, health checks — always serviced first
- HIGH    (1): Field evolution, propagation, macro state — high-value cognitive work
- NORMAL  (2): Regular transactions (allocation, capture) — standard priority
- LOW     (3): Relaxation, pruning, decay — background maintenance
- BACKGROUND (4): Telemetry, logging, analytics — best-effort only

Priority aging: lower-priority entries get a boost based on wait time,
preventing starvation of any priority class during sustained high load.

Phase 47: Distributed Resilience — preventing transaction starvation.
"""

import time
import heapq
import logging
import threading
from typing import Any, List, Optional
from enum import IntEnum

logger = logging.getLogger(__name__)


class PriorityLevel(IntEnum):
    """Priority levels for queued transactions. Lower number = higher priority."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


class PriorityQueueEntry:
    """An entry in the transactional priority queue."""

    __slots__ = ("priority", "timestamp", "aging_count", "label", "trace_id",
                 "entry_id", "payload", "_tie_breaker")

    def __init__(
        self,
        priority: PriorityLevel,
        label: str,
        trace_id: str,
        payload: Optional[Any] = None,
        entry_id: Optional[int] = None,
    ):
        self.priority = priority
        self.timestamp = time.time()
        self.aging_count = 0
        self.label = label
        self.trace_id = trace_id
        self.payload = payload

    @property
    def effective_priority(self) -> float:
        """Compute effective priority with aging boost.

        Each aging cycle reduces the numeric priority by 0.5 (making it
        effectively higher priority). After 6 aging cycles, a BACKGROUND
        entry becomes equivalent to NORMAL. After 12, it reaches HIGH.
        This ensures no transaction is starved indefinitely.
        """
        return max(0.0, self.priority - self.aging_count * 0.5)

    def age(self):
        """Apply one aging cycle."""
        self.aging_count += 1

    def __lt__(self, other: "PriorityQueueEntry") -> bool:
        """Heap ordering: lower effective_priority = higher priority."""
        if abs(self.effective_priority - other.effective_priority) < 0.001:
            # Tie-break by arrival time (FIFO for same priority)
            return self.timestamp < other.timestamp
        return self.effective_priority < other.effective_priority

    def to_dict(self) -> dict:
        return {
            "priority": int(self.priority),
            "effective_priority": round(self.effective_priority, 2),
            "aging_count": self.aging_count,
            "label": self.label,
            "trace_id": self.trace_id,
            "wait_seconds": round(time.time() - self.timestamp, 2),
            "timestamp": self.timestamp,
        }


class TransactionalPriorityQueue:
    """Priority queue for transactions with aging to prevent starvation.

    Thread-safe: uses a reentrant lock for all queue operations.
    Integrates with the existing transaction system via callback execution.

    Usage:
        queue = TransactionalPriorityQueue()
        queue.push(PriorityLevel.HIGH, label="field_evolution", trace_id="abc123")
        entry = queue.pop()  # Returns highest-priority entry
        # Execute the transaction using the entry's trace_id
        queue.mark_completed(entry)
    """

    def __init__(self, max_size: int = 1000, aging_interval: float = 5.0):
        self._heap: List[PriorityQueueEntry] = []
        self._lock = threading.RLock()
        self._max_size = max_size
        self._aging_interval = aging_interval
        self._last_aging = time.time()
        self._counter = 0
        self._next_entry_id = 0

        # Tracking
        self._completed_count = 0
        self._aged_count = 0
        self._starvation_warnings = 0
        self._priority_counts = {p: 0 for p in PriorityLevel}

    def push(
        self,
        priority: PriorityLevel,
        label: str,
        trace_id: Optional[str] = None,
        payload: Optional[Any] = None,
    ) -> str:
        """Push a new transaction onto the priority queue.

        Args:
            priority: Priority level for this transaction
            label: Human-readable label for the transaction
            trace_id: Optional trace ID (generated if not provided)
            payload: Optional payload data for the transaction

        Returns:
            trace_id of the queued entry
        """
        import uuid
        tid = trace_id or str(uuid.uuid4())[:8]

        entry = PriorityQueueEntry(
            priority=priority,
            label=label,
            trace_id=tid,
            payload=payload,
        )

        with self._lock:
            if len(self._heap) >= self._max_size:
                # Evict lowest-priority entry (last in heap after aging)
                if self._heap:
                    lowest = heapq.nlargest(1, self._heap)[0]
                    if lowest.effective_priority > entry.effective_priority:
                        # Remove lowest by filtering (heapq cannot delete arbitrary)
                        self._heap.remove(lowest)
                        heapq.heapify(self._heap)
                        logger.warning(
                            "PRIORITY QUEUE EVICTED: label=%s priority=%.2f to make room for %s",
                            lowest.label, lowest.effective_priority, label,
                        )
                    else:
                        logger.warning("PRIORITY QUEUE FULL: dropping entry %s", label)
                        return tid
                else:
                    return tid

            heapq.heappush(self._heap, entry)
            self._counter += 1
            self._priority_counts[priority] = self._priority_counts.get(priority, 0) + 1

        return tid

    def pop(self) -> Optional[PriorityQueueEntry]:
        """Pop the highest-priority entry from the queue.

        Applies aging before popping if the aging interval has elapsed.
        Returns None if the queue is empty.
        """
        self._maybe_age()

        with self._lock:
            if not self._heap:
                return None
            entry = heapq.heappop(self._heap)
            self._priority_counts[entry.priority] = max(
                0, self._priority_counts.get(entry.priority, 0) - 1
            )
            return entry

    def peek(self) -> Optional[PriorityQueueEntry]:
        """Return the highest-priority entry without removing it."""
        self._maybe_age()
        with self._lock:
            if not self._heap:
                return None
            return self._heap[0]

    def remove(self, trace_id: str) -> bool:
        """Remove an entry by trace_id (e.g., on timeout or cancellation)."""
        with self._lock:
            for i, entry in enumerate(self._heap):
                if entry.trace_id == trace_id:
                    removed = self._heap.pop(i)
                    heapq.heapify(self._heap)
                    self._priority_counts[removed.priority] = max(
                        0, self._priority_counts.get(removed.priority, 0) - 1
                    )
                    return True
        return False

    def mark_completed(self, entry: PriorityQueueEntry):
        """Increment completed counter (for metrics, entry already popped)."""
        self._completed_count += 1

    def size(self) -> int:
        """Return the current queue size."""
        with self._lock:
            return len(self._heap)

    def clear(self):
        """Clear all queued entries."""
        with self._lock:
            self._heap.clear()
            self._priority_counts = {p: 0 for p in PriorityLevel}
            self._counter = 0

    # ─── Aging ─────────────────────────────────────────────────────

    def _maybe_age(self):
        """Apply priority aging if the interval has elapsed."""
        now = time.time()
        if now - self._last_aging < self._aging_interval:
            return

        with self._lock:
            self._last_aging = now
            aged = 0
            for entry in self._heap:
                # Age entries that have been waiting long enough
                wait_time = now - entry.timestamp
                if wait_time > self._aging_interval * (entry.aging_count + 1):
                    entry.age()
                    aged += 1

            if aged > 0:
                self._aged_count += aged
                heapq.heapify(self._heap)  # Re-heapify after priority changes

                # Check for starvation: any entry waiting > 10x aging interval
                for entry in self._heap:
                    if (now - entry.timestamp) > self._aging_interval * 10:
                        self._starvation_warnings += 1
                        logger.warning(
                            "STARVATION WARNING: label=%s waiting=%.1fs priority=%d aging=%d",
                            entry.label, now - entry.timestamp,
                            int(entry.priority), entry.aging_count,
                        )
                        # Force-age this entry to prevent actual starvation
                        entry.aging_count += 2
                        heapq.heapify(self._heap)
                        break

    def force_age_all(self):
        """Force-aging cycle for all entries (e.g., during maintenance)."""
        with self._lock:
            for entry in self._heap:
                entry.age()
            heapq.heapify(self._heap)
            self._aged_count += len(self._heap)

    # ─── Status ─────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return queue status for observability."""
        with self._lock:
            entries = sorted(self._heap, key=lambda e: e.effective_priority)
            return {
                "size": len(self._heap),
                "max_size": self._max_size,
                "total_pushed": self._counter,
                "completed": self._completed_count,
                "aged": self._aged_count,
                "starvation_warnings": self._starvation_warnings,
                "priority_distribution": {
                    p.name: self._priority_counts.get(p, 0) for p in PriorityLevel
                },
                "oldest_wait_seconds": round(
                    time.time() - entries[0].timestamp, 2
                ) if entries else 0.0,
                "top_entries": [e.to_dict() for e in entries[:5]],
            }


# Global singleton
_queue: Optional[TransactionalPriorityQueue] = None


def get_priority_queue() -> TransactionalPriorityQueue:
    """Get or create the global TransactionalPriorityQueue instance."""
    global _queue
    if _queue is None:
        _queue = TransactionalPriorityQueue()
    return _queue


def reset_priority_queue():
    """Reset the global queue (for testing)."""
    global _queue
    _queue = None
