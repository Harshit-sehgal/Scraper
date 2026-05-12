"""
Semantic Contradiction Engine
===============================
Detects impossible or incoherent semantic configurations.

Examples of contradictions:
- A price value in a date field → "price = London"
- A date value in a price field → "date = ₹5200"
- A numeric value claiming to describe a text entity
- Circular ownership (A owns B, B owns A)
- Conflicting temporal ordering

Core principle: Syntactically valid ≠ semantically possible.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict

from app.semantic_ir import (
    SemanticType, RegionType, RecordType,
    SemanticToken, SemanticRecord, SemanticRegion,
    RelationshipEdge, OwnershipEdge, SemanticGraph,
)


@dataclass
class Contradiction:
    """A detected semantic contradiction."""
    contradiction_type: str
    description: str
    source_ids: List[int]
    confidence_damage: float  # 0.0-1.0 how much confidence to deduct
    severity: str  # "critical", "major", "minor"
    evidence: List[str] = field(default_factory=list)


# Type-role compatibility matrix: which types are valid for which roles
# These are structural incompatibilities, NOT domain rules
INCOMPATIBLE_TYPE_ROLE: Dict[str, Set[SemanticType]] = {
    "price": {SemanticType.TEXT, SemanticType.DATE, SemanticType.LOCATION},
    "date": {SemanticType.PRICE, SemanticType.NUMBER},
    "location": {SemanticType.PRICE, SemanticType.EMAIL, SemanticType.PHONE},
    "rating": {SemanticType.URL, SemanticType.PHONE},
}


def detect_contradictions(graph: SemanticGraph) -> List[Contradiction]:
    """Detect all semantic contradictions in a graph."""
    contradictions: List[Contradiction] = []

    # 1. Type-role contradictions
    contradictions.extend(_detect_type_role_contradictions(graph))

    # 2. Ownership contradictions
    contradictions.extend(_detect_ownership_contradictions(graph))

    # 3. Temporal contradictions
    contradictions.extend(_detect_temporal_contradictions(graph))

    # 4. Coherence contradictions
    contradictions.extend(_detect_coherence_contradictions(graph))

    return contradictions


def _detect_type_role_contradictions(graph: SemanticGraph) -> List[Contradiction]:
    """Detect tokens whose type contradicts their assigned role."""
    contradictions: List[Contradiction] = []

    for region in graph.regions:
        for token in region.tokens:
            for role, incompatible_types in INCOMPATIBLE_TYPE_ROLE.items():
                if token.primary_type in incompatible_types:
                    # Check if this token's role matches
                    if _token_plays_role(token, region, role):
                        contradictions.append(Contradiction(
                            contradiction_type="type_role_mismatch",
                            description=f"Token '{token.raw}' has type {token.primary_type.value} "
                                        f"but plays role '{role}'",
                            source_ids=[id(token)],
                            confidence_damage=0.4,
                            severity="major",
                            evidence=[f"incompatible:{token.primary_type.value}:{role}"],
                        ))

    return contradictions


def _detect_ownership_contradictions(graph: SemanticGraph) -> List[Contradiction]:
    """Detect impossible ownership relationships."""
    contradictions: List[Contradiction] = []

    for edge in graph.ownership_edges:
        owner = graph.get_region(edge.owner_region_id)
        owned = graph.get_region(edge.owned_region_id)
        if not owner or not owned:
            continue

        # Circular ownership
        if owned.owned_by == owner.region_id and owner.owned_by == owned.region_id:
            contradictions.append(Contradiction(
                contradiction_type="circular_ownership",
                description=f"Circular ownership between region {owner.region_id} and {owned.region_id}",
                source_ids=[owner.region_id, owned.region_id],
                confidence_damage=0.6,
                severity="critical",
                evidence=["circular:ownership"],
            ))

        # Price owning entity name (inverted hierarchy)
        if (owner.region_type == RegionType.PRICE_REGION and
                owned.region_type == RegionType.ENTITY_NAME):
            contradictions.append(Contradiction(
                contradiction_type="inverted_ownership",
                description=f"Price region owns entity name (inverted)",
                source_ids=[owner.region_id, owned.region_id],
                confidence_damage=0.5,
                severity="major",
                evidence=["inverted:price_owns_entity"],
            ))

    return contradictions


def _detect_temporal_contradictions(graph: SemanticGraph) -> List[Contradiction]:
    """Detect temporal contradictions."""
    contradictions: List[Contradiction] = []
    date_tokens = [t for t in graph.tokens if t.primary_type == SemanticType.DATE]

    if len(date_tokens) < 2:
        return contradictions

    # Check if any date relationships conflict
    from app.temporal_reasoning import parse_date
    parsed_dates = [(t, parse_date(t.raw)) for t in date_tokens]
    parsed_dates = [(t, d) for t, d in parsed_dates if d]

    for i in range(len(parsed_dates)):
        for j in range(i + 1, len(parsed_dates)):
            ti, di = parsed_dates[i]
            tj, dj = parsed_dates[j]

            # Check for temporal implication contradictions
            # e.g., if A is "before" B but date(A) > date(B)
            for rel in graph.relationships:
                if (rel.source_idx == ti.position and rel.target_idx == tj.position
                        and rel.relationship_type == "before" and di > dj):
                    contradictions.append(Contradiction(
                        contradiction_type="temporal_conflict",
                        description=f"Date {ti.raw} before {tj.raw} but dates reversed",
                        source_ids=[ti.position, tj.position],
                        confidence_damage=0.5,
                        severity="major",
                        evidence=[f"temporal_conflict:{ti.raw}>{tj.raw}"],
                    ))

    return contradictions


def _detect_coherence_contradictions(graph: SemanticGraph) -> List[Contradiction]:
    """Detect contradictions from low coherence."""
    contradictions: List[Contradiction] = []

    # If a record has high semantic density but near-zero coherence
    meaningful_tokens = [t for t in graph.tokens
                         if t.primary_type not in (SemanticType.TEXT, SemanticType.NUMBER)]
    if len(meaningful_tokens) >= 3 and graph.coherence_score < 0.3:
        contradictions.append(Contradiction(
            contradiction_type="low_coherence",
            description=f"{len(meaningful_tokens)} meaningful tokens but coherence={graph.coherence_score:.2f}",
            source_ids=[t.position for t in meaningful_tokens],
            confidence_damage=0.3,
            severity="minor",
            evidence=[f"coherence:{graph.coherence_score:.2f}"],
        ))

    return contradictions


def _token_plays_role(token: SemanticToken, region: SemanticRegion, role: str) -> bool:
    """Check if a token plays a specific semantic role."""
    return region.region_type.value == role or token.primary_type.value == role


def compute_contradiction_impact(contradictions: List[Contradiction]) -> float:
    """Compute the total impact of all contradictions on confidence.

    Returns a penalty multiplier (0.0-1.0).
    """
    if not contradictions:
        return 0.0

    total_penalty = sum(c.confidence_damage for c in contradictions
                        if c.severity == "critical") * 1.0
    total_penalty += sum(c.confidence_damage for c in contradictions
                         if c.severity == "major") * 0.5
    total_penalty += sum(c.confidence_damage for c in contradictions
                         if c.severity == "minor") * 0.2

    return min(total_penalty, 1.0)


def apply_contradiction_penalties(
    graph: SemanticGraph,
    contradictions: List[Contradiction],
) -> SemanticGraph:
    """Apply confidence penalties to a graph based on contradictions."""
    penalty = compute_contradiction_impact(contradictions)
    graph.contradiction_score = penalty
    graph.has_contradictions = len(contradictions) > 0
    graph.coherence_score *= (1.0 - penalty)
    return graph
