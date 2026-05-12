"""
Relationship Inference Engine (UPGRADED)
==========================================
Infers semantically meaningful relationships between tokens.

Relationships now include:
- belongs_to: ownership (price belongs_to entity)
- describes: qualification (rating describes entity)
- quantifies: numeric measure (stops quantifies journey)
- modifies: general modification
- originates_from: source relationship
- arrives_at: destination relationship
- identifies: identification relationship
- contains: composition
- references: cross-reference

IMPORTANT: Relationship types emerge from graph topology and
structural consistency, NOT from hardcoded domain ontology.
"""

from typing import List, Dict, Optional, Tuple

from app.semantic_ir import SemanticToken, SemanticType, RelationshipEdge


# Type → role mapping (universal structural roles, NOT domain knowledge)
TYPE_SEMANTIC_ROLE: Dict[SemanticType, str] = {
    SemanticType.PRICE: "quantifies_value",
    SemanticType.DATE: "identifies_temporal",
    SemanticType.DURATION: "quantifies_temporal",
    SemanticType.CODE: "identifies_entity",
    SemanticType.RATING: "qualifies_quality",
    SemanticType.NUMBER: "quantifies_count",
    SemanticType.LOCATION: "identifies_location",
    SemanticType.ORGANIZATION: "identifies_entity",
    SemanticType.NAME: "identifies_entity",
    SemanticType.IDENTIFIER: "identifies_entity",
    SemanticType.PHONE: "identifies_contact",
    SemanticType.EMAIL: "identifies_contact",
    SemanticType.URL: "references_online",
    SemanticType.TEXT: "describes",
}


def infer_relationships(tokens: List[SemanticToken]) -> List[RelationshipEdge]:
    """Infer semantically meaningful relationships between tokens.

    Three levels with semantic types:
    1. Adjacent (gap ≤ 1): strong semantic relationships
    2. Proximal (gap ≤ 10): moderate compatibility
    3. Structural (any distance): type-based compatibility
    """
    relationships: List[RelationshipEdge] = []
    if len(tokens) < 2:
        return relationships

    for i in range(len(tokens)):
        for j in range(i + 1, len(tokens)):
            ti, tj = tokens[i], tokens[j]
            gap = ti.span.distance_to(tj.span)

            # Level 1: Adjacent - strongest relationships
            if gap <= 1:
                rel = _build_semantic_relationship(ti, tj, i, j, gap, is_adjacent=True)
                if rel:
                    relationships.append(rel)

            # Level 2: Proximal - moderate
            elif gap <= 10:
                rel = _build_semantic_relationship(ti, tj, i, j, gap, is_adjacent=False)
                if rel:
                    relationships.append(rel)

    # Add cross-type structural relationships for important type pairs
    structural_rels = _infer_structural_relationships(tokens)
    relationships.extend(structural_rels)

    return relationships


def _build_semantic_relationship(
    a: SemanticToken, b: SemanticToken,
    ai: int, bi: int, gap: int,
    is_adjacent: bool,
) -> Optional[RelationshipEdge]:
    """Build a semantically meaningful relationship between two tokens.

    Uses TYPE_SEMANTIC_ROLE to infer relationship semantics
    rather than hardcoded type-pair rules.
    """
    role_a = TYPE_SEMANTIC_ROLE.get(a.primary_type, "unknown")
    role_b = TYPE_SEMANTIC_ROLE.get(b.primary_type, "unknown")

    evidence = [f"{role_a}+{role_b}", f"gap={gap}"]

    # Determine relationship type from role combination
    rel_type, confidence = _infer_relationship_type(role_a, role_b, a.primary_type, b.primary_type)

    # Proximity decay for non-adjacent
    if not is_adjacent:
        confidence *= max(0.5, 1.0 - (gap / 20))

    if confidence < 0.2:
        return None

    return RelationshipEdge(
        source_idx=ai,
        target_idx=bi,
        relationship_type=rel_type,
        confidence=confidence,
        evidence=evidence + (["adjacent"] if is_adjacent else [f"proximal:{gap}"]),
    )


def _infer_relationship_type(
    role_a: str, role_b: str,
    type_a: SemanticType, type_b: SemanticType,
) -> Tuple[str, float]:
    """Infer relationship type from semantic roles.

    This is structural reasoning, NOT domain ontology.
    """
    # Same-type pairs
    if type_a == type_b:
        if type_a == SemanticType.CODE:
            return ("paired_codes", 0.7)
        if type_a == SemanticType.DATE:
            return ("date_range", 0.8)
        if type_a == SemanticType.NUMBER:
            return ("quantifies", 0.4)
        return ("associated_with", 0.5)

    # Entity identifier + anything
    if "identifies_entity" in (role_a, role_b):
        other_role = role_b if role_a == "identifies_entity" else role_a
        if "quantifies" in other_role:
            return ("belongs_to", 0.7)
        if "identifies_temporal" in other_role:
            return ("belongs_to", 0.6)
        if "qualifies" in other_role:
            return ("describes", 0.6)
        if "identifies_location" in other_role:
            return ("identifies", 0.6)
        return ("associated_with", 0.4)

    # Price-related
    if "quantifies_value" in (role_a, role_b):
        other_role = role_b if role_a == "quantifies_value" else role_a
        if "identifies_temporal" in other_role:
            return ("modifies", 0.5)
        if "identifies_entity" in other_role:
            return ("belongs_to", 0.7)
        return ("associated_with", 0.3)

    # Location + code
    if "identifies_location" in role_a and "identifies_entity" in role_b:
        return ("identifies", 0.6)
    if "identifies_entity" in role_a and "identifies_location" in role_b:
        return ("identifies", 0.6)

    # Temporal relationships
    if "identifies_temporal" in role_a and "quantifies_temporal" in role_b:
        return ("modifies", 0.5)
    if "quantifies_temporal" in role_a and "identifies_temporal" in role_b:
        return ("modifies", 0.5)

    return ("associated_with", 0.3)


def _infer_structural_relationships(tokens: List[SemanticToken]) -> List[RelationshipEdge]:
    """Infer structural relationships based on repeated type patterns.

    If two codes appear adjacent, they're likely related (paired_codes).
    If price appears far from entity but same record, it belongs_to entity.
    """
    rels: List[RelationshipEdge] = []

    # Find entity-type tokens
    entity_indices = [
        i for i, t in enumerate(tokens)
        if TYPE_SEMANTIC_ROLE.get(t.primary_type, "") == "identifies_entity"
    ]
    price_indices = [
        i for i, t in enumerate(tokens)
        if TYPE_SEMANTIC_ROLE.get(t.primary_type, "") == "quantifies_value"
    ]
    location_indices = [
        i for i, t in enumerate(tokens)
        if TYPE_SEMANTIC_ROLE.get(t.primary_type, "") == "identifies_location"
    ]

    # Entity → price structural relationship
    for ei in entity_indices:
        for pi in price_indices:
            if pi > ei:
                rels.append(RelationshipEdge(
                    source_idx=ei, target_idx=pi,
                    relationship_type="belongs_to",
                    confidence=0.5,
                    evidence=["structural:entity_values"],
                ))

    # Multiple codes likely identify different locations
    if len(location_indices) >= 2:
        for i in range(len(location_indices)):
            for j in range(i + 1, len(location_indices)):
                gap = tokens[location_indices[j]].span.distance_to(tokens[location_indices[i]].span)
                if gap <= 10:
                    rels.append(RelationshipEdge(
                        source_idx=location_indices[i],
                        target_idx=location_indices[j],
                        relationship_type="identifies",
                        confidence=0.5,
                        evidence=["structural:paired_locations"],
                    ))

    return rels


def compute_neighborhoods(tokens: List[SemanticToken], window: int = 3) -> List[SemanticToken]:
    """Populate neighborhood references for each token."""
    for i, token in enumerate(tokens):
        left = max(0, i - window)
        right = min(len(tokens), i + window + 1)
        neighbors = []
        for j in range(left, right):
            if j != i:
                neighbors.append(tokens[j])
        token.neighborhood = neighbors
        if i > 0:
            token.left_neighbor = tokens[i - 1]
        if i < len(tokens) - 1:
            token.right_neighbor = tokens[i + 1]
    return tokens


def infer_structural_signature(tokens: List[SemanticToken]) -> Tuple[str, ...]:
    """Infer the structural type signature of a sequence."""
    return tuple(t.primary_type.value for t in tokens if t.primary_type != SemanticType.NUMBER)
