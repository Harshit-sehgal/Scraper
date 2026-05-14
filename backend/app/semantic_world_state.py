import math
import time
from collections import Counter
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field


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


@dataclass
class TopologyMetrics:
    total_records_processed: int = 0
    total_co_occurrences: int = 0
    transition_observations: int = 0
    learning_count: int = 0
    # Equilibrium metrics
    cumulative_density: float = 0.0
    cumulative_uncertainty: float = 0.0
    global_energy: float = 5.0 # High energy = unstable universe
    global_entropy: float = 1.0 # High entropy = low order
    exclusion_count: int = 0 # Number of active learned exclusions
    
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
        """Unified semantic field pressure — fuses energy, entropy, uncertainty,
        and contradiction density into one scalar.

        All cognition should derive from this single scalar.
        High pressure = unstable, contradictory, uncertain field.
        Low pressure = stable, coherent, convergent field.
        """
        norm_energy = min(self.global_energy / 10.0, 1.0)
        contr_density = min(self.exclusion_count / max(self.total_records_processed, 1), 1.0)
        pressure = (norm_energy + self.global_entropy + self.average_uncertainty + contr_density) / 4.0
        return max(0.0, min(1.0, pressure))

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
        """Propagate instability from field regions to neighboring roles.

        Propagation is DAMPED — each wave spreads less energy than the last.
        This prevents recursive amplification while still allowing the field
        to evolve before allocation sees the propagated pressure.
        Returns the number of affected roles.
        """
        from app.semantic_allocation_engine import ROLE_EXCLUSIVITY
        affected = 0
        for region in self.field_regions:
            for role in region.competing_roles:
                for ra, rb in ROLE_EXCLUSIVITY:
                    peer = None
                    if role == ra:
                        peer = rb
                    elif role == rb:
                        peer = ra
                    if peer is not None and peer not in region.competing_roles:
                        # Damped propagation: each wave spreads less energy
                        decay = 1.0 / (1.0 + self.field_activation_count * 0.1)
                        spread = region.instability * 0.3 * decay
                        key = tuple(sorted([role, peer]))
                        current = self.learned_exclusions.get(key, 0.0)
                        self.learned_exclusions[key] = min(1.0, current + spread)
                        affected += 1
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
                            existing.instability = min(1.0, existing.instability + 0.15)
                            existing.recurrence_score = min(1.0, existing.recurrence_score + 0.1)
                            existing.semantic_pressure = self.metrics.field_pressure
                            existing.source_record = f"recurrence_{self.field_activation_count}"
                        else:
                            region = FieldConflictRegion(
                                competing_roles=[roles[i], roles[j]],
                                token=token_val,
                                instability=0.5,
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

    def decay_field_regions(self):
        """Apply local instability decay and prune converged regions.

        Each field region decays toward 0 independently — this is
        LOCAL equilibrium rather than global damping. Regions that
        reach 0 instability are removed (they have converged).
        High recurrence_score slows the decay (topology inertia).
        """
        surviving = []
        for r in self.field_regions:
            r.instability *= 0.95
            # Inertia: high recurrence means the region resists decay
            if r.recurrence_score > 0.3:
                r.instability = min(r.instability + 0.02, 1.0)
            if r.instability > 0.05:
                surviving.append(r)
        self.field_regions = surviving

    def snapshot(self, label: str = ""):
        """Record a compact topology snapshot for replay/debugging."""
        self.topology_snapshots.append({
            "label": label,
            "time": self.metrics.total_records_processed,
            "energy": self.metrics.global_energy,
            "entropy": self.metrics.global_entropy,
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

    def trace_field_evolution(self) -> dict:
        """Reconstruct the causal chain of field state evolution.

        Returns a dict mapping each field region to its propagation
        effects, equilibrium influence, and persistence over time.
        This enables semantic lineage tracing and causal chain
        reconstruction for debugging field dynamics.
        """
        chain = {
            "regions": len(self.field_regions),
            "activations": self.field_activation_count,
            "current_pressure": self.metrics.field_pressure,
            "topology_density": self.topology_density,
            "exclusion_count": len(self.learned_exclusions),
            "wave_events": len(self.trace_waves()),
        }
        if self.field_regions:
            regions_by_token = {}
            for r in self.field_regions:
                token = r.token
                if token not in regions_by_token:
                    regions_by_token[token] = []
                regions_by_token[token].append({
                    "roles": r.competing_roles,
                    "instability": round(r.instability, 3),
                    "pressure": round(r.semantic_pressure, 3),
                    "recurrence": round(r.recurrence_score, 3),
                })
            chain["regions_by_token"] = regions_by_token
        return chain

    def field_lineage(self, token: str) -> list:
        """Trace the lineage of a specific conflicting token across records.

        Returns the history of field regions for this token, showing how
        its instability, exclusion pressure, and recurrence evolved.
        """
        return [
            {
                "roles": r.competing_roles,
                "instability": round(r.instability, 3),
                "pressure": round(r.semantic_pressure, 3),
            }
            for r in self.field_regions if r.token == token
        ]

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
        self.decision_history.clear()
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
