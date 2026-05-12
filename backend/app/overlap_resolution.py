"""
Overlap Resolution Engine
===========================
Resolves span conflicts where broader semantic entities dominate
their child fragments.

Problem:
  22-05-2026
   ↓
  22  (number)
  05  (number)
  2026 (number)

Solution:
  The date "22-05-2026" dominates its child fragments.
  Child tokens are suppressed when a parent covers their span.

Core rule:
  Broader semantic entities dominate narrower ones.
  Price > number fragments, Date > number parts, Email > substrings.
"""

from typing import Dict, List, Set

from app.semantic_ir import SemanticRecord, SemanticToken, SemanticType

# Hierarchical dominance: broader types dominate narrower ones
DOMINANCE_HIERARCHY = {
    SemanticType.EMAIL: 100,
    SemanticType.PRICE: 90,
    SemanticType.DATE: 85,
    SemanticType.PHONE: 80,
    SemanticType.URL: 80,
    SemanticType.DURATION: 70,
    SemanticType.RATING: 65,
    SemanticType.CODE: 50,
    SemanticType.LOCATION: 45,
    SemanticType.ORGANIZATION: 40,
    SemanticType.NAME: 35,
    SemanticType.NUMBER: 20,
    SemanticType.IDENTIFIER: 15,
    SemanticType.TEXT: 10,
}


def resolve_overlaps(tokens: List[SemanticToken]) -> List[SemanticToken]:
    """Resolve span overlaps by suppressing dominated child tokens.

    When two tokens overlap:
    - The broader type (higher dominance) survives
    - The narrower type is suppressed
    - Equal dominance: the larger span survives (more specific)

    Returns a filtered token list with dominated tokens removed.
    """
    if not tokens:
        return tokens

    # Sort by DOMINANCE descending (highest dominance first)
    # Within same dominance, sort by span length descending (larger = more specific)
    sorted_tokens = sorted(
        tokens,
        key=lambda t: (
            -DOMINANCE_HIERARCHY.get(t.primary_type, 0),
            -(t.span.end - t.span.start)
        )
    )

    # Build suppression set: higher-dominance tokens suppress overlapping lower-dominance ones
    suppressed: Set[int] = set()

    for i in range(len(sorted_tokens)):
        if i in suppressed:
            continue
        for j in range(i + 1, len(sorted_tokens)):
            if j in suppressed:
                continue
            ti, tj = sorted_tokens[i], sorted_tokens[j]

            # Only check actual overlap
            if not ti.span.overlaps_with(tj.span):
                continue

            # Higher dominance (i) always suppresses lower (j) on overlap
            suppressed.add(j)

    result = [t for idx, t in enumerate(sorted_tokens) if idx not in suppressed]

    # Rebuild positions
    for pos, token in enumerate(result):
        token.position = pos

    return result


def resolve_record_overlaps(record: SemanticRecord) -> SemanticRecord:
    """Resolve all span overlaps within a semantic record."""
    record.tokens = resolve_overlaps(record.tokens)
    return record


def compute_overlap_statistics(tokens: List[SemanticToken]) -> Dict:
    """Compute overlap statistics for debugging."""
    stats = {
        "total_tokens": len(tokens),
        "overlap_pairs": 0,
        "suppressed_candidates": 0,
    }
    for i in range(len(tokens)):
        for j in range(i + 1, len(tokens)):
            if tokens[i].span.overlaps_with(tokens[j].span):
                stats["overlap_pairs"] += 1
    return stats
