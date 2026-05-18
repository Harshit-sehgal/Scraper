"""TopologyState — owns the field region graph and ALL topology-derived structures.

True ownership boundary: NO external code should mutate field_regions,
global_communities, schema_patterns, topological_laws, or cohesion
structures directly. All topology changes go through this state object.
"""

from typing import Callable, Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from app.core_types import FieldConflictRegion, MAX_COUPLING_TRANSFER
from app.transaction_context import active_transaction

class ConflictError(Exception):
    """Raised when an optimistic concurrency conflict is detected."""
    pass


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp_signed(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


# ─── RegionSnapshot: Immutable Read-Only View ──────────────────────────────

@dataclass(frozen=True)
class RegionSnapshot:
    """Frozen, immutable representation of a field region for read-only access.
    
    This is the ONLY way external code should read region data.
    FieldConflictRegion dataclass instances are mutable — never expose them directly.
    """
    region_id: str
    token: str
    competing_roles: tuple
    instability: float
    local_energy: float
    integrity: float
    recurrence_score: float
    persistence: float
    semantic_pressure: float
    stability_momentum: float
    free_energy: float  # thermodynamic potential = local_energy - local_temperature * instability
    local_convergence: float
    local_temperature: float
    source_record: str
    domain: str
    version: int # For validation


@dataclass(frozen=True)
class EdgeFieldSnapshot:
    """Unified read model for role-pair topology forces.

    This is derived from topology-owned structures only. It does not create a
    second edge authority; it makes existing cohesion/law/region pressure
    observable through one bounded field representation.
    """
    source: str
    target: str
    affinity: float
    repulsion: float
    uncertainty: float
    route_strength: float
    pressure: float
    law: float
    cohesion: float
    impossible: bool
    semantics: str


@dataclass(frozen=True)
class MesoClusterSnapshot:
    """Active meso-scale semantic entity — first-class field structure.

    Unlike the previous passive summary dict, this carries its own
    dynamic properties (pressure, entropy, drift, stability) and
    governs its constituent regions through cross-scale feedback.

    Meso clusters are the intermediate scale between micro (regions)
    and macro (continents). They form naturally from shared roles
    and exert top-down stabilization/perturbation on their regions.
    """
    cluster_id: str
    size: int
    region_ids: tuple
    tokens: tuple
    shared_roles: tuple
    all_roles: tuple
    avg_instability: float
    avg_convergence: float
    avg_pressure: float
    # Active entity properties
    entropy: float  # internal disorder
    drift: float    # how much the cluster's center is moving
    stability: float  # inverse of avg instability, smoothed
    boundary_strength: float  # 0=porous, 1=tightly bounded
    interaction_policy: str  # "cooperative", "competitive", "neutral", "isolated"
    centroid: tuple  # center of mass in role space
    version: int = 1


@dataclass(frozen=True)
class MacroContinentSnapshot:
    """Macro-scale semantic continent — large-scale field structure.

    Continents group related meso clusters into the largest scale of
    organization. They provide long-range guidance, preserve diversity,
    and prevent monopolistic attractors from dominating the field.

    Properties:
    - pressure: Top-down governance pressure on constituent meso clusters
    - entropy: Diversity of meso clusters within the continent
    - stability: Long-term structural persistence
    - guidance_strength: How strongly the continent influences its clusters
    - diversity_pressure: Mechanism to prevent single-attractor dominance
    """
    continent_id: str
    size: int  # total regions across all constituent clusters
    meso_cluster_ids: tuple
    all_roles: tuple
    pressure: float
    entropy: float
    stability: float
    convergence: float
    guidance_strength: float  # how strongly this continent influences meso
    diversity_pressure: float  # 0=monoculture risk, 1=max diversity
    centroid: tuple  # center of mass
    version: int = 1


class TopologyView:
    """Read-only view of the topology graph.
    
    Returns immutable snapshots (dicts/RegionSnapshots) instead of live
    FieldConflictRegion objects. No mutation is possible through this interface.
    """

    def __init__(self, regions: List[FieldConflictRegion],
                 global_communities, schema_patterns, topological_laws,
                 neighborhood_cohesion, global_centrality,
                 impossible_neighborhoods, restructuring_queue,
                 cohesion_merge_success, cohesion_merge_attempts,
                 cohesion_split_success, cohesion_split_attempts,
                 meso_clusters=None,
                 macro_continents=None,
                 read_callback: Optional[Callable[[str, int], None]] = None):
        self._regions = list(regions)
        self._communities = [set(c) for c in global_communities]
        self._schema_patterns = dict(schema_patterns)
        self._laws = dict(topological_laws)
        self._cohesion = dict(neighborhood_cohesion)
        self._centrality = dict(global_centrality)
        self._impossible = [set(c) for c in impossible_neighborhoods]
        self._restructuring = set(restructuring_queue)
        self._merge_success = dict(cohesion_merge_success)
        self._merge_attempts = dict(cohesion_merge_attempts)
        self._split_success = dict(cohesion_split_success)
        self._split_attempts = dict(cohesion_split_attempts)
        self._meso_clusters = list(meso_clusters) if meso_clusters else []
        self._macro_continents = list(macro_continents) if macro_continents else []
        self._read_callback = read_callback

    def _snapshot(self, r: FieldConflictRegion) -> RegionSnapshot:
        if self._read_callback:
            self._read_callback(r.region_id, r.version)
        # Thermodynamic free energy = internal energy - temperature * entropy
        # For field regions: local_energy (potential) - local_temperature * instability (disorder)
        free_energy = r.local_energy - r.local_temperature * r.instability
        return RegionSnapshot(
            region_id=r.region_id,
            token=r.token,
            competing_roles=tuple(r.competing_roles),
            instability=r.instability,
            local_energy=r.local_energy,
            integrity=r.integrity,
            recurrence_score=r.recurrence_score,
            persistence=r.persistence,
            semantic_pressure=r.semantic_pressure,
            stability_momentum=r.stability_momentum,
            local_convergence=r.local_convergence,
            local_temperature=r.local_temperature,
            free_energy=free_energy,
            source_record=r.source_record,
            domain=getattr(r, 'domain', ''),
            version=r.version,
        )

    def _snapshot_dict(self, r: FieldConflictRegion) -> dict:
        """Return a region as a plain dict — for use in serialization/formatting."""
        return {
            "region_id": r.region_id,
            "token": r.token,
            "competing_roles": list(r.competing_roles),
            "instability": round(r.instability, 3),
            "local_energy": round(r.local_energy, 3),
            "integrity": round(r.integrity, 3),
            "recurrence_score": round(r.recurrence_score, 3),
            "persistence": round(r.persistence, 3),
            "semantic_pressure": round(r.semantic_pressure, 3),
            "local_convergence": round(r.local_convergence, 3),
            "local_temperature": round(r.local_temperature, 3),
            "source_record": r.source_record,
            "version": r.version,
        }

    # ─── Region Access ────────────────────────────────────────────────

    def all_regions(self) -> List[RegionSnapshot]:
        """Return immutable snapshots of all regions."""
        return [self._snapshot(r) for r in self._regions]

    def get_topology_edges(self) -> List[dict]:
        """Return dashboard-compatible topology edges from the unified edge field."""
        edges = []
        for edge in self.get_edge_fields():
            if edge.route_strength > 0.05:
                edges.append({
                    "source": edge.source,
                    "target": edge.target,
                    "weight": edge.route_strength,
                    "affinity": edge.affinity,
                    "repulsion": edge.repulsion,
                    "uncertainty": edge.uncertainty,
                    "pressure": edge.pressure,
                    "semantics": edge.semantics,
                })
        return edges

    def get_edge_fields(self) -> List[EdgeFieldSnapshot]:
        """Return one bounded edge field model for all topology-owned edges."""
        pairs = set(self._cohesion) | set(self._laws)
        impossible_pairs = set()
        for item in self._impossible:
            if len(item) == 2:
                impossible_pairs.add(tuple(sorted(item)))
        pairs |= impossible_pairs

        region_instability: Dict[Tuple[str, str], List[float]] = {}
        for region in self._regions:
            roles = sorted(set(region.competing_roles))
            for i, ra in enumerate(roles):
                for rb in roles[i + 1:]:
                    pair = tuple(sorted((ra, rb)))
                    pairs.add(pair)
                    region_instability.setdefault(pair, []).append(region.instability)

        edges = []
        for source, target in sorted(pairs):
            pair = tuple(sorted((source, target)))
            cohesion = _clamp01(self._cohesion.get(pair, 0.0))
            law = _clamp_signed(self._laws.get(pair, 0.0))
            impossible = pair in impossible_pairs
            instabilities = region_instability.get(pair, [])
            uncertainty = _clamp01(sum(instabilities) / len(instabilities)) if instabilities else 0.0

            affinity = _clamp01(cohesion + max(law, 0.0) * (1.0 - cohesion))
            repulsion = _clamp01(max(-law, 1.0 if impossible else 0.0))
            route_strength = _clamp01(affinity * (1.0 - repulsion) * (1.0 - uncertainty * 0.5))
            # Thermodynamic edge pressure: field-derived from region free energy
            # pressure = (uncertainty + repulsion) * (1.0 - affinity * 0.5)
            # High uncertainty + repulsion = high pressure (wants to break)
            # High affinity = low pressure (wants to stay together)
            # This replaces the heuristic weight formula with a principled
            # thermodynamic relationship: pressure scales with disorder and repulsion
            # and is dampened by cohesive affinity.
            pressure = _clamp01((uncertainty + repulsion) * (1.0 - affinity * 0.5))
            if repulsion > affinity and repulsion >= 0.2:
                semantics = "repulsive"
            elif affinity > 0.2:
                semantics = "attractive"
            elif uncertainty > 0.2:
                semantics = "uncertain"
            else:
                semantics = "latent"

            edges.append(EdgeFieldSnapshot(
                source=source,
                target=target,
                affinity=round(affinity, 3),
                repulsion=round(repulsion, 3),
                uncertainty=round(uncertainty, 3),
                route_strength=round(route_strength, 3),
                pressure=round(pressure, 3),
                law=round(law, 3),
                cohesion=round(cohesion, 3),
                impossible=impossible,
                semantics=semantics,
            ))
        return edges

    def all_region_dicts(self) -> List[dict]:
        """Return all regions as plain dicts (for serialization/display)."""
        return [self._snapshot_dict(r) for r in self._regions]

    def region_count(self) -> int:
        return len(self._regions)

    def find(self, token: str, roles: Set[str]) -> Optional[RegionSnapshot]:
        for r in self._regions:
            if r.token == token and set(r.competing_roles) == roles:
                return self._snapshot(r)
        return None

    def find_by_token_and_roles(self, token: str, sorted_roles: tuple) -> Optional[RegionSnapshot]:
        for r in self._regions:
            if r.token == token and tuple(sorted(r.competing_roles)) == sorted_roles:
                return self._snapshot(r)
        return None

    def find_by_token(self, token: str) -> List[RegionSnapshot]:
        return [self._snapshot(r) for r in self._regions if r.token == token]

    def get_all_tokens(self) -> List[str]:
        return list(set(r.token for r in self._regions))

    def get_regions_for_role(self, role: str) -> List[RegionSnapshot]:
        return [self._snapshot(r) for r in self._regions if role in r.competing_roles]

    def aggregate_metrics(self) -> dict:
        if not self._regions:
            return {}
        n = len(self._regions)
        return {
            "convergence": sum(r.local_convergence for r in self._regions) / n,
            "temperature": sum(r.local_temperature for r in self._regions) / n,
            "energy": sum(r.local_energy for r in self._regions) / n,
            "count": n,
        }

    def compute_entropy(self) -> float:
        if not self._regions:
            return 0.0
        return sum(r.instability for r in self._regions) / len(self._regions)

    def compute_macro_energy(self, convergence: float) -> float:
        if not self._regions:
            return 5.0
        avg_energy = sum(r.local_energy for r in self._regions) / len(self._regions)
        attractor_strength = 1.0 / (1.0 + 2.718 ** (-15 * (convergence - 0.6)))
        attractor_pull = min(attractor_strength * convergence * 2.0, 2.0)
        target_energy = max(0.0, avg_energy - attractor_pull)
        return target_energy

    # ─── Topology Structure Access ────────────────────────────────────

    @property
    def global_communities(self) -> List[Set[str]]:
        return [set(c) for c in self._communities]

    @property
    def schema_patterns(self) -> Dict[Tuple[str, str], float]:
        return dict(self._schema_patterns)

    @property
    def topological_laws(self) -> dict:
        return dict(self._laws)

    @property
    def neighborhood_cohesion(self) -> Dict[Tuple[str, str], float]:
        return dict(self._cohesion)

    @property
    def global_centrality(self) -> Dict[str, float]:
        return dict(self._centrality)

    @property
    def impossible_neighborhoods(self) -> List[Set[str]]:
        return [set(c) for c in self._impossible]

    @property
    def restructuring_queue(self) -> Set[Tuple[str, str]]:
        return set(self._restructuring)

    # ─── Multi-Scale Access ──────────────────────────────────────────

    def get_meso_clusters(self) -> List[dict]:
        """Return meso clusters as active entity dicts."""
        return list(self._meso_clusters)

    def get_macro_continents(self) -> List[dict]:
        """Return macro continents as active entity dicts."""
        return list(self._macro_continents)


class TopologyState:
    """Sole owner of the semantic field's topology structure."""

    @property
    def _tombstones(self) -> Set[str]:
        tx = self._staging
        if tx is not None:
            return tx["tombstones"]
        return self.__dict__.get('_tombstones_real', set())

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

    def __init__(self, delta_callback: Optional[Callable[[str, str, dict], None]] = None,
                 read_callback: Optional[Callable[[str, int], None]] = None):
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
        self._tombstones_real: Set[str] = set() # Final storage for tombstones

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
                        raise ConflictError(f"MVCC CONFLICT: Region [{rid}] version {live.version} != expected {expected}")

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
        """Assign every region to a shard based on community membership (Phase 53)."""
        communities = self._get_struct("communities")
        role_to_shard = {}
        for idx, community in enumerate(communities):
            shard_id = f"shard_{idx}"
            for role in community:
                role_to_shard[role] = shard_id
                
        shard_assignment: Dict[str, List[str]] = {}
        for r in self._get_regions():
            # Assign region to the shard of its first competing role
            primary_role = r.competing_roles[0] if r.competing_roles else "_unidentified"
            shard_id = role_to_shard.get(primary_role, "shard_default")
            shard_assignment.setdefault(shard_id, []).append(r.region_id)
            
        return shard_assignment

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
            if (r.token == token and set(r.competing_roles) == roles
                    and getattr(r, 'domain', '') == domain):
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
            read_callback=self._read_callback
        )

    def find_region_for_mutation(self, token: str, sorted_roles: tuple) -> Optional[str]:
        for r in self._get_regions():
            if r.token == token and tuple(sorted(r.competing_roles)) == sorted_roles:
                return r.region_id
        return None

    def neighbors_of(self, region_id: Any) -> List[RegionSnapshot]:
        target = self.get_region(region_id)
        if not target: return []
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
        """Move extremely stable regions into the permanent atom store (Phase 34)."""
        import time
        regs = self._get_regions()
        atoms = self._get_struct("crystalline_atoms")
        
        remaining = []
        new_atoms_count = 0
        
        for r in regs:
            if r.integrity >= integrity_threshold and r.instability <= instability_threshold:
                # Distill to atom
                atom = {
                    "token": r.token,
                    "roles": list(r.competing_roles),
                    "domain": r.domain,
                    "timestamp": time.time()
                }
                atoms.append(atom)
                new_atoms_count += 1
            else:
                remaining.append(r)
                
        if new_atoms_count > 0:
            self._set_regions(remaining)
            self._set_struct("crystalline_atoms", atoms)
            self._record("distill_crystalline_atoms", {"count": new_atoms_count})
            
        return new_atoms_count

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
        """Flood-fill communities from cohesion + field regions."""
        graph = {}
        cohesion = self._get_struct("neighborhood_cohesion")
        for (ra, rb), val in cohesion.items():
            if val > 0.5:
                graph.setdefault(ra, set()).add(rb)
                graph.setdefault(rb, set()).add(ra)
        for r in self._get_regions():
            for i in range(len(r.competing_roles)):
                for j in range(i + 1, len(r.competing_roles)):
                    ra, rb = r.competing_roles[i], r.competing_roles[j]
                    graph.setdefault(ra, set()).add(rb)
                    graph.setdefault(rb, set()).add(ra)
        if not graph:
            from app.field_laws import ROLE_EXCLUSIVITY
            for ra, rb in ROLE_EXCLUSIVITY:
                graph.setdefault(ra, set()).add(rb)
                graph.setdefault(rb, set()).add(ra)
        seen = set()
        communities = []
        for node in graph:
            if node in seen:
                continue
            component = set()
            stack = [node]
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                component.add(cur)
                for neighbor in graph.get(cur, set()):
                    if neighbor not in seen:
                        stack.append(neighbor)
            if component:
                communities.append(component)
        self._set_struct("communities", communities)

    def update_schema_patterns(self, exclusion_key: tuple, exclusion_val: float):
        struct = self._get_struct("schema_patterns")
        cur = struct.get(exclusion_key, 0.0)
        struct[exclusion_key] = cur * 0.95 + exclusion_val * 0.05
        self._set_struct("schema_patterns", struct)

    def decay_topological_laws(self):
        struct = self._get_struct("topological_laws")
        for key in list(struct.keys()):
            struct[key] = _clamp_signed(struct[key] * 0.95)
            if abs(struct[key]) <= 0.005:
                del struct[key]
        self._set_struct("topological_laws", struct)

    def set_topological_law(self, pair: tuple, value: float):
        laws = self._get_struct("topological_laws")
        laws[tuple(sorted(pair))] = _clamp_signed(value)
        self._set_struct("topological_laws", laws)
        self._record("set_topological_law", {"pair": pair, "value": value})

    def add_impossible_neighborhood(self, item: Set[str]):
        struct = self._get_struct("impossible_neighborhoods")
        struct.append(set(item))
        self._set_struct("impossible_neighborhoods", struct)

    def clear_impossible_neighborhoods(self):
        struct = self._get_struct("impossible_neighborhoods")
        struct.clear()
        self._set_struct("impossible_neighborhoods", struct)

    # ─── Controlled Mutations — Region Lifecycle ───────────────────────

    def add(self, competing_roles: List[str], token: str,
            instability: float = 0.5, integrity: float = 0.5,
            domain: str = "") -> FieldConflictRegion:
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
        self._record("add", {"competing_roles": competing_roles, "token": token, 
                            "instability": instability, "integrity": integrity, "domain": domain})
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

    def replace_all(self, new_regions: List[FieldConflictRegion]):
        """Replace the entire regional manifold (Phase 50)."""
        self._set_regions(list(new_regions))
        if self._staging is not None:
            self._staging["structural_change"] = True
        self._record("replace_all_regions", {"count": len(new_regions)})

    def trim(self, max_size: int, keep_from_end: int = 0):
        regs = self._get_regions()
        if len(regs) > max_size:
            if keep_from_end > 0:
                regs = regs[-keep_from_end:]
            else:
                regs = regs[-max_size:]
            self._set_regions(regs)
            if self._staging is not None:
                self._staging["structural_change"] = True

    def filter_regions(self, predicate: Callable[[FieldConflictRegion], bool]):
        regs = [r for r in self._get_regions() if predicate(r)]
        self._set_regions(regs)
        if self._staging is not None:
            self._staging["structural_change"] = True

    def prune(self, min_instability: float = 0.02, min_energy: float = 0.5) -> int:
        regs = self._get_regions()
        before = len(regs)
        regs = [r for r in regs
                         if r.instability > min_instability or r.local_energy > min_energy]
        self._set_regions(regs)
        if len(regs) != before and self._staging is not None:
            self._staging["structural_change"] = True
        return before - len(regs)

    def garbage_collect(self, max_idle: int = 10) -> int:
        """Resource-aware pruning of dead semantic regions (Phase 9)."""
        regs = self._get_regions()
        before = len(regs)
        # Prune regions that have been idle for too many cycles
        regs = [r for r in regs if r.idle_cycles < max_idle]
        self._set_regions(regs)
        if len(regs) != before and self._staging is not None:
            self._staging["structural_change"] = True
        return before - len(regs)

    def self_prune(self, instability_threshold: float = 0.9, community_required: bool = True) -> int:
        """Autonomous topology pruning (Phase 62).
        
        Removes regions that:
        1. Have very high instability (> threshold)
        2. Are NOT part of any detected community (isolated noise)
        """
        regs = self._get_regions()
        if not regs:
            return 0
            
        before = len(regs)
        in_community = set().union(*self.global_communities)
        
        new_regs = []
        for r in regs:
            # Keep if stable OR in community OR part of the schema
            is_noise = r.instability > instability_threshold
            has_community = any(role in in_community for role in r.competing_roles)
            
            if is_noise and community_required and not has_community:
                self._record("prune_dead_zone", {"region_id": r.region_id, "instability": r.instability})
                self._structural_change = True
                continue
                
            new_regs.append(r)
            
        self._set_regions(new_regs)
        return before - len(new_regs)

    def induce_topological_laws(self, min_success_rate: float = 0.8, min_attempts: int = 10):
        """Autonomous law discovery (Phase 62).
        
        Promotes frequently successful structural patterns into formal laws.
        """
        # 1. Analyze successful merges
        for pair, success in self._cohesion_merge_success.items():
            attempts = self._cohesion_merge_attempts.get(pair, 0)
            if attempts >= min_attempts:
                rate = success / attempts
                if rate >= min_success_rate:
                    # Induced affinity law
                    current = self.topological_laws.get(pair, 0.0)
                    self.set_topological_law(pair, max(current, 0.5 + (rate - 0.5) * 0.5))
                    self._record("induce_law", {"pair": pair, "type": "affinity", "rate": rate})
                    
        # 2. Analyze successful splits
        for pair, success in self._cohesion_split_success.items():
            attempts = self._cohesion_split_attempts.get(pair, 0)
            if attempts >= min_attempts:
                rate = success / attempts
                if rate >= min_success_rate:
                    # Induced repulsion law
                    current = self.topological_laws.get(pair, 0.0)
                    self.set_topological_law(pair, min(current, -0.5 * rate))
                    self._record("induce_law", {"pair": pair, "type": "repulsion", "rate": rate})

    def clear(self):
        if self._staging is not None:
            self._staging["regions"].clear()
            self._staging["communities"].clear()
            self._staging["schema_patterns"].clear()
            self._staging["topological_laws"].clear()
            self._staging["neighborhood_cohesion"].clear()
            self._staging["impossible_neighborhoods"].clear()
            self._staging["restructuring_queue"].clear()
            self._staging["merge_success"].clear()
            self._staging["merge_attempts"].clear()
            self._staging["split_success"].clear()
            self._staging["split_attempts"].clear()
            self._staging["centrality"].clear()
            self._staging["anchors"].clear()
            self._staging["crystalline_atoms"].clear()
            self._staging["meso_clusters"].clear()
            self._staging["macro_continents"].clear()
        else:
            self._regions.clear()
            self._communities.clear()
            self._schema_patterns.clear()
            self._topological_laws.clear()
            self._neighborhood_cohesion.clear()
            self._impossible_neighborhoods.clear()
            self._restructuring_queue.clear()
            self._cohesion_merge_success.clear()
            self._cohesion_merge_attempts.clear()
            self._cohesion_split_success.clear()
            self._cohesion_split_attempts.clear()
            self._centrality.clear()
            self._anchors.clear()
            self._crystalline_atoms.clear()
            self._meso_clusters.clear()
            self._macro_continents.clear()


    # ─── Controlled Mutations — Region Attributes ──────────────────────

    def get_region(self, region_id: Any) -> Optional[FieldConflictRegion]:
        """Internal helper to get a mutable region reference by ID or object."""
        rid = region_id
        if hasattr(region_id, 'region_id'):
            rid = region_id.region_id
            
        for r in self._get_regions():
            if r.region_id == rid:
                return r
        return None

    def set_region_instability(self, region_id: Any, value: float):
        r = self.get_region(region_id)
        if r: 
            r.instability = max(0.01, min(1.0, value))
            self._record("set_region_instability", {"region_id": r.region_id, "value": value})

    def adjust_region_instability(self, region_id: Any, delta: float):
        r = self.get_region(region_id)
        if r: self.set_region_instability(r.region_id, r.instability + delta)

    def set_region_energy(self, region_id: Any, value: float):
        r = self.get_region(region_id)
        if r: 
            r.local_energy = max(0.0, min(10.0, value))
            self._record("set_region_energy", {"region_id": r.region_id, "value": value})

    def adjust_region_energy(self, region_id: Any, delta: float):
        r = self.get_region(region_id)
        if r: self.set_region_energy(r.region_id, r.local_energy + delta)

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
        if r: self.set_region_recurrence(region_id, r.recurrence_score + delta)

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
        if not r: return
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
        No external code should recompute forces from raw cohesion/law data.
        """
        view = self.get_view()
        forces: Dict[Tuple[str, str], Dict[str, float]] = {}
        for edge in view.get_edge_fields():
            pair = tuple(sorted([edge.source, edge.target]))
            forces[pair] = {
                'affinity': edge.affinity,
                'repulsion': edge.repulsion,
                'pressure': edge.pressure,
                'route_strength': edge.route_strength,
                'semantics': edge.semantics,
            }
        return forces

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
        route_targets = {}  # target_role -> weight
        for role in source_region.competing_roles:
            for pair, force in forces.items():
                if role not in pair:
                    continue
                peer = pair[0] if pair[1] == role else pair[1]
                if peer in source_region.competing_roles:
                    continue
                # High-affinity edges with decent route_strength are good targets
                if force['affinity'] > 0.3 and force['route_strength'] > 0.2:
                    weight = force['affinity'] * force['route_strength']
                    if peer not in route_targets or weight > route_targets[peer]:
                        route_targets[peer] = weight

        if not route_targets:
            # No alternative routes: dissipate trapped pressure as heat
            source_region.local_temperature = min(1.0, source_region.local_temperature + pressure_amount * 0.1)
            self._record("redirect_repulsive_pressure_dissipate", {
                "region_id": source_region.region_id,
                "pressure_amount": round(pressure_amount, 4),
            })
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
                    # Apply edge-field-modulated pressure to target region state
                    target_r.instability = min(1.0, target_r.instability + redirect_amount * 0.05)
                    target_r.semantic_pressure = max(0.0, target_r.semantic_pressure + redirect_amount * 0.03)
                    redirected += redirect_amount
                    affected_targets.append(target_r.region_id)
                    # Record each target mutation for MVCC tracking
                    self._record("redirect_pressure_to_target", {
                        "region_id": target_r.region_id,  # MVCC: track target as modified
                        "source": source_region.region_id,
                        "target_role": target_role,
                        "redirect_amount": round(redirect_amount, 4),
                        "new_instability": round(target_r.instability, 4),
                        "new_pressure": round(target_r.semantic_pressure, 4),
                    })
                    break

        # 3. Any unredirected pressure heats the source (thermodynamic dissipation)
        remaining = pressure_amount - redirected
        if remaining > 0.01:
            source_region.local_temperature = min(1.0, source_region.local_temperature + remaining * 0.05)
            self._record("redirect_repulsive_pressure_remainder", {
                "region_id": source_region.region_id,
                "remaining_heat": round(remaining, 4),
            })

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
            strength: How strong the contradiction pressure is (0-1)

        Returns:
            dict with:
            - redirected: pressure redirected through alternative routes
            - excluded: pressure that still goes to scalar exclusion
            - through_edge_field: whether edge field data was available
        """
        forces = self._compute_edge_field_forces()
        pair = tuple(sorted([role_a, role_b]))
        force = forces.get(pair, {})

        if not force:
            # No edge field data for this pair: establish a basic repulsive topological law
            # An empty force dict {} means the pair was not found in get_edge_fields()
            current = self._topological_laws.get(pair, 0.0)
            self.set_topological_law(pair, min(current - strength * 0.3, -0.01))
            return {"redirected": 0.0, "excluded": strength, "through_edge_field": False}

        is_repulsive = force.get('semantics') == 'repulsive' or force.get('repulsion', 0) > 0.3

        if is_repulsive:
            # Repulsive edge: redirect pressure via the topology, not scalar exclusion
            for r in self._get_regions():
                if role_a in r.competing_roles or role_b in r.competing_roles:
                    self._redirect_repulsive_pressure(r, strength * 0.5, forces)

            # Strengthen the repulsive topological law to encode the contradiction
            current_law = self._topological_laws.get(pair, 0.0)
            self.set_topological_law(pair, min(current_law - strength * 0.1, -0.01))

            return {
                "redirected": round(strength * 0.5, 4),
                "excluded": round(strength * 0.1, 4),
                "through_edge_field": True,
            }
        else:
            # Non-repulsive pair contradicting: establish/strengthen a repulsive law
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
                    pair = tuple(sorted([roles[i], roles[j]]))
                    f = forces.get(pair)
                    if f:
                        region_pressure = max(region_pressure, f['pressure'])
                        region_affinity = max(region_affinity, f['affinity'])

            # Edge field modulates evolution
            # High pressure forces evolution; high affinity adds stability
            local_force = force or region_pressure > 0.3
            if region_pressure > 0.3:
                r.semantic_pressure = region_pressure

            effects = r.evolve(force=local_force)
            all_effects.extend(effects)

            # Survival: high affinity keeps regions alive even at low instability
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
                    spread_potential = r.instability * force['pressure']

                    if force['semantics'] == 'repulsive':
                        # ─── Repulsive Edge: Redirect Through Edge Field ───
                        # Accumulate pressure for redirection through alternative
                        # high-affinity routes instead of only scalar exclusion
                        repulsive_pressure += spread_potential * MAX_COUPLING_TRANSFER
                        # Still emit a minimal exclusion signal for learning continuity
                        spread = spread_potential * MAX_COUPLING_TRANSFER * 0.1
                        if spread > 0.001:
                            effects.append((pair, spread))
                    elif force['semantics'] == 'attractive':
                        # Attractive edges propagate but dampened by containment
                        spread = spread_potential * MAX_COUPLING_TRANSFER * 0.3
                        if spread > 0.001:
                            effects.append((pair, spread))
                            # Also propagate instability directly through attractive edges
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
                self._record("redirect_repulsive_pressure", {
                    "region_id": r.region_id,
                    "pressure_redirected": round(repulsive_pressure, 4),
                })

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
        sink_flow = 0.0    # Flow INTO sink regions
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
                        pair = tuple(sorted([ra, rb]))
                        force = forces.get(pair)
                        if force:
                            # Edge conductance = route_strength (how well signals flow)
                            edge_conductance = max(edge_conductance, force['route_strength'])

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
                # Flow direction: positive = ri → rj (ri loses instability, rj gains)
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
                r = self.get_region(rid)
                if r:
                    self.set_region_instability(rid, r.instability + delta)

        total_flow = round(sum(abs(d) for d in deltas.values()), 4)
        self._record("redistribute_instability", {
            "count": len(regs),
            "total_flow": total_flow,
            "pairs_coupled": pairs_coupled,
        })

        return {
            "total_flow": total_flow,
            "source_flow": round(source_flow, 4),
            "sink_flow": round(sink_flow, 4),
            "pairs_coupled": pairs_coupled,
        }

    def aggregate_metrics(self):
        regs = self._get_regions()
        if not regs:
            return {}, {}, {}
        n = len(regs)
        avg_convergence = sum(r.local_convergence for r in regs) / n
        avg_temp = sum(r.local_temperature for r in regs) / n
        avg_energy = sum(r.local_energy for r in regs) / n
        return {"convergence": avg_convergence, "temperature": avg_temp,
                "energy": avg_energy, "count": n}

    def compute_entropy(self) -> float:
        regs = self._get_regions()
        if not regs:
            return 0.0
        return sum(r.instability for r in regs) / len(regs)

    def compute_macro_energy(self, convergence: float) -> float:
        regs = self._get_regions()
        if not regs:
            return 5.0
        avg_energy = sum(r.local_energy for r in regs) / len(regs)
        attractor_strength = 1.0 / (1.0 + 2.718 ** (-15 * (convergence - 0.6)))
        attractor_pull = min(attractor_strength * convergence * 2.0, 2.0)
        target_energy = max(0.0, avg_energy - attractor_pull)
        return target_energy

    # ─── Multi-Scale Topology (Micro / Meso / Macro) ────────────────────

    @property
    def meso_clusters(self) -> List[dict]:
        """Read-only access to meso cluster data."""
        return list(self._get_struct("meso_clusters"))

    def compute_meso_clusters(self):
        """Compute meso-scale clusters from current field regions.

        Meso clusters group regions that share competing roles, forming
        intermediate-scale structures between micro (single region) and
        macro (global aggregate). These clusters are now first-class field
        entities with their own dynamics: pressure, entropy, drift, stability,
        boundary_strength, and interaction_policy.

        LAW: Meso clustering is derived from topology itself, not from
        any external partitioning scheme. Clusters are active entities
        that evolve and exert feedback on constituent regions.
        """
        regs = self._get_regions()
        clusters = []
        assigned = set()
        import uuid

        # Retrieve previous clusters to carry forward their dynamic properties
        prev_clusters = self._get_struct("meso_clusters")
        prev_map = {}
        for pc in prev_clusters:
            # Match by sorted tuple of region_ids for continuity
            rid_tuple = tuple(sorted(pc.get("region_ids", [])))
            prev_map[rid_tuple] = pc

        for i in range(len(regs)):
            if i in assigned:
                continue
            cluster_indices = [i]
            for j in range(i + 1, len(regs)):
                if j in assigned:
                    continue
                shared = set(regs[i].competing_roles) & set(regs[j].competing_roles)
                if shared:
                    cluster_indices.append(j)
                    assigned.add(j)
            assigned.add(i)

            cluster_regions = [regs[k] for k in cluster_indices]
            if len(cluster_regions) == 1:
                continue  # Single regions are micro-scale, not meso

            # Compute meso cluster properties
            avg_instability = sum(r.instability for r in cluster_regions) / len(cluster_regions)
            avg_convergence = sum(r.local_convergence for r in cluster_regions) / len(cluster_regions)
            avg_pressure = sum(r.semantic_pressure for r in cluster_regions) / len(cluster_regions)
            shared_roles = list(set.intersection(
                *[set(r.competing_roles) for r in cluster_regions]
            )) if len(cluster_regions) > 0 else []
            all_roles = list(set.union(
                *[set(r.competing_roles) for r in cluster_regions]
            ))
            tokens = list(set(r.token for r in cluster_regions))

            # Build region_id tuple for continuity tracking
            rid_tuple = tuple(sorted([r.region_id for r in cluster_regions]))
            prev = prev_map.get(rid_tuple, {})

            # Compute active entity properties
            # Entropy: diversity of instability within cluster
            instabilities = [r.instability for r in cluster_regions]
            if len(instabilities) > 1:
                mean_inst = sum(instabilities) / len(instabilities)
                entropy = sum(abs(i - mean_inst) for i in instabilities) / len(instabilities)
            else:
                entropy = 0.0

            # Drift: how much avg_instability changed from previous
            prev_instability = prev.get("avg_instability", avg_instability)
            drift = abs(avg_instability - prev_instability)

            # Stability: smoothed inverse of instability
            prev_stability = prev.get("stability", 0.5)
            raw_stability = 1.0 - avg_instability
            stability = prev_stability * 0.7 + raw_stability * 0.3

            # Boundary strength: how tightly coupled the regions are
            # High shared_role_count / total_role_count = tight boundary
            if all_roles:
                boundary_strength = len(shared_roles) / len(all_roles) if len(all_roles) > 0 else 0.0
            else:
                boundary_strength = 0.0
            # Carry forward previous boundary strength with momentum
            prev_boundary = prev.get("boundary_strength", boundary_strength)
            boundary_strength = prev_boundary * 0.8 + boundary_strength * 0.2

            # Interaction policy: derived from cluster-level properties
            prev_policy = prev.get("interaction_policy", "neutral")
            if avg_instability > 0.7 and avg_convergence < 0.3:
                interaction_policy = "competitive"
            elif avg_convergence > 0.7 and avg_instability < 0.3:
                interaction_policy = "cooperative"
            elif boundary_strength > 0.8:
                interaction_policy = "isolated"
            else:
                interaction_policy = "neutral"
            # Smooth policy transitions: only change if properties are decisive
            if interaction_policy != prev_policy:
                if abs(avg_instability - 0.5) < 0.2:
                    interaction_policy = prev_policy  # Keep previous in ambiguous zones

            # Centroid: average of all competing role vectors (simulated from role names)
            # In a full implementation this would use actual manifold vectors
            role_hash = sum(hash(r) for r in all_roles) if all_roles else 0
            centroid = (role_hash / 1e10 % 1.0, sum(hash(r) * 7 for r in all_roles) / 1e10 % 1.0) if all_roles else (0.0, 0.0)

            cluster_id = prev.get("cluster_id", f"meso_{uuid.uuid4().hex[:8]}")

            clusters.append({
                "cluster_id": cluster_id,
                "size": len(cluster_regions),
                "region_ids": [r.region_id for r in cluster_regions],
                "tokens": tokens,
                "shared_roles": shared_roles,
                "all_roles": all_roles,
                "avg_instability": round(avg_instability, 3),
                "avg_convergence": round(avg_convergence, 3),
                "avg_pressure": round(avg_pressure, 3),
                # Active entity properties
                "entropy": round(entropy, 3),
                "drift": round(drift, 3),
                "stability": round(stability, 3),
                "boundary_strength": round(boundary_strength, 3),
                "interaction_policy": interaction_policy,
                "centroid": centroid,
            })

        self._set_struct("meso_clusters", clusters)
        self._record("compute_meso_clusters", {"count": len(clusters)})

    def compute_macro_from_meso(self) -> dict:
        """Compute macro-scale properties from meso clusters.

        Macro properties are field-derived from meso clusters, not hardcoded
        thresholds. This replaces fixed procedural thresholds with emergent
        field behavior.

        Returns a dict with:
        - avg_convergence: weighted by cluster size
        - avg_instability: weighted by cluster size
        - fragmentation: how many distinct meso clusters exist
        - cluster_diversity: std dev of cluster instabilities
        - macro_pressure: average pressure weighted by cluster size
        """
        clusters = self._get_struct("meso_clusters")
        if not clusters:
            regs = self._get_regions()
            if not regs:
                return {
                    "avg_convergence": 0.5,
                    "avg_instability": 0.5,
                    "fragmentation": 0.0,
                    "cluster_diversity": 0.0,
                    "macro_pressure": 0.3,
                }
            return {
                "avg_convergence": sum(r.local_convergence for r in regs) / len(regs),
                "avg_instability": sum(r.instability for r in regs) / len(regs),
                "fragmentation": 0.0,
    "cluster_diversity": 0.0,
    "pressure": sum(r.semantic_pressure for r in regs) / len(regs),
            }

        total_size = sum(c["size"] for c in clusters)
        if total_size == 0:
            return {
                "avg_convergence": 0.5, "avg_instability": 0.5,
                "fragmentation": 0.0, "cluster_diversity": 0.0, "macro_pressure": 0.3,
            }

        weighted_convergence = sum(c["avg_convergence"] * c["size"] for c in clusters) / total_size
        weighted_instability = sum(c["avg_instability"] * c["size"] for c in clusters) / total_size
        weighted_pressure = sum(c["avg_pressure"] * c["size"] for c in clusters) / total_size

        # Fragmentation: more clusters = more fragmented
        fragmentation = len(clusters) / max(total_size, 1)

        # Cluster diversity: std dev of cluster avg instabilities
        mean_inst = weighted_instability
        if len(clusters) > 1:
            variance = sum((c["avg_instability"] - mean_inst) ** 2 for c in clusters) / len(clusters)
            diversity = variance ** 0.5
        else:
            diversity = 0.0

        return {
            "avg_convergence": round(weighted_convergence, 3),
            "avg_instability": round(weighted_instability, 3),
            "fragmentation": round(fragmentation, 3),
            "cluster_diversity": round(diversity, 3),
            "pressure": round(weighted_pressure, 3),
        }

    def compute_macro_continents(self):
        """Compute macro-scale semantic continents from meso clusters.

        Macro continents group related meso clusters into the largest scale of
        semantic organization. They provide long-range stabilization, preserve
        diversity, and prevent monopolistic attractors from dominating.

        Continents are computed from cluster proximity (shared roles) and
        carry their own dynamic properties: pressure, entropy, stability,
        convergence, guidance_strength, and diversity_pressure.

        LAW: Macro organization emerges from meso cluster interaction,
        not from global partitioning. Continents are field-derived.
        """
        clusters = self._get_struct("meso_clusters")
        if not clusters:
            self._set_struct("macro_continents", [])
            self._record("compute_macro_continents", {"count": 0})
            return

        prev_continents = self._get_struct("macro_continents")
        prev_map = {}
        for pc in prev_continents:
            cid_tuple = tuple(sorted(pc.get("meso_cluster_ids", [])))
            prev_map[cid_tuple] = pc

        # Group clusters that share roles
        import uuid
        continents = []
        assigned = set()
        for i in range(len(clusters)):
            if i in assigned:
                continue
            continent_indices = [i]
            for j in range(i + 1, len(clusters)):
                if j in assigned:
                    continue
                # Two clusters belong to the same continent if they share roles
                a_roles = set(clusters[i].get("all_roles", []))
                b_roles = set(clusters[j].get("all_roles", []))
                if a_roles & b_roles:
                    continent_indices.append(j)
                    assigned.add(j)
            assigned.add(i)

            if len(continent_indices) == 1:
                # Single cluster can still form its own micro-continent
                pass

            continent_clusters = [clusters[k] for k in continent_indices]
            all_meso_ids = tuple(sorted([c["cluster_id"] for c in continent_clusters]))

            # Compute continental properties from constituent clusters
            total_regions = sum(c["size"] for c in continent_clusters)
            all_roles = list(set.union(*[set(c.get("all_roles", [])) for c in continent_clusters]))

            # Pressure: weighted by cluster size
            total_size = sum(c["size"] for c in continent_clusters)
            pressure = sum(c["avg_pressure"] * c["size"] for c in continent_clusters) / max(total_size, 1)

            # Entropy: diversity across constituent clusters
            if len(continent_clusters) > 1:
                instabilities = [c["avg_instability"] for c in continent_clusters]
                mean_inst = sum(instabilities) / len(instabilities)
                entropy = sum(abs(i - mean_inst) for i in instabilities) / len(instabilities)
            else:
                entropy = 0.0

            # Stability: weighted average of cluster stabilities
            stability = sum(c.get("stability", 0.5) * c["size"] for c in continent_clusters) / max(total_size, 1)

            # Convergence: weighted average
            convergence = sum(c["avg_convergence"] * c["size"] for c in continent_clusters) / max(total_size, 1)

            # Guidance strength: how strongly this continent influences its clusters
            # Derived from entropy + stability: stable diverse continents guide strongly
            prev = prev_map.get(all_meso_ids, {})
            prev_guidance = prev.get("guidance_strength", 0.5)
            raw_guidance = min(1.0, stability * (1.0 + entropy) * 0.7)
            guidance_strength = prev_guidance * 0.85 + raw_guidance * 0.15

            # Diversity pressure: mechanism to prevent monoculture
            # High when clusters within the continent have varied instability
            if len(continent_clusters) > 1:
                instabilities = [c["avg_instability"] for c in continent_clusters]
                variance = sum((i - sum(instabilities)/len(instabilities))**2 for i in instabilities) / len(instabilities)
                diversity_pressure = min(1.0, variance * 5.0)  # Scale up variance
            else:
                diversity_pressure = 0.0  # Single cluster: no internal diversity

            # Centroid: simplified from cluster centroids
            centroids = [c.get("centroid", (0.0, 0.0)) for c in continent_clusters]
            if centroids:
                cx = sum(c[0] for c in centroids) / len(centroids)
                cy = sum(c[1] for c in centroids) / len(centroids)
                centroid = (cx, cy)
            else:
                centroid = (0.0, 0.0)

            continent_id = prev.get("continent_id", f"macro_{uuid.uuid4().hex[:8]}")

            continents.append({
                "continent_id": continent_id,
                "size": total_regions,
                "meso_cluster_ids": list(all_meso_ids),
                "all_roles": all_roles,
                "pressure": round(pressure, 3),
                "entropy": round(entropy, 3),
                "stability": round(stability, 3),
                "convergence": round(convergence, 3),
                "guidance_strength": round(guidance_strength, 3),
                "diversity_pressure": round(diversity_pressure, 3),
                "centroid": centroid,
            })

        self._set_struct("macro_continents", continents)
        self._record("compute_macro_continents", {"count": len(continents)})

    def _evolve_meso_clusters(self):
        """Evolve meso clusters — apply cluster-level feedback to constituent regions.

        Meso clusters exert pressure on their regions based on cluster-level
        instability and convergence. This creates a top-down coupling:
        stable clusters stabilize their regions; unstable clusters destabilize them.

        The interaction is now modulated by the cluster's active entity properties:
        - boundary_strength: tightly bounded clusters shield regions from feedback
        - interaction_policy: cooperative clusters stabilize; competitive destabilize
        - entropy: high-entropy clusters apply uneven feedback

        This is the core multi-scale interaction: micro (region) affects meso (cluster)
        which then feeds back to micro. The field restructures itself through
        this reciprocal interaction rather than through procedural overrides.
        """
        clusters = self._get_struct("meso_clusters")
        if not clusters:
            return 0

        regs = self._get_regions()
        reg_map = {r.region_id: r for r in regs}
        affected = 0

        # Compute macro pressure for top-down influence (meso gets guidance from macro)
        continents = self._get_struct("macro_continents")
        macro_pressure_map = {}
        for cont in continents:
            for cid in cont.get("meso_cluster_ids", []):
                macro_pressure_map[cid] = cont.get("pressure", 0.0)

        for cluster in clusters:
            cid = cluster["cluster_id"]
            # Active entity properties
            boundary = cluster.get("boundary_strength", 0.5)
            policy = cluster.get("interaction_policy", "neutral")
            cluster_entropy = cluster.get("entropy", 0.0)
            cluster_stability = cluster.get("stability", 0.5)

            # Macro top-down pressure
            macro_pressure = macro_pressure_map.get(cid, 0.0)

            # Cluster-level properties determine the feedback direction
            feedback_strength = cluster["avg_instability"] * (1.0 - cluster["avg_convergence"])
            if feedback_strength < 0.001:
                continue

            # Modulate by policy
            if policy == "isolated":
                # Isolated clusters have very weak feedback — regions are loosely coupled
                boundary_factor = boundary * 3.0  # Strong boundary = very isolated
                feedback_strength *= max(0.0, 1.0 - boundary_factor * 0.3)
            elif policy == "cooperative":
                # Cooperative clusters stabilize more uniformly
                pass  # Use standard feedback
            elif policy == "competitive":
                # Competitive clusters amplify feedback — more chaotic
                feedback_strength *= 1.3

            # Entropy modulation: high-entropy clusters apply uneven feedback
            entropy_noise = 1.0 + (cluster_entropy - 0.5) * 0.5  # 0.75–1.25 range
            feedback_strength *= entropy_noise

            for rid in cluster["region_ids"]:
                r = reg_map.get(rid)
                if not r:
                    continue

                # Meso feedback to region instability
                if cluster_stability > 0.6:
                    # Stable cluster: pull region toward stability
                    # Pull strength is higher for cooperative clusters
                    pull_mod = 1.2 if policy == "cooperative" else 1.0
                    pull = cluster_stability * 0.05 * feedback_strength * pull_mod
                    r.instability = max(0.01, r.instability - pull)
                else:
                    # Unstable cluster: push region toward exploration
                    # Push is amplified for competitive clusters
                    push_mod = 1.4 if policy == "competitive" else 1.0
                    push = (1.0 - cluster_stability) * 0.05 * feedback_strength * push_mod
                    r.instability = min(1.0, r.instability + push)

                # Macro top-down guidance: high macro pressure regions get extra push
                if macro_pressure > 0.5:
                    r.instability = min(1.0, r.instability + macro_pressure * 0.01)

                # Temperature coupling
                base_temp_influence = cluster["avg_instability"] * 0.05
                # Isolated clusters heat up less
                if policy == "isolated":
                    base_temp_influence *= (1.0 - boundary * 0.5)
                r.local_temperature = r.local_temperature * 0.95 + base_temp_influence

                # Boundary modulates pressure propagation
                if boundary > 0.6 and policy == "isolated":
                    # Tight boundary: less external influence reaches regions
                    pass  # Already handled through reduced feedback

                affected += 1

        if affected:
            self._record("evolve_meso_clusters", {"affected_regions": affected, "cluster_count": len(clusters)})
        return affected

    def _evolve_macro_continents(self):
        """Evolve macro continents — apply continent-level guidance to meso clusters.

        Macro continents provide top-down ecological governance:
        - Stable continents guide their clusters toward convergence
        - Unstable continents release clusters to explore
        - Diversity pressure prevents any single cluster from dominating
        - Guidance strength modulates the influence

        LAW: Macro governance is emergent from meso cluster dynamics,
        not procedural orchestration. Continents do not override;
        they modulate.
        """
        continents = self._get_struct("macro_continents")
        if not continents:
            return 0

        clusters = self._get_struct("meso_clusters")
        cluster_map = {c["cluster_id"]: c for c in clusters}
        affected = 0

        for continent in continents:
            guidance = continent.get("guidance_strength", 0.5)
            c_stability = continent.get("stability", 0.5)
            c_pressure = continent.get("pressure", 0.0)
            d_pressure = continent.get("diversity_pressure", 0.0)
            conv = continent.get("convergence", 0.5)

            if guidance < 0.05:
                continue  # Negligible influence

            for cid in continent.get("meso_cluster_ids", []):
                cluster = cluster_map.get(cid)
                if not cluster:
                    continue

                # 1. Stability guidance: stable continents pull clusters toward stability
                if c_stability > 0.6:
                    pull = (c_stability - 0.5) * guidance * 0.02
                    cluster["avg_instability"] = max(0.01, cluster["avg_instability"] - pull)
                    # Also nudge convergence upward
                    cluster["avg_convergence"] = min(1.0, cluster["avg_convergence"] + pull * 0.5)

                # 2. Pressure diffusion: continent pressure shapes cluster pressure
                pressure_diff = c_pressure - cluster["avg_pressure"]
                cluster["avg_pressure"] = cluster["avg_pressure"] + pressure_diff * guidance * 0.05

                # 3. Diversity pressure: prevent monopolistic clusters
                # If one cluster dominates (large size, low instability), diversity pushes
                # it to release some tension
                if d_pressure > 0.4:
                    release = d_pressure * guidance * 0.01
                    cluster["avg_instability"] = min(1.0, cluster["avg_instability"] + release)

                # 4. Convergence guidance: continents channel toward convergence
                if conv > 0.7:
                    # High convergence continent: pull all clusters toward convergence
                    gap = conv - cluster["avg_convergence"]
                    cluster["avg_convergence"] = min(1.0, cluster["avg_convergence"] + gap * guidance * 0.03)

                affected += 1

        # After evolving cluster properties, re-compute continent-level properties
        # from the updated clusters
        self.compute_macro_continents()

        if affected:
            self._record("evolve_macro_continents", {"affected_clusters": affected, "continent_count": len(continents)})
        return affected

    def cross_scale_pressure_flow(self):
        """Orchestrate bidirectional pressure flow across all three scales.

        Flow path:
        1. Micro → Meso: Region instabilities aggregate into cluster-level pressure
        2. Meso → Micro: Cluster-level dynamics feed back to constituent regions
        3. Meso → Macro: Cluster properties aggregate into continent-level dynamics
        4. Macro → Meso: Continent-level governance shapes cluster behavior
        5. Macro → Micro: Continental stability provides long-range attractor field

        The flow is temporal (continuous, not step-based) with damping
        to prevent oscillations.

        LAW: Cross-scale pressure flow is the canonical mechanism for
        multi-scale interaction. No scale bypass or procedural override.
        """
        import time
        now = time.time()

        # 1. Micro → Meso: Recompute clusters from evolved regions
        self.compute_meso_clusters()

        # 2. Meso → Micro: Apply meso feedback to regions
        meso_affected = self._evolve_meso_clusters()

        # 3. Meso → Macro: Build/update continents from evolved clusters
        self.compute_macro_continents()

        # 4. Macro → Meso: Apply continent guidance to clusters
        macro_affected = self._evolve_macro_continents()

        # 5. Re-sync: after macro guidance, recompute clusters with updated properties
        #    This ensures the macro → meso flow is reflected in cluster state
        if macro_affected > 0:
            self.compute_meso_clusters()

        self._last_pressure_flow_time = now
        self._record("cross_scale_pressure_flow", {
            "meso_feedback": meso_affected,
            "macro_guidance": macro_affected,
        })

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return {
            "regions": [asdict(r) for r in self._get_regions()],
            "communities": [list(c) for c in self.global_communities],
            "schema_patterns": {f"{k[0]}|{k[1]}": v for k, v in self.schema_patterns.items()},
            "topological_laws": {f"{k[0]}|{k[1]}": v for k, v in self.topological_laws.items()},
            "neighborhood_cohesion": {f"{k[0]}|{k[1]}": v for k, v in self.neighborhood_cohesion.items()},
            "cohesion_merge_success": {f"{k[0]}|{k[1]}": v for k, v in self.get_cohesion_merge_success().items()},
            "cohesion_merge_attempts": {f"{k[0]}|{k[1]}": v for k, v in self.get_cohesion_merge_attempts().items()},
            "cohesion_split_success": {f"{k[0]}|{k[1]}": v for k, v in self.get_cohesion_split_success().items()},
            "cohesion_split_attempts": {f"{k[0]}|{k[1]}": v for k, v in self.get_cohesion_split_attempts().items()},
            "centrality": self.global_centrality,
            "anchors": [list(a) for a in self.anchors],
            "impossible_neighborhoods": [list(n) for n in self.impossible_neighborhoods],
            "restructuring_queue": [list(r) for r in self.restructuring_queue],
            "crystalline_atoms": list(self._get_struct("crystalline_atoms")),
            "meso_clusters": list(self._get_struct("meso_clusters")),
            "macro_continents": list(self._get_struct("macro_continents")),
            "topology_epoch": self._topology_epoch,
            "tombstones": list(self._tombstones),
        }

    def from_dict(self, data: dict):
        self.clear()
        
        # Identity and Epoch (Phase 60)
        self._topology_epoch = data.get("topology_epoch", 1)
        self._tombstones = set(data.get("tombstones", []))

        # Regions
        regions = []
        for r_data in data.get("regions", []):
            r = FieldConflictRegion(
                competing_roles=r_data["competing_roles"],
                token=r_data["token"],
                instability=r_data["instability"],
                region_id=r_data.get("region_id")
            )
            for k, v in r_data.items():
                if k not in ["competing_roles", "token", "instability", "region_id"]:
                    setattr(r, k, v)
            regions.append(r)
        self._set_regions(regions)

        # Communities
        self._set_struct("communities", [set(c) for c in data.get("communities", [])])

        # Pipe-separated-key dicts
        for data_key, struct_key in [
            ("schema_patterns", "schema_patterns"),
            ("topological_laws", "topological_laws"),
            ("neighborhood_cohesion", "neighborhood_cohesion"),
            ("cohesion_merge_success", "merge_success"),
            ("cohesion_merge_attempts", "merge_attempts"),
            ("cohesion_split_success", "split_success"),
            ("cohesion_split_attempts", "split_attempts"),
        ]:
            target = {}
            for k, v in data.get(data_key, {}).items():
                parts = k.split("|")
                if len(parts) == 2:
                    target[tuple(parts)] = v
            self._set_struct(struct_key, target)

        # Simple replacements
        self._set_struct("centrality", dict(data.get("centrality", {})))
        self._set_struct("impossible_neighborhoods", [set(n) for n in data.get("impossible_neighborhoods", [])])
        self._set_struct("restructuring_queue", {tuple(r) for r in data.get("restructuring_queue", [])})
        self._set_struct("anchors", {tuple(a) for a in data.get("anchors", []) if len(a) == 2})
        self._set_struct("crystalline_atoms", list(data.get("crystalline_atoms", [])))
        self._set_struct("meso_clusters", list(data.get("meso_clusters", [])))
        self._set_struct("macro_continents", list(data.get("macro_continents", [])))

    def merge(self, other_data: dict, alpha: float = 0.5):
        """Merge remote topology state into local (Phase 32/60)."""
        remote_epoch = other_data.get("topology_epoch", 1)
        remote_tombstones = set(other_data.get("tombstones", []))
        
        # Phase 60: Causal Reconciliation Heuristic
        # 1. Update local tombstones (union)
        self._tombstones.update(remote_tombstones)
        
        # 2. Sync Epoch
        if remote_epoch > self._topology_epoch:
            self._topology_epoch = remote_epoch
        
        # 3. Prune local regions that are tombstones in remote
        if remote_epoch >= self._topology_epoch:
            regs = self._get_regions()
            new_regs = [r for r in regs if r.region_id not in remote_tombstones]
            if len(new_regs) < len(regs):
                self._set_regions(new_regs)
                self._structural_change = True

        remote_regions = other_data.get("regions", [])
        local_ids = {r.region_id: r for r in self._get_regions()}
        
        for r_data in remote_regions:
            rid = r_data.get("region_id")
            # Phase 60: Skip if region is a local tombstone
            if rid in self._tombstones:
                continue
                
            if rid in local_ids:
                # Merge existing region attributes (Phase 32)
                l_reg = local_ids[rid]
                l_reg.instability = l_reg.instability * (1.0 - alpha) + r_data["instability"] * alpha
                l_reg.local_energy = l_reg.local_energy * (1.0 - alpha) + r_data.get("local_energy", 0.5) * alpha
                l_reg.integrity = max(l_reg.integrity, r_data.get("integrity", 0.5))
            else:
                # Add new region from remote
                r = FieldConflictRegion(
                    competing_roles=r_data["competing_roles"],
                    token=r_data["token"],
                    instability=r_data["instability"],
                    region_id=rid
                )
                for k, v in r_data.items():
                    if k not in ["competing_roles", "token", "instability", "region_id"]:
                        setattr(r, k, v)
                self.append_region(r)

        # Merge topological laws (Max)
        remote_laws = other_data.get("topological_laws", {})
        for key_str, r_val in remote_laws.items():
            parts = key_str.split("|")
            if len(parts) == 2:
                pair = tuple(parts)
                local = self.topological_laws.get(pair, 0.0)
                merged = r_val if abs(r_val) > abs(local) else local
                self.set_topological_law(pair, merged)

        # Merge anchors
        remote_anchors = other_data.get("anchors", [])
        for a in remote_anchors:
            if len(a) == 2: self.record_anchor(tuple(a))
            
        self._record("merge", {"remote_regions": len(remote_regions)})
