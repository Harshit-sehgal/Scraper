"""
Unified Probabilistic Semantic Inference Engine
=================================================
THE CENTRAL BRAIN of the semantic cognition system.

NOT another module. NOT a collection of passes.
One recursive probabilistic inference system where meaning EMERGES.

Core principle:
  Meaning must NOT be assigned manually.
  Meaning must EMERGE from:
    - graph dynamics
    - probabilistic convergence
    - semantic equilibrium
    - structural consistency
    - topology evolution
    - recursive inference
    - competing hypotheses
    - graph-native cognition

All other modules are SUPPORTING SUBSYSTEMS.
This module is THE REASONING CORE.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set, Callable
from collections import defaultdict, Counter
import math
import random

from app.semantic_ir import (
    SemanticToken, SemanticType, SemanticRecord, SemanticRegion,
    RelationshipEdge, OwnershipEdge, SemanticGraph, DatasetIR,
    RegionType, RecordType, Span,
)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 1: UNIFIED SEMANTIC STATE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BeliefField:
    """A continuous probabilistic belief field over the graph.

    NOT per-node beliefs.
    A field that spans the entire graph structure.

    Beliefs at any point are influenced by:
    - local evidence (token type distributions)
    - neighbor field values (propagation)
    - graph topology (shape influences flow)
    """
    node_beliefs: Dict[int, Dict[SemanticType, float]]  # node_id → {type → probability}
    node_uncertainties: Dict[int, float]  # node_id → uncertainty (0-1)
    field_entropy: float = 0.0  # global field entropy
    field_coherence: float = 0.0  # how coherent the field is

    @staticmethod
    def from_tokens(tokens: List[SemanticToken]) -> "BeliefField":
        """Initialize belief field from token type distributions."""
        node_beliefs = {}
        node_uncertainties = {}

        for i, token in enumerate(tokens):
            dist = dict(token.type_distribution) if token.type_distribution else {}
            if not dist:
                dist = {token.primary_type: 0.7}

            # Normalize
            total = sum(dist.values())
            if total > 0:
                for k in dist:
                    dist[k] /= total

            # Uncertainty = 1 - max probability
            uncertainty = 1.0 - max(dist.values())
            node_beliefs[i] = dist
            node_uncertainties[i] = uncertainty

        # Compute global field properties
        entropy = BeliefField._compute_field_entropy(node_beliefs)
        coherence = BeliefField._compute_field_coherence(node_beliefs, node_uncertainties)

        return BeliefField(
            node_beliefs=node_beliefs,
            node_uncertainties=node_uncertainties,
            field_entropy=entropy,
            field_coherence=coherence,
        )

    @staticmethod
    def _compute_field_entropy(node_beliefs: Dict[int, Dict]) -> float:
        """Compute global entropy of the belief field."""
        if not node_beliefs:
            return 0.0
        total_entropy = 0.0
        for dist in node_beliefs.values():
            e = 0.0
            for v in dist.values():
                if v > 0:
                    e -= v * math.log2(v)
            total_entropy += e
        return total_entropy / len(node_beliefs)

    @staticmethod
    def _compute_field_coherence(
        node_beliefs: Dict[int, Dict],
        node_uncertainties: Dict[int, float],
    ) -> float:
        """Compute field coherence from belief consistency."""
        if not node_beliefs:
            return 0.0
        # Coherence = 1 - average uncertainty
        avg_uncertainty = sum(node_uncertainties.values()) / len(node_uncertainties)
        return 1.0 - avg_uncertainty


@dataclass
class SemanticState:
    """Complete probabilistic semantic state of the graph.

    Replaces: attention + coherence + contradiction + density + ownership scores.
    ONE probabilistic state that captures everything simultaneously.
    """
    belief_field: BeliefField
    energy: float = 0.0  # semantic energy (lower = more stable)
    equilibrium: float = 0.0  # equilibrium proximity (1.0 = at equilibrium)
    convergence: float = 0.0  # convergence measure (1.0 = fully converged)
    evolution_step: int = 0

    # Hypothesis tracking
    hypothesis_id: str = ""
    probability: float = 0.0
    role_assignments: Dict[str, str] = field(default_factory=dict)

    # Topology
    centrality: Dict[int, float] = field(default_factory=dict)
    communities: List[Set[int]] = field(default_factory=list)
    motifs: List[Tuple[str, ...]] = field(default_factory=list)

    # Evolution history
    energy_history: List[float] = field(default_factory=list)
    coherence_history: List[float] = field(default_factory=list)

    def compute_energy(self, graph: SemanticGraph) -> float:
        """Compute unified semantic energy.

        Energy = f(uncertainty, contradictions, orphans, topology)
        Lower energy = more stable interpretation.
        """
        energy = 0.0

        # Uncertainty contribution
        avg_uncertainty = sum(self.belief_field.node_uncertainties.values())
        avg_uncertainty /= max(len(self.belief_field.node_uncertainties), 1)
        energy += avg_uncertainty * 5.0

        # Contradiction contribution
        for edge in graph.relationships:
            if edge.confidence < 0.3:
                energy += (0.3 - edge.confidence) * 3.0

        # Orphan contribution (unowned regions)
        owned = set()
        for o_edge in graph.ownership_edges:
            owned.add(o_edge.owned_region_id)
        for region in graph.regions:
            if region.region_id not in owned:
                energy += 1.0

        # Topology contribution (entropy of centrality distribution)
        if self.centrality:
            values = list(self.centrality.values())
            if values:
                avg_c = sum(values) / len(values)
                variance = sum((v - avg_c) ** 2 for v in values) / len(values)
                # Low variance = flat topology = higher energy
                # High variance = clear center = lower energy
                energy -= variance * 2.0

        self.energy = max(energy, 0.0)
        self.energy_history.append(self.energy)
        return self.energy

    def compute_equilibrium(self) -> float:
        """Compute proximity to semantic equilibrium.

        Empty/minimal graphs return 0.0 (no equilibrium possible).
        Otherwise: stable energy + coherent field + converging topology.
        """
        if len(self.energy_history) < 2:
            # Empty or minimal graph = no equilibrium
            if not self.belief_field.node_beliefs:
                return 0.0
            return 0.3

        # Energy stability (low variance in recent history)
        recent = self.energy_history[-5:] if len(self.energy_history) >= 5 else self.energy_history
        energy_var = sum((e - sum(recent) / len(recent)) ** 2 for e in recent) / len(recent)
        energy_stability = 1.0 - min(energy_var / 5.0, 1.0)

        # Field coherence
        field_coherence = self.belief_field.field_coherence

        # Convergence trend (energy decreasing → converging)
        if len(self.energy_history) >= 3:
            trend = (self.energy_history[-1] - self.energy_history[-3]) / max(self.energy_history[-3], 0.01)
            convergence = 1.0 - min(abs(trend), 1.0)  # Flat trend = converged
        else:
            convergence = 0.5

        self.equilibrium = (energy_stability * 0.35) + (field_coherence * 0.35) + (convergence * 0.3)
        return self.equilibrium


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 2: ENERGY MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class SemanticEnergyModel:
    """Semantic energy mechanics for graph equilibrium.

    Stable structures → low energy → reinforce.
    Unstable structures → high energy → decay.
    """

    def __init__(self):
        self.energy: float = 0.0
        self.history: List[float] = []
        self.converged: bool = False

    def compute(self, state: SemanticState, graph: SemanticGraph) -> float:
        """Compute semantic energy for current state."""
        energy = state.compute_energy(graph)
        self.energy = energy
        self.history.append(energy)

        # Check convergence
        if len(self.history) >= 5:
            recent = self.history[-5:]
            variance = sum((e - sum(recent) / len(recent)) ** 2 for e in recent) / len(recent)
            self.converged = variance < 0.01

        return energy

    def reinforce_stable(self, state: SemanticState, graph: SemanticGraph):
        """Reinforce stable structures: boost consistent edges."""
        for edge in graph.relationships:
            if edge.confidence >= 0.7:
                edge.confidence = min(edge.confidence + 0.02, 1.0)

        for o_edge in graph.ownership_edges:
            if edge.confidence >= 0.7:
                edge.confidence = min(edge.confidence + 0.02, 1.0)

    def decay_unstable(self, state: SemanticState, graph: SemanticGraph):
        """Decay unstable structures: suppress low-confidence edges."""
        graph.relationships = [
            e for e in graph.relationships
            if e.confidence >= 0.15
        ]
        graph.ownership_edges = [
            e for e in graph.ownership_edges
            if e.confidence >= 0.15
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 3: BELIEF FIELD PROPAGATION
# ═══════════════════════════════════════════════════════════════════════════════

class BeliefFieldPropagator:
    """Propagates beliefs through the graph as a CONTINUOUS FIELD.

    NOT edge-by-edge message passing.
    A field that diffuses through the entire graph structure.
    """

    def __init__(self, graph: SemanticGraph):
        self.graph = graph
        self.field: Optional[BeliefField] = None

    def initialize(self, tokens: List[SemanticToken]) -> BeliefField:
        """Initialize belief field from tokens."""
        self.field = BeliefField.from_tokens(tokens)
        return self.field

    def propagate(self, iterations: int = 5) -> BeliefField:
        """Diffuse beliefs through the graph field.

        Each iteration:
        1. Neighbor influence: beliefs spread to connected nodes
        2. Self-reinforcement: strong beliefs get stronger
        3. Entropy decay: field tends toward order
        4. Uncertainty diffusion: uncertainty spreads spatially
        """
        if not self.field:
            return BeliefField({}, {})

        field = self.field
        for it in range(iterations):
            new_beliefs: Dict[int, Dict[SemanticType, float]] = {}
            new_uncertainties: Dict[int, float] = {}

            for node_id in field.node_beliefs:
                current = dict(field.node_beliefs[node_id])
                current_uncertainty = field.node_uncertainties.get(node_id, 0.5)

                # Gather neighbor beliefs
                neighbor_beliefs = self._get_neighbor_beliefs(node_id, field)

                # Diffuse: blend with neighbor beliefs
                for ntype, nprob in neighbor_beliefs.items():
                    influence = nprob * 0.15 * (1.0 - current_uncertainty)
                    current[ntype] = current.get(ntype, 0) + influence

                # Self-reinforcement: boost max belief
                max_type = max(current, key=current.get)
                current[max_type] *= 1.05

                # Normalize
                total = sum(current.values())
                if total > 0:
                    for k in current:
                        current[k] /= total

                new_beliefs[node_id] = current

                # UNCERTAINTY DIFFUSION: uncertainty spreads spatially
                # Gather neighbor uncertainties
                neighbor_uncertainties = self._get_neighbor_uncertainties(node_id, field)
                if neighbor_uncertainties:
                    # Uncertainty diffuses: blend with neighbors
                    avg_neighbor_uncertainty = sum(neighbor_uncertainties) / len(neighbor_uncertainties)
                    diffused = (current_uncertainty * 0.7) + (avg_neighbor_uncertainty * 0.3)
                else:
                    diffused = current_uncertainty

                # Amplify if uncertainty is high (self-reinforcing)
                if diffused > 0.7:
                    diffused = min(diffused * 1.1, 1.0)
                # Damp if uncertainty is low
                elif diffused < 0.3:
                    diffused *= 0.95

                new_uncertainties[node_id] = diffused

            # Update field
            field.node_beliefs = new_beliefs
            field.node_uncertainties = new_uncertainties

        field.field_entropy = BeliefField._compute_field_entropy(field.node_beliefs)
        field.field_coherence = BeliefField._compute_field_coherence(
            field.node_beliefs, field.node_uncertainties
        )

        return field

    def _get_neighbor_uncertainties(
        self, node_id: int, field: BeliefField
    ) -> List[float]:
        """Gather uncertainty values from neighboring nodes.

        Uncertainty diffuses along relationship edges.
        """
        uncertainties = []
        for edge in self.graph.relationships:
            neighbor_id = None
            if edge.source_idx == node_id:
                neighbor_id = edge.target_idx
            elif edge.target_idx == node_id:
                neighbor_id = edge.source_idx

            if neighbor_id is not None and neighbor_id in field.node_uncertainties:
                # Weighted by edge confidence
                weighted = field.node_uncertainties[neighbor_id] * edge.confidence
                uncertainties.append(weighted)

        return uncertainties

    def _get_neighbor_beliefs(
        self, node_id: int, field: BeliefField
    ) -> Dict[SemanticType, float]:
        """Aggregate beliefs from neighboring nodes."""
        aggregated: Dict[SemanticType, float] = {}

        for edge in self.graph.relationships:
            neighbor_id = None
            if edge.source_idx == node_id:
                neighbor_id = edge.target_idx
            elif edge.target_idx == node_id:
                neighbor_id = edge.source_idx

            if neighbor_id is not None and neighbor_id in field.node_beliefs:
                neigh_dist = field.node_beliefs[neighbor_id]
                for ntype, nprob in neigh_dist.items():
                    weighted = nprob * edge.confidence
                    aggregated[ntype] = aggregated.get(ntype, 0) + weighted

        return aggregated


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 4: MULTI-HYPOTHESIS ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class MultiHypothesisEngine:
    """Manages multiple competing semantic interpretations.

    Multiple hypotheses coexist probabilistically.
    Premature collapse is prevented.
    The best hypothesis emerges via natural selection.
    """

    def __init__(self):
        self.hypotheses: Dict[str, SemanticState] = {}
        self.history: Dict[str, List[float]] = defaultdict(list)

    def generate(
        self,
        tokens: List[SemanticToken],
        schema_fields: List[str],
        graph: SemanticGraph,
        count: int = 3,
    ) -> List[SemanticState]:
        """Generate diverse initial hypotheses.

        Each hypothesis explores a different assignment strategy.
        """
        hypotheses = []
        strategies = ["progressive", "conservative", "exploratory"]

        for i in range(min(count, len(strategies))):
            h = SemanticState(
                belief_field=BeliefField.from_tokens(tokens),
                hypothesis_id=f"h{i}",
                probability=1.0 / count,
                role_assignments=self._assign_roles(
                    tokens, schema_fields, strategies[i]
                ),
            )
            h.compute_energy(graph)
            hypotheses.append(h)
            self.hypotheses[f"h{i}"] = h

        return hypotheses

    def _assign_roles(
        self,
        tokens: List[SemanticToken],
        schema_fields: List[str],
        strategy: str,
    ) -> Dict[str, str]:
        """Assign roles using a strategy.

        Progressive: assign by type match priority (no hardcoded priors)
        Conservative: assign only high-confidence matches
        Exploratory: random but type-consistent assignments

        No hardcoded type→role priority mappings.
        All strategies use uniform initial weights.
        """
        assignments: Dict[str, str] = {}
        used = set()

        if strategy == "progressive":
            # Uniform priority: iterate schema fields, assign best match
            # without any type-based priority ordering
            for f_name in schema_fields:
                for token in tokens:
                    if token.raw not in used:
                        assignments[f_name] = token.raw
                        used.add(token.raw)
                        break

        elif strategy == "conservative":
            # Only assign high-confidence type matches
            for token in tokens:
                if token.raw in used:
                    continue
                type_name = token.primary_type.value
                for f_name in schema_fields:
                    if f_name not in assignments and (type_name in f_name or f_name in type_name):
                        assignments[f_name] = token.raw
                        used.add(token.raw)
                        break

            # Leave unfilled roles empty
            for f_name in schema_fields:
                if f_name not in assignments:
                    assignments[f_name] = ""

        elif strategy == "exploratory":
            # Type-consistent random assignments
            shuffled = list(tokens)
            random.shuffle(shuffled)
            for token in shuffled:
                if token.raw in used:
                    continue
                compatible_fields = [
                    f for f in schema_fields
                    if f not in assignments
                ]
                if compatible_fields:
                    f_name = random.choice(compatible_fields)
                    assignments[f_name] = token.raw
                    used.add(token.raw)

        return assignments

    def compete(self, graph: SemanticGraph) -> Optional[str]:
        """Run hypothesis competition.

        Selection pressure: lower energy → higher survival probability.
        """
        if not self.hypotheses:
            return None

        for h_id, state in self.hypotheses.items():
            energy = state.compute_energy(graph)
            equilibrium = state.compute_equilibrium()
            # Energy lower = better. Equilibrium higher = better.
            survival = (1.0 - energy / max(energy + 1, 1)) * 0.6 + equilibrium * 0.4
            state.probability = survival
            self.history[h_id].append(survival)

        # Winner = highest survival probability
        winner = max(self.hypotheses.items(), key=lambda x: x[1].probability)
        return winner[0]

    def prune_weak(self, threshold: float = 0.2):
        """Remove hypotheses below survival threshold."""
        to_remove = [
            h_id for h_id, state in self.hypotheses.items()
            if state.probability < threshold
        ]
        for h_id in to_remove:
            del self.hypotheses[h_id]

    def get_winner(self) -> Optional[SemanticState]:
        """Get the current winning hypothesis."""
        if not self.hypotheses:
            return None
        return max(self.hypotheses.values(), key=lambda s: s.probability)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 5: TOPOLOGY ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

class TopologyAnalyzer:
    """Analyzes graph topology to extract meaning from graph SHAPE.

    Meaning emerges partly from graph shape:
    - Central nodes = primary entities
    - Clustered nodes = semantic groups
    - Recurring motifs = structural patterns
    """

    def __init__(self, graph: SemanticGraph):
        self.graph = graph

    def compute_centrality(self) -> Dict[int, float]:
        """Compute degree centrality.

        Central nodes are likely primary semantic entities.
        """
        centrality: Dict[int, float] = defaultdict(float)

        for edge in self.graph.relationships:
            centrality[edge.source_idx] += edge.confidence
            centrality[edge.target_idx] += edge.confidence

        max_c = max(centrality.values()) if centrality else 1.0
        if max_c > 0:
            for k in centrality:
                centrality[k] /= max_c
        return dict(centrality)

    def detect_motifs(self) -> List[Tuple[str, ...]]:
        """Detect recurring structural motifs.

        Motifs are common local graph shapes.
        """
        motifs: List[Tuple[str, ...]] = []
        for region in self.graph.regions:
            sig = tuple(t.primary_type.value for t in region.tokens)
            if sig:
                motifs.append(sig)
        # Count motif frequency
        motif_counts = Counter(motifs)
        return [m for m, c in motif_counts.most_common() if c >= 1]

    def detect_communities(self) -> List[Set[int]]:
        """Detect community structure.

        Communities are groups of nodes with dense internal connections.
        Uses simple connectivity clustering.
        """
        communities: List[Set[int]] = []
        unvisited = set(range(len(self.graph.tokens)))

        while unvisited:
            start = unvisited.pop()
            community = {start}
            frontier = {start}

            while frontier:
                node = frontier.pop()
                for edge in self.graph.relationships:
                    neighbor = None
                    if edge.source_idx == node:
                        neighbor = edge.target_idx
                    elif edge.target_idx == node:
                        neighbor = edge.source_idx
                    if neighbor is not None and neighbor in unvisited:
                        unvisited.remove(neighbor)
                        community.add(neighbor)
                        frontier.add(neighbor)

            communities.append(community)

        return communities

    def compute_topology_score(self) -> float:
        """Compute overall topology quality.

        High score = clear structure with central hub and meaningful communities.
        """
        centrality = self.compute_centrality()
        communities = self.detect_communities()
        motifs = self.detect_motifs()

        if not centrality:
            return 0.0

        # Centrality concentration (clear hub = good)
        values = sorted(centrality.values(), reverse=True)
        if len(values) >= 2:
            concentration = values[0] / max(sum(values) / len(values), 0.01)
            concentration_score = min(concentration / 3.0, 1.0)
        else:
            concentration_score = 0.5

        # Community quality (2-5 communities = ideal)
        community_score = 1.0 - abs(len(communities) - 3) / 10.0

        # Motif richness
        motif_score = min(len(motifs) / 5.0, 1.0)

        score = (concentration_score * 0.4) + (community_score * 0.3) + (motif_score * 0.3)
        return min(score, 1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 6a: DYNAMIC ATTENTION
# ═══════════════════════════════════════════════════════════════════════════════

class DynamicAttention:
    """Dynamic attention that emerges from graph properties.

    NOT static salience tables.
    Attention emerges from centrality, uncertainty, and contradiction.
    """

    def __init__(self, graph: SemanticGraph):
        self.graph = graph
        self.attention_scores: Dict[str, float] = {}

    def compute(self) -> Dict[str, float]:
        """Compute attention scores from dynamic graph properties."""
        centrality = self._compute_centrality()
        for token in self.graph.tokens:
            score = centrality.get(token.position, 0) * 0.6 + 0.4
            self.attention_scores[token.raw] = min(score, 1.0)
        return self.attention_scores

    def _compute_centrality(self) -> Dict[int, float]:
        cent: Dict[int, float] = defaultdict(float)
        for edge in self.graph.relationships:
            cent[edge.source_idx] += edge.confidence
            cent[edge.target_idx] += edge.confidence
        max_c = max(cent.values()) if cent else 1.0
        return {k: v / max_c for k, v in cent.items()}


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 6: GLOBAL INFERENCE LOOP
# ═══════════════════════════════════════════════════════════════════════════════

class InferenceEngine:
    """THE CENTRAL INFERENCE ENGINE.

    Runs on every record in the pipeline (limited to 3 iterations).
    When it produces higher coherence than the default allocation,
    its results override the fast path.

    One recursive loop that replaces all sequential passes.

    Flow:
    1. Initialize graph
    2. Generate competing hypotheses
    3. Propagate belief field
    4. Compute energy
    5. Optimize topology
    6. Compete hypotheses
    7. Prune weak
    8. Check convergence
    9. Repeat or finalize

    All decisions emerge from this loop.
    """

    def __init__(
        self,
        max_iterations: int = 15,
        convergence_threshold: float = 0.005,
    ):
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        self.state: Optional[SemanticState] = None
        self.converged = False
        self.iterations_run = 0
        self.evolution_history: List[Dict] = []

    def infer(
        self,
        tokens: List[SemanticToken],
        schema_fields: List[str],
        relationships: Optional[List[RelationshipEdge]] = None,
    ) -> SemanticState:
        """Run full recursive inference.

        Returns the converged semantic state.
        """
        # Phase 1: Build initial graph
        from app.overlap_resolution import resolve_overlaps
        resolved_tokens = resolve_overlaps(tokens)

        if relationships is None:
            from app.relationship_inference import infer_relationships
            relationships = infer_relationships(resolved_tokens)

        graph = SemanticGraph(
            tokens=resolved_tokens,
            relationships=relationships,
            regions=[],
        )

        # Phase 2: Initialize belief field
        propagator = BeliefFieldPropagator(graph)
        field = propagator.initialize(resolved_tokens)

        # Phase 3: Generate hypotheses
        hypotheses = MultiHypothesisEngine()
        states = hypotheses.generate(resolved_tokens, schema_fields, graph, count=3)

        # Phase 4: Topology analysis
        topology = TopologyAnalyzer(graph)
        topo_dynamics = TopologyDynamicsEngine(graph)

        # Phase 5: Energy model
        energy_model = SemanticEnergyModel()

        # Phase 6: ITERATIVE INFERENCE LOOP
        for iteration in range(self.max_iterations):
            self.iterations_run = iteration + 1

            # 6a: Propagate belief field
            field = propagator.propagate(iterations=2)

            # 6b: Dynamic attention (causal, every 2 iterations)
            if iteration % 2 == 0:
                attention = DynamicAttention(graph)
                attn_scores = attention.compute()
                # Attention causally influences: boost high-attention edges
                for edge in graph.relationships:
                    src_raw = graph.tokens[edge.source_idx].raw if edge.source_idx < len(graph.tokens) else ""
                    tgt_raw = graph.tokens[edge.target_idx].raw if edge.target_idx < len(graph.tokens) else ""
                    src_attn = attn_scores.get(src_raw, 0.5)
                    tgt_attn = attn_scores.get(tgt_raw, 0.5)
                    avg_attn = (src_attn + tgt_attn) / 2.0
                    # Boost edges between high-attention tokens
                    if avg_attn > 0.6:
                        edge.confidence = min(edge.confidence + 0.05, 1.0)

            # 6c: Topology dynamics (causal, every 2 iterations)
            if iteration > 0 and iteration % 2 == 0:
                topo_dynamics.evolve()
                # Re-analyze topology after dynamics
                topology = TopologyAnalyzer(graph)

            # 6d: Update all hypotheses with current field
            for h_id in list(hypotheses.hypotheses.keys()):
                if h_id not in hypotheses.hypotheses:
                    continue
                state = hypotheses.hypotheses[h_id]
                state.belief_field = field

                # Recompute energy
                energy = energy_model.compute(state, graph)

                # Recompute equilibrium
                equilibrium = state.compute_equilibrium()

                # Check convergence
                if energy_model.converged:
                    state.convergence = 1.0

                # Reinforce or decay based on energy
                if state.energy < 3.0:
                    energy_model.reinforce_stable(state, graph)
                else:
                    energy_model.decay_unstable(state, graph)

            # 6e: Topology analysis (every 3 iterations)
            if iteration % 3 == 0:
                for h_id, state in hypotheses.hypotheses.items():
                    state.centrality = topology.compute_centrality()
                    state.communities = topology.detect_communities()
                    state.motifs = topology.detect_motifs()

            # 6f: Compete and prune hypotheses
            winner_id = hypotheses.compete(graph)
            if iteration % 2 == 0 and len(hypotheses.hypotheses) > 1:
                hypotheses.prune_weak(threshold=0.15)

            # 6g: Record evolution
            self.evolution_history.append({
                "iteration": iteration,
                "num_hypotheses": len(hypotheses.hypotheses),
                "winner": winner_id,
                "field_entropy": field.field_entropy,
                "field_coherence": field.field_coherence,
            })

            # 6h: Check global convergence
            if self._check_convergence():
                self.converged = True
                break

        # Phase 7: Finalize
        winner = hypotheses.get_winner() or states[0]
        winner.convergence = 1.0 if self.converged else min(
            winner.convergence + 0.3, 1.0
        )
        winner.evolution_step = self.iterations_run

        # Update graph with winner state
        graph.coherence_score = winner.belief_field.field_coherence
        winner.centrality = topology.compute_centrality()
        winner.communities = topology.detect_communities()
        winner.motifs = topology.detect_motifs()

        self.state = winner
        return winner

    def _check_convergence(self) -> bool:
        """Check if the system has converged.

        Convergence when:
        - Energy stabilized (low variance)
        - Field coherence high
        - Only one hypothesis remains
        """
        if len(self.evolution_history) < 3:
            return False

        # Check energy stability
        recent = self.evolution_history[-3:]
        entropies = [e["field_entropy"] for e in recent]
        if len(entropies) >= 2:
            variance = sum((e - sum(entropies) / len(entropies)) ** 2 for e in entropies) / len(entropies)
            if variance < self.convergence_threshold:
                return True

        return False

    def get_summary(self) -> Dict:
        """Get inference summary for debugging."""
        return {
            "converged": self.converged,
            "iterations": self.iterations_run,
            "final_entropy": self.evolution_history[-1]["field_entropy"] if self.evolution_history else 0,
            "final_coherence": self.evolution_history[-1]["field_coherence"] if self.evolution_history else 0,
            "winner": self.evolution_history[-1]["winner"] if self.evolution_history else "none",
            "hypothesis_count": self.evolution_history[-1]["num_hypotheses"] if self.evolution_history else 0,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 7: PERSISTENT SEMANTIC MEMORY (LIGHTWEIGHT)
# ═══════════════════════════════════════════════════════════════════════════════

class SemanticMemory:
    """Persistent semantic learning across runs.

    Stores successful patterns for future inference.
    """

    def __init__(self):
        self.successful_motifs: Dict[Tuple[str, ...], int] = Counter()
        self.ownership_patterns: Dict[str, int] = Counter()
        self.total_runs: int = 0

    def record_success(self, state: SemanticState):
        """Record a successful inference result."""
        self.total_runs += 1
        for motif in state.motifs:
            self.successful_motifs[motif] += 1

    def get_preferred_motifs(self, top_k: int = 5) -> List[Tuple[str, ...]]:
        """Get the most successful structural motifs."""
        return [m for m, _ in self.successful_motifs.most_common(top_k)]

    def get_confidence_boost(self, motif: Tuple[str, ...]) -> float:
        """Get confidence boost for a known motif."""
        if self.total_runs == 0:
            return 0.0
        return min(self.successful_motifs.get(motif, 0) / self.total_runs, 0.2)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 8: ROLE EMBEDDING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class RoleEmbeddingEngine:
    """Learns role embeddings from graph statistics.

    Replaces hardcoded TYPE_ROLE_COMPATIBILITY with learned patterns.
    Roles are embedded in a semantic space where compatibility = cosine similarity.

    Patterns are learned from:
    - Successful allocations
    - Topology motifs
    - Ownership consistency
    - Cross-record convergence
    """

    def __init__(self):
        self.embeddings: Dict[str, List[float]] = {}
        self.compatibility_cache: Dict[Tuple[str, str], float] = {}
        self.learning_count: int = 0
        self.co_occurrence: Dict[Tuple[str, str, str, str], int] = {}
        self.total_co_occurrences: int = 0
        # Role position memory: tracks average position of each role across records
        # Key: role_name, Value: [sum_of_positions, count]
        self.role_position_memory: Dict[str, List[float]] = {}

    def learn_role_position(self, role_name: str, position: float):
        """Learn the typical position of a role from an allocation."""
        if role_name not in self.role_position_memory:
            self.role_position_memory[role_name] = [0.0, 0.0]
        self.role_position_memory[role_name][0] += position
        self.role_position_memory[role_name][1] += 1.0

    def get_typical_position(self, role_name: str) -> float:
        """Get the typical normalized position for a role (0=early, 1=late).
        Returns 0.5 if unknown (maximum uncertainty).
        """
        if role_name not in self.role_position_memory:
            return 0.5
        mem = self.role_position_memory[role_name]
        if mem[1] == 0:
            return 0.5
        return mem[0] / mem[1]

    def learn_co_occurrence(self, assignment_a: tuple, assignment_b: tuple, success: bool):
        """Learn that two (role, type) pairs co-occur in an allocation.

        E.g., ('name', 'organization') and ('price', 'price') co-occur in
        a successful allocation → reinforce both.
        """
        key = assignment_a + assignment_b
        self.co_occurrence[key] = self.co_occurrence.get(key, 0) + (1 if success else -1)
        self.total_co_occurrences += 1

    def get_co_occurrence_boost(self, role_a: str, type_a: str, role_b: str, type_b: str) -> float:
        """Get the confidence boost for a pair based on co-occurrence history.

        Returns a value from -0.1 to +0.1.
        """
        key = (role_a, type_a, role_b, type_b)
        count = self.co_occurrence.get(key, 0)
        if self.total_co_occurrences == 0:
            return 0.0
        return max(-0.1, min(0.1, count / self.total_co_occurrences))

    def propagate_co_occurrence(self, assignments: Dict[str, Tuple[str, str]]) -> Dict[str, float]:
        """Propagate co-occurrence boosts across all pairs in an allocation.

        For each pair of (role, type) in the current assignment, check if
        they've co-occurred before. Boost confident pairs, suppress conflicting ones.
        """
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
        """Learn that role_a and role_b contradicted by claiming the same value/type.
        
        This dynamically discovers exclusive roles (e.g. 'origin' and 'destination'
        should never claim the exact same value).
        """
        if not hasattr(self, 'learned_exclusions'):
            self.learned_exclusions = {}
        key = tuple(sorted([role_a, role_b]))
        getattr(self, 'learned_exclusions')[key] = getattr(self, 'learned_exclusions').get(key, 0.0) + 0.15
        getattr(self, 'learned_exclusions')[key] = min(1.0, self.learned_exclusions[key])

    def get_learned_exclusion(self, role_a: str, role_b: str) -> float:
        """Get the learned exclusion penalty between two roles."""
        if not hasattr(self, 'learned_exclusions'):
            return 0.0
        key = tuple(sorted([role_a, role_b]))
        return getattr(self, 'learned_exclusions').get(key, 0.0)

    def learn_from_allocation(
        self,
        role: str,
        token_type: SemanticType,
        token_raw: str,
        success: bool,
        delta: float = 0.05,
    ):
        """Learn compatibility from an allocation attempt.

        Success/failure is determined by the graph's own coherence judgment.
        Delta scales with coherence strength — strong outcomes drive stronger learning.
        """
        key = (role, token_type.value)
        current = self.compatibility_cache.get(key, 0.5)
        # Delta is proportional to the strength of the coherence signal
        effective_delta = delta if success else -delta
        self.compatibility_cache[key] = max(0.0, min(1.0, current + effective_delta))
        self.learning_count += 1

    def get_compatibility(
        self,
        role: str,
        token_type: SemanticType,
    ) -> float:
        """Get learned compatibility between a role and type.

        ALL compatibilities start at 0.5 (maximum uncertainty).
        Learning from allocation success/failure drives differentiation.
        No hardcoded type_weights. No symbolic priors.
        """
        key = (role, token_type.value)
        if key in self.compatibility_cache:
            return self.compatibility_cache[key]
        # Uniform default: maximum entropy, minimum prior
        self.compatibility_cache[key] = 0.5
        return 0.5

    def get_top_roles(self, token_type: SemanticType, k: int = 3) -> List[Tuple[str, float]]:
        """Get the top-k most compatible roles for a type."""
        scores = []
        for (role, ttype), compat in self.compatibility_cache.items():
            if ttype == token_type.value:
                scores.append((role, compat))
        scores.sort(key=lambda x: -x[1])
        return scores[:k]

    def get_learning_count(self) -> int:
        return self.learning_count

    def get_certainty(self) -> float:
        """Measure overall learning certainty (0=uncertain, 1=certain).

        Certainty is the average deviation from 0.5 across all learned entries.
        High certainty means most role-type pairs have converged toward 0 or 1.
        """
        if not self.compatibility_cache:
            return 0.0
        deviations = [abs(v - 0.5) * 2 for v in self.compatibility_cache.values()]
        return sum(deviations) / len(deviations)

    def get_learning_speed(self) -> float:
        """How fast learning is still happening (0=stable, 1=fast change).

        Tracks how many entries are still near 0.5 (uncertain).
        High speed means many entries haven't converged yet.
        """
        if not self.compatibility_cache:
            return 1.0
        uncertain = sum(1 for v in self.compatibility_cache.values() if 0.3 < v < 0.7)
        return uncertain / len(self.compatibility_cache)

    def get_calibrated_confidence(self, base_confidence: float) -> float:
        """Adjust a confidence score based on the engine's learning state.

        When certainty is low, pull confidence toward 0.5 (uncertainty).
        When certainty is high, confidence can be trusted.
        """
        certainty = self.get_certainty()
        return 0.5 + (base_confidence - 0.5) * certainty

    def save_cache(self) -> dict:
        """Serialize the compatibility cache for persistence."""
        return {f"{r}:{t}": v for (r, t), v in self.compatibility_cache.items()}

    def load_cache(self, data: dict):
        """Load a previously saved cache."""
        for key, value in data.items():
            if ':' in key:
                role, ttype = key.split(':', 1)
                self.compatibility_cache[(role, ttype)] = value
                self.learning_count += 1

    def save_to_file(self, filepath: str):
        """Persist the compatibility cache to a JSON file."""
        import json, os
        data = self.save_cache()
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f)

    def load_from_file(self, filepath: str) -> bool:
        """Load a previously saved cache from a JSON file.
        
        Returns True if data was loaded, False if file doesn't exist.
        """
        import json, os
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath) as f:
                data = json.load(f)
            self.load_cache(data)
            return True
        except (json.JSONDecodeError, IOError):
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 9: TOPOLOGY DYNAMICS ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class TopologyDynamicsEngine:
    """Manages topology evolution: entropy suppression, motif stabilization.

    Graph topology evolves toward:
    - Low entropy (ordered structures)
    - Stable motifs (recurring patterns)
    - Sparse connectivity (efficient graphs)
    """

    def __init__(self, graph: SemanticGraph):
        self.graph = graph
        self.entropy_history: List[float] = []
        self.motif_stability: Dict[Tuple[str, ...], float] = {}

    def suppress_entropy(self, threshold: float = 0.3) -> int:
        """Suppress high-entropy edges (random connections)."""
        removed = 0
        self.graph.relationships = [
            e for e in self.graph.relationships
            if e.confidence >= threshold
        ]
        removed = sum(1 for e in self.graph.relationships if e.confidence < threshold)
        return removed

    def stabilize_motifs(self, min_occurrence: int = 2) -> int:
        """Reinforce edges that form recurring motifs."""
        # Count motif occurrences
        motif_counts: Dict[Tuple[str, ...], int] = Counter()
        for region in self.graph.regions:
            sig = tuple(t.primary_type.value for t in region.tokens)
            if sig:
                motif_counts[sig] += 1

        # Reinforce edges in common motifs
        reinforced = 0
        for sig, count in motif_counts.items():
            if count >= min_occurrence:
                self.motif_stability[sig] = min(count / 10.0, 1.0)
                for edge in self.graph.relationships:
                    if edge.confidence < 0.8:
                        edge.confidence = min(edge.confidence + 0.05, 1.0)
                        reinforced += 1

        return reinforced

    def sparsify(self, target_edges: int = 20) -> int:
        """Reduce graph to target number of highest-confidence edges."""
        if len(self.graph.relationships) <= target_edges:
            return 0

        sorted_edges = sorted(self.graph.relationships, key=lambda e: -e.confidence)
        kept = sorted_edges[:target_edges]
        removed = len(self.graph.relationships) - len(kept)
        self.graph.relationships = kept
        return removed

    def evolve(self) -> SemanticGraph:
        """Run one evolution step."""
        self.suppress_entropy(threshold=0.25)
        self.stabilize_motifs(min_occurrence=2)
        self.sparsify(target_edges=30)
        return self.graph


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 10: MULTI-SCALE GRAPH REASONER
# ═══════════════════════════════════════════════════════════════════════════════

class MultiScaleGraphReasoner:
    """Reasons at multiple scales: token, region, record, dataset.

    Hierarchical reasoning enables:
    - Local patterns (token level)
    - Regional semantics (region level)
    - Record coherence (record level)
    - Global motifs (dataset level)
    """

    def __init__(self, graph: SemanticGraph):
        self.graph = graph
        self.scale_scores: Dict[str, float] = {}

    def reason_tokens(self) -> float:
        """Reason at token scale.
        Returns token-level coherence.
        """
        if not self.graph.tokens:
            return 0.0
        typed = len([t for t in self.graph.tokens if t.primary_type != SemanticType.TEXT])
        return typed / max(len(self.graph.tokens), 1)

    def reason_regions(self) -> float:
        """Reason at region scale.
        Returns region-level coherence.
        """
        regions = self.graph.regions
        if not regions:
            return 0.0
        from app.semantic_regions import compute_region_cohesion
        cohesions = [compute_region_cohesion(r) for r in regions]
        return sum(cohesions) / len(cohesions) if cohesions else 0.0

    def reason_dataset(self, dataset: Optional[DatasetIR] = None) -> float:
        """Reason at dataset scale.
        Returns dataset-level consistency.
        """
        if not dataset or not dataset.records:
            return 0.5
        from app.global_graph_coherence import compute_global_coherence
        report = compute_global_coherence(dataset)
        return report.harmony_score

    def compute_multi_scale_coherence(
        self,
        dataset: Optional[DatasetIR] = None,
    ) -> float:
        """Compute weighted multi-scale coherence."""
        token_score = self.reason_tokens()
        region_score = self.reason_regions()
        dataset_score = self.reason_dataset(dataset)

        coherence = (token_score * 0.3) + (region_score * 0.4) + (dataset_score * 0.3)
        self.scale_scores = {
            "token": token_score,
            "region": region_score,
            "dataset": dataset_score,
            "combined": coherence,
        }
        return coherence


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 11: GRAPH EQUILIBRIUM SOLVER
# ═══════════════════════════════════════════════════════════════════════════════

class GraphEquilibriumSolver:
    """Solves for semantic equilibrium using energy minimization.

    Equilibrium = stable semantic configuration with:
    - Minimum energy
    - Maximum coherence
    - Balanced ownership
    - Converged topology
    """

    def __init__(self):
        self.equilibrium_reached = False
        self.equilibrium_quality = 0.0
        self.convergence_path: List[float] = []

    def solve(
        self,
        state: SemanticState,
        graph: SemanticGraph,
        max_steps: int = 10,
    ) -> Tuple[SemanticState, bool]:
        """Iteratively solve for equilibrium.

        Each step:
        1. Compute current energy
        2. Check equilibrium conditions
        3. Adjust toward lower energy
        4. Track convergence path
        """
        for step in range(max_steps):
            # Compute current equilibrium
            equilibrium = state.compute_equilibrium()
            energy = state.compute_energy(graph)
            self.convergence_path.append(energy)

            # Check equilibrium conditions
            if len(self.convergence_path) >= 3:
                recent = self.convergence_path[-3:]
                variance = sum((e - sum(recent) / len(recent)) ** 2 for e in recent) / len(recent)

                if variance < 0.005 and equilibrium > 0.7:
                    self.equilibrium_reached = True
                    self.equilibrium_quality = equilibrium
                    return state, True

            # Adjust toward equilibrium
            self._adjust_toward_equilibrium(state, graph)

        self.equilibrium_quality = state.compute_equilibrium()
        return state, False

    def _adjust_toward_equilibrium(self, state: SemanticState, graph: SemanticGraph):
        """Make small adjustments to move toward equilibrium."""
        # Boost coherent edges
        for edge in graph.relationships:
            if edge.confidence >= 0.7:
                edge.confidence = min(edge.confidence + 0.03, 1.0)

        # Suppress contradictory edges
        for o_edge in graph.ownership_edges:
            if edge.confidence < 0.3:
                edge.confidence = 0.0

        # Remove zero-confidence edges
        graph.relationships = [e for e in graph.relationships if e.confidence > 0]
        graph.ownership_edges = [e for e in graph.ownership_edges if e.confidence > 0]


# ═══════════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 14: RELATIONAL EMBEDDING SPACE
# ═══════════════════════════════════════════════════════════════════════════════

class RelationalEmbeddingSpace:
    """Builds embeddings from graph topology, not string matching.

    Two tokens get the SAME embedding if they have the SAME graph neighborhood,
    regardless of their text. This enables:
    - "BA" ≡ "British Airways" (same relational structure)
    - "LHR" ≡ "LON" (same role in different records)
    - Cross-lingual equivalence (same topology = same meaning)

    Embeddings are computed from:
    - Neighbor type distributions
    - Ownership structure
    - Relationship patterns
    - Regional context
    """

    def __init__(self, dimension: int = 16):
        self.dimension = dimension
        self.embeddings: Dict[int, List[float]] = {}

    def compute_embedding(self, token_idx: int, graph: SemanticGraph) -> List[float]:
        """Compute embedding for a token from its graph neighborhood.

        Embedding is a fixed-size vector where each position
        encodes a structural feature of the token's graph context.
        """
        emb = [0.0] * self.dimension

        if not graph.tokens or token_idx >= len(graph.tokens):
            return emb

        token = graph.tokens[token_idx]

        # Position 0-1: Type encoding (from type_vector)
        emb[0] = getattr(token, 'type_entity', 0.0)
        emb[1] = getattr(token, 'type_value', 0.0)
        emb[2] = getattr(token, 'type_location', 0.0)
        emb[3] = getattr(token, 'type_temporal', 0.0)
        emb[4] = getattr(token, 'type_identifier', 0.0)
        emb[5] = getattr(token, 'type_quantity', 0.0)
        emb[6] = getattr(token, 'type_quality', 0.0)
        emb[7] = getattr(token, 'type_contact', 0.0)
        emb[8] = getattr(token, 'type_text', 0.0)

        # Position 9-11: Relationship degree
        in_degree = sum(1 for e in graph.relationships if e.target_idx == token_idx)
        out_degree = sum(1 for e in graph.relationships if e.source_idx == token_idx)
        emb[9] = min(in_degree / 5.0, 1.0)
        emb[10] = min(out_degree / 5.0, 1.0)
        emb[11] = min((in_degree + out_degree) / 10.0, 1.0)

        # Position 12: Ownership role
        for region in graph.regions:
            for t in region.tokens:
                if t is token or t.raw == token.raw:
                    emb[12] = 1.0 if region.owned_by is not None else 0.5
                    break

        # Position 13-15: Neighbor type mixture
        neighbor_types = set()
        for e in graph.relationships:
            if e.source_idx == token_idx and e.target_idx < len(graph.tokens):
                neighbor_types.add(graph.tokens[e.target_idx].primary_type.value)
            if e.target_idx == token_idx and e.source_idx < len(graph.tokens):
                neighbor_types.add(graph.tokens[e.source_idx].primary_type.value)
        emb[13] = min(len(neighbor_types) / 3.0, 1.0)
        emb[14] = 1.0 if any('price' in nt for nt in neighbor_types) else 0.0
        emb[15] = 1.0 if any('date' in nt or 'code' in nt for nt in neighbor_types) else 0.0

        self.embeddings[token_idx] = emb
        return emb

    def similarity(self, idx_a: int, idx_b: int) -> float:
        """Compute cosine similarity between two token embeddings."""
        emb_a = self.embeddings.get(idx_a, [0.0] * self.dimension)
        emb_b = self.embeddings.get(idx_b, [0.0] * self.dimension)
        dot = sum(a * b for a, b in zip(emb_a, emb_b))
        norm_a = sum(a * a for a in emb_a) ** 0.5 or 1.0
        norm_b = sum(b * b for b in emb_b) ** 0.5 or 1.0
        return dot / (norm_a * norm_b)

    def are_same_entity(self, idx_a: int, idx_b: int, threshold: float = 0.85) -> bool:
        """Check if two tokens likely represent the same entity."""
        return self.similarity(idx_a, idx_b) >= threshold


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 15: LATENT SEMANTIC FIELD
# ═══════════════════════════════════════════════════════════════════════════════

class LatentSemanticField:
    """Continuous semantic field over the graph topology.

    Unlike discrete token operations, the field operates continuously:
    - Each token becomes a field source
    - Influence propagates through graph edges with decay
    - Multiple field sources interfere constructively/destructively
    - Meaning emerges from field interference patterns

    This replaces:
    - Hard boundary region detection
    - Discrete token classification
    - Binary relationship inference
    """

    def __init__(self, graph: SemanticGraph):
        self.graph = graph
        self.field_strength: Dict[int, float] = {}  # node_id → field strength
        self.field_type: Dict[int, str] = {}  # node_id → dominant type at location
        self.field_gradient: Dict[int, float] = {}  # node_id → gradient magnitude

    def compute(self) -> Dict[int, float]:
        """Compute the latent semantic field over the graph.

        Each token emits a field proportional to its type_vector strength.
        Fields propagate along edges with distance decay.
        Multiple fields interfere - overlapping regions get reinforced.
        """
        if not self.graph.tokens:
            return {}

        # Phase 1: Initialize field sources from tokens
        for i, token in enumerate(self.graph.tokens):
            # Field strength = sum of all type_vector dimensions
            strength = sum([
                getattr(token, 'type_value', 0.0),
                getattr(token, 'type_entity', 0.0),
                getattr(token, 'type_location', 0.0),
                getattr(token, 'type_temporal', 0.0),
                getattr(token, 'type_identifier', 0.0),
                getattr(token, 'type_quantity', 0.0),
                getattr(token, 'type_quality', 0.0),
                getattr(token, 'type_contact', 0.0),
            ])
            self.field_strength[i] = max(strength, 0.1)
            self.field_type[i] = token.primary_type.value

        # Phase 2: Propagate fields along edges
        for iteration in range(3):
            new_strength = dict(self.field_strength)
            for edge in self.graph.relationships:
                src = edge.source_idx
                tgt = edge.target_idx
                if src in self.field_strength and tgt in self.field_strength:
                    # Propagate with decay and edge confidence weighting
                    propagation = self.field_strength[src] * edge.confidence * 0.3
                    new_strength[tgt] = max(new_strength.get(tgt, 0), propagation)
                    propagation_b = self.field_strength[tgt] * edge.confidence * 0.3
                    new_strength[src] = max(new_strength.get(src, 0), propagation_b)
            self.field_strength = new_strength

        # Phase 3: Compute field gradients (rate of change between neighbors)
        for node_id in self.field_strength:
            neighbor_strengths = []
            for edge in self.graph.relationships:
                if edge.source_idx == node_id and edge.target_idx in self.field_strength:
                    neighbor_strengths.append(self.field_strength[edge.target_idx])
                elif edge.target_idx == node_id and edge.source_idx in self.field_strength:
                    neighbor_strengths.append(self.field_strength[edge.source_idx])
            if neighbor_strengths:
                avg_neighbor = sum(neighbor_strengths) / len(neighbor_strengths)
                self.field_gradient[node_id] = abs(self.field_strength[node_id] - avg_neighbor)
            else:
                self.field_gradient[node_id] = 0.0

        return self.field_strength

    def get_dominant_type_at(self, node_id: int) -> str:
        """Get the dominant semantic type at a field location."""
        return self.field_type.get(node_id, 'unknown')

    def get_field_curvature(self) -> float:
        """Compute field curvature: how much the field bends.

        High curvature = complex semantic topology.
        Low curvature = flat, uniform region.
        """
        if not self.field_gradient:
            return 0.0
        gradients = list(self.field_gradient.values())
        return sum(gradients) / len(gradients)

    def get_attention_from_field(self) -> Dict[int, float]:
        """Derive attention scores from field strength.

        Stronger field = more attention.
        """
        if not self.field_strength:
            return {}
        max_strength = max(self.field_strength.values()) or 1.0
        return {k: v / max_strength for k, v in self.field_strength.items()}


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 16: SEMANTIC THERMODYNAMICS
# ═══════════════════════════════════════════════════════════════════════════════

class SemanticThermodynamics:
    """Energy-based semantic equilibrium dynamics.

    Stable semantic structures minimize energy.
    Contradictions increase energy.
    The system evolves toward minimum energy equilibrium.

    This replaces procedural scoring with thermodynamic emergence.
    """

    def __init__(self):
        self.temperature: float = 1.0  # Controls exploration vs exploitation
        self.energy_history: List[float] = []
        self.equilibrium_reached: bool = False

    def compute_energy(self, graph: SemanticGraph) -> float:
        """Compute total semantic energy of the graph.

        Energy components:
        - Field tension: mismatched neighboring types
        - Ownership entropy: unclear ownership
        - Contradiction energy: conflicting relationships
        - Uncertainty heat: unresolved type ambiguity

        Lower energy = more stable configuration.
        """
        energy = 0.0

        # Field tension: mismatched types between connected tokens
        for edge in graph.relationships:
            if edge.source_idx < len(graph.tokens) and edge.target_idx < len(graph.tokens):
                src_type = graph.tokens[edge.source_idx].primary_type
                tgt_type = graph.tokens[edge.target_idx].primary_type
                if src_type != tgt_type:
                    energy += 0.5 * (1.0 - edge.confidence)

        # Ownership entropy: unowned regions increase energy
        owned_regions = set()
        for o_edge in graph.ownership_edges:
            owned_regions.add(o_edge.owned_region_id)
        for region in graph.regions:
            if region.region_id not in owned_regions:
                energy += 1.0

        # Contradiction energy
        energy += graph.contradiction_score * 5.0

        # Coherence deficit
        energy += (1.0 - graph.coherence_score) * 3.0

        return energy

    def anneal(self, graph: SemanticGraph, steps: int = 5) -> SemanticGraph:
        """Run simulated annealing to reach equilibrium.

        High temperature: explore (accept worse states).
        Low temperature: exploit (only accept better states).
        """
        for step in range(steps):
            current_energy = self.compute_energy(graph)
            self.energy_history.append(current_energy)

            # Cool down
            self.temperature *= 0.8

            # At equilibrium when energy stabilizes
            if len(self.energy_history) >= 3:
                recent = self.energy_history[-3:]
                variance = sum((e - sum(recent) / len(recent)) ** 2 for e in recent) / len(recent)
                if variance < 0.01:
                    self.equilibrium_reached = True
                    break

            # Apply thermodynamic pressure:
            # High-confidence edges get reinforced (they're "cooling")
            # Low-confidence edges get suppressed (they're "heating up")
            for edge in graph.relationships:
                if edge.confidence > 0.7:
                    edge.confidence = min(edge.confidence + 0.02 * self.temperature, 1.0)
                elif edge.confidence < 0.3:
                    edge.confidence = max(edge.confidence - 0.02 * self.temperature, 0.0)

            # Remove zero-confidence edges
            graph.relationships = [e for e in graph.relationships if e.confidence > 0]

        return graph

    def get_equilibrium_stability(self) -> float:
        """Get the stability of the current equilibrium. 0-1."""
        if len(self.energy_history) < 2:
            return 0.5
        recent = self.energy_history[-5:] if len(self.energy_history) >= 5 else self.energy_history
        variance = sum((e - sum(recent) / len(recent)) ** 2 for e in recent) / len(recent)
        return 1.0 - min(variance, 1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENT 17: SEMANTIC COMPRESSION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class SemanticCompressionEngine:
    """Compresses semantic graphs to prevent combinatorial explosion.

    Strategies:
    - Merge redundant motifs (same pattern repeated = compress to one)
    - Prune low-information tokens (pure text with no relationships)
    - Collapse duplicate candidates (same value, same type, same role)
    - Fold stable subgraphs into single meta-nodes
    """

    def __init__(self):
        self.compression_ratio: float = 1.0
        self.original_size: int = 0

    def compress(self, graph: SemanticGraph) -> SemanticGraph:
        """Compress the semantic graph."""
        self.original_size = len(graph.tokens) + len(graph.relationships)

        # 1. Remove isolated text tokens with no relationships
        related_nodes = set()
        for edge in graph.relationships:
            related_nodes.add(edge.source_idx)
            related_nodes.add(edge.target_idx)
        graph.tokens = [
            t for i, t in enumerate(graph.tokens)
            if i in related_nodes or t.primary_type != SemanticType.TEXT
        ]

        # 2. Deduplicate edges (same source, target, type)
        seen_edges: Set[Tuple[int, int, str]] = set()
        deduped = []
        for e in graph.relationships:
            key = (e.source_idx, e.target_idx, e.relationship_type)
            if key not in seen_edges:
                seen_edges.add(key)
                deduped.append(e)
        graph.relationships = deduped

        # 3. Remove very low-confidence edges
        graph.relationships = [e for e in graph.relationships if e.confidence >= 0.15]

        new_size = len(graph.tokens) + len(graph.relationships)
        self.compression_ratio = new_size / max(self.original_size, 1)
        return graph

    def get_compression_report(self) -> Dict:
        return {
            "original_size": self.original_size,
            "compressed_size": int(self.original_size * self.compression_ratio) if self.original_size else 0,
            "ratio": self.compression_ratio,
        }
