"""
Semantic Graph Engine
======================
Graph-native reasoning substrate for semantic understanding.

The graph ITSELF is the reasoning substrate.
Meaning emerges from graph structure, not individual token heuristics.

Phases:
1. Build graph from tokens + regions + relationships
2. Propagate confidence through graph edges
3. Detect graph patterns (repeated sub-graphs)
4. Compute graph coherence
5. Resolve graph conflicts
"""

from collections import Counter, defaultdict
from typing import Dict, List

from app.ownership_inference import (
    infer_semantic_ownership,
    propagate_ownership_consistency,
)
from app.semantic_contradiction_engine import detect_contradictions
from app.semantic_ir import (
    DatasetIR,
    RegionType,
    SemanticGraph,
    SemanticRecord,
)
from app.semantic_regions import build_region_hierarchy, detect_semantic_regions


def build_semantic_graph(
    record: SemanticRecord,
) -> SemanticGraph:
    """Build a complete semantic graph from a record.

    Steps:
    1. Decompose tokens into regions
    2. Build region hierarchy
    3. Infer ownership relationships
    4. Compute graph-level properties
    """
    # Phase 1: Region decomposition
    regions = detect_semantic_regions(record.tokens)
    regions = build_region_hierarchy(regions)

    # Phase 2: Ownership inference
    ownership_edges, regions = infer_semantic_ownership(regions, record.relationships)
    ownership_edges = propagate_ownership_consistency(ownership_edges, regions)

    # Phase 3: Build graph
    graph = SemanticGraph(
        regions=regions,
        tokens=record.tokens,
        relationships=record.relationships,
        ownership_edges=ownership_edges,
    )

    # Phase 4: Compute graph properties
    graph.coherence_score = compute_graph_coherence(graph)
    graph.contradictions = detect_contradictions(graph)
    graph.contradiction_score = sum(c.confidence_damage for c in graph.contradictions)
    graph.has_contradictions = len(graph.contradictions) > 0

    return graph


def propagate_confidence(graph: SemanticGraph) -> SemanticGraph:
    """Propagate confidence through graph edges.

    Confidence flows from:
    - High-confidence regions to connected low-confidence regions
    - Ownership edges reinforce owned regions
    - Consistent relationships reinforce all participants
    """
    if not graph.regions:
        return graph

    # Build adjacency from ownership edges
    adj: Dict[int, List[int]] = defaultdict(list)
    for edge in graph.ownership_edges:
        adj[edge.owner_region_id].append(edge.owned_region_id)
        adj[edge.owned_region_id].append(edge.owner_region_id)

    # Propagate: high-confidence regions boost their neighbors
    for region in graph.regions:
        if region.confidence >= 0.8:
            for neighbor_id in adj.get(region.region_id, []):
                neighbor = graph.get_region(neighbor_id)
                if neighbor and neighbor.confidence < region.confidence:
                    boost = region.confidence * 0.1
                    neighbor.confidence = min(neighbor.confidence + boost, 1.0)
                    neighbor.evidence.append(f"confidence_propagated_from:{region.region_id}")

    return graph


def detect_graph_patterns(graph: SemanticGraph) -> List[Dict]:
    """Detect recurring sub-graph patterns.

    Patterns emerge from:
    - Repeated region type sequences
    - Common ownership structures
    - Consistent relationship topologies
    """
    patterns: List[Dict] = []

    if not graph.regions:
        return patterns

    # Region type sequence
    sequence = tuple(r.region_type.value for r in graph.regions)
    patterns.append({
        "type": "region_sequence",
        "signature": sequence,
        "length": len(graph.regions),
    })

    # Ownership structure
    owner_map = defaultdict(list)
    for edge in graph.ownership_edges:
        owner_map[edge.ownership_type].append({
            "owner": edge.owner_region_id,
            "owned": edge.owned_region_id,
            "confidence": edge.confidence,
        })
    for ownership_type, edges in owner_map.items():
        patterns.append({
            "type": "ownership_cluster",
            "ownership_type": ownership_type,
            "edge_count": len(edges),
            "avg_confidence": sum(e["confidence"] for e in edges) / len(edges),
        })

    return patterns


def compute_graph_coherence(graph: SemanticGraph) -> float:
    """Compute overall coherence of the semantic graph.

    Factors:
    1. Region cohesion (internal consistency of each region)
    2. Ownership coverage (what fraction of regions have ownership)
    3. Relationship density (edges per region)
    4. Contradiction absence (no contradictory assignments)
    """
    if not graph.regions:
        return 0.0

    # Region cohesion
    from app.semantic_regions import compute_region_cohesion
    cohesion_scores = [compute_region_cohesion(r) for r in graph.regions]
    avg_region_cohesion = sum(cohesion_scores) / len(cohesion_scores) if cohesion_scores else 0.0

    # Ownership coverage
    owned_count = len([r for r in graph.regions if r.owned_by is not None])
    ownership_coverage = owned_count / len(graph.regions)

    # Relationship density
    rel_density = len(graph.relationships) / max(len(graph.regions), 1)

    # Penalize contradictions
    contradiction_penalty = 1.0 - min(graph.contradiction_score, 1.0)

    coherence = (
        avg_region_cohesion * 0.3 +
        ownership_coverage * 0.3 +
        min(rel_density, 1.0) * 0.2 +
        contradiction_penalty * 0.2
    )

    return min(coherence, 1.0)





def resolve_graph_conflicts(graph: SemanticGraph) -> SemanticGraph:
    """Resolve conflicts in the semantic graph.

    Strategies:
    1. Remove circular ownership edges
    2. Fix inverted ownership (non-entity owning entity)
    3. Merge conflicting regions
    """
    # Filter out circular ownership
    graph.ownership_edges = [
        e for e in graph.ownership_edges
        if e.owner_region_id != e.owned_region_id
    ]

    # Fix inverted ownership
    for edge in graph.ownership_edges:
        owner = graph.get_region(edge.owner_region_id)
        owned = graph.get_region(edge.owned_region_id)
        if not owner or not owned:
            continue

        # If owned is an entity name, swap
        if (owned.region_type in (RegionType.ENTITY_NAME,) and
                owner.region_type not in (RegionType.ENTITY_NAME, RegionType.IDENTIFIER_REGION)):
            edge.owner_region_id, edge.owned_region_id = edge.owned_region_id, edge.owner_region_id
            edge.evidence.append("inverted_ownership_fixed")

    graph.coherence_score = compute_graph_coherence(graph)
    return graph


def build_dataset_graph(dataset: DatasetIR) -> List[SemanticGraph]:
    """Build semantic graphs for all records in a dataset."""
    return [build_semantic_graph(record) for record in dataset.records]


def compute_global_graph_coherence(graphs: List[SemanticGraph]) -> float:
    """Compute coherence across all graphs in a dataset.

    Measures:
    - Pattern convergence (do most graphs share similar patterns?)
    - Confidence consistency
    - Structural agreement
    """
    if not graphs:
        return 0.0

    # Extract region type sequences
    sequences = [tuple(r.region_type.value for r in g.regions) for g in graphs if g.regions]
    if not sequences:
        return 0.0

    # Pattern convergence
    most_common = Counter(sequences).most_common(1)
    convergence = most_common[0][1] / len(sequences) if most_common else 0.0

    # Average coherence
    avg_coherence = sum(g.coherence_score for g in graphs) / len(graphs)

    coherence = (convergence * 0.5) + (avg_coherence * 0.5)
    return min(coherence, 1.0)
