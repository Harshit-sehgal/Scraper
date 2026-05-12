"""
Semantic Repair Engine
=======================
Actively repairs detected semantic contradictions.

Core principle: The engine should ATTEMPT correction, not merely lower confidence.

Strategies:
1. Swap inverted ownership (price owns entity → entity owns price)
2. Reassign type-role mismatches
3. Resolve temporal conflicts
4. Merge conflicting entities
5. Repair broken region hierarchies
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
import copy

from app.semantic_ir import (
    SemanticType, RegionType, RecordType,
    SemanticToken, SemanticRecord, SemanticRegion,
    RelationshipEdge, OwnershipEdge, SemanticGraph,
)
from app.semantic_contradiction_engine import (
    detect_contradictions, Contradiction, compute_contradiction_impact,
)


@dataclass
class RepairAction:
    """A single repair action taken."""
    action_type: str  # "swap_ownership", "reassign_type", "merge_regions", "remove_edge"
    description: str
    target_ids: List[int]
    success: bool = False
    confidence_gain: float = 0.0


def repair_graph(graph: SemanticGraph) -> Tuple[SemanticGraph, List[RepairAction]]:
    """Attempt to repair all contradictions in a semantic graph.

    Returns (repaired_graph, repair_actions).
    """
    contradictions = detect_contradictions(graph)
    actions: List[RepairAction] = []

    if not contradictions:
        return graph, actions

    # Apply repairs
    graph, new_actions = _repair_ownership_contradictions(graph, contradictions)
    actions.extend(new_actions)

    graph, new_actions = _repair_type_role_contradictions(graph, contradictions)
    actions.extend(new_actions)

    graph, new_actions = _repair_temporal_contradictions(graph, contradictions)
    actions.extend(new_actions)

    # Verify repairs
    remaining = detect_contradictions(graph)
    if len(remaining) < len(contradictions):
        for action in actions:
            action.success = True

    return graph, actions


def _repair_ownership_contradictions(
    graph: SemanticGraph,
    contradictions: List[Contradiction],
) -> Tuple[SemanticGraph, List[RepairAction]]:
    """Repair inverted ownership by swapping owner and owned."""
    actions: List[RepairAction] = []

    for edge in graph.ownership_edges:
        owner = graph.get_region(edge.owner_region_id)
        owned = graph.get_region(edge.owned_region_id)
        if not owner or not owned:
            continue

        # If price owns entity, swap
        if (owner.region_type == RegionType.PRICE_REGION and
                owned.region_type == RegionType.ENTITY_NAME):
            edge.owner_region_id, edge.owned_region_id = edge.owned_region_id, edge.owner_region_id
            edge.evidence.append("repaired:swapped_ownership")
            edge.confidence *= 0.8  # Slightly lower confidence for repaired edges
            actions.append(RepairAction(
                action_type="swap_ownership",
                description=f"Swapped: {owner.region_type.value} ↔ {owned.region_type.value}",
                target_ids=[owner.region_id, owned.region_id],
                confidence_gain=0.3,
            ))

        # Remove circular ownership
        if edge.owner_region_id == edge.owned_region_id:
            graph.ownership_edges.remove(edge)
            actions.append(RepairAction(
                action_type="remove_edge",
                description="Removed circular ownership edge",
                target_ids=[edge.owner_region_id],
                confidence_gain=0.2,
            ))

    return graph, actions


def _repair_type_role_contradictions(
    graph: SemanticGraph,
    contradictions: List[Contradiction],
) -> Tuple[SemanticGraph, List[RepairAction]]:
    """Repair type-role mismatches by adjusting region types."""
    actions: List[RepairAction] = []

    for region in graph.regions:
        if not region.tokens:
            continue

        # If all tokens in a region have the same type, and it differs
        # from the region type, consider updating the region
        token_types = set(t.primary_type for t in region.tokens)
        if len(token_types) == 1:
            token_type = token_types.pop()
            expected_region = {
                SemanticType.PRICE: RegionType.PRICE_REGION,
                SemanticType.DATE: RegionType.DATE_REGION,
                SemanticType.CODE: RegionType.IDENTIFIER_REGION,
                SemanticType.RATING: RegionType.RATING_REGION,
                SemanticType.PHONE: RegionType.CONTACT_REGION,
                SemanticType.EMAIL: RegionType.CONTACT_REGION,
                SemanticType.DURATION: RegionType.DURATION_REGION,
                SemanticType.LOCATION: RegionType.LOCATION_REGION,
                SemanticType.ORGANIZATION: RegionType.ENTITY_NAME,
            }.get(token_type)

            if expected_region and region.region_type != expected_region:
                old_type = region.region_type
                region.region_type = expected_region
                region.evidence.append(f"repaired:type_mismatch:{old_type.value}->{expected_region.value}")
                actions.append(RepairAction(
                    action_type="reassign_type",
                    description=f"Region {region.region_id}: {old_type.value} → {expected_region.value}",
                    target_ids=[region.region_id],
                    confidence_gain=0.2,
                ))

    return graph, actions


def _repair_temporal_contradictions(
    graph: SemanticGraph,
    contradictions: List[Contradiction],
) -> Tuple[SemanticGraph, List[RepairAction]]:
    """Repair temporal contradictions by adjusting relationship types."""
    actions: List[RepairAction] = []

    from app.temporal_reasoning import parse_date

    for rel in graph.relationships:
        if rel.relationship_type not in ("before", "after"):
            continue

        source_token = next((t for t in graph.tokens if t.position == rel.source_idx), None)
        target_token = next((t for t in graph.tokens if t.position == rel.target_idx), None)
        if not source_token or not target_token:
            continue

        source_date = parse_date(source_token.raw)
        target_date = parse_date(target_token.raw)
        if not source_date or not target_date:
            continue

        # If before relationship but dates are reversed, swap
        if rel.relationship_type == "before" and source_date > target_date:
            rel.source_idx, rel.target_idx = rel.target_idx, rel.source_idx
            rel.evidence.append("repaired:temporal_swap")
            actions.append(RepairAction(
                action_type="swap_temporal",
                description=f"Swapped temporal order: {source_token.raw} ↔ {target_token.raw}",
                target_ids=[rel.source_idx, rel.target_idx],
                confidence_gain=0.2,
            ))

    return graph, actions


def repair_record(record: SemanticRecord) -> Tuple[SemanticRecord, List[RepairAction]]:
    """Convenience: repair a record's semantic graph."""
    from app.semantic_graph import build_semantic_graph
    graph = build_semantic_graph(record)
    repaired_graph, actions = repair_graph(graph)
    if actions:
        record.overall_confidence = repaired_graph.coherence_score
    return record, actions
