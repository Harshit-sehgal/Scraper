"""Event Journal — mutation tracing and causality chain for the semantic field.

Every mutation to the world state is recorded as a journal entry with:
- before/after state snapshots
- timestamp
- source/cause
- mutation type

This enables replay, rollback, and causality chain analysis.
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EventJournal:
    """Tracks mutations to the semantic field for replay and debugging."""

    def __init__(self, max_entries: int = 1000):
        self._entries: list = []
        self._max = max_entries
        self._enabled = True

    def record(self, source: str, mutation_type: str, before: dict, after: dict, metadata: Optional[dict] = None):
        """Record a mutation event."""
        if not self._enabled:
            return
        entry = {
            "timestamp": time.time(),
            "source": source,
            "type": mutation_type,
            "before": before,
            "after": after,
            "metadata": metadata or {},
        }
        self._entries.append(entry)
        if len(self._entries) > self._max:
            self._entries = self._entries[-self._max // 2:]

    def replay(self, start: int = 0) -> list:
        """Return journal entries from index `start` onward for replay."""
        return list(self._entries[start:])

    def get_causality_chain(self, mutation_type: Optional[str] = None) -> list:
        """Return the chain of events by type, showing causal relationships."""
        chain = []
        for e in self._entries:
            if mutation_type and e["type"] != mutation_type:
                continue
            chain.append({
                "type": e["type"],
                "source": e["source"],
                "timestamp": e["timestamp"],
                "delta": _compute_delta(e["before"], e["after"]),
            })
        return chain

    def get_last_n(self, n: int = 10) -> list:
        """Return the last N entries for debugging."""
        return self._entries[-n:]

    def clear(self):
        """Clear all journal entries."""
        self._entries.clear()

    @property
    def count(self) -> int:
        return len(self._entries)


# Global journal instance
_journal = EventJournal()


def get_journal() -> EventJournal:
    return _journal


def _compute_delta(before: dict, after: dict) -> dict:
    """Compute what changed between two state snapshots."""
    delta = {}
    all_keys = set(before.keys()) | set(after.keys())
    for k in all_keys:
        bv = before.get(k)
        av = after.get(k)
        if bv != av:
            delta[k] = {"from": bv, "to": av}
    return delta
