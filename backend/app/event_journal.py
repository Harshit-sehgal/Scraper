"""Event Journal — mutation tracing and causality chain for the semantic field.

Every mutation to the world state is recorded as a journal entry with:
- before / after state snapshots
- timestamp
- source / cause
- mutation type

This enables replay, rollback, and causality chain analysis.

ReplayBuffer integration: All journal entries are also persisted to the
large-scale ReplayBuffer for streaming replay from persistent storage.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class EventJournal:
    """Tracks mutations to the semantic field for replay and debugging.

    Now uses Delta-Encoding (Phase 57) to support million-event horizons.
    Streams historical deltas to ReplayBuffer for persistent storage (Phase 66).
    """

    def __init__(self, max_entries: int = 10000):
        self._entries: list = []
        self._max = max_entries
        self._enabled = True
        self._checkpoints: dict[int, dict] = {}  # event_idx -> full_snapshot
        self._current_idx = 0

    def record(self, source: str, mutation_type: str, before: dict, after: dict, metadata: Optional[dict] = None):
        """Record a mutation event using delta-encoding (Phase 57).

        Also persists to the large-scale ReplayBuffer for streaming replay
        from persistent storage (Phase 66).
        """
        if not self._enabled:
            return

        delta = _compute_delta(before, after)
        if not delta and mutation_type != "checkpoint":
            return  # No change

        # Phase 66: Hierarchical Causal Pruning - ignore high-frequency noise
        # in stable epochs
        if mutation_type == "apply_force_to_manifold" and metadata and metadata.get("displacement", 0) < 1e-3:
            # Trivial manifold shift, skip if not structural
            return

        entry = {
            "timestamp": time.time(),
            "source": source,
            "type": mutation_type,
            "delta": delta,
            "idx": self._current_idx,
            "metadata": metadata or {},
        }

        # Phase 57 / 61: Topology-Aware Snapshots
        # Trigger checkpoint if structural change OR fixed interval
        is_structural = mutation_type in ["restructure_topology", "merge_state", "add", "remove"]
        if self._current_idx % 500 == 0 or is_structural:
            self._checkpoints[self._current_idx] = dict(after)
            entry["checkpoint"] = True

        self._entries.append(entry)
        self._current_idx += 1

        # Phase 66 / ArchWeakness: Persist each event to the large-scale ReplayBuffer
        # for streaming replay from persistent storage.
        try:
            from app.replay_buffer import get_replay_buffer

            rb = get_replay_buffer()
            rb.append(
                {
                    "type": f"{source}.{mutation_type}",
                    "delta": delta if delta else {"source": source, "mutation_type": mutation_type},
                    "metadata": {
                        "source": source,
                        "mutation_type": mutation_type,
                        "idx": self._current_idx - 1,
                        "trace_id": (metadata or {}).get("trace_id"),
                        **({k: v for k, v in (metadata or {}).items() if k != "trace_id"}),
                    },
                }
            )
        except Exception as e:
            # ReplayBuffer failure is non-fatal — journal continues normally
            logger.debug("ReplayBuffer persist skipped: %s", e)

        if len(self._entries) > self._max:
            # Phase 57 / 58 / 61 / 66: Semantic Retention Prioritization
            # We keep recent entries AND historical structural transitions
            # (Skeletonization)
            keep_count = self._max // 2

            recent = self._entries[-keep_count:]
            historical = self._entries[:-keep_count]

            # Skeletonization: preserve ONLY structural events or high-value
            # checkpoints
            structural_types = {"restructure_topology", "merge_state", "promote_hypo", "crystallize", "add", "remove"}
            to_retain = [e for e in historical if e["type"] in structural_types or e.get("checkpoint")]

            # Further compress historical structural events if they exceed 10%
            if len(to_retain) > self._max // 10:
                # Keep only the most recent structural transitions from history
                to_retain = to_retain[-(self._max // 10):]

            self._entries = to_retain + recent

            # Prune checkpoints that are no longer reachable by any retained
            # entries
            if self._entries:
                first_remaining_idx = self._entries[0]["idx"]
                latest_valid_checkpoint = max((k for k in self._checkpoints if k <= first_remaining_idx), default=-1)

                for idx in list(self._checkpoints.keys()):
                    if idx < latest_valid_checkpoint:
                        del self._checkpoints[idx]

    def get_snapshot_at(self, idx: int) -> Optional[dict]:
        """Reconstruct the state snapshot at a specific event index."""
        if not self._entries:
            return None

        first_idx = self._entries[0]["idx"]
        if idx < first_idx:
            return None  # Pruned

        # 1. Find nearest preceding checkpoint
        checkpoint_idx = max((k for k in self._checkpoints if k <= idx), default=-1)
        if checkpoint_idx == -1:
            return None  # Cannot reconstruct without base

        state = dict(self._checkpoints[checkpoint_idx])
        # 2. Apply deltas forward
        relevant_entries = [e for e in self._entries if checkpoint_idx < e["idx"] <= idx]
        for e in relevant_entries:
            _apply_delta(state, e.get("delta", {}))

        return state

    def replay(self, start: int = 0) -> list:
        """Return journal entries from index `start` onward for replay."""
        return list(self._entries[start:])

    def get_causality_chain(self, mutation_type: Optional[str] = None) -> list:
        """Return the chain of events by type, showing causal relationships."""
        chain = []
        for e in self._entries:
            if mutation_type and e["type"] != mutation_type:
                continue
            chain.append(
                {
                    "type": e["type"],
                    "source": e["source"],
                    "timestamp": e["timestamp"],
                    "delta": e.get("delta", {}),
                }
            )
        return chain

    def get_last_n(self, n: int = 10) -> list:
        """Return the last N entries for debugging."""
        return self._entries[-n:]

    def clear(self):
        """Clear all journal entries."""
        self._entries.clear()
        self._checkpoints.clear()
        self._current_idx = 0

    @property
    def count(self) -> int:
        return len(self._entries)


# Global journal instance
_journal = EventJournal()


def get_journal() -> EventJournal:
    return _journal


def _compute_delta(before: dict, after: dict) -> dict:
    """Compute what changed between two state snapshots.

    Includes Semantic Delta Compression (Phase 61): ignores trivial
    numerical changes below the precision threshold.
    """
    delta = {}
    all_keys = set(before.keys()) | set(after.keys())
    for k in all_keys:
        bv = before.get(k)
        av = after.get(k)

        if bv != av:
            # Phase 61: Ignore minute floating point drift
            if isinstance(bv, float) and isinstance(av, float):
                if abs(bv - av) < 1e-4:
                    continue

            delta[k] = {"from": bv, "to": av}
    return delta


def _apply_delta(state: dict, delta: dict):
    """Apply a delta-encoded change to a state dictionary."""
    for k, change in delta.items():
        state[k] = change["to"]
