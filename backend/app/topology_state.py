"""TopologyState — owns the field region graph and ALL topology-derived structures.

Re-exports types / helpers from topology_state_types and TopologyView from
topology_view for backward compatibility.
"""

from typing import Any, Callable, Dict, List, Set, Tuple, Optional
from app.core_types import FieldConflictRegion, MAX_COUPLING_TRANSFER
from app.transaction_context import active_transaction

# Re-export public symbols from sub-modules for backward compatibility
from app.topology_state_types import (
    parse_topology_key,
    ConflictError,
    _clamp01,
    _clamp_signed,
    RegionSnapshot,
    EdgeFieldSnapshot,
    MesoClusterSnapshot,
    MacroContinentSnapshot,
)
from app.topology_view import TopologyView

# Multi-scale topology dynamics (extracted for modularity)
from app.topology_dynamics import (
    compute_meso_clusters,
    compute_macro_continents,
    compute_macro_from_meso,
    evolve_meso_clusters,
    evolve_macro_continents,
    cross_scale_pressure_flow,
)
from app.topology_metrics import (
    compute_aggregate_metrics,
    compute_topology_entropy,
    compute_macro_energy as _metrics_compute_macro_energy,
    distill_crystalline_atoms as _metrics_distill,
)
from app.topology_persistence import (
    replace_all_regions,
    trim_topology,
    filter_topology_regions,
    prune_topology as _persistence_prune,
    garbage_collect_topology as _persistence_gc,
    topology_to_dict,
    topology_from_dict,
    merge_topology,
    clear_topology,
    clear_topology_regions,
)
from app.topology_clustering import (
    detect_communities as _cluster_detect_communities,
    shard_topology_regions,
    update_schema_patterns as _cluster_update_schema,
    decay_topological_laws as _cluster_decay_laws,
    set_topological_law as _cluster_set_law,
    add_impossible_neighborhood as _cluster_add_impossible,
    clear_impossible_neighborhoods as _cluster_clear_impossible,
    self_prune_regions,
    induce_topological_laws as _cluster_induce_laws,
)

__all__ = [
    "TopologyState",
    "TopologyView",
    "RegionSnapshot",
    "EdgeFieldSnapshot",
    "MesoClusterSnapshot",
    "MacroContinentSnapshot",
    "ConflictError",
    "parse_topology_key",
    "_clamp01",
    "_clamp_signed",
]


class TopologyState:
    """Sole owner of the semantic field's topology structure."""

    @property
    def _tombstones(self) -> Set[str]:
        tx = self._staging
        if tx is not None:
            return tx["tombstones"]
        return self.__dict__.get("_tombstones_real", set())

    @_tombstones.setter
    def _tombstones(self, value: Set[str]):
        tx = self._staging
        if tx is not None:
            tx["tombstones"] = value
        else:
            self._tombstones_real = value

    @property
    def _structural_change(self) -> bool:
        tx = self._staging
        if tx is not None:
            return tx["structural_change"]
        return False

    @_structural_change.setter
    def _structural_change(self, value: bool):
        tx = self._staging
        if tx is not None:
            tx["structural_change"] = value

    def __init__(
        self,
        delta_callback: Optional[Callable[[str, str, dict], None]] = None,
        read_callback: Optional[Callable[[str, int], None]] = None,
    ):
        self._delta_callback = delta_callback
        self._read_callback = read_callback
        # ─── Region Graph ──────────────────────────────────────────────
        self._regions: List[FieldConflictRegion] = []

        # ─── Topology-Derived Structures ───────────────────────────────
        self._communities: List[Set[str]] = []
        self._schema_patterns: Dict[Tuple[str, str], float] = {}
        self._topological_laws: dict = {}
        self._neighborhood_cohesion: Dict[Tuple[str, str], float] = {}
        self._centrality: Dict[str, float] = {}
        self._impossible_neighborhoods: List[Set[str]] = []
        self._restructuring_queue: Set[Tuple[str, str]] = set()
        self._cohesion_merge_success: Dict[Tuple[str, str], float] = {}
        self._cohesion_merge_attempts: Dict[Tuple[str, str], float] = {}
        self._cohesion_split_success: Dict[Tuple[str, str], float] = {}
        self._cohesion_split_attempts: Dict[Tuple[str, str], float] = {}
        self._anchors: Set[Tuple[str, str]] = set()
        self._crystalline_atoms: List[dict] = []

        # ─── Meso Clusters (Multi-Scale Topology) ────────────────────
        self._meso_clusters: List[dict] = []

        # ─── Macro Continents (Multi-Scale Topology) ──────────────────
        self._macro_continents: List[dict] = []
        self._last_pressure_flow_time: float = 0.0

        # ─── Distributed Recovery (Phase 60) ──────────────────────────
        self._topology_epoch: int = 1

        # ─── Transaction Staging ──────────────────────────────────────

    @property
    def _staging(self) -> Optional[dict]:
        tx = active_transaction.get()
        if tx is not None:
            return tx.get(f"topology_staging_{id(self)}")
        return None

    @_staging.setter
    def _staging(self, value: Optional[dict]):
        tx = active_transaction.get()
        if tx is not None:
            tx[f"topology_staging_{id(self)}"] = value

    @property
    def _modified_regions(self) -> Set[str]:
        tx = active_transaction.get()
        if tx is not None:
            key = f"topology_modified_{id(self)}"
            if key not in tx:
                tx[key] = set()
            return tx[key]
        return set()

    def _record(self, action: str, details: dict):
        if "region_id" in details:
            self._modified_regions.add(details["region_id"])
        if self._delta_callback:
            self._delta_callback("topology", action, details)

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self):
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

    def commit(self, expected_versions: Optional[Dict[str, int]] = None):
        """Apply staged changes to the active state with MVCC validation."""
        if self._staging is not None:
            # 1. Optimistic Validation (Phase 51)
            if expected_versions:
                for rid, expected in expected_versions.items():
                    # Find live region
                    live = next((r for r in self._regions if r.region_id == rid), None)
                    if live and live.version != expected:
                        raise ConflictError(f"MVCC CONFLICT: Region [{rid}] version {
                            live.version} != expected {expected}")

            # 2. Increment versions for all modified regions
            for rid in self._modified_regions:
                r_staged = next((r for r in self._staging["regions"] if r.region_id == rid), None)
                if r_staged:
                    r_staged.version += 1

            # Phase 60: Structural Epoch increment
            if self._staging["structural_change"]:
                self._topology_epoch += 1

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
            self._tombstones_real = self._staging["tombstones"]

            self._staging = None
            self._modified_regions.clear()

    def rollback(self):
        """Discard staged changes."""
        self._staging = None
        self._modified_regions.clear()
        self._structural_change = False

    def restructure_topology(self, target_region_ids: Optional[List[str]] = None):
        """Forcibly rewire the substrate to escape metastable locks (Phase 52).

        Breaks strong cohesion edges and increases regional temperature to
        encourage discovery of new topological minima.
        """
        regs = self._get_regions()
        targets = target_region_ids if target_region_ids else [r.region_id for r in regs if r.instability < 0.1]

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

    def shard_topology(self) -> Dict[str, List[str]]:
        """Assign every region to a shard based on community membership (Phase 53). Delegates to topology_clustering."""
        return shard_topology_regions(self)

    def _get_regions(self) -> List[FieldConflictRegion]:
        return self._staging["regions"] if self._staging is not None else self._regions

    def _set_regions(self, regions: List[FieldConflictRegion]):
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

    def _set_struct(self, key: str, val):
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
    def regions(self) -> List[RegionSnapshot]:
        return self.get_view().all_regions()

    def iterate_regions(self):
        """Safe read-only iteration — yields immutable snapshots."""
        view = self.get_view()
        for r in self._get_regions():
            yield view._snapshot(r)

    def region_count(self) -> int:
        return len(self._get_regions())

    def find(self, token: str, roles: Set[str], domain: str = "") -> Optional[RegionSnapshot]:
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

    def find_region_for_mutation(self, token: str, sorted_roles: tuple) -> Optional[str]:
        for r in self._get_regions():
            if r.token == token and tuple(sorted(r.competing_roles)) == sorted_roles:
                return r.region_id
        return None

    def neighbors_of(self, region_id: Any) -> List[RegionSnapshot]:
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

    def get_all_tokens(self) -> List[str]:
        return list(set(r.token for r in self._get_regions()))

    # ─── Read-Only Accessors — Topology Structures ─────────────────────

    @property
    def global_communities(self) -> List[Set[str]]:
        return [set(c) for c in self._get_struct("communities")]

    @property
    def schema_patterns(self) -> Dict[Tuple[str, str], float]:
        return dict(self._get_struct("schema_patterns"))

    @property
    def topological_laws(self) -> dict:
        return dict(self._get_struct("topological_laws"))

    @property
    def neighborhood_cohesion(self) -> Dict[Tuple[str, str], float]:
        return dict(self._get_struct("neighborhood_cohesion"))

    @property
    def impossible_neighborhoods(self) -> List[Set[str]]:
        return [set(c) for c in self._get_struct("impossible_neighborhoods")]

    @property
    def restructuring_queue(self) -> Set[Tuple[str, str]]:
        return set(self._get_struct("restructuring_queue"))

    @property
    def global_centrality(self) -> Dict[str, float]:
        return dict(self._get_struct("centrality"))

    @property
    def anchors(self) -> Set[Tuple[str, str]]:
        return set(self._get_struct("anchors"))

    def record_anchor(self, pair: Tuple[str, str]):
        struct = self._get_struct("anchors")
        struct.add(tuple(sorted(pair)))
        self._set_struct("anchors", struct)
        self._record("record_anchor", {"pair": list(pair)})

    def distill_crystalline_atoms(self, integrity_threshold: float = 0.9, instability_threshold: float = 0.1) -> int:
        """Distill stable regions into atoms (Phase 34). Delegates to topology_metrics."""
        return _metrics_distill(self, integrity_threshold, instability_threshold)

    def get_cohesion_merge_success(self) -> Dict[Tuple[str, str], float]:
        return self._get_struct("merge_success")

    def get_cohesion_merge_attempts(self) -> Dict[Tuple[str, str], float]:
        return self._get_struct("merge_attempts")

    def get_cohesion_split_success(self) -> Dict[Tuple[str, str], float]:
        return self._get_struct("split_success")

    def get_cohesion_split_attempts(self) -> Dict[Tuple[str, str], float]:
        return self._get_struct("split_attempts")

    def record_cohesion_merge_attempt(self, pair: tuple):
        struct = self._get_struct("merge_attempts")
        struct[pair] = struct.get(pair, 0.0) + 1.0
        self._set_struct("merge_attempts", struct)

    def record_cohesion_merge_success(self, pair: tuple):
        struct = self._get_struct("merge_success")
        struct[pair] = struct.get(pair, 0.0) + 1.0
        self._set_struct("merge_success", struct)

    def set_neighborhood_cohesion(self, pair: tuple, value: float):
        """Formally set a neighborhood cohesion value (Phase 68)."""
        struct = self._get_struct("neighborhood_cohesion")
        struct[tuple(sorted(pair))] = max(0.0, min(1.0, value))
        self._set_struct("neighborhood_cohesion", struct)
        self._record("set_neighborhood_cohesion", {"pair": pair, "value": value})

    def record_cohesion_split_attempt(self, pair: tuple):
        struct = self._get_struct("split_attempts")
        struct[pair] = struct.get(pair, 0.0) + 1.0
        self._set_struct("split_attempts", struct)

    def record_cohesion_split_success(self, pair: tuple):
        struct = self._get_struct("split_success")
        struct[pair] = struct.get(pair, 0.0) + 1.0
        self._set_struct("split_success", struct)

    def detect_communities(self):
        """Flood-fill communities from cohesion + field regions. Delegates to topology_clustering."""
        _cluster_detect_communities(self)

    def update_schema_patterns(self, exclusion_key: tuple, exclusion_val: float):
        """Update schema patterns with EMA. Delegates to topology_clustering."""
        _cluster_update_schema(self, exclusion_key, exclusion_val)

    def decay_topological_laws(self):
        """Apply exponential decay to topological laws. Delegates to topology_clustering."""
        _cluster_decay_laws(self)

    def set_topological_law(self, pair: tuple, value: float):
        """Set a topological law for a role pair. Delegates to topology_clustering."""
        _cluster_set_law(self, pair, value)

    def add_impossible_neighborhood(self, item: Set[str]):
        """Add an impossible neighborhood. Delegates to topology_clustering."""
        _cluster_add_impossible(self, item)

    def clear_impossible_neighborhoods(self):
        """Clear impossible neighborhoods. Delegates to topology_clustering."""
        _cluster_clear_impossible(self)

    # ─── Controlled Mutations — Region Lifecycle ───────────────────────

    def add(
        self, competing_roles: List[str], token: str, instability: float = 0.5, integrity: float = 0.5, domain: str = ""
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

    def append_region(self, region: FieldConflictRegion):
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

    def replace_all(self, new_regions: list):
        """Replace the entire regional manifold (Phase 50)."""
        replace_all_regions(self, new_regions)

    def trim(self, max_size: int, keep_from_end: int = 0):
        """Trim regions to max_size."""
        trim_topology(self, max_size, keep_from_end)

    def filter_regions(self, predicate: Callable[[FieldConflictRegion], bool]):
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

    def induce_topological_laws(self, min_success_rate: float = 0.8, min_attempts: int = 10):
        """Autonomous law discovery (Phase 62). Delegates to topology_clustering."""
        _cluster_induce_laws(self, min_success_rate, min_attempts)

    def clear(self):
        """Clear all topology structures. Delegates to topology_persistence."""
        clear_topology(self)

    def clear_regions(self):
        """Clear only the regions list. Delegates to topology_persistence."""
        clear_topology_regions(self)

    # ─── Controlled Mutations — Region Attributes ──────────────────────

    def get_region(self, region_id: Any) -> Optional[FieldConflictRegion]:
        """Internal helper to get a mutable region reference by ID or object."""
        rid = region_id
        if hasattr(region_id, "region_id"):
            rid = region_id.region_id

        for r in self._get_regions():
            if r.region_id == rid:
                return r
        return None

    def set_region_instability(self, region_id: Any, value: float):
        r = self.get_region(region_id)
        if r:
            old_val = r.instability
            r.instability = max(0.01, min(1.0, value))
            self._record("set_region_instability", {"region_id": r.region_id, "value": value})

            # Phase 71: Emit wave on significant instability spike
            delta = value - old_val
            if delta > 0.15:
                self.emit_field_wave(r.region_id, delta)

    def adjust_region_instability(self, region_id: Any, delta: float):
        r = self.get_region(region_id)
        if r:
            self.set_region_instability(r.region_id, r.instability + delta)

    def set_region_energy(self, region_id: Any, value: float):
        r = self.get_region(region_id)
        if r:
            r.local_energy = max(0.0, min(10.0, value))
            self._record("set_region_energy", {"region_id": r.region_id, "value": value})

    def adjust_region_energy(self, region_id: Any, delta: float):
        r = self.get_region(region_id)
        if r:
            self.set_region_energy(r.region_id, r.local_energy + delta)

    def set_region_integrity(self, region_id: Any, value: float):
        r = self.get_region(region_id)
        if r:
            r.integrity = max(0.1, min(1.0, value))
            self._record("set_region_integrity", {"region_id": r.region_id, "value": value})

    def set_region_recurrence(self, region_id: Any, value: float):
        r = self.get_region(region_id)
        if r:
            r.recurrence_score = max(0.0, min(1.0, value))
            self._record("set_region_recurrence", {"region_id": r.region_id, "value": value})

    def adjust_region_recurrence(self, region_id: str, delta: float):
        r = self.get_region(region_id)
        if r:
            self.set_region_recurrence(region_id, r.recurrence_score + delta)

    def set_region_momentum(self, region_id: str, value: float):
        r = self.get_region(region_id)
        if r:
            r.stability_momentum = max(0.0, min(1.0, value))
            self._record("set_region_momentum", {"region_id": r.region_id, "value": value})

    def set_region_persistence(self, region_id: str, value: float):
        r = self.get_region(region_id)
        if r:
            r.persistence = max(0.0, min(2.0, value))
            self._record("set_region_persistence", {"region_id": r.region_id, "value": value})

    def set_region_pressure(self, region_id: str, value: float):
        r = self.get_region(region_id)
        if r:
            r.semantic_pressure = value
            self._record("set_region_pressure", {"region_id": r.region_id, "value": value})

    def set_region_temperature(self, region_id: str, value: float):
        r = self.get_region(region_id)
        if r:
            r.local_temperature = max(0.0, min(1.0, value))
            self._record("set_region_temperature", {"region_id": r.region_id, "value": value})

    def set_region_convergence(self, region_id: str, value: float):
        r = self.get_region(region_id)
        if r:
            r.local_convergence = max(0.0, min(1.0, value))
            self._record("set_region_convergence", {"region_id": r.region_id, "value": value})

    def update_region_after_recurrence(self, region_id: str, field_pressure: float):
        r = self.get_region(region_id)
        if not r:
            return
        target_instability = min(1.0, r.instability + 0.15)
        r.stability_momentum = r.stability_momentum * 0.7 + 0.3 * target_instability
        r.instability = r.stability_momentum
        r.recurrence_score = min(1.0, r.recurrence_score + 0.1)
        r.semantic_pressure = field_pressure
        r.persistence = max(0.5, r.persistence - 0.1)

    def update_local_memory_from_instability(self):
        for r in self._get_regions():
            for role in r.competing_roles:
                r.local_memory[str(role)] = r.instability

    # ─── Edge Field Forces ──────────────────────────────────────────

    def _compute_edge_field_forces(self) -> Dict[Tuple[str, str], Dict[str, float]]:
        """Compute force vectors from the unified edge field for each role pair.

        Returns a dict mapping (role_a, role_b) -> {
            'affinity': float,
            'repulsion': float,
            'pressure': float,
            'route_strength': float,
            'semantics': str
        }

        LAW: Edge field forces are the canonical driver of all topology dynamics.
        No external code should recompute forces from raw cohesion / law data.
        """
        view = self.get_view()
        forces: Dict[Tuple[str, str], Dict[str, float | str]] = {}
        for edge in view.get_edge_fields():
            # type: ignore[assignment]
            pair = tuple(sorted([edge.source, edge.target]))
            forces[pair] = {  # type: ignore[arg-type, index]
                "affinity": edge.affinity,
                "repulsion": edge.repulsion,
                "pressure": edge.pressure,
                "route_strength": edge.route_strength,
                "semantics": edge.semantics,
            }
        return forces  # type: ignore[return-value]

    def _redirect_repulsive_pressure(self, source_region, pressure_amount: float, forces: dict):
        """Redirect repulsive pressure through alternative high-affinity edge field routes.

        When a repulsive edge blocks direct scalar exclusion propagation, this method:
        1. Finds high-affinity alternative routes from the source region's roles
        2. Redirects pressure to target regions via those routes
        3. Updates target region instability and semantic_pressure
        4. Heats the source region with any unredirected remainder

        All target region mutations are recorded via _record() to ensure
        the delta system and MVCC commit correctly track all changes.

        LAW: Repulsive edges do not only store exclusion values — they redirect
        uncertainty and pressure waves through the topology via alternative
        high-affinity routes, creating dynamic field-level redistribution.
        """
        # 1. Find high-affinity routes from the source region's roles
        route_targets: dict[str, float] = {}  # target_role -> weight
        for role in source_region.competing_roles:
            for pair, force in forces.items():
                if role not in pair:
                    continue
                peer = pair[0] if pair[1] == role else pair[1]
                if peer in source_region.competing_roles:
                    continue
                # High-affinity edges with decent route_strength are good
                # targets
                if force["affinity"] > 0.3 and force["route_strength"] > 0.2:
                    weight = force["affinity"] * force["route_strength"]
                    if peer not in route_targets or weight > route_targets[peer]:
                        route_targets[peer] = weight

        if not route_targets:
            # No alternative routes: dissipate trapped pressure as heat
            source_region.local_temperature = min(1.0, source_region.local_temperature + pressure_amount * 0.1)
            self._record(
                "redirect_repulsive_pressure_dissipate",
                {
                    "region_id": source_region.region_id,
                    "pressure_amount": round(pressure_amount, 4),
                },
            )
            return

        # 2. Normalize weights and redirect pressure
        total_weight = sum(route_targets.values())
        regs = self._get_regions()
        redirected = 0.0
        affected_targets = []

        for target_role, weight in route_targets.items():
            redirect_amount = (weight / total_weight) * pressure_amount * 0.5
            # Find target regions containing this role
            for target_r in regs:
                if target_role in target_r.competing_roles and target_r.region_id != source_region.region_id:
                    # Apply edge-field-modulated pressure to target region
                    # state
                    target_r.instability = min(1.0, target_r.instability + redirect_amount * 0.05)
                    target_r.semantic_pressure = max(0.0, target_r.semantic_pressure + redirect_amount * 0.03)
                    redirected += redirect_amount
                    affected_targets.append(target_r.region_id)
                    # Record each target mutation for MVCC tracking
                    self._record(
                        "redirect_pressure_to_target",
                        {
                            "region_id": target_r.region_id,  # MVCC: track target as modified
                            "source": source_region.region_id,
                            "target_role": target_role,
                            "redirect_amount": round(redirect_amount, 4),
                            "new_instability": round(target_r.instability, 4),
                            "new_pressure": round(target_r.semantic_pressure, 4),
                        },
                    )
                    break

        # 3. Any unredirected pressure heats the source (thermodynamic
        # dissipation)
        remaining = pressure_amount - redirected
        if remaining > 0.01:
            source_region.local_temperature = min(1.0, source_region.local_temperature + remaining * 0.05)
            self._record(
                "redirect_repulsive_pressure_remainder",
                {
                    "region_id": source_region.region_id,
                    "remaining_heat": round(remaining, 4),
                },
            )

    def route_contradiction(self, role_a: str, role_b: str, strength: float = 0.1) -> dict:
        """Route a contradiction event through the unified edge field.

        Instead of only storing a scalar exclusion value, this method:
        1. Looks up the edge field for the contradicting roles
        2. If the edge is repulsive, redirects pressure via high-affinity routes
        3. Updates topological laws and region-level state
        4. Returns flow tracking data for the caller

        LAW: Contradiction pressure flows through the unified edge field.
        Repulsive edges redirect uncertainty and pressure waves through
        alternative high-affinity routes, not just scalar exclusions.

        Args:
            role_a: First role in the contradiction pair
            role_b: Second role in the contradiction pair
            strength: How strong the contradiction pressure is (0 - 1)

        Returns:
            dict with:
            - redirected: pressure redirected through alternative routes
            - excluded: pressure that still goes to scalar exclusion
            - through_edge_field: whether edge field data was available
        """
        forces = self._compute_edge_field_forces()
        pair = tuple(sorted([role_a, role_b]))  # type: ignore[assignment]
        force = forces.get(pair, {})  # type: ignore[arg-type]

        if not force:
            # No edge field data for this pair: establish a basic repulsive topological law
            # An empty force dict {} means the pair was not found in
            # get_edge_fields()
            current = self._topological_laws.get(pair, 0.0)
            self.set_topological_law(pair, min(current - strength * 0.3, -0.01))
            return {"redirected": 0.0, "excluded": strength, "through_edge_field": False}

        is_repulsive = force.get("semantics") == "repulsive" or force.get("repulsion", 0) > 0.3

        if is_repulsive:
            # Repulsive edge: redirect pressure via the topology, not scalar
            # exclusion
            for r in self._get_regions():
                if role_a in r.competing_roles or role_b in r.competing_roles:
                    self._redirect_repulsive_pressure(r, strength * 0.5, forces)

            # Strengthen the repulsive topological law to encode the
            # contradiction
            current_law = self._topological_laws.get(pair, 0.0)
            self.set_topological_law(pair, min(current_law - strength * 0.1, -0.01))

            return {
                "redirected": round(strength * 0.5, 4),
                "excluded": round(strength * 0.1, 4),
                "through_edge_field": True,
            }
        else:
            # Non-repulsive pair contradicting: establish / strengthen a
            # repulsive law
            current_law = self._topological_laws.get(pair, 0.0)
            self.set_topological_law(pair, min(current_law - strength * 0.2, -0.01))

            return {
                "redirected": 0.0,
                "excluded": round(strength * 0.8, 4),
                "through_edge_field": True,
            }

    # ─── Bulk Operations ───────────────────────────────────────────────

    def evolve_all(self, force: bool = False):
        """Evolve all basins modulated by edge field forces and multi-scale feedback.

        Returns list of (exclusion_key, delta) effects for the caller to
        apply through InstabilityState APIs.

        Multi-scale evolution:
        1. Micro: edge field forces (pressure, affinity) modulate per-region evolution
        2. Meso: clusters of related regions exert top-down feedback
        3. Macro: continents provide long-range ecological governance
        4. Cross-scale: pressure flows bidirectionally between all scales

        LAW: Edge field forces (pressure, affinity) modulate evolution speed.
        High pressure regions evolve faster; high affinity regions stabilize.
        Meso clusters and macro continents provide field-derived multi-scale coupling.
        All scales interact through the cross-scale pressure flow.
        """
        forces = self._compute_edge_field_forces()

        # 1. Compute meso clusters and macro continents BEFORE evolving
        #    (so feedback is from previous cycle's state)
        self.compute_meso_clusters()
        self.compute_macro_continents()

        survivors = []
        all_effects = []
        for r in self._get_regions():
            # Compute edge field force on this region
            region_pressure = 0.0
            region_affinity = 0.0
            roles = r.competing_roles
            for i in range(len(roles)):
                for j in range(i + 1, len(roles)):
                    # type: ignore[assignment]
                    pair = tuple(sorted([roles[i], roles[j]]))
                    f = forces.get(pair)  # type: ignore[arg-type]
                    if f:
                        region_pressure = max(region_pressure, f["pressure"])
                        region_affinity = max(region_affinity, f["affinity"])

            # Edge field modulates evolution
            # High pressure forces evolution; high affinity adds stability
            local_force = force or region_pressure > 0.3
            if region_pressure > 0.3:
                r.semantic_pressure = region_pressure

            effects = r.evolve(force=local_force)
            all_effects.extend(effects)

            # Survival: high affinity keeps regions alive even at low
            # instability
            if r.instability > 0.001 or r.idle_cycles < 20 or region_affinity > 0.4:
                survivors.append(r)

        self._set_regions(survivors)

        # 2. Apply full cross-scale pressure flow
        #    Meso → Micro feedback + Macro → Meso guidance + complete sync
        self.cross_scale_pressure_flow()

        return all_effects

    def propagate_all(self):
        """Propagate instability through the unified edge field.

        When repulsive edges are encountered, instead of only emitting scalar
        exclusion effects, this method redirects the pressure wave through
        alternative high-affinity routes in the edge field. This converts
        scalar exclusion learning into dynamic field-level pressure routing.

        Returns list of (exclusion_key, delta) effects for the caller to
        apply through InstabilityState APIs. Some pressure is also redirected
        internally via _redirect_repulsive_pressure(), directly updating
        region-level state (instability, semantic_pressure, temperature).

        LAW: Propagation follows edge field forces, not ROLE_EXCLUSIVITY.
        Instability flows along edge field connections, modulated by
        the edge field's pressure, repulsion, and route strength.
        Repulsive edges redirect flow; they don't just store scalar values.
        """
        forces = self._compute_edge_field_forces()
        all_effects = []
        for r in self._get_regions():
            effects = []
            repulsive_pressure = 0.0

            for role in r.competing_roles:
                # Find all edges from this role in the edge field
                for pair, force in forces.items():
                    if role not in pair:
                        continue
                    peer = pair[0] if pair[1] == role else pair[1]
                    if peer in r.competing_roles:
                        continue  # Don't propagate within the same region

                    # Edge-field-modulated propagation
                    # pressure amplifies spread, affinity dampens
                    spread_potential = r.instability * force["pressure"]

                    if force["semantics"] == "repulsive":
                        # ─── Repulsive Edge: Redirect Through Edge Field ───
                        # Accumulate pressure for redirection through alternative
                        # high-affinity routes instead of only scalar exclusion
                        repulsive_pressure += spread_potential * MAX_COUPLING_TRANSFER
                        # Still emit a minimal exclusion signal for learning
                        # continuity
                        spread = spread_potential * MAX_COUPLING_TRANSFER * 0.1
                        if spread > 0.001:
                            effects.append((pair, spread))
                    elif force["semantics"] == "attractive":
                        # Attractive edges propagate but dampened by
                        # containment
                        spread = spread_potential * MAX_COUPLING_TRANSFER * 0.3
                        if spread > 0.001:
                            effects.append((pair, spread))
                            # Also propagate instability directly through
                            # attractive edges
                            for target_r in self._get_regions():
                                if peer in target_r.competing_roles and target_r.region_id != r.region_id:
                                    target_r.instability = min(1.0, target_r.instability + spread * 0.005)
                                    break
                    else:
                        spread = spread_potential * MAX_COUPLING_TRANSFER * 0.5
                        if spread > 0.001:
                            effects.append((pair, spread))

            # Redirect accumulated repulsive pressure through edge field routes
            if repulsive_pressure > 0.01:
                self._redirect_repulsive_pressure(r, repulsive_pressure, forces)
                self._record(
                    "redirect_repulsive_pressure",
                    {
                        "region_id": r.region_id,
                        "pressure_redirected": round(repulsive_pressure, 4),
                    },
                )

            if not effects:
                # Fallback: use legacy propagation when no edge field exists
                effects = r.propagate()
            all_effects.extend(effects)
        return all_effects

    def redistribute_instability(self, damping: float = 1.0) -> dict:
        """Redistribute instability across regions using thermodynamic free energy gradients.

        LAW 14: Instability is a fluid that flows from high free-energy to low free-energy
        regions via edge field conductance. Flow = conductance * d(free_energy) * coefficient.

        Free energy = local_energy - local_temperature * instability.
        Regions with higher free energy (more trapped tension) transfer instability
        to regions with lower free energy (more stable) through edge field connections.

        Returns dict with flow tracking data for energy conservation recording.
        """
        from app.field_laws import COUPLING_COEFFICIENT, FREE_ENERGY_CLAMP

        regs = self._get_regions()
        if len(regs) < 2:
            return {"total_flow": 0.0, "source_flow": 0.0, "sink_flow": 0.0, "pairs_coupled": 0}

        forces = self._compute_edge_field_forces()

        # Compute free energy for each region
        # free_energy = internal_energy - temperature * entropy
        free_energies = {}
        for r in regs:
            fe = r.local_energy - r.local_temperature * r.instability
            free_energies[r.region_id] = fe

        # 1. Compute flows using thermodynamic free energy gradient
        deltas = {r.region_id: 0.0 for r in regs}
        source_flow = 0.0  # Flow OUT of source regions
        sink_flow = 0.0  # Flow INTO sink regions
        pairs_coupled = 0

        for i in range(len(regs)):
            for j in range(i + 1, len(regs)):
                ri = regs[i]
                rj = regs[j]

                # Compute edge field conductance between these regions
                # Conductance = max route_strength across all shared role pairs
                edge_conductance = 0.0
                for ra in ri.competing_roles:
                    for rb in rj.competing_roles:
                        # type: ignore[assignment]
                        pair = tuple(sorted([ra, rb]))
                        force = forces.get(pair)  # type: ignore[arg-type]
                        if force:
                            # Edge conductance = route_strength (how well
                            # signals flow)
                            edge_conductance = max(edge_conductance, force["route_strength"])

                if edge_conductance < 0.01:
                    continue  # No field connection: no thermodynamic coupling

                pairs_coupled += 1

                # Thermodynamic free energy gradient
                fe_ri = free_energies[ri.region_id]
                fe_rj = free_energies[rj.region_id]
                fe_gradient = fe_ri - fe_rj

                # Clamp gradient to prevent extreme oscillations
                fe_gradient = max(-FREE_ENERGY_CLAMP, min(FREE_ENERGY_CLAMP, fe_gradient))

                # Flow = conductance * gradient * damping * coefficient
                # This is analogous to Ohm's law: I = G * V
                # Flow direction: positive = ri → rj (ri loses instability, rj
                # gains)
                flow = edge_conductance * fe_gradient * damping * COUPLING_COEFFICIENT
                flow = max(-0.1, min(0.1, flow))

                deltas[ri.region_id] -= flow
                deltas[rj.region_id] += flow

                if flow > 0:
                    source_flow += flow
                    sink_flow += flow
                else:
                    source_flow += abs(flow)
                    sink_flow += abs(flow)

        # 2. Apply deltas
        for rid, delta in deltas.items():
            if abs(delta) > 1e-6:
                r = self.get_region(rid)  # type: ignore[assignment]
                if r is not None:
                    self.set_region_instability(rid, r.instability + delta)

        total_flow = round(sum(abs(d) for d in deltas.values()), 4)
        self._record(
            "redistribute_instability",
            {
                "count": len(regs),
                "total_flow": total_flow,
                "pairs_coupled": pairs_coupled,
            },
        )

        return {
            "total_flow": total_flow,
            "source_flow": round(source_flow, 4),
            "sink_flow": round(sink_flow, 4),
            "pairs_coupled": pairs_coupled,
        }

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
    def meso_clusters(self) -> List[dict]:
        """Read-only access to meso cluster data."""
        return list(self._get_struct("meso_clusters"))

    def compute_meso_clusters(self):
        """Delegate to topology_dynamics.compute_meso_clusters."""
        compute_meso_clusters(self)

    def compute_macro_from_meso(self) -> dict:
        """Delegate to topology_dynamics.compute_macro_from_meso."""
        return compute_macro_from_meso(self)

    def compute_macro_continents(self):
        """Delegate to topology_dynamics.compute_macro_continents."""
        compute_macro_continents(self)

    def _evolve_meso_clusters(self):
        """Delegate to topology_dynamics.evolve_meso_clusters."""
        return evolve_meso_clusters(self)

    def _evolve_macro_continents(self):
        """Delegate to topology_dynamics.evolve_macro_continents."""
        return evolve_macro_continents(self)

    def cross_scale_pressure_flow(self):
        """Delegate to topology_dynamics.cross_scale_pressure_flow."""
        cross_scale_pressure_flow(self)

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the full topology state. Delegates to topology_persistence."""
        return topology_to_dict(self)

    def from_dict(self, data: dict):
        """Deserialize topology state. Delegates to topology_persistence."""
        topology_from_dict(self, data)

    def merge(self, other_data: dict, alpha: float = 0.5):
        """Merge remote topology state into local (Phase 32 / 60). Delegates to topology_persistence."""
        merge_topology(self, other_data, alpha)

    # ─── Active Field Waves (Decentralized Propagation) ──────────────

    def emit_field_wave(self, source_region_id: str, intensity: float):
        """Emit a semantic wave from a region into the field.

        Instead of a global scheduler calling propagate(), individual regions
        now emit "waves" that ripple through the topology.
        """
        if intensity < 0.01:
            return

        from app.event_dispatcher import get_dispatcher
        from app.semantic_events import SemanticEvent, SemanticEventType

        get_dispatcher().dispatch(
            SemanticEvent(
                event_type=SemanticEventType.FIELD_WAVE,
                source=f"region:{source_region_id}",
                payload={"intensity": intensity, "source_id": source_region_id},
                instability_delta=intensity * 0.1,
            )
        )

    def process_field_wave(self, source_region_id: str, intensity: float):
        """Reactive handling of a field wave by neighboring regions."""
        source = self.get_region(source_region_id)
        if not source:
            return

        forces = self._compute_edge_field_forces()
        regs = self._get_regions()

        # 1. Propagate along edge field forces
        for target in regs:
            if target.region_id == source_region_id:
                continue

            # Find max route strength between any shared role pairs
            max_route = 0.0
            for ra in source.competing_roles:
                for rb in target.competing_roles:
                    pair = tuple(sorted([ra, rb]))  # type: ignore[assignment]
                    f = forces.get(pair)  # type: ignore[arg-type]
                    if f:
                        max_route = max(max_route, f["route_strength"])

            if max_route > 0.1:
                # Wave intensity decays as it spreads
                absorption = getattr(target, "persistence", 0.5) * 0.2
                received_intensity = intensity * max_route * (1.0 - absorption)

                if received_intensity > 0.01:
                    # Update target region
                    # Phase 71: Intensity now has a stronger impact to overcome
                    # natural decay
                    target.instability = min(1.0, target.instability + received_intensity * 0.3)
                    target.semantic_pressure = max(0.0, target.semantic_pressure + received_intensity * 0.1)

                    # High intensity waves trigger immediate evolution pass
                    if received_intensity > 0.4:
                        target.evolve(force=True)

                    self._record(
                        "wave_absorption",
                        {
                            "region_id": target.region_id,
                            "source_id": source_region_id,
                            "intensity": round(received_intensity, 4),
                        },
                    )

                    # Phase 71: Causal telemetry for field waves
                    from app.semantic_world_state import get_world_state

                    ws = get_world_state()
                    ws.emit_telemetry(
                        "wave_absorption",
                        {
                            "region_id": target.region_id,
                            "source_id": source_region_id,
                            "intensity": round(received_intensity, 4),
                        },
                    )

                    # Causal chaining: target may emit its own (weaker) wave
                    # (modulated to prevent infinite feedback loops)
                    if received_intensity > 0.2:
                        # Schedule next wave hop via dispatcher to avoid deep
                        # recursion
                        from app.graph_update_scheduler import get_scheduler, TaskPriority

                        get_scheduler().schedule(
                            f"wave_hop:{target.region_id}",
                            TaskPriority.NORMAL,
                            self.emit_field_wave,
                            target.region_id,
                            received_intensity * 0.5,
                        )
