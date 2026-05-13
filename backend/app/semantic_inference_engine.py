"""
Unified Probabilistic Semantic Inference Engine (Evolutionary)
==============================================================
THE CENTRAL BRAIN of the semantic cognition system.

Implements Continuous Semantic Evolution via Graph Relaxation 
and Topological Stabilization.

Meaning emerges from energy minimization over the relational topology.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from app.semantic_ir import (
    ExclusionEdge,
    SemanticGraph,
    SemanticToken,
    SemanticType,
)
from app.semantic_world_state import get_world_state
from app.event_dispatcher import get_dispatcher
from app.semantic_events import SemanticEvent, SemanticEventType

# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 1: BELIEF FIELD (Graph-Native)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BeliefField:
    """A continuous probabilistic belief field over the graph topology.
    Beliefs propagate along edges, biased by global motif memory.
    """
    node_beliefs: Dict[int, Dict[SemanticType, float]]
    node_uncertainties: Dict[int, float]
    field_entropy: float = 0.0
    field_coherence: float = 0.0

    @staticmethod
    def from_tokens(tokens: List[SemanticToken]) -> "BeliefField":
        node_beliefs = {}
        node_uncertainties = {}
        for i, token in enumerate(tokens):
            dist = dict(token.type_distribution) if token.type_distribution else {token.primary_type: 0.5}
            total = sum(dist.values())
            if total > 0:
                for k in dist:
                    dist[k] /= total
            node_beliefs[i] = dist
            node_uncertainties[i] = 1.0 - max(dist.values())
        return BeliefField(
            node_beliefs=node_beliefs,
            node_uncertainties=node_uncertainties,
            field_entropy=BeliefField._compute_field_entropy(node_beliefs),
            field_coherence=BeliefField._compute_field_coherence(node_beliefs, node_uncertainties),
        )

    @staticmethod
    def _compute_field_entropy(node_beliefs: Dict[int, Dict]) -> float:
        if not node_beliefs:
            return 1.0
        total_e = 0.0
        for dist in node_beliefs.values():
            e = sum(-v * math.log2(v) for v in dist.values() if v > 0)
            total_e += e
        return total_e / len(node_beliefs)

    @staticmethod
    def _compute_field_coherence(node_beliefs: Dict[int, Dict], node_uncertainties: Dict[int, float]) -> float:
        if not node_beliefs:
            return 0.0
        return 1.0 - (sum(node_uncertainties.values()) / len(node_uncertainties))


@dataclass
class SemanticState:
    """A single hypothesis for the graph topology."""
    belief_field: BeliefField
    energy: float = 5.0
    equilibrium: float = 0.0
    convergence: float = 0.0
    
    role_assignments: Dict[str, str] = field(default_factory=dict)
    motifs: List[Tuple[str, ...]] = field(default_factory=list)
    
    energy_history: List[float] = field(default_factory=list)

    def compute_equilibrium(self) -> float:
        """Measure proximity to semantic equilibrium."""
        if len(self.energy_history) < 2:
            return 0.0
        variance = sum((e - sum(self.energy_history[-3:]) / 3)**2 for e in self.energy_history[-3:]) / 3
        self.equilibrium = 1.0 - min(variance, 1.0)
        return self.equilibrium


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 2: SEMANTIC THERMODYNAMICS (Energy Minimization)
# ═══════════════════════════════════════════════════════════════════════════════

class SemanticThermodynamics:
    """Manages the evolution of the graph toward minimum energy equilibrium."""

    def __init__(self):
        self.ws = get_world_state()

    def compute_energy(self, state: SemanticState, graph: SemanticGraph) -> float:
        """Energy = Uncertainty + Contradiction + Entropy."""
        energy = 0.0
        
        # 1. Uncertainty heat (Global average vs local)
        local_u = sum(state.belief_field.node_uncertainties.values()) / max(len(graph.tokens), 1)
        energy += local_u * 3.0
        
        # 2. Contradiction pressure (Exclusion edges)
        for edge in graph.exclusion_edges:
            # If both nodes are active/assigned in this hypothesis, energy spikes
            v_src = state.role_assignments.get(str(edge.source_id))
            v_tgt = state.role_assignments.get(str(edge.target_id))
            if v_src and v_tgt and v_src == v_tgt:
                energy += edge.strength * 5.0
                
        # 3. Motif stability (Negative energy / Stabilizing force)
        for motif in state.motifs:
            stability = self.ws.get_motif_stability(motif)
            energy -= stability * 2.0
            
        state.energy = max(energy, 0.0)
        state.energy_history.append(state.energy)
        return state.energy

    def stabilize(self, state: SemanticState, graph: SemanticGraph):
        """Reinforce stable edges, decay high-energy ones."""
        if state.energy < self.ws.metrics.global_energy:
            # Universe cooling: stabilize
            for edge in graph.relationships:
                if edge.confidence > 0.5:
                    edge.confidence = min(edge.confidence + 0.02, 1.0)
        else:
            # Universe heating: destabilize
            for edge in graph.relationships:
                edge.confidence = max(edge.confidence - 0.05, 0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 3: CONTINUOUS INFERENCE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class InferenceEngine:
    """Orchestrates topological evolution and convergence."""

    def __init__(self, max_iterations: int = 10):
        self.max_iterations = max_iterations
        self.thermo = SemanticThermodynamics()
        self.ws = get_world_state()
        self.dispatcher = get_dispatcher()

    def infer(self, tokens: List[SemanticToken], schema_fields: List[str]) -> SemanticState:
        """Evolve the graph topology until equilibrium is reached."""
        graph = SemanticGraph(regions=[], tokens=tokens)
        self._build_exclusion_topology(graph, schema_fields)
        
        state = SemanticState(belief_field=BeliefField.from_tokens(tokens))
        
        for iteration in range(self.max_iterations):
            self._relax_graph(state, graph)
            self.thermo.compute_energy(state, graph)
            if state.compute_equilibrium() > 0.95:
                break
            self.thermo.stabilize(state, graph)
            self.ws.metrics.cumulative_uncertainty += (1.0 - state.belief_field.field_coherence)
            
        self.dispatcher.dispatch(SemanticEvent(
            event_type=SemanticEventType.EQUILIBRIUM_REACHED,
            source="inference_engine",
            payload={"energy": state.energy}
        ))
        return state

    def _build_exclusion_topology(self, graph: SemanticGraph, fields: List[str]):
        for i in range(len(fields)):
            for j in range(i+1, len(fields)):
                pair = tuple(sorted([fields[i], fields[j]]))
                if pair in self.ws.learned_exclusions:
                    graph.exclusion_edges.append(ExclusionEdge(
                        source_id=i, target_id=j, 
                        strength=self.ws.learned_exclusions[pair]
                    ))

    def _relax_graph(self, state: SemanticState, graph: SemanticGraph):
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 4: ROLE EMBEDDING ENGINE (Unified State Proxy)
# ═══════════════════════════════════════════════════════════════════════════════

class RoleEmbeddingEngine:
    """Learns role embeddings from global graph statistics."""

    def __init__(self):
        self.ws = get_world_state()

    @property
    def compatibility_cache(self) -> Dict[Tuple[str, str], float]:
        return self.ws.role_compatibility

    @property
    def learning_count(self) -> int:
        return self.ws.metrics.learning_count

    @learning_count.setter
    def learning_count(self, value: int):
        self.ws.metrics.learning_count = value

    @property
    def co_occurrence(self) -> Dict[Tuple[str, str, str, str], int]:
        return self.ws.role_co_occurrence

    @property
    def total_co_occurrences(self) -> int:
        return self.ws.metrics.total_co_occurrences

    @total_co_occurrences.setter
    def total_co_occurrences(self, value: int):
        self.ws.metrics.total_co_occurrences = value

    @property
    def _learned_exclusions(self) -> Dict[Tuple[str, str], float]:
        return self.ws.learned_exclusions

    @property
    def role_position_memory(self) -> Dict[str, List[float]]:
        return self.ws.role_position_memory

    def learn_role_position(self, role_name: str, position: float):
        if role_name not in self.role_position_memory:
            self.role_position_memory[role_name] = [0.0, 0.0]
        self.role_position_memory[role_name][0] += position
        self.role_position_memory[role_name][1] += 1.0

    def get_typical_position(self, role_name: str) -> float:
        if role_name not in self.role_position_memory:
            return 0.5
        mem = self.role_position_memory[role_name]
        if mem[1] == 0:
            return 0.5
        return mem[0] / mem[1]

    def learn_co_occurrence(self, assignment_a: tuple, assignment_b: tuple, success: bool):
        key = assignment_a + assignment_b
        self.co_occurrence[key] = self.co_occurrence.get(key, 0) + (1 if success else -1)
        self.total_co_occurrences += 1

    def get_co_occurrence_boost(self, role_a: str, type_a: str, role_b: str, type_b: str) -> float:
        key = (role_a, type_a, role_b, type_b)
        count = self.co_occurrence.get(key, 0)
        if self.total_co_occurrences == 0:
            return 0.0
        return max(-0.1, min(0.1, count / self.total_co_occurrences))

    def propagate_co_occurrence(self, assignments: Dict[str, Tuple[str, str]]) -> Dict[str, float]:
        boosts: Dict[str, float] = {}
        items = list(assignments.items())
        for i in range(len(items)):
            role_i, (type_i, _) = items[i]
            boost = 0.0
            for j in range(len(items)):
                if i == j:
                    continue
                role_j, (type_j, _) = items[j]
                boost += self.get_co_occurrence_boost(role_i, type_i, role_j, type_j)
            boosts[role_i] = boost / max(len(items) - 1, 1)
        return boosts

    def learn_contradiction(self, role_a: str, role_b: str, token_type: str):
        key = tuple(sorted([role_a, role_b]))
        self._learned_exclusions[key] = min(1.0, self._learned_exclusions.get(key, 0.0) + 0.15)

    def get_learned_exclusion(self, role_a: str, role_b: str) -> float:
        key = tuple(sorted([role_a, role_b]))
        return self._learned_exclusions.get(key, 0.0)

    def learn_from_allocation(self, role: str, token_type: SemanticType, token_raw: str, success: bool, delta: float = 0.05):
        type_str = token_type.value if hasattr(token_type, 'value') else str(token_type)
        key = (role, type_str)
        current = self.get_compatibility(role, token_type)
        effective_delta = delta if success else -delta
        self.compatibility_cache[key] = max(0.0, min(1.0, current + effective_delta))
        self.learning_count += 1

    def get_compatibility(self, role: str, token_type: SemanticType) -> float:
        type_str = token_type.value if hasattr(token_type, 'value') else str(token_type)
        key = (role, type_str)
        return self.compatibility_cache.get(key, 0.5)

    def get_certainty(self) -> float:
        if not self.compatibility_cache:
            return 0.0
        return sum(abs(v - 0.5) * 2 for v in self.compatibility_cache.values()) / len(self.compatibility_cache)

    def get_learning_speed(self) -> float:
        return min(self.learning_count / 100.0, 1.0)

    def get_calibrated_confidence(self, score: float) -> float:
        certainty = self.get_certainty()
        return score * (0.7 + 0.3 * certainty)
    
    def save_cache(self) -> dict:
        return {f"{r}:{t}": v for (r, t), v in self.compatibility_cache.items()}

    def load_cache(self, data: dict):
        self.compatibility_cache.clear()
        for k, v in data.items():
            if ':' in k:
                parts = k.split(':')
                self.compatibility_cache[(parts[0], parts[1])] = v


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 5: PERSISTENT SEMANTIC MEMORY
# ═══════════════════════════════════════════════════════════════════════════════

class SemanticMemory:
    def __init__(self):
        self.ws = get_world_state()

    def record_success(self, state: SemanticState):
        for motif in state.motifs:
            self.ws.reinforce_motif(motif)

    def get_preferred_motifs(self, top_k: int = 5) -> List[Tuple[str, ...]]:
        return [m for m, _ in self.ws.motif_counts.most_common(top_k)]

    def get_confidence_boost(self, motif: Tuple[str, ...]) -> float:
        return self.ws.get_motif_stability(motif) * 0.2

# Additional legacy/utility classes
@dataclass
class RelationshipEmbeddingSpace:
    dimension: int = 16
    def compute_embedding(self, node_idx: int, graph: SemanticGraph) -> List[float]:
        return [0.5] * self.dimension

class TopologyDynamicsEngine:
    def __init__(self, graph: SemanticGraph):
        self.graph = graph
    def evolve(self):
        pass

class DynamicAttention:
    def __init__(self, graph: SemanticGraph):
        self.graph = graph
    def compute(self) -> Dict[str, float]:
        return {}

def is_likely_noise_field(field_name: str, value: str) -> Tuple[bool, float, List[str]]:
    return False, 1.0, []
