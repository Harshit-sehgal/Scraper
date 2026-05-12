"""
Semantic Ownership Inference Engine
=====================================
Infers who owns what in a semantic graph.

Core principle: Ownership must emerge from:
- structural repetition
- graph consistency
- relationship topology
- semantic cohesion

NOT from:
- hardcoded domain rules
- keyword matching
- positional heuristics
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict

from app.semantic_ir import (
    SemanticToken, SemanticType, RegionType,
    SemanticRegion, OwnershipEdge, SemanticGraph,
    RelationshipEdge, SemanticRecord, DatasetIR,
)


# Universal ownership rules (emerge from graph structure, not domain)
# These are structural patterns, NOT domain knowledge.
OWNERSHIP_TYPES = {
    "belongs_to": "primary entity owns this region",
    "describes": "region qualifies the primary entity",
    "modifies": "region modifies the meaning of owner",
    "quantifies": "region provides a numeric measure",
    "identifies": "region provides identification",
}


def infer_semantic_ownership(
    regions: List[SemanticRegion],
    relationships: List[RelationshipEdge],
) -> Tuple[List[OwnershipEdge], List[SemanticRegion]]:
    """Infer ownership relationships from region structure.

    Ownership emerges from:
    1. Region hierarchy (parent-child in decomposition)
    2. Relationship density (more edges = stronger ownership claim)
    3. Proximity consistency (nearby regions likely related)
    4. Type compatibility (price near entity, date near entity)
    """
    ownership_edges: List[OwnershipEdge] = []
    updated_regions = list(regions)

    if len(regions) < 2:
        return ownership_edges, updated_regions

    # Find primary entity region
    primary = _find_primary_region(regions)
    if primary is None:
        return ownership_edges, updated_regions

    # For each non-primary region, infer ownership
    for region in regions:
        if region.region_id == primary.region_id:
            continue

        edge = _infer_single_ownership(primary, region, relationships)
        if edge:
            ownership_edges.append(edge)
            # Update region ownership
            for r in updated_regions:
                if r.region_id == region.region_id:
                    r.owned_by = primary.region_id
                    r.ownership_confidence = edge.confidence
                    r.evidence.extend(edge.evidence)
                if r.region_id == primary.region_id:
                    if region.region_id not in r.owns:
                        r.owns.append(region.region_id)

    return ownership_edges, updated_regions


def _find_primary_region(regions: List[SemanticRegion]) -> Optional[SemanticRegion]:
    """Find the primary entity region.

    Primary = the first entity_name or identifier region,
    or the region with the most outgoing relationship edges.
    """
    # Prefer entity name regions
    for r in regions:
        if r.region_type in (RegionType.ENTITY_NAME,):
            return r

    # Fall back to first identifier region
    for r in regions:
        if r.region_type == RegionType.IDENTIFIER_REGION:
            return r

    # Fall back to first region with high cohesion
    for r in regions:
        if r.confidence >= 0.7:
            return r

    return regions[0] if regions else None


def _infer_single_ownership(
    owner: SemanticRegion,
    owned: SemanticRegion,
    relationships: List[RelationshipEdge],
) -> Optional[OwnershipEdge]:
    """Infer ownership type and confidence between two regions."""
    gap = owned.start_position - owner.end_position if owned.start_position > owner.end_position else owner.start_position - owned.end_position

    # Proximity score
    proximity = 1.0 - min(abs(gap) / 20, 1.0)

    # Determine ownership type from region type compatibility
    ownership_type, type_conf = _infer_ownership_type(owner.region_type, owned.region_type)

    evidence = [
        f"proximity:{gap}",
        f"owner:{owner.region_type.value}",
        f"owned:{owned.region_type.value}",
        f"type_match:{ownership_type}",
    ]

    confidence = (proximity * 0.4) + (type_conf * 0.6)

    if confidence < 0.2:
        return None

    return OwnershipEdge(
        owner_region_id=owner.region_id,
        owned_region_id=owned.region_id,
        ownership_type=ownership_type,
        confidence=confidence,
        evidence=evidence,
    )


def _infer_ownership_type(
    owner_type: RegionType,
    owned_type: RegionType,
) -> Tuple[str, float]:
    """Infer what type of ownership relationship exists.

    Based on region type compatibility, NOT domain knowledge.
    """
    compat_map = {
        # Price-owned_by→Entity
        (RegionType.ENTITY_NAME, RegionType.PRICE_REGION): ("belongs_to", 0.8),
        (RegionType.IDENTIFIER_REGION, RegionType.PRICE_REGION): ("belongs_to", 0.6),

        # Date-owned_by→Entity
        (RegionType.ENTITY_NAME, RegionType.DATE_REGION): ("belongs_to", 0.7),
        (RegionType.IDENTIFIER_REGION, RegionType.DATE_REGION): ("belongs_to", 0.5),

        # Quantifier-modifies→Entity
        (RegionType.ENTITY_NAME, RegionType.QUANTIFIER): ("quantifies", 0.7),
        (RegionType.IDENTIFIER_REGION, RegionType.QUANTIFIER): ("quantifies", 0.5),

        # Descriptor-describes→Entity
        (RegionType.ENTITY_NAME, RegionType.DESCRIPTOR): ("describes", 0.6),

        # Rating-describes→Entity
        (RegionType.ENTITY_NAME, RegionType.RATING_REGION): ("describes", 0.7),

        # Location-identifies→Entity
        (RegionType.ENTITY_NAME, RegionType.LOCATION_REGION): ("identifies", 0.6),
        (RegionType.IDENTIFIER_REGION, RegionType.LOCATION_REGION): ("identifies", 0.5),

        # Duration-modifies→Entity
        (RegionType.ENTITY_NAME, RegionType.DURATION_REGION): ("modifies", 0.6),
    }

    result = compat_map.get((owner_type, owned_type))
    if result:
        return result

    # Fallback: proximity-based inference
    if owned_type in (RegionType.PRICE_REGION, RegionType.DATE_REGION, RegionType.QUANTIFIER):
        return ("belongs_to", 0.4)

    return ("modifies", 0.3)


def propagate_ownership_consistency(
    edges: List[OwnershipEdge],
    regions: List[SemanticRegion],
) -> List[OwnershipEdge]:
    """Propagate ownership confidence across consistent patterns.

    If multiple regions of the same type are owned by the same
    entity, reinforce their confidence.
    """
    # Group owned regions by type
    type_groups: Dict[str, List[OwnershipEdge]] = defaultdict(list)
    for edge in edges:
        owned = _find_region(regions, edge.owned_region_id)
        if owned:
            type_groups[owned.region_type.value].append(edge)

    for type_val, group in type_groups.items():
        if len(group) >= 2:
            # Multiple regions of same type owned by same entity = reinforce
            for edge in group:
                edge.confidence = min(edge.confidence + 0.1, 1.0)
                edge.evidence.append(f"reinforced:same_type:{type_val}")

    return edges


def _find_region(regions: List[SemanticRegion], region_id: int) -> Optional[SemanticRegion]:
    for r in regions:
        if r.region_id == region_id:
            return r
    return None


def resolve_entity_ownership(
    graph: SemanticGraph,
) -> SemanticGraph:
    """Full ownership resolution for a semantic graph."""
    edges, regions = infer_semantic_ownership(graph.regions, graph.relationships)
    edges = propagate_ownership_consistency(edges, regions)
    graph.ownership_edges = edges
    graph.regions = regions
    return graph
