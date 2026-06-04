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
from collections.abc import Callable
from typing import Any

from app.transaction_context import active_transaction


class HistoryState:
    """Sole owner of the semantic field's diagnostic / history structures."""

    def __init__(self, delta_callback: Callable[[str, str, dict], None] | None = None) -> None:
        self._delta_callback = delta_callback
        self._decision_history: list = []
        self._topology_snapshots: list = []
        self._crystalline_records: list = []
        self._dataset_consensus: dict = {}
        self._solidified_motifs: list = []
        self._transaction_journal: list = []
        self._field_activation_count: int = 0

    @property
    def _staging(self) -> dict | None:
        tx = active_transaction.get()
        if tx is not None:
            return tx.get(f"history_staging_{id(self)}")
        return None

    @_staging.setter
    def _staging(self, value: dict | None) -> None:
        tx = active_transaction.get()
        if tx is not None:
            tx[f"history_staging_{id(self)}"] = value

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self) -> None:
        """Snapshot current state for staging."""
        self._staging = {
            "decision_history": list(self._decision_history),
            "topology_snapshots": list(self._topology_snapshots),
            "crystalline_records": list(self._crystalline_records),
            "dataset_consensus": dict(self._dataset_consensus),
            "solidified_motifs": list(self._solidified_motifs),
            "transaction_journal": list(self._transaction_journal),
            "field_activation_count": self._field_activation_count,
        }

    def commit(self) -> None:
        """Apply staged changes to the active state."""
        if self._staging is not None:
            self._decision_history = self._staging["decision_history"]
            self._topology_snapshots = self._staging["topology_snapshots"]
            self._crystalline_records = self._staging["crystalline_records"]
            self._dataset_consensus = self._staging["dataset_consensus"]
            self._solidified_motifs = self._staging["solidified_motifs"]
            self._transaction_journal = self._staging["transaction_journal"]
            self._field_activation_count = self._staging["field_activation_count"]
            self._staging = None

    def rollback(self) -> None:
        """Discard staged changes."""
        self._staging = None

    def _get_val(self, key: str):
        if self._staging is not None:
            return self._staging[key]
        attr_map = {
            "decision_history": "_decision_history",
            "topology_snapshots": "_topology_snapshots",
            "crystalline_records": "_crystalline_records",
            "dataset_consensus": "_dataset_consensus",
            "solidified_motifs": "_solidified_motifs",
            "transaction_journal": "_transaction_journal",
            "field_activation_count": "_field_activation_count",
        }
        return getattr(self, attr_map[key])

    def _set_val(self, key: str, val: Any) -> None:
        if self._staging is not None:
            self._staging[key] = val
        else:
            attr_map = {
                "decision_history": "_decision_history",
                "topology_snapshots": "_topology_snapshots",
                "crystalline_records": "_crystalline_records",
                "dataset_consensus": "_dataset_consensus",
                "solidified_motifs": "_solidified_motifs",
                "transaction_journal": "_transaction_journal",
                "field_activation_count": "_field_activation_count",
            }
            setattr(self, attr_map[key], val)

    # ─── Read-Only Accessors ─────────────────────────────────────────────

    @property
    def transaction_journal(self) -> list:
        return list(self._get_val("transaction_journal"))

    def transaction_count(self) -> int:
        return len(self._get_val("transaction_journal"))

    @property
    def decision_history(self) -> list:
        return list(self._get_val("decision_history"))

    @decision_history.setter
    def decision_history(self, value: list) -> None:
        self._set_val("decision_history", list(value))

    @property
    def topology_snapshots(self) -> list:
        return list(self._get_val("topology_snapshots"))

    @topology_snapshots.setter
    def topology_snapshots(self, value: list) -> None:
        self._set_val("topology_snapshots", list(value))

    @property
    def crystalline_records(self) -> list:
        return list(self._get_val("crystalline_records"))

    @property
    def field_activation_count(self) -> int:
        return self._get_val("field_activation_count")  # type: ignore[no-any-return]

    @field_activation_count.setter
    def field_activation_count(self, value: int) -> None:
        self._set_val("field_activation_count", int(value))

    def crystalline_count(self) -> int:
        return len(self._get_val("crystalline_records"))

    @property
    def dataset_consensus(self) -> dict:
        return dict(self._get_val("dataset_consensus"))

    @property
    def solidified_motifs(self) -> list:
        return list(self._get_val("solidified_motifs"))

    def add_solidified_motifs(self, new_motifs: list) -> int:
        """Merge new motifs into the solidified set, deduplicating.

        Each motif is normalised to a sorted tuple to make set-membership
        order-independent, then stored as a list of strings (which is the
        serialised shape consumers expect).

        Returns the number of motifs that were newly added.
        """
        if not new_motifs:
            return 0
        current = list(self._get_val("solidified_motifs"))
        existing = {tuple(sorted(m)) for m in current}
        added = 0
        for m in new_motifs:
            try:
                m_sorted = tuple(sorted(m))
            except TypeError:
                continue
            if m_sorted in existing:
                continue
            existing.add(m_sorted)
            current.append(list(m_sorted))
            added += 1
        if added:
            self._set_val("solidified_motifs", current)
            self._record("add_solidified_motifs", {"added": added})
        return added

    # ─── Resource Management ────────────────────────────────────────────

    def trim_journal(self, max_entries: int = 500) -> None:
        """Trim the transaction journal to free memory (Phase 47)."""
        journal = self._get_val("transaction_journal")
        if len(journal) > max_entries:
            self._set_val("transaction_journal", journal[-max_entries:])
            self._record("trim_journal", {"kept": max_entries})

    def trim_snapshots(self, max_size: int = 100, keep: int = 50) -> None:
        """Trim the topology snapshots to free memory (Phase 47)."""
        snapshots = self._get_val("topology_snapshots")
        if len(snapshots) > max_size:
            self._set_val("topology_snapshots", snapshots[-keep:])
            self._record("trim_snapshots", {"max_size": max_size, "keep": keep})

    def merge_journal(self, remote_journal: list) -> None:
        """Merge a remote transaction journal into local history (Phase 67).

        Identifies missing transactions using trace_id and inserts them in
        temporal order.
        """
        local_journal = self._get_val("transaction_journal")
        local_traces = {tx.get("trace_id") for tx in local_journal if tx.get("trace_id")}

        added = 0
        for remote_tx in remote_journal:
            tid = remote_tx.get("trace_id")
            if tid and tid not in local_traces:
                # Missing transaction: insert in local journal
                local_journal.append(dict(remote_tx))
                added += 1
                local_traces.add(tid)

        if added > 0:
            # Re-sort journal by timestamp to maintain causal order
            local_journal.sort(key=lambda x: x.get("timestamp", 0))
            self._set_val("transaction_journal", local_journal)
            self._record("merge_journal", {"added": added, "count": len(local_journal)})

    # ─── Controlled Mutations: Decision History ─────────────────────────

    def _record(self, action: str, details: dict) -> None:
        if self._delta_callback:
            self._delta_callback("history", action, details)

    def record_decision(self, entry: dict) -> None:
        dh = self._get_val("decision_history")
        dh.append(entry)
        self._set_val("decision_history", dh)
        self._record("record_decision", {"entry": entry})

    def trim_decision_history(self, max_size: int = 1000, keep: int = 500) -> None:
        dh = self._get_val("decision_history")
        if len(dh) > max_size:
            dh = dh[-keep:]
            self._set_val("decision_history", dh)
        self._record("trim_decision_history", {"max_size": max_size, "keep": keep})

    def clear_decision_history(self) -> None:
        self._set_val("decision_history", [])
        self._record("clear_decision_history", {})

    def get_recent_decisions(self, n: int = 20) -> list:
        """Get the n most recent decisions as a COPY (no alias risk)."""
        dh = self._get_val("decision_history")
        recent = dh[-n:]
        return [dict(d) if isinstance(d, dict) else d for d in recent]

    def update_recent_decision_metadata(self, recent_copy: list, coherence: float, threshold: float) -> None:
        """Update matching recent decisions in the real history.

        Takes a COPY previously returned by get_recent_decisions, updates
        metadata on it, and writes the updated entries back by index.
        This prevents in-place alias mutation of list element dicts.
        """
        n = len(recent_copy)
        if n == 0:
            return
        dh = self._get_val("decision_history")
        start_idx = max(0, len(dh) - n)
        for i, md in enumerate(recent_copy):
            if isinstance(md, dict):
                md["coherence_after"] = coherence
                md["success"] = coherence > threshold
                idx = start_idx + i
                if idx < len(dh):
                    dh[idx] = md
            else:
                md.coherence_after = coherence
                md.success = coherence > threshold
        self._set_val("decision_history", dh)
        self._record("update_recent_decision_metadata", {"coherence": coherence, "threshold": threshold})

    # ─── Controlled Mutations: Topology Snapshots ────────────────────────

    def add_snapshot(self, snapshot: dict) -> None:
        ts = self._get_val("topology_snapshots")
        ts.append(snapshot)
        self._set_val("topology_snapshots", ts)
        self._record("add_snapshot", {"snapshot": snapshot})

    def get_snapshots(self) -> list:
        return list(self._get_val("topology_snapshots"))

    def get_wave_snapshots(self) -> list:
        ts = self._get_val("topology_snapshots")
        return [s for s in ts if "wave" in s.get("label", "")]

    def diff_snapshots(self, idx_a: int = -2, idx_b: int = -1) -> dict:
        """Return the diff between two snapshots for causal chain inspection."""
        ts = self._get_val("topology_snapshots")
        if len(ts) < 2:
            return {}
        a = ts[idx_a]
        b = ts[idx_b]
        diff = {}
        for k in a:
            if k in ("label", "time"):
                continue
            delta = b.get(k, 0) - a.get(k, 0)
            if abs(delta) > 0.001:
                diff[k] = delta
        return diff

    # ─── Controlled Mutations: Crystalline Records ───────────────────────

    def synthesize_crystalline(self, record: dict, current_record: int) -> None:
        """Synthesize a high-integrity knowledge record with temporal awareness."""
        record["_record_index"] = current_record
        cr = self._get_val("crystalline_records")
        cr.append(record)
        self._set_val("crystalline_records", cr)
        self._record("synthesize_crystalline", {"record": record, "current_record": current_record})

    def get_crystalline_attractors(self, token_vals=None) -> list:
        cr = self._get_val("crystalline_records")
        if not cr:
            return []
        if token_vals:
            if not isinstance(token_vals, list):
                token_vals = [token_vals]
            return [r for r in cr if any(str(tv) in str(v) for tv in token_vals for v in r.values() if v is not None)]
        return list(cr)

    def topological_search(self, query: str) -> list:
        q = query.lower()
        cr = self._get_val("crystalline_records")
        return [r for r in cr if any(q in str(v).lower() for v in r.values())]

    def find_crystalline_matches(self, token_val: str, current_record: int = 0) -> float:
        """Find crystalline matches and return a temporally weighted knowledge score (Phase 31)."""
        score = 0.0
        cr = self._get_val("crystalline_records")
        for r in cr:
            if any(token_val == str(v) for v in r.values() if v is not None):
                # Temporal Weighting: newer knowledge is more relevant
                age = current_record - r.get("_record_index", 0)
                # Decay factor: e^(-age / 500)
                weight = math.exp(-max(0, age) / 500.0)
                score += weight
        return min(1.0, score)

    def record_transaction(self, tx: dict, capacity: int = 1000) -> None:
        tj = self._get_val("transaction_journal")
        tj.append(tx)
        if len(tj) > capacity:
            tj = tj[-(capacity // 2) :]
        self._set_val("transaction_journal", tj)
        # Phase 57 / 58: DO NOT call self._record here!
        # Causal journaling already captures this; recording the recording
        # causes infinite recursion.

    def get_transaction_journal(self) -> list:
        return list(self._get_val("transaction_journal"))

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        dh = self._get_val("decision_history")
        ts = self._get_val("topology_snapshots")
        tj = self._get_val("transaction_journal")
        cr = self._get_val("crystalline_records")
        ds = self._get_val("dataset_consensus")
        sm = self._get_val("solidified_motifs")
        return {
            "decision_history": list(dh[-500:]),
            "topology_snapshots": [dict(s) for s in ts[-250:]],
            "transaction_journal": [dict(tx) for tx in tj[-250:]],
            "crystalline_records": [dict(r) for r in cr],
            "dataset_consensus": dict(ds),
            "solidified_motifs": list(sm),
            "field_activation_count": self.field_activation_count,
        }

    def from_dict(self, data: dict) -> None:
        self.clear()
        self._set_val("decision_history", list(data.get("decision_history", [])))
        self._set_val("topology_snapshots", list(data.get("topology_snapshots", [])))
        self._set_val("transaction_journal", list(data.get("transaction_journal", [])))
        self._set_val("crystalline_records", list(data.get("crystalline_records", [])))
        self._set_val("dataset_consensus", dict(data.get("dataset_consensus", {})))
        self._set_val("solidified_motifs", list(data.get("solidified_motifs", [])))
        self._set_val("field_activation_count", data.get("field_activation_count", 0))

    def clear(self) -> None:
        self._set_val("decision_history", [])
        self._set_val("topology_snapshots", [])
        self._set_val("transaction_journal", [])
        self._set_val("crystalline_records", [])
        self._set_val("dataset_consensus", {})
        self._set_val("solidified_motifs", [])
        self._set_val("field_activation_count", 0)
