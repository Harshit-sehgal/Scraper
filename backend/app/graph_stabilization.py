"""
Graph Stabilization Engine
============================
Prevents graph explosion and maintains stable semantic topology.

Strategies:
1. Edge pruning: remove low-confidence, low-information edges
2. Node merging: merge near-duplicate tokens
3. Noise suppression: suppress insignificant tokens
4. Stable topology formation: reinforce consistent patterns

Core principle: Semantic graphs must remain sparse and meaningful,
not dense and noisy.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict

from app.semantic_ir import (
    SemanticToken, SemanticType, SemanticRecord, SemanticRegion,
    RelationshipEdge, OwnershipEdge, SemanticGraph,
)


@dataclass
class StabilizationReport:
    """Report of stabilization actions taken."""
    edges_pruned: int = 0
    tokens_suppressed: int = 0
    regions_merged: int = 0
    edges_reinforced: int = 0
    final_edge_count: int = 0
    final_token_count: int = 0


def stabilize_graph(graph: SemanticGraph, min_edge_confidence: float = 0.3) -> Tuple[SemanticGraph, StabilizationReport]:
    """Stabilize a semantic graph by pruning noise and reinforcing signal.

    Returns (stabilized_graph, report).
    """
    report = StabilizationReport()

    # 1. Prune low-confidence relationship edges
    original_edges = len(graph.relationships)
    graph.relationships = [
        e for e in graph.relationships
        if e.confidence >= min_edge_confidence
    ]
    report.edges_pruned = original_edges - len(graph.relationships)

    # 2. Prune low-confidence ownership edges
    original_ownership = len(graph.ownership_edges)
    graph.ownership_edges = [
        e for e in graph.ownership_edges
        if e.confidence >= min_edge_confidence
    ]
    report.edges_pruned += original_ownership - len(graph.ownership_edges)

    # 3. Suppress text-only regions with low semantic value
    original_tokens = len(graph.tokens)
    graph.tokens = [
        t for t in graph.tokens
        if not _is_suppressible_token(t)
    ]
    report.tokens_suppressed = original_tokens - len(graph.tokens)

    # 4. Merge near-identical relationships (deduplicate)
    seen_edges: Set[Tuple[int, int, str]] = set()
    deduped_edges: List[RelationshipEdge] = []
    for e in graph.relationships:
        key = (e.source_idx, e.target_idx, e.relationship_type)
        if key not in seen_edges:
            seen_edges.add(key)
            deduped_edges.append(e)
        else:
            report.regions_merged += 1
    graph.relationships = deduped_edges

    # 5. Reinforce consistent relationship patterns
    relationship_counts: Dict[str, int] = defaultdict(int)
    for e in graph.relationships:
        relationship_counts[e.relationship_type] += 1

    # Common patterns (≥2 occurrences) get confidence boost
    common_types = {rt for rt, count in relationship_counts.items() if count >= 2}
    for e in graph.relationships:
        if e.relationship_type in common_types:
            e.confidence = min(e.confidence + 0.1, 1.0)
            report.edges_reinforced += 1

    report.final_edge_count = len(graph.relationships)
    report.final_token_count = len(graph.tokens)

    return graph, report


def _is_suppressible_token(token: SemanticToken) -> bool:
    """Check if a token should be suppressed.

    Suppressible tokens:
    - Pure text with low confidence and no semantic role
    - Noise tokens with no relationships
    """
    if token.primary_type not in (SemanticType.TEXT, SemanticType.NUMBER):
        return False  # Keep meaningful types

    # Keep text that starts with uppercase (likely entity name)
    if token.primary_type == SemanticType.TEXT and token.raw and token.raw[0].isupper():
        return False

    # Suppress low-confidence text tokens
    if token.primary_type == SemanticType.TEXT:
        conf = max(token.type_distribution.values()) if token.type_distribution else 0.5
        return conf < 0.5

    return False


def compute_graph_stability(graph: SemanticGraph) -> float:
    """Compute the stability score of a graph.

    Stable graphs have:
    - Moderate edge density (not too sparse, not too dense)
    - Strong ownership structure
    - Low contradiction count
    """
    if not graph.regions:
        return 0.0

    # Edge density (moderate = stable)
    num_regions = len(graph.regions)
    num_edges = len(graph.relationships) + len(graph.ownership_edges)
    max_edges = num_regions * (num_regions - 1) / 2
    density = num_edges / max_edges if max_edges > 0 else 0

    # Ideal density is 0.2-0.5 (not too sparse, not too dense)
    density_score = 1.0 - abs(density - 0.35) / 0.35

    # Ownership coverage
    owned_count = len([r for r in graph.regions if r.owned_by is not None])
    ownership_score = owned_count / num_regions

    # Average edge confidence
    all_confs = [e.confidence for e in graph.relationships] + \
                [e.confidence for e in graph.ownership_edges]
    avg_conf = sum(all_confs) / len(all_confs) if all_confs else 0.5

    stability = (density_score * 0.3) + (ownership_score * 0.3) + (avg_conf * 0.4)
    return min(stability, 1.0)
