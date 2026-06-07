"""TopologyState — owns the field region graph and ALL topology-derived structures.

Re-exports types / helpers from topology_state_types and TopologyView from
topology_view for backward compatibility.
"""

from collections.abc import Callable
from typing import Any

from app.core_types import FieldConflictRegion
from app.topology_clustering import (
    add_impossible_neighborhood as _cluster_add_impossible,
)
from app.topology_clustering import (
    clear_impossible_neighborhoods as _cluster_clear_impossible,
)
from app.topology_clustering import (
    decay_topological_laws as _cluster_decay_laws,
)
from app.topology_clustering import (
    detect_communities as _cluster_detect_communities,
)
from app.topology_clustering import (
    induce_topological_laws as _cluster_induce_laws,
)
from app.topology_clustering import (
    self_prune_regions,
    shard_topology_regions,
)
from app.topology_clustering import (
    set_topological_law as _cluster_set_law,
)
from app.topology_clustering import (
    update_schema_patterns as _cluster_update_schema,
)

# Multi-scale topology dynamics (extracted for modularity)
from app.topology_dynamics import (
    compute_macro_continents,
    compute_macro_from_meso,
    compute_meso_clusters,
    cross_scale_pressure_flow,
    evolve_macro_continents,
    evolve_meso_clusters,
)

# Extracted force & thermodynamic modules (Phase 1 refactor)
from app.topology_forces import (
    compute_edge_field_forces as _forces_compute,
)
from app.topology_forces import (
    redirect_repulsive_pressure as _forces_redirect,
)
from app.topology_forces import (
    route_contradiction as _forces_route_contradiction,
)
from app.topology_metrics import (
    compute_aggregate_metrics,
    compute_topology_entropy,
)
from app.topology_metrics import (
    compute_macro_energy as _metrics_compute_macro_energy,
)
from app.topology_metrics import (
    distill_crystalline_atoms as _metrics_distill,
)
from app.topology_persistence import (
    clear_topology,
    clear_topology_regions,
    filter_topology_regions,
    merge_topology,
    replace_all_regions,
    topology_from_dict,
    topology_to_dict,
    trim_topology,
)
from app.topology_persistence import (
    garbage_collect_topology as _persistence_gc,
)
from app.topology_persistence import (
    prune_topology as _persistence_prune,
)
from app.topology_region_ops import (
    adjust_region_energy as _ops_adj_energy,
)
from app.topology_region_ops import (
    adjust_region_instability as _ops_adj_instability,
)
from app.topology_region_ops import (
    adjust_region_recurrence as _ops_adj_recurrence,
)
from app.topology_region_ops import (
    set_region_convergence as _ops_set_convergence,
)
from app.topology_region_ops import (
    set_region_energy as _ops_set_energy,
)
from app.topology_region_ops import (
    set_region_instability as _ops_set_instability,
)
from app.topology_region_ops import (
    set_region_integrity as _ops_set_integrity,
)
from app.topology_region_ops import (
    set_region_momentum as _ops_set_momentum,
)
from app.topology_region_ops import (
    set_region_persistence as _ops_set_persistence,
)
from app.topology_region_ops import (
    set_region_pressure as _ops_set_pressure,
)
from app.topology_region_ops import (
    set_region_recurrence as _ops_set_recurrence,
)
from app.topology_region_ops import (
    set_region_temperature as _ops_set_temperature,
)
from app.topology_region_ops import (
    update_local_memory_from_instability as _ops_update_local_memory,
)
from app.topology_region_ops import (
    update_region_after_recurrence as _ops_update_after_recurrence,
)

# Re-export public symbols from sub-modules for backward compatibility
from app.topology_state_types import (
    ConflictError,
    EdgeFieldSnapshot,
    MacroContinentSnapshot,
    MesoClusterSnapshot,
    RegionSnapshot,
    _clamp01,
    _clamp_signed,
    parse_topology_key,
)
from app.topology_thermodynamics import (
    evolve_all as _thermo_evolve_all,
)
from app.topology_thermodynamics import (
    propagate_all as _thermo_propagate_all,
)
from app.topology_thermodynamics import (
    redistribute_instability as _thermo_redistribute,
)
from app.topology_view import TopologyView
from app.topology_waves import (
    emit_field_wave as _waves_emit,
)
from app.topology_waves import (
    process_field_wave as _waves_process,
)
from app.transaction_context import active_transaction

__all__ = [
    "ConflictError",
    "EdgeFieldSnapshot",
    "MacroContinentSnapshot",
    "MesoClusterSnapshot",
    "RegionSnapshot",
    "TopologyState",
    "TopologyView",
    "_clamp01",
    "_clamp_signed",
    "parse_topology_key",
]


class TopologyState:
    """Sole owner of the semantic field's topology structure."""

    @property
    def _tombstones(self) -> set[str]:
        tx = self._staging
        if tx is not None:
            return tx["tombstones"]  # type: ignore[no-any-return]
        return self.__dict__.get("_tombstones_real", set())  # type: ignore[no-any-return]

    @_tombstones.setter
    def _tombstones(self, value: set[str]) -> None:
        tx = self._staging
        if tx is not None:
            tx["tombstones"] = value
        else:
            self._tombstones_real = value

    @property
    def _structural_change(self) -> bool:
        tx = self._staging
        if tx is not None:
            return tx["structural_change"]  # type: ignore[no-any-return]
        return False

    @_structural_change.setter
    def _structural_change(self, value: bool) -> None:
        tx = self._staging
        if tx is not None:
            tx["structural_change"] = value

    def __init__(
        self,
        delta_callback: Callable[[str, str, dict], None] | None = None,
        read_callback: Callable[[str, int], None] | None = None,
    ) -> None:
        self._delta_callback = delta_callback
        self._read_callback = read_callback
        # ─── Region Graph ──────────────────────────────────────────────
        self._regions: list[FieldConflictRegion] = []

        # ─── Topology-Derived Structures ───────────────────────────────
        self._communities: list[set[str]] = []
        self._schema_patterns: dict[tuple[str, str], float] = {}
        self._topological_laws: dict = {}
        self._neighborhood_cohesion: dict[tuple[str, str], float] = {}
        self._centrality: dict[str, float] = {}
        self._impossible_neighborhoods: list[set[str]] = []
        self._restructuring_queue: set[tuple[str, str]] = set()
        self._cohesion_merge_success: dict[tuple[str, str], float] = {}
        self._cohesion_merge_attempts: dict[tuple[str, str], float] = {}
        self._cohesion_split_success: dict[tuple[str, str], float] = {}
        self._cohesion_split_attempts: dict[tuple[str, str], float] = {}
        self._anchors: set[tuple[str, str]] = set()
        self._crystalline_atoms: list[dict] = []

        # ─── Meso Clusters (Multi-Scale Topology) ────────────────────
        self._meso_clusters: list[dict] = []

        # ─── Macro Continents (Multi-Scale Topology) ──────────────────
        self._macro_continents: list[dict] = []
        self._last_pressure_flow_time: float = 0.0

        # ─── Distributed Recovery (Phase 60) ──────────────────────────
        self._topology_epoch: int = 1

        # Tombstones track removed region_ids outside a transaction.
        # MUST be initialised here, not via ``__dict__.get(..., set())``
        # in the property getter, otherwise the getter returns a fresh
        # empty set on every call and any ``.add()`` mutation is lost
        # (the non-staging path in ``remove()`` would silently no-op).
        self._tombstones_real: set[str] = set()  # type: ignore[no-redef]

        # ─── Transaction Staging ──────────────────────────────────────

    @property
    def _staging(self) -> dict | None:
        tx = active_transaction.get()
        if tx is not None:
            return tx.get(f"topology_staging_{id(self)}")
        return None

    @_staging.setter
    def _staging(self, value: dict | None) -> None:
        tx = active_transaction.get()
        if tx is not None:
            tx[f"topology_staging_{id(self)}"] = value

    @property
    def _modified_regions(self) -> set[str]:
        tx = active_transaction.get()
        if tx is not None:
            key = f"topology_modified_{id(self)}"
            if key not in tx:
                tx[key] = set()
            return tx[key]  # type: ignore[no-any-return]
        return set()

    def _record(self, action: str, details: dict) -> None:
        if "region_id" in details:
            self._modified_regions.add(details["region_id"])
        if self._delta_callback:
            self._delta_callback("topology", action, details)

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self) -> None:
        """Start a transaction by snapshotting all topology structures."""
        from dataclasses import replace

        self._modified_regions.clear()
        self._structural_change = False
        self._staging = {
            "regions": [replace(r) for r in self._regions],
            "communities": [set(c) for c in self._communities],
            "schema_patterns": dict(self._schema_patterns),
            "topological_laws": dict(self._topological_laws),
            "neighborhood_cohesion": dict(self._neighborhood_cohesion),
            "impossible_neighborhoods": [set(c) for c in self._impossible_neighborhoods],
            "restructuring_queue": set(self._restructuring_queue),
            "merge_success": dict(self._cohesion_merge_success),
            "merge_attempts": dict(self._cohesion_merge_attempts),
            "split_success": dict(self._cohesion_split_success),
            "split_attempts": dict(self._cohesion_split_attempts),
            "centrality": dict(self._centrality),
            "anchors": set(self._anchors),
            "crystalline_atoms": list(self._crystalline_atoms),
            "meso_clusters": list(self._meso_clusters),
            "macro_continents": list(self._macro_continents),
            "tombstones": set(self._tombstones),
            "structural_change": False,
        }

    def commit(self, expected_versions: dict[str, int] | None = None) -> None:
        """Apply staged changes to the active state with MVCC validation."""
        if self._staging is not None:
            # 1. Optimistic Validation (Phase 51)
            if expected_versions:
                for rid, expected in expected_versions.items():
                    # Find live region
                    live = next((r for r in self._regions if r.region_id == rid), None)
                    if live and live.version != expected:
                        msg = f"MVCC CONFLICT: Region [{rid}] version {live.version} != expected {expected}"
                        raise ConflictError(msg)

            # 2. Increment versions for all modified regions
            for rid in self._modified_regions:
                r_staged = next((r for r in self._staging["regions"] if r.region_id == rid), None)
                if r_staged:
                    r_staged.version += 1

            # Phase 60: Structural Epoch increment
            if self._staging["structural_change"]:
                self._topology_epoch += 1

            tombstones = self._staging["tombstones"]

            self._regions = self._staging["regions"]
            self._communities = self._staging["communities"]
            self._schema_patterns = self._staging["schema_patterns"]
            self._topological_laws = self._staging["topological_laws"]
            self._neighborhood_cohesion = self._staging["neighborhood_cohesion"]
            self._impossible_neighborhoods = self._staging["impossible_neighborhoods"]
            self._restructuring_queue = self._staging["restructuring_queue"]
            self._cohesion_merge_success = self._staging["merge_success"]
            self._cohesion_merge_attempts = self._staging["merge_attempts"]
            self._cohesion_split_success = self._staging["split_success"]
            self._cohesion_split_attempts = self._staging["split_attempts"]
            self._centrality = self._staging["centrality"]
            self._anchors = self._staging["anchors"]
            self._crystalline_atoms = self._staging["crystalline_atoms"]
            self._meso_clusters = self._staging["meso_clusters"]
            self._macro_continents = self._staging["macro_continents"]

            self._staging = None
            # Route through the property setter so any future notification
            # hook (e.g. invalidation observers) fires consistently.
            self._tombstones = tombstones
            self._modified_regions.clear()

    def rollback(self) -> None:
        """Discard staged changes."""
        self._staging = None
        self._modified_regions.clear()
        self._structural_change = False

    def restructure_topology(self, target_region_ids: list[str] | None = None) -> None:
        """Forcibly rewire the substrate to escape metastable locks (Phase 52).

        Breaks strong cohesion edges and increases regional temperature to
        encourage discovery of new topological minima.
        """
        regs = self._get_regions()
        targets = target_region_ids or [r.region_id for r in regs if r.instability < 0.1]

        for rid in targets:
            # 1. Break edges (Clear neighbors)
            self._record("break_topology_edges", {"region_id": rid})
            r = self.get_region(rid)
            if r:
                r.topology_neighbors = []
                # 2. Temperature Spike (Phase 48)
                self.set_region_temperature(rid, 0.9)
                # 3. Momentum Reset
                self.set_region_momentum(rid, 0.0)

        self._record("restructure_topology", {"count": len(targets)})

    def shard_topology(self) -> dict[str, list[str]]:
        """Assign every region to a shard based on community membership (Phase 53). Delegates to topology_clustering."""
        return shard_topology_regions(self)

    def _get_regions(self) -> list[FieldConflictRegion]:
        return self._staging["regions"] if self._staging is not None else self._regions

    def _set_regions(self, regions: list[FieldConflictRegion]) -> None:
        if self._staging is not None:
            self._staging["regions"] = regions
        else:
            self._regions = regions

    def _get_struct(self, key: str):
        if self._staging is not None:
            return self._staging[key]
        # Map internal attr names to staging keys
        attr_map = {
            "communities": "_communities",
            "schema_patterns": "_schema_patterns",
            "topological_laws": "_topological_laws",
            "neighborhood_cohesion": "_neighborhood_cohesion",
            "impossible_neighborhoods": "_impossible_neighborhoods",
            "restructuring_queue": "_restructuring_queue",
            "merge_success": "_cohesion_merge_success",
            "merge_attempts": "_cohesion_merge_attempts",
            "split_success": "_cohesion_split_success",
            "split_attempts": "_cohesion_split_attempts",
            "centrality": "_centrality",
            "anchors": "_anchors",
            "crystalline_atoms": "_crystalline_atoms",
            "meso_clusters": "_meso_clusters",
            "macro_continents": "_macro_continents",
        }
        return getattr(self, attr_map[key])

    def _set_struct(self, key: str, val) -> None:
        if self._staging is not None:
            self._staging[key] = val
            return
        attr_map = {
            "communities": "_communities",
            "schema_patterns": "_schema_patterns",
            "topological_laws": "_topological_laws",
            "neighborhood_cohesion": "_neighborhood_cohesion",
            "impossible_neighborhoods": "_impossible_neighborhoods",
            "restructuring_queue": "_restructuring_queue",
            "merge_success": "_cohesion_merge_success",
            "merge_attempts": "_cohesion_merge_attempts",
            "split_success": "_cohesion_split_success",
            "split_attempts": "_cohesion_split_attempts",
            "centrality": "_centrality",
            "anchors": "_anchors",
            "crystalline_atoms": "_crystalline_atoms",
            "meso_clusters": "_meso_clusters",
            "macro_continents": "_macro_continents",
        }
        setattr(self, attr_map[key], val)

    # ─── Read-Only View — Regions ──────────────────────────────────────

    @property
    def regions(self) -> list[RegionSnapshot]:
        return self.get_view().all_regions()

    def iterate_regions(self):
        """Safe read-only iteration — yields immutable snapshots."""
        view = self.get_view()
        for r in self._get_regions():
            yield view._snapshot(r)

    def region_count(self) -> int:
        return len(self._get_regions())

    def find(self, token: str, roles: set[str], domain: str = "") -> RegionSnapshot | None:
        view = self.get_view()
        for r in self._get_regions():
            if r.token == token and set(r.competing_roles) == roles and getattr(r, "domain", "") == domain:
                return view._snapshot(r)
        return None

    def get_view(self) -> TopologyView:
        return TopologyView(
            regions=self._get_regions(),
            global_communities=self._get_struct("communities"),
            schema_patterns=self._get_struct("schema_patterns"),
            topological_laws=self._get_struct("topological_laws"),
            neighborhood_cohesion=self._get_struct("neighborhood_cohesion"),
            global_centrality=self._get_struct("centrality"),
            impossible_neighborhoods=self._get_struct("impossible_neighborhoods"),
            restructuring_queue=self._get_struct("restructuring_queue"),
            cohesion_merge_success=self._get_struct("merge_success"),
            cohesion_merge_attempts=self._get_struct("merge_attempts"),
            cohesion_split_success=self._get_struct("split_success"),
            cohesion_split_attempts=self._get_struct("split_attempts"),
            meso_clusters=self._get_struct("meso_clusters"),
            macro_continents=self._get_struct("macro_continents"),
            read_callback=self._read_callback,
        )

    def find_region_for_mutation(self, token: str, sorted_roles: tuple) -> str | None:
        for r in self._get_regions():
            if r.token == token and tuple(sorted(r.competing_roles)) == sorted_roles:
                return r.region_id
        return None

    def neighbors_of(self, region_id: Any) -> list[RegionSnapshot]:
        target = self.get_region(region_id)
        if not target:
            return []
        view = self.get_view()
        result = []
        target_roles = set(target.competing_roles)
        for r in self._get_regions():
            if r.region_id != target.region_id and set(r.competing_roles) & target_roles:
                result.append(view._snapshot(r))
        return result

    def get_all_tokens(self) -> list[str]:
        return list({r.token for r in self._get_regions()})

    # ─── Read-Only Accessors — Topology Structures ─────────────────────

    @property
    def global_communities(self) -> list[set[str]]:
        return [set(c) for c in self._get_struct("communities")]

    @property
    def schema_patterns(self) -> dict[tuple[str, str], float]:
        return dict(self._get_struct("schema_patterns"))

    @property
    def topological_laws(self) -> dict:
        return dict(self._get_struct("topological_laws"))

    @property
    def neighborhood_cohesion(self) -> dict[tuple[str, str], float]:
        return dict(self._get_struct("neighborhood_cohesion"))

    @property
    def impossible_neighborhoods(self) -> list[set[str]]:
        return [set(c) for c in self._get_struct("impossible_neighborhoods")]

    @property
    def restructuring_queue(self) -> set[tuple[str, str]]:
        return set(self._get_struct("restructuring_queue"))

    @property
    def global_centrality(self) -> dict[str, float]:
        return dict(self._get_struct("centrality"))

    @property
    def anchors(self) -> set[tuple[str, str]]:
        return set(self._get_struct("anchors"))

    def record_anchor(self, pair: tuple[str, str]) -> None:
        struct = self._get_struct("anchors")
        struct.add(tuple(sorted(pair)))
        self._set_struct("anchors", struct)
        self._record("record_anchor", {"pair": list(pair)})

    def distill_crystalline_atoms(self, integrity_threshold: float = 0.9, instability_threshold: float = 0.1) -> int:
        """Distill stable regions into atoms (Phase 34). Delegates to topology_metrics."""
        return _metrics_distill(self, integrity_threshold, instability_threshold)

    def get_cohesion_merge_success(self) -> dict[tuple[str, str], float]:
        return self._get_struct("merge_success")  # type: ignore[no-any-return]

    def get_cohesion_merge_attempts(self) -> dict[tuple[str, str], float]:
        return self._get_struct("merge_attempts")  # type: ignore[no-any-return]

    def get_cohesion_split_success(self) -> dict[tuple[str, str], float]:
        return self._get_struct("split_success")  # type: ignore[no-any-return]

    def get_cohesion_split_attempts(self) -> dict[tuple[str, str], float]:
        return self._get_struct("split_attempts")  # type: ignore[no-any-return]

    def record_cohesion_merge_attempt(self, pair: tuple) -> None:
        struct = self._get_struct("merge_attempts")
        struct[pair] = struct.get(pair, 0.0) + 1.0
        self._set_struct("merge_attempts", struct)

    def record_cohesion_merge_success(self, pair: tuple) -> None:
        struct = self._get_struct("merge_success")
        struct[pair] = struct.get(pair, 0.0) + 1.0
        self._set_struct("merge_success", struct)

    def set_neighborhood_cohesion(self, pair: tuple, value: float) -> None:
        """Formally set a neighborhood cohesion value (Phase 68)."""
        struct = self._get_struct("neighborhood_cohesion")
        struct[tuple(sorted(pair))] = max(0.0, min(1.0, value))
        self._set_struct("neighborhood_cohesion", struct)
        self._record("set_neighborhood_cohesion", {"pair": pair, "value": value})

    def record_cohesion_split_attempt(self, pair: tuple) -> None:
        struct = self._get_struct("split_attempts")
        struct[pair] = struct.get(pair, 0.0) + 1.0
        self._set_struct("split_attempts", struct)

    def record_cohesion_split_success(self, pair: tuple) -> None:
        struct = self._get_struct("split_success")
        struct[pair] = struct.get(pair, 0.0) + 1.0
        self._set_struct("split_success", struct)

    def detect_communities(self) -> None:
        """Flood-fill communities from cohesion + field regions. Delegates to topology_clustering."""
        _cluster_detect_communities(self)

    def update_schema_patterns(self, exclusion_key: tuple, exclusion_val: float) -> None:
        """Update schema patterns with EMA. Delegates to topology_clustering."""
        _cluster_update_schema(self, exclusion_key, exclusion_val)

    def decay_topological_laws(self) -> None:
        """Apply exponential decay to topological laws. Delegates to topology_clustering."""
        _cluster_decay_laws(self)

    def set_topological_law(self, pair: tuple, value: float) -> None:
        """Set a topological law for a role pair. Delegates to topology_clustering."""
        _cluster_set_law(self, pair, value)

    def add_impossible_neighborhood(self, item: set[str]) -> None:
        """Add an impossible neighborhood. Delegates to topology_clustering."""
        _cluster_add_impossible(self, item)

    def clear_impossible_neighborhoods(self) -> None:
        """Clear impossible neighborhoods. Delegates to topology_clustering."""
        _cluster_clear_impossible(self)

    # ─── Controlled Mutations — Region Lifecycle ───────────────────────

    def add(
        self,
        competing_roles: list[str],
        token: str,
        instability: float = 0.5,
        integrity: float = 0.5,
        domain: str = "",
    ) -> FieldConflictRegion:
        region = FieldConflictRegion(
            competing_roles=list(competing_roles),
            token=token,
            instability=max(0.01, min(1.0, instability)),
            integrity=max(0.1, min(1.0, integrity)),
        )
        if domain:
            region.domain = domain
        regs = self._get_regions()
        regs.append(region)
        self._set_regions(regs)
        if self._staging is not None:
            self._staging["structural_change"] = True
        self._record(
            "add",
            {
                "competing_roles": competing_roles,
                "token": token,
                "instability": instability,
                "integrity": integrity,
                "domain": domain,
            },
        )

        # Phase 71: Emit wave on new region creation
        self.emit_field_wave(region.region_id, instability)

        return region

    def append_region(self, region: FieldConflictRegion) -> None:
        region.instability = max(0.01, min(1.0, region.instability))
        region.integrity = max(0.1, min(1.0, region.integrity))
        regs = self._get_regions()
        regs.append(region)
        self._set_regions(regs)
        if self._staging is not None:
            self._staging["structural_change"] = True
        # We don't record the full object, just enough to reconstruct if needed,
        # or use add() for replay.

    def remove(self, region: FieldConflictRegion) -> bool:
        regs = self._get_regions()
        if region in regs:
            regs.remove(region)
            self._set_regions(regs)
            if self._staging is not None:
                self._staging["structural_change"] = True
                self._staging["tombstones"].add(region.region_id)
            else:
                self._tombstones.add(region.region_id)
            self._record("remove", {"region_id": region.region_id})
            return True
        return False

    def replace_all(self, new_regions: list) -> None:
        """Replace the entire regional manifold (Phase 50)."""
        replace_all_regions(self, new_regions)

    def trim(self, max_size: int, keep_from_end: int = 0) -> None:
        """Trim regions to max_size."""
        trim_topology(self, max_size, keep_from_end)

    def filter_regions(self, predicate: Callable[[FieldConflictRegion], bool]) -> None:
        """Filter regions with a predicate."""
        filter_topology_regions(self, predicate)

    def prune(self, min_instability: float = 0.02, min_energy: float = 0.5) -> int:
        """Prune regions below instability and energy thresholds."""
        return _persistence_prune(self, min_instability, min_energy)

    def garbage_collect(self, max_idle: int = 10) -> int:
        """Resource-aware pruning of dead semantic regions (Phase 9)."""
        return _persistence_gc(self, max_idle)

    def self_prune(self, instability_threshold: float = 0.9, community_required: bool = True) -> int:
        """Autonomous topology pruning (Phase 62). Delegates to topology_clustering."""
        return self_prune_regions(self, instability_threshold, community_required)

    def induce_topological_laws(self, min_success_rate: float = 0.8, min_attempts: int = 10) -> None:
        """Autonomous law discovery (Phase 62). Delegates to topology_clustering."""
        _cluster_induce_laws(self, min_success_rate, min_attempts)

    def clear(self) -> None:
        """Clear all topology structures. Delegates to topology_persistence."""
        clear_topology(self)

    def clear_regions(self) -> None:
        """Clear only the regions list. Delegates to topology_persistence."""
        clear_topology_regions(self)

    # ─── Controlled Mutations — Region Attributes ──────────────────────

    def get_region(self, region_id: Any) -> FieldConflictRegion | None:
        """Internal helper to get a mutable region reference by ID or object."""
        rid = region_id
        if hasattr(region_id, "region_id"):
            rid = region_id.region_id

        for r in self._get_regions():
            if r.region_id == rid:
                return r
        return None

    def set_region_instability(self, region_id: Any, value: float) -> None:
        """Set region instability. Delegates to topology_region_ops."""
        _ops_set_instability(self, region_id, value)

    def adjust_region_instability(self, region_id: Any, delta: float) -> None:
        """Adjust region instability by delta. Delegates to topology_region_ops."""
        _ops_adj_instability(self, region_id, delta)

    def set_region_energy(self, region_id: Any, value: float) -> None:
        """Set region local_energy. Delegates to topology_region_ops."""
        _ops_set_energy(self, region_id, value)

    def adjust_region_energy(self, region_id: Any, delta: float) -> None:
        """Adjust region energy by delta. Delegates to topology_region_ops."""
        _ops_adj_energy(self, region_id, delta)

    def set_region_integrity(self, region_id: Any, value: float) -> None:
        """Set region integrity. Delegates to topology_region_ops."""
        _ops_set_integrity(self, region_id, value)

    def set_region_recurrence(self, region_id: Any, value: float) -> None:
        """Set region recurrence_score. Delegates to topology_region_ops."""
        _ops_set_recurrence(self, region_id, value)

    def adjust_region_recurrence(self, region_id: str, delta: float) -> None:
        """Adjust region recurrence by delta. Delegates to topology_region_ops."""
        _ops_adj_recurrence(self, region_id, delta)

    def set_region_momentum(self, region_id: str, value: float) -> None:
        """Set region stability_momentum. Delegates to topology_region_ops."""
        _ops_set_momentum(self, region_id, value)

    def set_region_persistence(self, region_id: str, value: float) -> None:
        """Set region persistence. Delegates to topology_region_ops."""
        _ops_set_persistence(self, region_id, value)

    def set_region_pressure(self, region_id: str, value: float) -> None:
        """Set region semantic_pressure. Delegates to topology_region_ops."""
        _ops_set_pressure(self, region_id, value)

    def set_region_temperature(self, region_id: str, value: float) -> None:
        """Set region local_temperature. Delegates to topology_region_ops."""
        _ops_set_temperature(self, region_id, value)

    def set_region_convergence(self, region_id: str, value: float) -> None:
        """Set region local_convergence. Delegates to topology_region_ops."""
        _ops_set_convergence(self, region_id, value)

    def update_region_after_recurrence(self, region_id: str, field_pressure: float) -> None:
        """Update region after recurrence event. Delegates to topology_region_ops."""
        _ops_update_after_recurrence(self, region_id, field_pressure)

    def update_local_memory_from_instability(self) -> None:
        """Sync local_memory from instability. Delegates to topology_region_ops."""
        _ops_update_local_memory(self)

    # ─── Edge Field Forces ──────────────────────────────────────────

    def _compute_edge_field_forces(self) -> dict[tuple[str, str], dict[str, float]]:
        """Compute force vectors from the unified edge field for each role pair.

        Delegates to ``topology_forces.compute_edge_field_forces``.
        """
        return _forces_compute(self)

    def _redirect_repulsive_pressure(self, source_region, pressure_amount: float, forces: dict):
        """Redirect repulsive pressure through alternative high-affinity edge field routes.

        Delegates to ``topology_forces.redirect_repulsive_pressure``.
        """
        return _forces_redirect(self, source_region, pressure_amount, forces)

    def route_contradiction(self, role_a: str, role_b: str, strength: float = 0.1) -> dict:
        """Route a contradiction event through the unified edge field.

        Delegates to ``topology_forces.route_contradiction``.
        """
        return _forces_route_contradiction(self, role_a, role_b, strength)

    # ─── Bulk Operations ───────────────────────────────────────────────

    def evolve_all(self, force: bool = False):
        """Evolve all basins modulated by edge field forces and multi-scale feedback.

        Delegates to ``topology_thermodynamics.evolve_all``.
        """
        return _thermo_evolve_all(self, force=force)

    def propagate_all(self):
        """Propagate instability through the unified edge field.

        Delegates to ``topology_thermodynamics.propagate_all``.
        """
        return _thermo_propagate_all(self)

    def redistribute_instability(self, damping: float = 1.0) -> dict:
        """Redistribute instability across regions using thermodynamic free energy gradients.

        Delegates to ``topology_thermodynamics.redistribute_instability``.
        """
        return _thermo_redistribute(self, damping=damping)

    def aggregate_metrics(self):
        """Aggregate region metrics. Delegates to topology_metrics."""
        return compute_aggregate_metrics(self)

    def compute_entropy(self) -> float:
        """Compute global topology entropy. Delegates to topology_metrics."""
        return compute_topology_entropy(self)

    def compute_macro_energy(self, convergence: float) -> float:
        """Compute target macro energy. Delegates to topology_metrics."""
        return _metrics_compute_macro_energy(self, convergence)

    # ─── Multi-Scale Topology (Micro / Meso / Macro) ────────────────────

    @property
    def meso_clusters(self) -> list[dict]:
        """Read-only access to meso cluster data."""
        return list(self._get_struct("meso_clusters"))

    def compute_meso_clusters(self) -> None:
        """Delegate to topology_dynamics.compute_meso_clusters."""
        compute_meso_clusters(self)

    def compute_macro_from_meso(self) -> dict:
        """Delegate to topology_dynamics.compute_macro_from_meso."""
        return compute_macro_from_meso(self)

    def compute_macro_continents(self) -> None:
        """Delegate to topology_dynamics.compute_macro_continents."""
        compute_macro_continents(self)

    def _evolve_meso_clusters(self):
        """Delegate to topology_dynamics.evolve_meso_clusters."""
        return evolve_meso_clusters(self)

    def _evolve_macro_continents(self):
        """Delegate to topology_dynamics.evolve_macro_continents."""
        return evolve_macro_continents(self)

    def cross_scale_pressure_flow(self) -> None:
        """Delegate to topology_dynamics.cross_scale_pressure_flow."""
        cross_scale_pressure_flow(self)

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the full topology state. Delegates to topology_persistence."""
        return topology_to_dict(self)

    def from_dict(self, data: dict) -> None:
        """Deserialize topology state. Delegates to topology_persistence."""
        topology_from_dict(self, data)

    def merge(self, other_data: dict, alpha: float = 0.5) -> None:
        """Merge remote topology state into local (Phase 32 / 60). Delegates to topology_persistence."""
        merge_topology(self, other_data, alpha)

    # ─── Active Field Waves (Decentralized Propagation) ──────────────

    def emit_field_wave(self, source_region_id: str, intensity: float) -> None:
        """Emit a semantic wave from a region. Delegates to topology_waves."""
        _waves_emit(self, source_region_id, intensity)

    def process_field_wave(self, source_region_id: str, intensity: float) -> None:
        """Process a field wave by neighboring regions. Delegates to topology_waves."""
        _waves_process(self, source_region_id, intensity)
