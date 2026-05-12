"""
Uncertainty Propagation Engine
===============================
Models how uncertainty evolves across the semantic graph.

Core principle: Uncertainty is not static - it propagates, decays,
reinforces, and amplifies through graph edges.

Mechanisms:
1. Propagation: uncertainty flows along edges (connected = correlated)
2. Decay: uncertainty decreases with distance from source
3. Reinforcement: multiple consistent edges reduce uncertainty
4. Amplification: contradictory edges increase uncertainty
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
import math

from app.semantic_ir import (
    SemanticToken, SemanticType, SemanticRegion,
    RelationshipEdge, OwnershipEdge, SemanticGraph,
)
from app.semantic_contradiction_engine import (
    detect_contradictions, Contradiction, compute_contradiction_impact,
)


@dataclass
class UncertaintyProfile:
    """Complete uncertainty profile for a semantic graph."""
    token_uncertainties: Dict[int, float] = field(default_factory=dict)
    region_uncertainties: Dict[int, float] = field(default_factory=dict)
    global_uncertainty: float = 0.0
    entropy: float = 0.0
    evidence: List[str] = field(default_factory=list)


def compute_token_uncertainty(token: SemanticToken) -> float:
    """Compute uncertainty from a token's type distribution.

    Higher entropy = higher uncertainty.
    """
    dist = token.type_distribution
    if not dist:
        return 0.5

    total = sum(dist.values())
    if total == 0:
        return 0.5

    entropy = 0.0
    for v in dist.values():
        p = v / total
        if p > 0:
            entropy -= p * math.log2(p)

    max_entropy = math.log2(max(len(dist), 2))
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.5

    return min(normalized_entropy, 1.0)


def compute_region_uncertainty(region: SemanticRegion) -> float:
    """Compute uncertainty for a region.

    Factors:
    - Token-level uncertainties
    - Region cohesion (low cohesion = high uncertainty)
    - Ownership clarity (unclear ownership = high uncertainty)
    """
    token_uncertainties = [compute_token_uncertainty(t) for t in region.tokens]
    avg_token_uncertainty = sum(token_uncertainties) / max(len(token_uncertainties), 1)

    # Cohesion maps inversely to uncertainty
    from app.semantic_regions import compute_region_cohesion
    cohesion = compute_region_cohesion(region)
    cohesion_uncertainty = 1.0 - cohesion

    # Ownership clarity
    ownership_uncertainty = 0.3 if region.owned_by is None else 0.1

    uncertainty = (avg_token_uncertainty * 0.4) + (cohesion_uncertainty * 0.4) + (ownership_uncertainty * 0.2)
    return min(uncertainty, 1.0)


def propagate_uncertainty(graph: SemanticGraph) -> UncertaintyProfile:
    """Propagate uncertainty through the graph.

    Phase 1: Compute base uncertainties
    Phase 2: Propagate along edges
    Phase 3: Apply contradiction amplification
    Phase 4: Compute global metrics
    """
    # Phase 1: Base uncertainties
    token_uncertainties: Dict[int, float] = {}
    region_uncertainties: Dict[int, float] = {}

    for token in graph.tokens:
        token_uncertainties[token.position] = compute_token_uncertainty(token)

    for region in graph.regions:
        region_uncertainties[region.region_id] = compute_region_uncertainty(region)

    # Phase 2: Propagate along relationship edges
    # Uncertainty flows from source to target, decaying with distance
    edge_uncertainty_map: Dict[int, float] = defaultdict(float)

    for edge in graph.relationships:
        source_uncertainty = token_uncertainties.get(edge.source_idx, 0.5)
        propagated = source_uncertainty * (1.0 - edge.confidence) * 0.5
        edge_uncertainty_map[edge.target_idx] = max(
            edge_uncertainty_map.get(edge.target_idx, 0),
            propagated,
        )

    for token_idx, propagated_uncertainty in edge_uncertainty_map.items():
        if token_idx in token_uncertainties:
            token_uncertainties[token_idx] = max(
                token_uncertainties[token_idx],
                propagated_uncertainty,
            )

    # Phase 3: Contradiction amplification
    contradictions = detect_contradictions(graph)
    if contradictions:
        impact = compute_contradiction_impact(contradictions)
        # Amplify uncertainty proportional to contradiction severity
        for token_idx in token_uncertainties:
            token_uncertainties[token_idx] = min(
                token_uncertainties[token_idx] + (impact * 0.3),
                1.0,
            )
        for region_id in region_uncertainties:
            region_uncertainties[region_id] = min(
                region_uncertainties[region_id] + (impact * 0.3),
                1.0,
            )

    # Phase 4: Global metrics
    all_uncertainties = list(token_uncertainties.values()) + list(region_uncertainties.values())
    global_uncertainty = sum(all_uncertainties) / max(len(all_uncertainties), 1)

    # Global entropy (average token entropy)
    entropies = [
        compute_token_uncertainty(t)
        for t in graph.tokens
        if t.type_distribution and len(t.type_distribution) > 1
    ]
    avg_entropy = sum(entropies) / max(len(entropies), 1) if entropies else 0.0

    return UncertaintyProfile(
        token_uncertainties=token_uncertainties,
        region_uncertainties=region_uncertainties,
        global_uncertainty=global_uncertainty,
        entropy=avg_entropy,
        evidence=[
            f"tokens:{len(token_uncertainties)}",
            f"regions:{len(region_uncertainties)}",
            f"contradictions:{len(contradictions)}",
        ],
    )


def reinforce_certainty(
    token: SemanticToken,
    graph: SemanticGraph,
) -> SemanticToken:
    """Reinforce certainty for a token based on consistent evidence.

    If a token has strong relationships and clear type, its certainty
    is reinforced.
    """
    relationships = [
        e for e in graph.relationships
        if e.source_idx == token.position or e.target_idx == token.position
    ]

    if len(relationships) >= 2:
        # Multiple relationships = multiple evidence sources = reinforce
        avg_rel_conf = sum(e.confidence for e in relationships) / len(relationships)
        if avg_rel_conf >= 0.6:
            # Boost the primary type confidence
            dist = dict(token.type_distribution)
            if token.primary_type in dist:
                dist[token.primary_type] = min(dist[token.primary_type] + 0.1, 1.0)
                token.type_distribution = dist
                token.evidence.append(f"certainty_reinforced:{len(relationships)}_edges")

    return token
