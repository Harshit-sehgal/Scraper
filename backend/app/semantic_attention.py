"""
Semantic Attention Engine
===========================
Computes semantic salience to determine which regions and tokens
deserve the most attention.

Core principle: Not all parts of a semantic graph are equally important.
The engine must prioritize high-information semantic regions.

Attention factors:
1. Type salience (prices > text, dates > numbers)
2. Structural position (first entity > secondary)
3. Relationship centrality (more edges = more important)
4. Uniqueness (rare types = more important)
5. Confidence weight (high confidence = more attention)
"""

from typing import List, Dict, Optional

from app.semantic_ir import (
    SemanticType, RegionType,
    SemanticToken, SemanticRegion,
    SemanticGraph,
)


# Intrinsic salience of semantic types (universal, NOT domain-specific)
TYPE_SALIENCE: Dict[SemanticType, float] = {
    SemanticType.PRICE: 0.95,
    SemanticType.PHONE: 0.90,
    SemanticType.EMAIL: 0.90,
    SemanticType.URL: 0.85,
    SemanticType.DATE: 0.80,
    SemanticType.RATING: 0.75,
    SemanticType.DURATION: 0.70,
    SemanticType.LOCATION: 0.65,
    SemanticType.CODE: 0.60,
    SemanticType.ORGANIZATION: 0.60,
    SemanticType.NAME: 0.55,
    SemanticType.IDENTIFIER: 0.50,
    SemanticType.NUMBER: 0.30,
    SemanticType.TEXT: 0.15,
}

REGION_SALIENCE: Dict[RegionType, float] = {
    RegionType.PRICE_REGION: 0.95,
    RegionType.CONTACT_REGION: 0.90,
    RegionType.DATE_REGION: 0.80,
    RegionType.RATING_REGION: 0.75,
    RegionType.LOCATION_REGION: 0.70,
    RegionType.DURATION_REGION: 0.70,
    RegionType.ENTITY_NAME: 0.65,
    RegionType.IDENTIFIER_REGION: 0.60,
    RegionType.QUANTIFIER: 0.40,
    RegionType.DESCRIPTOR: 0.20,
}


def compute_token_attention(token: SemanticToken, graph: SemanticGraph) -> float:
    """Compute attention score for a single token."""
    # Type salience
    type_salience = TYPE_SALIENCE.get(token.primary_type, 0.3)

    # Edge count centrality
    edge_count = sum(
        1 for e in graph.relationships
        if e.source_idx == token.position or e.target_idx == token.position
    )
    centrality = min(edge_count / 5, 1.0)

    # Position bonus (early tokens get slightly more attention)
    position_bonus = max(0, 1.0 - token.position / 20) * 0.1

    # Confidence
    conf = token.type_distribution.get(token.primary_type, 0.5) if token.type_distribution else 0.5

    attention = (type_salience * 0.4) + (centrality * 0.3) + (conf * 0.2) + (position_bonus * 0.1)
    return min(attention, 1.0)


def compute_region_attention(region: SemanticRegion, graph: SemanticGraph) -> float:
    """Compute attention score for a semantic region."""
    # Region type salience
    type_salience = REGION_SALIENCE.get(region.region_type, 0.3)

    # Ownership centrality (regions that own others get more attention)
    ownership_count = len(region.owns)
    ownership_centrality = min(ownership_count / 3, 1.0)

    # Owned by someone? slightly less attention (secondary)
    owned_penalty = 0.8 if region.owned_by is not None else 1.0

    # Confidence
    conf = region.confidence

    attention = (type_salience * 0.4) + (ownership_centrality * 0.3) + (conf * 0.2) + (0.1 * owned_penalty)
    return min(attention, 1.0)


def compute_graph_attention_map(graph: SemanticGraph) -> Dict[str, float]:
    """Compute an attention map for the entire graph.

    Returns {token_text: attention_score} for the top tokens.
    """
    attention_map: Dict[str, float] = {}

    for token in graph.tokens:
        score = compute_token_attention(token, graph)
        attention_map[token.raw] = score

    for region in graph.regions:
        score = compute_region_attention(region, graph)
        for token in region.tokens:
            attention_map[token.raw] = max(attention_map.get(token.raw, 0), score)

    return attention_map


def prioritize_regions(regions: List[SemanticRegion], graph: SemanticGraph) -> List[SemanticRegion]:
    """Sort regions by attention score (highest first)."""
    scored = [(compute_region_attention(r, graph), r) for r in regions]
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored]


def get_focus_region(graph: SemanticGraph) -> Optional[SemanticRegion]:
    """Get the single most important region in the graph."""
    if not graph.regions:
        return None
    prioritized = prioritize_regions(graph.regions, graph)
    return prioritized[0] if prioritized else None
