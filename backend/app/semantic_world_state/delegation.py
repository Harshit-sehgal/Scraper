"""Delegation properties for :class:`SemanticWorldState`.

These methods are thin compatibility proxies over subsystem state objects.
Keeping them in a mixin keeps the canonical world-state orchestrator below
the complexity gate while preserving the public API expected by older code.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


class DelegationMixin:
    _abstraction: Any
    _energy: Any
    _history: Any
    _instability: Any
    _lock: Any
    _manifold: Any
    _motif: Any
    _topology: Any
    _transition: Any

    # ─── Energy & Topology API Delegation Properties ───────────────────────

    @property
    def energy_state(self) -> Any:
        return self._energy

    @property
    def topology_state(self) -> Any:
        return self._topology

    @property
    def topology_anchors(self) -> set[Any]:
        return self._topology.anchors

    @property
    def meso_clusters(self) -> list[Any]:
        return self._topology.meso_clusters

    def compute_meso_clusters(self) -> None:
        self._topology.compute_meso_clusters()

    def compute_macro_from_meso(self) -> dict[str, Any]:
        return self._topology.compute_macro_from_meso()

    @property
    def macro_continents(self) -> list[Any]:
        return self._topology.get_view().get_macro_continents()

    def compute_macro_continents(self) -> None:
        self._topology.compute_macro_continents()

    # ─── Authority Delegation Properties ─────────────────────────────────

    @property
    def field_regions(self):
        return self._topology.get_view().all_regions()

    @field_regions.setter
    def field_regions(self, value) -> None:
        self._topology.replace_all(list(value))

    @property
    def learned_exclusions(self):
        return dict(self._instability.exclusions)

    # ─── Delegation Properties: ManifoldState ─────────────────────────────

    @property
    def role_manifold(self):
        return {k: list(v) for k, v in self._manifold.role_manifold.items()}

    @property
    def role_compatibility(self):
        return dict(self._manifold.role_compatibility)

    @property
    def role_position_memory(self):
        return {k: list(v) for k, v in self._manifold.role_position_memory.items()}

    @role_position_memory.setter
    def role_position_memory(self, value) -> None:
        self._manifold.role_position_memory = value

    @property
    def role_co_occurrence(self):
        return dict(self._manifold.role_co_occurrence)

    @property
    def learning_count(self) -> int:
        return self._manifold.learning_count

    @learning_count.setter
    def learning_count(self, value: int) -> None:
        self._manifold.set_learning_count(value)

    @property
    def total_co_occurrences(self) -> int:
        return self._manifold.total_co_occurrences

    @total_co_occurrences.setter
    def total_co_occurrences(self, value: int) -> None:
        self._manifold.set_total_co_occurrences(value)

    # ─── Delegation Properties: MotifState ───────────────────────────────

    @property
    def motif_counts(self):
        return Counter(self._motif.motif_counts)

    @property
    def motif_timestamps(self):
        return dict(self._motif.motif_timestamps)

    @property
    def motif_stability(self):
        return dict(self._motif.motif_stability)

    # ─── Delegation Properties: TransitionState ───────────────────────────

    @property
    def transition_probs(self):
        return dict(self._transition.transition_probs)

    @property
    def transition_observations(self) -> int:
        return self._transition.transition_observations

    @transition_observations.setter
    def transition_observations(self, value: int) -> None:
        self._transition.set_transition_observations(value)

    # ─── Delegation Properties: HistoryState ──────────────────────────────

    @property
    def decision_history(self):
        return list(self._history.decision_history)

    @decision_history.setter
    def decision_history(self, value) -> None:
        self._history.decision_history = value

    @property
    def topology_snapshots(self):
        return list(self._history.topology_snapshots)

    @topology_snapshots.setter
    def topology_snapshots(self, value) -> None:
        self._history.topology_snapshots = value

    @property
    def crystalline_records(self):
        return list(self._history.crystalline_records)

    @property
    def field_activation_count(self) -> int:
        return self._history.field_activation_count

    @field_activation_count.setter
    def field_activation_count(self, value: int) -> None:
        self._history.field_activation_count = value

    @property
    def dataset_consensus(self):
        return dict(self._history.dataset_consensus)

    @property
    def solidified_motifs(self):
        return list(self._history.solidified_motifs)

    def add_solidified_motifs(self, new_motifs: list[Any]) -> int:
        """Atomically merge ``new_motifs`` into the solidified set.

        Holds the substrate lock for the read-modify-write so concurrent
        callers can't lose updates. Returns the number of newly added
        motifs (existing duplicates are skipped).
        """
        if not new_motifs:
            return 0
        with self._lock:
            return self._history.add_solidified_motifs(new_motifs)

    # ─── Delegation Properties: Topology-Derived Structures ───────────────

    @property
    def global_communities(self):
        return [set(c) for c in self._topology.global_communities]

    @property
    def schema_patterns(self):
        return dict(self._topology.schema_patterns)

    @property
    def topological_laws(self):
        return dict(self._topology.topological_laws)

    @property
    def neighborhood_cohesion(self):
        return dict(self._topology.neighborhood_cohesion)

    @property
    def global_centrality(self):
        return dict(self._topology.global_centrality)

    @property
    def impossible_neighborhoods(self):
        return [set(c) for c in self._topology.impossible_neighborhoods]

    @property
    def restructuring_queue(self):
        return set(self._topology.restructuring_queue)

    @property
    def cohesion_merge_success(self):
        return dict(self._topology.get_cohesion_merge_success())

    @property
    def cohesion_merge_attempts(self):
        return dict(self._topology.get_cohesion_merge_attempts())

    @property
    def cohesion_split_success(self):
        return dict(self._topology.get_cohesion_split_success())

    @property
    def cohesion_split_attempts(self):
        return dict(self._topology.get_cohesion_split_attempts())
