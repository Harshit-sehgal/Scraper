import math
import time
from collections import Counter
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass

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
        
        # Cohesion Field: Merge vs Split biases
        self.cohesion_merge_success: Dict[Tuple[str, str], float] = {}
        self.cohesion_merge_attempts: Dict[Tuple[str, str], float] = {}
        self.cohesion_split_success: Dict[Tuple[str, str], float] = {}
        self.cohesion_split_attempts: Dict[Tuple[str, str], float] = {}
        
        # Global Topology Distributions
        self.global_centrality: Dict[str, float] = {}
        self.global_communities: List[Set[str]] = []
        
        # Uncertainty Fields & Diagnostics
        self.decision_history: list = []
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


# Global Singleton
_world_state: Optional[SemanticWorldState] = None

def get_world_state() -> SemanticWorldState:
    global _world_state
    if _world_state is None:
        _world_state = SemanticWorldState()
    return _world_state
