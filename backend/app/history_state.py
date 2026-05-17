"""HistoryState — owns all diagnostic and history data.

True ownership boundary: NO external code should mutate decision_history,
topology_snapshots, or crystalline_records directly. All changes go through
this state object which enforces bounded growth.

Owns:
- decision_history: list — recorded decisions and events
- topology_snapshots: list — periodic field state snapshots
- crystalline_records: list — synthesized high-integrity knowledge units
- field_activation_count: int — total field activations
"""

import math

class HistoryState:
    """Sole owner of the semantic field's diagnostic/history structures."""

    def __init__(self):
        self._decision_history: list = []
        self._topology_snapshots: list = []
        self._crystalline_records: list = []
        self._dataset_consensus: dict = {}
        self._solidified_motifs: list = []
        self._transaction_journal: list = []
        self.field_activation_count: int = 0

    # ─── Read-Only Accessors ─────────────────────────────────────────────

    @property
    def transaction_journal(self) -> list:
        return list(self._transaction_journal)

    def transaction_count(self) -> int:
        return len(self._transaction_journal)

    # ... rest of properties ...

    @property
    def decision_history(self) -> list:
        return list(self._decision_history)

    @decision_history.setter
    def decision_history(self, value: list):
        self._decision_history = list(value)

    @property
    def topology_snapshots(self) -> list:
        return list(self._topology_snapshots)

    @topology_snapshots.setter
    def topology_snapshots(self, value: list):
        self._topology_snapshots = list(value)

    @property
    def crystalline_records(self) -> list:
        return list(self._crystalline_records)

    def crystalline_count(self) -> int:
        return len(self._crystalline_records)

    @property
    def dataset_consensus(self) -> dict:
        return dict(self._dataset_consensus)

    @property
    def solidified_motifs(self) -> list:
        return list(self._solidified_motifs)

    # ─── Controlled Mutations: Decision History ─────────────────────────

    def record_decision(self, entry: dict):
        self._decision_history.append(entry)

    def trim_decision_history(self, max_size: int = 1000, keep: int = 500):
        if len(self._decision_history) > max_size:
            self._decision_history = self._decision_history[-keep:]

    def clear_decision_history(self):
        self._decision_history.clear()

    def get_recent_decisions(self, n: int = 20) -> list:
        """Get the n most recent decisions as a COPY (no alias risk)."""
        recent = self._decision_history[-n:]
        return [dict(d) if isinstance(d, dict) else d for d in recent]

    def update_recent_decision_metadata(self, recent_copy: list, coherence: float, threshold: float):
        """Update matching recent decisions in the real history.
        
        Takes a COPY previously returned by get_recent_decisions, updates
        metadata on it, and writes the updated entries back by index.
        This prevents in-place alias mutation of list element dicts.
        """
        n = len(recent_copy)
        if n == 0:
            return
        start_idx = max(0, len(self._decision_history) - n)
        for i, md in enumerate(recent_copy):
            if isinstance(md, dict):
                md["coherence_after"] = coherence
                md["success"] = coherence > threshold
                idx = start_idx + i
                if idx < len(self._decision_history):
                    self._decision_history[idx] = md
            else:
                md.coherence_after = coherence
                md.success = coherence > threshold

    # ─── Controlled Mutations: Topology Snapshots ────────────────────────

    def add_snapshot(self, snapshot: dict):
        self._topology_snapshots.append(snapshot)

    def trim_snapshots(self, max_size: int = 500, keep: int = 250):
        if len(self._topology_snapshots) > max_size:
            self._topology_snapshots = self._topology_snapshots[-keep:]

    def get_snapshots(self) -> list:
        return list(self._topology_snapshots)

    def get_wave_snapshots(self) -> list:
        return [s for s in self._topology_snapshots if "wave" in s.get("label", "")]

    def diff_snapshots(self, idx_a: int = -2, idx_b: int = -1) -> dict:
        """Return the diff between two snapshots for causal chain inspection."""
        if len(self._topology_snapshots) < 2:
            return {}
        a = self._topology_snapshots[idx_a]
        b = self._topology_snapshots[idx_b]
        diff = {}
        for k in a:
            if k in ("label", "time"):
                continue
            delta = b.get(k, 0) - a.get(k, 0)
            if abs(delta) > 0.001:
                diff[k] = delta
        return diff

    # ─── Controlled Mutations: Crystalline Records ───────────────────────

    def synthesize_crystalline(self, record: dict, current_record: int):
        """Synthesize a high-integrity knowledge record with temporal awareness."""
        record["_record_index"] = current_record
        self._crystalline_records.append(record)

    def get_crystalline_attractors(self, token_vals=None) -> list:
        if not self._crystalline_records:
            return []
        if token_vals:
            if not isinstance(token_vals, list):
                token_vals = [token_vals]
            return [r for r in self._crystalline_records if any(str(tv) in str(v) for tv in token_vals for v in r.values() if v is not None)]
        return list(self._crystalline_records)

    def topological_search(self, query: str) -> list:
        q = query.lower()
        return [r for r in self._crystalline_records if any(q in str(v).lower() for v in r.values())]

    def find_crystalline_matches(self, token_val: str, current_record: int = 0) -> float:
        """Find crystalline matches and return a temporally weighted knowledge score (Phase 31)."""
        score = 0.0
        for r in self._crystalline_records:
            if any(token_val == str(v) for v in r.values() if v is not None):
                # Temporal Weighting: newer knowledge is more relevant
                age = current_record - r.get("_record_index", 0)
                # Decay factor: e^(-age / 500)
                weight = math.exp(-max(0, age) / 500.0)
                score += weight
        return min(1.0, score)

    def record_transaction(self, tx: dict):
        self._transaction_journal.append(tx)
        if len(self._transaction_journal) > 1000:
            self._transaction_journal = self._transaction_journal[-500:]

    def get_transaction_journal(self) -> list:
        return list(self._transaction_journal)

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "decision_history": self._decision_history[-500:] if len(self._decision_history) > 500 else self._decision_history,
            "topology_snapshots": self._topology_snapshots[-250:] if len(self._topology_snapshots) > 250 else self._topology_snapshots,
            "transaction_journal": self._transaction_journal[-250:] if len(self._transaction_journal) > 250 else self._transaction_journal,
            "crystalline_records": list(self._crystalline_records),
            "dataset_consensus": dict(self._dataset_consensus),
            "solidified_motifs": list(self._solidified_motifs),
            "field_activation_count": self.field_activation_count,
        }

    def from_dict(self, data: dict):
        self.clear()
        self._decision_history = list(data.get("decision_history", []))
        self._topology_snapshots = list(data.get("topology_snapshots", []))
        self._transaction_journal = list(data.get("transaction_journal", []))
        self._crystalline_records = list(data.get("crystalline_records", []))
        self._dataset_consensus = dict(data.get("dataset_consensus", {}))
        self._solidified_motifs = list(data.get("solidified_motifs", []))
        self.field_activation_count = data.get("field_activation_count", 0)

    def clear(self):
        self._decision_history.clear()
        self._topology_snapshots.clear()
        self._transaction_journal.clear()
        self._crystalline_records.clear()
        self._dataset_consensus.clear()
        self._solidified_motifs.clear()
        self.field_activation_count = 0
