"""TopologyView — read-only view of the topology graph.

Returns immutable snapshots (RegionSnapshots, dicts) instead of live
FieldConflictRegion objects. No mutation is possible through this interface.
"""

from collections.abc import Callable

from app.core_types import FieldConflictRegion
from app.topology_state_types import (
    EdgeFieldSnapshot,
    RegionSnapshot,
    _clamp01,
    _clamp_signed,
)


class TopologyView:
    """Read-only view of the topology graph.

    Returns immutable snapshots (dicts / RegionSnapshots) instead of live
    FieldConflictRegion objects. No mutation is possible through this interface.
    """

    def __init__(
        self,
        regions: list[FieldConflictRegion],
        global_communities,
        schema_patterns,
        topological_laws,
        neighborhood_cohesion,
        global_centrality,
        impossible_neighborhoods,
        restructuring_queue,
        cohesion_merge_success,
        cohesion_merge_attempts,
        cohesion_split_success,
        cohesion_split_attempts,
        meso_clusters=None,
        macro_continents=None,
        read_callback: Callable[[str, int], None] | None = None,
    ):
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
        # For field regions: local_energy (potential) - local_temperature *
        # instability (disorder)
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
            domain=getattr(r, "domain", ""),
            version=r.version,
        )

    def _snapshot_dict(self, r: FieldConflictRegion) -> dict:
        """Return a region as a plain dict — for use in serialization / formatting."""
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

    def all_regions(self) -> list[RegionSnapshot]:
        """Return immutable snapshots of all regions."""
        return [self._snapshot(r) for r in self._regions]

    def get_topology_edges(self) -> list[dict]:
        """Return dashboard-compatible topology edges from the unified edge field."""
        edges = []
        for edge in self.get_edge_fields():
            if edge.route_strength > 0.05:
                edges.append(
                    {
                        "source": edge.source,
                        "target": edge.target,
                        "weight": edge.route_strength,
                        "affinity": edge.affinity,
                        "repulsion": edge.repulsion,
                        "uncertainty": edge.uncertainty,
                        "pressure": edge.pressure,
                        "semantics": edge.semantics,
                    },
                )
        return edges

    def get_edge_fields(self) -> list[EdgeFieldSnapshot]:
        """Return one bounded edge field model for all topology-owned edges."""
        pairs = set(self._cohesion) | set(self._laws)
        impossible_pairs = set()
        for item in self._impossible:
            if len(item) == 2:
                impossible_pairs.add(tuple(sorted(item)))
        pairs |= impossible_pairs

        region_instability: dict[tuple[str, str], list[float]] = {}
        for region in self._regions:
            roles = sorted(set(region.competing_roles))
            for i, ra in enumerate(roles):
                for rb in roles[i + 1 :]:
                    pair = (ra, rb) if ra < rb else (rb, ra)
                    pairs.add(pair)
                    region_instability.setdefault(pair, []).append(region.instability)

        edges = []
        for source, target in sorted(pairs):
            pair = (source, target) if source < target else (target, source)
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
            pressure = _clamp01((uncertainty + repulsion) * (1.0 - affinity * 0.5))
            if repulsion > affinity and repulsion >= 0.2:
                semantics = "repulsive"
            elif affinity > 0.2:
                semantics = "attractive"
            elif uncertainty > 0.2:
                semantics = "uncertain"
            else:
                semantics = "latent"

            edges.append(
                EdgeFieldSnapshot(
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
                ),
            )
        return edges

    def all_region_dicts(self) -> list[dict]:
        """Return all regions as plain dicts (for serialization / display)."""
        return [self._snapshot_dict(r) for r in self._regions]

    def region_count(self) -> int:
        return len(self._regions)

    def find(self, token: str, roles: set[str]) -> RegionSnapshot | None:
        for r in self._regions:
            if r.token == token and set(r.competing_roles) == roles:
                return self._snapshot(r)
        return None

    def find_by_token_and_roles(self, token: str, sorted_roles: tuple) -> RegionSnapshot | None:
        for r in self._regions:
            if r.token == token and tuple(sorted(r.competing_roles)) == sorted_roles:
                return self._snapshot(r)
        return None

    def find_by_token(self, token: str) -> list[RegionSnapshot]:
        return [self._snapshot(r) for r in self._regions if r.token == token]

    def get_all_tokens(self) -> list[str]:
        return list(set(r.token for r in self._regions))

    def get_regions_for_role(self, role: str) -> list[RegionSnapshot]:
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
        return target_energy  # type: ignore[no-any-return]

    # ─── Topology Structure Access ────────────────────────────────────

    @property
    def global_communities(self) -> list[set[str]]:
        return [set(c) for c in self._communities]

    @property
    def schema_patterns(self) -> dict[tuple[str, str], float]:
        return dict(self._schema_patterns)

    @property
    def topological_laws(self) -> dict:
        return dict(self._laws)

    @property
    def neighborhood_cohesion(self) -> dict[tuple[str, str], float]:
        return dict(self._cohesion)

    @property
    def global_centrality(self) -> dict[str, float]:
        return dict(self._centrality)

    @property
    def impossible_neighborhoods(self) -> list[set[str]]:
        return [set(c) for c in self._impossible]

    @property
    def restructuring_queue(self) -> set[tuple[str, str]]:
        return set(self._restructuring)

    # ─── Multi-Scale Access ──────────────────────────────────────────

    def get_meso_clusters(self) -> list[dict]:
        """Return meso clusters as active entity dicts."""
        return list(self._meso_clusters)

    def get_macro_continents(self) -> list[dict]:
        """Return macro continents as active entity dicts."""
        return list(self._macro_continents)
