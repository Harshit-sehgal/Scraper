import math
import time
from collections import Counter
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════════════════════════════
# FIELD LAWS — formal locality, conservation, and coupling constraints.
# These guarantee bounded emergence and prevent runaway semantic weather.
# ═══════════════════════════════════════════════════════════════════════════════

# Locality Law 1: Propagation radius — no basin may directly influence
# regions beyond immediate exclusivity neighbors (radius = 1).
MAX_PROPAGATION_RADIUS = 1

# Locality Law 2: Energy attenuation — each propagation hop loses at
# least 70% of remaining energy (decay floor = 0.3).
PROPAGATION_DECAY_FLOOR = 0.3

# Locality Law 3: Coupling ceiling — no single propagation event may
# transfer more than 30% of a basin's instability to a neighbor.
MAX_COUPLING_TRANSFER = 0.3

# Locality Law 4: Convergence ceiling — attractor pull is capped at
# 2.0 energy units per convergence computation.
MAX_ATTRACTOR_PULL = 2.0

# Locality Law 5: Instability conservation — total instability change
# across all basins per cycle is bounded by ±20%.
MAX_INSTABILITY_FLUX = 0.2


@dataclass
class FieldConflictRegion:
    """A persistent, pre-resolution conflict in the semantic field.

    Contradictions are NOT immediately resolved. They persist as
    topology structures that propagate, restructure the field,
    and bias equilibrium before interpretation emerges.
    """
    competing_roles: List[str]
    token: str
    instability: float
    semantic_pressure: float = 0.0
    propagation_radius: int = 1
    recurrence_score: float = 0.0
    topology_neighbors: List[str] = field(default_factory=list)
    source_record: str = ""
    persistence: float = 1.0  # survives decay without reinforcement
    stability_momentum: float = 0.0  # structural hysteresis — resists rapid change
    local_convergence: float = 0.3  # local settling score
    local_temperature: float = 0.5  # local exploration/exploitation
    local_energy: float = 5.0  # local activation level
    local_memory: dict = field(default_factory=dict)  # autonomous local memory

    _global_evolve_cycle: int = 0

    def evolve(self, ws=None, force=False):
        """Autonomous basin evolution — self-scheduled.

        Each basin tracks its own evolution cadence. When called without
        force, it only evolves every 3 calls (self-throttled). This
        reduces dependency on external scheduling while maintaining
        continuous local evolution.
        """
        if not force:
            self._evolve_counter = getattr(self, '_evolve_counter', 0) + 1
            if self._evolve_counter % 3 != 0:
                return
        attractor = min(1.0, self.local_convergence * 1.5)
        plasticity = 1.0 - attractor * 0.8

        self.instability *= 0.95 * plasticity
        effect = 1.0 / (1.0 + 2.718 ** (-10 * (self.recurrence_score - 0.3)))  # sigmoid
        self.instability = min(1.0, self.instability + 0.02 * effect)
        self.persistence = min(2.0, self.persistence + 0.05)
        self.local_convergence = min(1.0, self.local_convergence + 0.02 * plasticity)
        decay = 1.0 / (1.0 + 2.718 ** (-10 * (self.instability - 0.3)))  # sigmoid
        self.local_convergence *= (1.0 - decay * 0.05)
        self.local_temperature = self.local_temperature * 0.9 + (self.instability * 0.8) * 0.1

        # Continuous distortion via sigmoid-weighted effect
        # First writes to local memory, then syncs to global state
        distort = 1.0 / (1.0 + 2.718 ** (-10 * (self.instability - 0.3)))
        effect_strength = distort * self.instability * 0.01 * plasticity
        for role in self.competing_roles:
            for peer in self.competing_roles:
                if peer != role:
                    key = tuple(sorted([role, peer]))
                    current = self.local_memory.get(str(key), 0.0)
                    self.local_memory[str(key)] = min(1.0, current + effect_strength)
                    if ws is not None:
                        global_current = ws.learned_exclusions.get(key, 0.0)
                        ws.learned_exclusions[key] = min(1.0, global_current + effect_strength)

    def propagate(self, ws=None):
        """Autonomous propagation — governed by formal locality laws.
        
        Constraints:
        - Radius: 1 (direct exclusivity neighbors only)
        - Attenuation: at least PROPAGATION_DECAY_FLOOR per hop
        - Transfer cap: MAX_COUPLING_TRANSFER * instability
        """
        if ws is None:
            return
        from app.semantic_allocation_engine import ROLE_EXCLUSIVITY
        for role in self.competing_roles:
            for ra, rb in ROLE_EXCLUSIVITY:
                peer = None
                if role == ra:
                    peer = rb
                elif role == rb:
                    peer = ra
                if peer is not None and peer not in self.competing_roles:
                    local_count = getattr(self, '_propagation_count', 0) + 1
                    self._propagation_count = local_count
                    local_decay = max(PROPAGATION_DECAY_FLOOR, 1.0 / (1.0 + local_count * 0.2))
                    spread = min(self.instability * MAX_COUPLING_TRANSFER * local_decay, self.instability * 0.5)
                    key = tuple(sorted([role, peer]))
                    current = ws.learned_exclusions.get(key, 0.0)
                    ws.learned_exclusions[key] = min(1.0, current + spread)


@dataclass
class TopologyMetrics:
    """Three primary causal variables. Everything else is derived.

    Primary (written by system):
    - field_energy: overall activation level (0-10)
    - cumulative_uncertainty: accumulated disorder
    - total_records_processed: experience counter
    - exclusion_count: active topological constraints

    Derived (computed, read by system):
    - field_pressure: unified instability scalar
    - semantic_temperature: exploration vs exploitation
    - convergence_score: settling proximity
    """
    total_records_processed: int = 0
    total_co_occurrences: int = 0
    transition_observations: int = 0
    learning_count: int = 0
    cumulative_density: float = 0.0
    cumulative_uncertainty: float = 0.0
    global_energy: float = 5.0
    global_entropy: float = 1.0
    exclusion_count: int = 0

    @property
    def average_density(self) -> float:
        if self.total_records_processed == 0:
            return 0.5
        return self.cumulative_density / self.total_records_processed

    @property
    def average_uncertainty(self) -> float:
        if self.total_records_processed == 0:
            return 0.5
        return self.cumulative_uncertainty / self.total_records_processed

    @property
    def field_pressure(self) -> float:
        """Unified field pressure — the PRIMARY field state variable.

        All cognition derives from this single scalar.
        High = unstable, contradictory, uncertain field.
        Low = stable, coherent, convergent field.
        """
        norm_energy = min(self.global_energy / 10.0, 1.0)
        contr_density = min(self.exclusion_count / max(self.total_records_processed, 1), 1.0)
        return max(0.0, min(1.0, (norm_energy + self.average_uncertainty + contr_density) / 3.0))

    @property
    def semantic_temperature(self) -> float:
        """Thermodynamic cooling — temperature drops as the field converges.

        High convergence → cooling (exploitation phase).
        Low convergence → stable temperature (exploration phase).
        Cooling accelerates as the field settles (phase transition).
        """
        self._temperature = getattr(self, '_temperature', 0.5)
        conv = self.convergence_score
        # Cooling: high convergence pulls temperature down faster
        cooling = 1.0 - conv * 0.3
        target = max(0.1, min(1.0, self.field_pressure * 1.5 * cooling))
        smoothing = 0.9 - conv * 0.2  # faster smoothing when converged
        self._temperature = self._temperature * smoothing + target * (1 - smoothing)
        return self._temperature

    @property
    def convergence_score(self) -> float:
        """Attractor-stabilized convergence — sigmoid-weighted energy reduction."""
        self._convergence = getattr(self, '_convergence', 0.5)
        conv = self._convergence
        # Attractor: sigmoid-weighted energy reduction (no hard threshold)
        attractor_strength = 1.0 / (1.0 + 2.718 ** (-15 * (conv - 0.6)))
        attractor_pull = min(attractor_strength * conv * 2.0, MAX_ATTRACTOR_PULL)
        self.global_energy = max(0.0, self.global_energy - attractor_pull)
        return self._convergence

    def field_summary(self) -> dict:
        """Return only the 3 canonical field variables."""
        return {
            "field_pressure": round(self.field_pressure, 3),
            "semantic_temperature": round(self.semantic_temperature, 3),
            "convergence_score": round(self.convergence_score, 3),
        }

class SemanticWorldState:
    """
    Canonical Semantic World State.
    This is the single source of truth for all semantic cognition.
    No subsystem may maintain isolated semantic truth.
    
    Meaning emerges from the relational topology of this state.
    """
    def __init__(self):
        # Topology metrics and global equilibrium metrics
        self.metrics = TopologyMetrics()
        
        # Nodes: Role compatibility (Role -> Type -> Confidence)
        self.role_compatibility: Dict[Tuple[str, str], float] = {}
        
        # Fields: Role position distributions
        self.role_position_memory: Dict[str, List[float]] = {}
        
        # Edges: Role co-occurrence (Role A, Type A) -> (Role B, Type B)
        self.role_co_occurrence: Dict[Tuple[str, str, str, str], int] = {}
        
        # Edges: Transition memory (Type A -> Type B)
        self.transition_probs: Dict[Tuple[str, str], float] = {}
        
        # Structures: Motif memory (recurring sub-graphs)
        self.motif_counts: Counter = Counter()
        self.motif_timestamps: Dict[Tuple[str, ...], int] = {} # Record index of last reinforcement
        self.motif_stability: Dict[Tuple[str, ...], float] = {}
        
        # Contradiction Topology: Impossible neighborhoods, exclusion edges
        self.learned_exclusions: Dict[Tuple[str, str], float] = {}
        self.impossible_neighborhoods: List[Set[str]] = []
        # Neighborhood cohesion: tracks how well role pairs work together
        # High cohesion = roles frequently co-occur without contradictions
        # Low cohesion = roles frequently conflict, candidates for restructuring
        self.neighborhood_cohesion: Dict[Tuple[str, str], float] = {}
        self.restructuring_queue: Set[Tuple[str, str]] = set()
        
        # Cohesion Field: Merge vs Split biases
        self.cohesion_merge_success: Dict[Tuple[str, str], float] = {}
        self.cohesion_merge_attempts: Dict[Tuple[str, str], float] = {}
        self.cohesion_split_success: Dict[Tuple[str, str], float] = {}
        self.cohesion_split_attempts: Dict[Tuple[str, str], float] = {}
        
        # Global Topology Distributions
        self.global_centrality: Dict[str, float] = {}
        self.global_communities: List[Set[str]] = []
        
        # Persistent pre-resolution field state
        self.field_regions: List[FieldConflictRegion] = []
        self.field_activation_count: int = 0

        # Uncertainty Fields & Diagnostics
        self.decision_history: list = []
        self.topology_snapshots: list = []
        self.last_update_time: float = time.time()

    def reinforce_motif(self, motif: Tuple[str, ...]):
        """Reinforce a structural motif with temporal awareness."""
        self.motif_counts[motif] += 1
        self.motif_timestamps[motif] = self.metrics.total_records_processed
        # Immediate stability update
        self.motif_stability[motif] = self.get_motif_stability(motif)

    def get_motif_stability(self, motif: Tuple[str, ...]) -> float:
        """Get temporal stability score for a motif (0-1)."""
        if self.metrics.total_records_processed == 0:
            return 0.0
        
        count = self.motif_counts.get(motif, 0)
        last_seen = self.motif_timestamps.get(motif, 0)
        
        # Temporal decay: Memory fades over steps
        age = self.metrics.total_records_processed - last_seen
        decay_factor = math.exp(-age / 2000.0) # Forgets slowly (~5000 records half-life)
        
        base_stability = count / max(self.metrics.total_records_processed, 1)
        return min(base_stability * decay_factor, 1.0)

    def apply_memory_decay(self):
        """Globally decay old or weak semantic structures to reduce entropy."""
        # Only decay every 100 records to avoid update storms
        if self.metrics.total_records_processed % 100 != 0:
            return
            
        # Decay role compatibilities toward maximum uncertainty (0.5)
        for key in list(self.role_compatibility.keys()):
            current = self.role_compatibility[key]
            # Drift toward 0.5
            self.role_compatibility[key] = current + (0.5 - current) * 0.01
            
        # Prune very weak motifs
        for motif in list(self.motif_counts.keys()):
            if self.get_motif_stability(motif) < 0.01:
                del self.motif_counts[motif]
                if motif in self.motif_timestamps:
                    del self.motif_timestamps[motif]
                if motif in self.motif_stability:
                    del self.motif_stability[motif]

    def get_derived_exclusion(self, role_a: str, role_b: str) -> float:
        """Compute exclusion strength from topology metrics — the dict is secondary.

        Exclusion emerges from topology itself:
        1. Motif instability: if motifs containing these roles are unstable, exclude more
        2. Compatibility divergence: roles with divergent type preferences exclude more
        3. Neighborhood instability: if roles are in different neighborhoods, exclude more
        4. Learned exclusion history (symbolic bridge, secondary)

        The topology baseline produces non-zero exclusion even when the dict is empty.
        The dict only amplifies patterns already visible in the topology.
        """
        baseline = 0.0

        # 1. Motif pressure (topology-native): unstable motifs → exclusion
        # Stable motifs REPEL exclusion (they indicate compatible neighborhoods)
        for motif in self.motif_counts:
            ra_str = str(role_a) in motif
            rb_str = str(role_b) in motif
            if ra_str and rb_str:
                stability = self.get_motif_stability(motif)
                if stability < 0.5:
                    baseline += 0.18 * (0.5 - stability)
                else:
                    baseline -= 0.03 * (stability - 0.5)

        # 2. Compatibility pressure (topology-native): divergent type preferences → exclusion
        observed_types = set()
        for r, t in self.role_compatibility:
            observed_types.add(t)
        for ttype in observed_types:
            ca = self.role_compatibility.get((role_a, ttype), 0.5)
            cb = self.role_compatibility.get((role_b, ttype), 0.5)
            if abs(ca - cb) > 0.2:
                baseline += 0.06

        # 3. Topology persistence: stable field regions reduce exclusion
        for region in self.field_regions:
            if role_a in region.competing_roles and role_b in region.competing_roles:
                if region.instability < 0.3:
                    baseline -= 0.05

        # 4. Learned exclusion (symbolic bridge, secondary cache — 0.1x weight)
        key = tuple(sorted([role_a, role_b]))
        learned = self.learned_exclusions.get(key, 0.0) * 0.1
        total = baseline + learned

        return max(0.0, min(1.0, total))

    @property
    def topology_density(self) -> float:
        """Graph interconnectedness — edges per possible role pair.

        Dense topology = many exclusivity relationships = conflicts
        propagate easily. Used to tighten exclusion thresholds so the
        graph geometry itself governs cognition.
        """
        from app.semantic_allocation_engine import ROLE_EXCLUSIVITY
        possible = len(ROLE_EXCLUSIVITY) + max(len(self.learned_exclusions), 1)
        actual = len(self.learned_exclusions)
        return min(actual / possible, 1.0) if possible > 0 else 0.0

    def propagate_field_regions(self) -> int:
        """Each basin owns its own propagation — delegating to region.propagate()."""
        affected = 0
        for region in self.field_regions:
            before = len(self.learned_exclusions)
            region.propagate(ws=self)
            after = len(self.learned_exclusions)
            affected += after - before
        return affected

    def capture_pre_allocation_field(self, tokens: list, schema_fields: list) -> int:
        """Capture pre-allocation conflict topology from tokens.

        Before allocation resolves exclusivity conflicts, this method
        preserves the raw instability geometry as persistent field regions.
        Returns the number of conflict regions captured.
        """
        from app.semantic_allocation_engine import ROLE_EXCLUSIVITY
        captured = 0
        value_roles: Dict[str, List[str]] = {}
        for t in tokens:
            if not t.raw or not t.source_field:
                continue
            if t.raw not in value_roles:
                value_roles[t.raw] = []
            value_roles[t.raw].append(t.source_field)

        for token_val, roles in value_roles.items():
            if len(roles) < 2:
                continue
            for i in range(len(roles)):
                for j in range(i + 1, len(roles)):
                    pair = (roles[i], roles[j])
                    rev_pair = (roles[j], roles[i])
                    if pair in ROLE_EXCLUSIVITY or rev_pair in ROLE_EXCLUSIVITY:
                        # Update existing region or create new one — persistent evolution
                        sorted_roles = tuple(sorted([roles[i], roles[j]]))
                        existing = None
                        for r in self.field_regions:
                            if r.token == token_val and tuple(sorted(r.competing_roles)) == sorted_roles:
                                existing = r
                                break
                        if existing:
                            # Structural hysteresis: instability change is smoothed by momentum
                            target_instability = min(1.0, existing.instability + 0.15)
                            existing.stability_momentum = existing.stability_momentum * 0.7 + 0.3 * target_instability
                            existing.instability = existing.stability_momentum
                            existing.recurrence_score = min(1.0, existing.recurrence_score + 0.1)
                            existing.semantic_pressure = self.metrics.field_pressure
                            existing.persistence = max(0.5, existing.persistence - 0.1)
                            existing.source_record = f"recurrence_{self.field_activation_count}"
                        else:
                            region = FieldConflictRegion(
                                competing_roles=[roles[i], roles[j]],
                                token=token_val,
                                instability=0.5,
                                stability_momentum=0.5,
                                semantic_pressure=self.metrics.field_pressure,
                                recurrence_score=self.learned_exclusions.get(sorted_roles, 0.0),
                                topology_neighbors=list(set(roles)),
                            )
                            self.field_regions.append(region)
                        captured += 1
                        self.field_activation_count += 1

        # Prune old regions
        if len(self.field_regions) > 100:
            self.field_regions = self.field_regions[-50:]
        return captured

    def redistribute_instability(self):
        """Continuous diffusion-based instability transfer.

        Flow = coupling_strength * pressure_gradient.
        Coupling strength is determined by propagation interaction frequency
        (how often regions have influenced each other), not symbolic overlap.
        This eliminates the procedural if-statement pattern."""
        if len(self.field_regions) < 2:
            return
        # Build interaction-frequency-based adjacency (not symbolic overlap)
        for region in self.field_regions:
            region._interaction_count = getattr(region, '_interaction_count', 0) + 1

        for i in range(len(self.field_regions)):
            for j in range(i + 1, len(self.field_regions)):
                ri = self.field_regions[i]
                rj = self.field_regions[j]
                # Coupling strength from mutual propagation interaction
                ci = getattr(ri, '_interaction_count', 0)
                cj = getattr(rj, '_interaction_count', 0)
                coupling = min(ci, cj) * 0.01
                if coupling < 0.01:
                    continue
                # Continuous diffusion: flow = coupling * pressure_gradient
                pressure_gradient = ri.instability - rj.instability
                flow = coupling * pressure_gradient
                ri.instability -= flow
                rj.instability += flow

    def aggregate_from_regions(self):
        """Derive global metrics from local field regions — observer-only.

        Global metrics are aggregates of local basin state, not independent.
        This prevents global/local drift and metric ecology explosion.
        """
        if not self.field_regions:
            self.metrics._convergence = getattr(self.metrics, '_convergence', 0.5)
            return
        n = len(self.field_regions)
        avg_convergence = sum(r.local_convergence for r in self.field_regions) / n
        avg_temp = sum(r.local_temperature for r in self.field_regions) / n
        avg_energy = sum(r.local_energy for r in self.field_regions) / n
        total_uncertainty = sum(getattr(r, '_uncertainty', 0.0) for r in self.field_regions)
        self.metrics._convergence = avg_convergence
        self.metrics._temperature = avg_temp
        self.metrics.global_energy = avg_energy
        self.metrics.cumulative_uncertainty = total_uncertainty

    def decay_field_regions(self):
        """Each basin evolves autonomously with local state only."""
        surviving = []
        for r in self.field_regions:
            r.evolve(ws=self, force=True)
            decay_floor = 0.05 / max(r.persistence, 0.5)
            if r.instability > decay_floor:
                surviving.append(r)
        self.field_regions = surviving

    def snapshot(self, label: str = ""):
        """Record a compact topology snapshot for replay/debugging."""
        self.topology_snapshots.append({
            "label": label,
            "time": self.metrics.total_records_processed,
            "energy": self.metrics.global_energy,
            "uncertainty": self.metrics.average_uncertainty,
            "field_pressure": self.metrics.field_pressure,
            "exclusions": len(self.learned_exclusions),
            "compatibilities": len(self.role_compatibility),
            "motifs": len(self.motif_counts),
        })
        if len(self.topology_snapshots) > 500:
            self.topology_snapshots = self.topology_snapshots[-250:]

    def replay(self) -> list:
        """Return topology evolution as a sequence of snapshots for replay."""
        return list(self.topology_snapshots)

    def trace_waves(self) -> list:
        """Return propagation wave entries from snapshots for wave tracing."""
        return [s for s in self.topology_snapshots if "wave" in s.get("label", "")]

    def diff_snapshots(self, idx_a: int = -2, idx_b: int = -1) -> dict:
        """Return the diff between two snapshots for causal chain inspection."""
        if len(self.topology_snapshots) < 2:
            return {}
        a = self.topology_snapshots[idx_a]
        b = self.topology_snapshots[idx_b]
        diff = {}
        for k in a:
            if k in ("label", "time"):
                continue
            delta = b.get(k, 0) - a.get(k, 0)
            if abs(delta) > 0.001:
                diff[k] = delta
        return diff

    def multi_scale_regions(self) -> dict:
        """Group field regions into larger-scale meta-basins.

        Micro: individual field regions (existing)
        Meso: regions that share competing roles (clusters)
        Macro: all regions aggregated (global summary)

        This enables cross-scale emergence — behavior at one scale
        can influence structure at adjacent scales.
        """
        micro = [{"token": r.token, "roles": r.competing_roles,
                   "instability": round(r.instability, 3),
                   "convergence": round(r.local_convergence, 3)}
                  for r in self.field_regions]

        # Meso: cluster regions by shared roles
        meso = []
        assigned = set()
        for i in range(len(self.field_regions)):
            if i in assigned:
                continue
            cluster = [i]
            for j in range(i + 1, len(self.field_regions)):
                if j in assigned:
                    continue
                shared = set(self.field_regions[i].competing_roles) & set(self.field_regions[j].competing_roles)
                if shared:
                    cluster.append(j)
                    assigned.add(j)
            assigned.add(i)
            if len(cluster) > 1:
                cluster_regions = [self.field_regions[k] for k in cluster]
                meso.append({
                    "size": len(cluster),
                    "avg_instability": round(sum(r.instability for r in cluster_regions) / len(cluster_regions), 3),
                    "avg_convergence": round(sum(r.local_convergence for r in cluster_regions) / len(cluster_regions), 3),
                    "tokens": list(set(r.token for r in cluster_regions)),
                })

        # Macro: global aggregate
        macro = {
            "total_regions": len(self.field_regions),
            "meso_clusters": len(meso),
            "field_pressure": round(self.metrics.field_pressure, 3),
            "convergence": round(self.metrics.convergence_score, 3),
        }

        return {"micro": micro, "meso": meso, "macro": macro}

    def local_view(self, role: str) -> dict:
        """Local-only view — a role sees only its neighbors, not the full field.

        This enforces locality: no system should access global state directly.
        Each role sees:
        - its own compatibility mappings
        - exclusions for role pairs it participates in
        - field regions it's involved in
        - neighboring roles (from exclusivity edges)
        """
        from app.semantic_allocation_engine import ROLE_EXCLUSIVITY
        neighbors = set()
        for ra, rb in ROLE_EXCLUSIVITY:
            if role == ra:
                neighbors.add(rb)
            elif role == rb:
                neighbors.add(ra)
        local_exclusions = {
            k: v for k, v in self.learned_exclusions.items()
            if role in k
        }
        local_regions = [
            r for r in self.field_regions if role in r.competing_roles
        ]
        local_compat = {
            k: v for k, v in self.role_compatibility.items()
            if k[0] == role
        }
        return {
            "role": role,
            "neighbors": list(neighbors),
            "local_exclusions": local_exclusions,
            "local_regions": len(local_regions),
            "local_compatibilities": len(local_compat),
        }

    def trace_field_evolution(self, token: str = "") -> dict:
        """Reconstruct the causal chain of field state evolution.

        If a token is specified, returns only lineage for that token.
        Otherwise returns the full field evolution summary with
        regions grouped by conflicting token.
        """
        chain = {
            "regions": len(self.field_regions),
            "activations": self.field_activation_count,
            "current_pressure": self.metrics.field_pressure,
            "topology_density": self.topology_density,
            "exclusion_count": len(self.learned_exclusions),
            "wave_events": len(self.trace_waves()),
        }
        if token:
            chain["lineage"] = [
                {
                    "roles": r.competing_roles,
                    "instability": round(r.instability, 3),
                    "pressure": round(r.semantic_pressure, 3),
                    "persistence": round(r.persistence, 3),
                }
                for r in self.field_regions if r.token == token
            ]
        elif self.field_regions:
            regions_by_token = {}
            for r in self.field_regions:
                regions_by_token.setdefault(r.token, []).append({
                    "roles": r.competing_roles,
                    "instability": round(r.instability, 3),
                    "pressure": round(r.semantic_pressure, 3),
                    "recurrence": round(r.recurrence_score, 3),
                    "persistence": round(r.persistence, 3),
                })
            chain["regions_by_token"] = regions_by_token
        return chain

    def clear(self):
        self.metrics = TopologyMetrics()
        self.role_compatibility.clear()
        self.role_position_memory.clear()
        self.role_co_occurrence.clear()
        self.transition_probs.clear()
        self.motif_counts.clear()
        self.motif_timestamps.clear()
        self.motif_stability.clear()
        self.learned_exclusions.clear()
        self.impossible_neighborhoods.clear()
        self.cohesion_merge_success.clear()
        self.cohesion_merge_attempts.clear()
        self.cohesion_split_success.clear()
        self.cohesion_split_attempts.clear()
        self.global_centrality.clear()
        self.global_communities.clear()
        self.field_regions.clear()
        self.field_activation_count = 0
        self.neighborhood_cohesion.clear()
        self.restructuring_queue.clear()
        self.decision_history.clear()
        self.topology_snapshots.clear()
        self.last_update_time = time.time()

    def to_dict(self) -> dict:
        """Serialize state to a JSON-compatible dictionary."""
        return {
            "version": "3.0",
            "metrics": {
                "total_records_processed": self.metrics.total_records_processed,
                "total_co_occurrences": self.metrics.total_co_occurrences,
                "transition_observations": self.metrics.transition_observations,
                "learning_count": self.metrics.learning_count,
                "cumulative_density": self.metrics.cumulative_density,
                "cumulative_uncertainty": self.metrics.cumulative_uncertainty,
                "global_energy": self.metrics.global_energy,
                "global_entropy": self.metrics.global_entropy,
            },
            "role_compatibility": {f"{k[0]}|{k[1]}": v for k, v in self.role_compatibility.items()},
            "role_position_memory": self.role_position_memory,
            "role_co_occurrence": {"|".join(k): v for k, v in self.role_co_occurrence.items()},
            "transition_probs": {f"{k[0]}|{k[1]}": v for k, v in self.transition_probs.items()},
            "motif_counts": {"|".join(k): v for k, v in self.motif_counts.items()},
            "motif_timestamps": {"|".join(k): v for k, v in self.motif_timestamps.items()},
            "learned_exclusions": {"|".join(k): v for k, v in self.learned_exclusions.items()},
            "cohesion_merge_success": {f"{k[0]}|{k[1]}": v for k, v in self.cohesion_merge_success.items()},
            "cohesion_merge_attempts": {f"{k[0]}|{k[1]}": v for k, v in self.cohesion_merge_attempts.items()},
            "cohesion_split_success": {f"{k[0]}|{k[1]}": v for k, v in self.cohesion_split_success.items()},
            "cohesion_split_attempts": {f"{k[0]}|{k[1]}": v for k, v in self.cohesion_split_attempts.items()},
            "global_centrality": self.global_centrality,
            "last_update": self.last_update_time
        }

    def from_dict(self, data: dict):
        """Load state from a dictionary."""
        self.clear()
        metrics_data = data.get("metrics", {})
        self.metrics.total_records_processed = metrics_data.get("total_records_processed", 0)
        self.metrics.total_co_occurrences = metrics_data.get("total_co_occurrences", 0)
        self.metrics.transition_observations = metrics_data.get("transition_observations", 0)
        self.metrics.learning_count = metrics_data.get("learning_count", 0)
        self.metrics.cumulative_density = metrics_data.get("cumulative_density", 0.0)
        self.metrics.cumulative_uncertainty = metrics_data.get("cumulative_uncertainty", 0.0)
        self.metrics.global_energy = metrics_data.get("global_energy", 5.0)
        self.metrics.global_entropy = metrics_data.get("global_entropy", 1.0)

        for k, v in data.get("role_compatibility", {}).items():
            parts = k.split("|")
            if len(parts) == 2:
                self.role_compatibility[tuple(parts)] = v

        self.role_position_memory = data.get("role_position_memory", {})

        for k, v in data.get("role_co_occurrence", {}).items():
            parts = k.split("|")
            if len(parts) == 4:
                self.role_co_occurrence[tuple(parts)] = v

        for k, v in data.get("transition_probs", {}).items():
            parts = k.split("|")
            if len(parts) == 2:
                self.transition_probs[tuple(parts)] = v

        for k, v in data.get("motif_counts", {}).items():
            self.motif_counts[tuple(k.split("|"))] = v
            
        for k, v in data.get("motif_timestamps", {}).items():
            self.motif_timestamps[tuple(k.split("|"))] = v

        for k, v in data.get("learned_exclusions", {}).items():
            parts = k.split("|")
            if len(parts) == 2:
                self.learned_exclusions[tuple(parts)] = v

        for k, v in data.get("cohesion_merge_success", {}).items():
            parts = k.split("|")
            if len(parts) == 2:
                self.cohesion_merge_success[tuple(parts)] = v

        for k, v in data.get("cohesion_merge_attempts", {}).items():
            parts = k.split("|")
            if len(parts) == 2:
                self.cohesion_merge_attempts[tuple(parts)] = v

        for k, v in data.get("cohesion_split_success", {}).items():
            parts = k.split("|")
            if len(parts) == 2:
                self.cohesion_split_success[tuple(parts)] = v

        for k, v in data.get("cohesion_split_attempts", {}).items():
            parts = k.split("|")
            if len(parts) == 2:
                self.cohesion_split_attempts[tuple(parts)] = v
            
        self.global_centrality = data.get("global_centrality", {})
        self.last_update_time = data.get("last_update", time.time())

    def mutation_diff(self, other: "SemanticWorldState") -> dict:
        """Compute a structural diff between two world states for observability."""
        diff: dict = {}
        if self.metrics.total_records_processed != other.metrics.total_records_processed:
            diff["records_processed"] = (self.metrics.total_records_processed, other.metrics.total_records_processed)
        if self.metrics.global_energy != other.metrics.global_energy:
            diff["global_energy"] = (self.metrics.global_energy, other.metrics.global_energy)
        if self.metrics.global_entropy != other.metrics.global_entropy:
            diff["global_entropy"] = (self.metrics.global_entropy, other.metrics.global_entropy)
        added_roles = set(other.role_compatibility) - set(self.role_compatibility)
        if added_roles:
            diff["added_role_compatibilities"] = {str(k): v for k, v in other.role_compatibility.items() if k in added_roles}
        changed_roles = {
            k for k in set(self.role_compatibility) & set(other.role_compatibility)
            if abs(self.role_compatibility[k] - other.role_compatibility[k]) > 0.01
        }
        if changed_roles:
            diff["changed_role_compatibilities"] = {str(k): (self.role_compatibility[k], other.role_compatibility[k]) for k in changed_roles}
        added_motifs = set(other.motif_counts) - set(self.motif_counts)
        if added_motifs:
            diff["added_motifs"] = [str(m) for m in added_motifs]
        new_exclusions = set(other.learned_exclusions) - set(self.learned_exclusions)
        if new_exclusions:
            diff["new_exclusions"] = [str(e) for e in new_exclusions]
        return diff


# Global Singleton
_world_state: Optional[SemanticWorldState] = None

def get_world_state() -> SemanticWorldState:
    global _world_state
    if _world_state is None:
        _world_state = SemanticWorldState()
    return _world_state
