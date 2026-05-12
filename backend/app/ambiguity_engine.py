"""
Ambiguity Engine
==================
Manages uncertainty in semantic classification.

The system MUST support:
- Multiple candidate meanings for any token
- Confidence distributions across types
- Unresolved semantic states
- Gradual disambiguation as evidence accumulates

Core principle: Do NOT force certainty prematurely.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable
from copy import deepcopy

from app.semantic_ir import SemanticToken, SemanticType, SemanticRecord


@dataclass
class AmbiguityState:
    """Captures the ambiguity of a single token."""
    token_idx: int
    possibilities: Dict[SemanticType, float]  # type -> confidence
    is_resolved: bool = False
    resolved_type: Optional[SemanticType] = None
    resolution_evidence: List[str] = field(default_factory=list)


@dataclass
class AmbiguityProfile:
    """Complete ambiguity profile for a record or dataset."""
    token_states: Dict[int, AmbiguityState] = field(default_factory=dict)
    overall_entropy: float = 0.0  # Shannon entropy across all tokens
    unresolved_count: int = 0
    resolution_count: int = 0


def compute_ambiguity_distribution(raw: str, detected_type: str) -> Dict[SemanticType, float]:
    """Compute a distribution of possible types for a token.

    This provides the initial ambiguity estimate.
    Later stages refine this with contextual evidence.
    """
    distribution: Dict[SemanticType, float] = {}

    # Map string type to SemanticType
    type_map = {
        "price": SemanticType.PRICE,
        "date": SemanticType.DATE,
        "duration": SemanticType.DURATION,
        "code": SemanticType.CODE,
        "rating": SemanticType.RATING,
        "number": SemanticType.NUMBER,
        "phone": SemanticType.PHONE,
        "email": SemanticType.EMAIL,
        "url": SemanticType.URL,
        "text": SemanticType.TEXT,
        "location": SemanticType.LOCATION,
        "organization": SemanticType.ORGANIZATION,
    }

    primary = type_map.get(detected_type, SemanticType.TEXT)
    distribution[primary] = 0.7

    # Add secondary possibilities based on value characteristics
    upper = raw.upper()

    # 3-letter uppercase codes could be location OR code
    if detected_type == "code" and len(raw) == 3 and raw == upper:
        distribution[SemanticType.LOCATION] = 0.2
        distribution[SemanticType.CODE] = 0.7
        distribution[SemanticType.IDENTIFIER] = 0.1

    # Prices could also be numbers
    elif detected_type == "price":
        distribution[SemanticType.PRICE] = 0.85
        distribution[SemanticType.NUMBER] = 0.15

    # Numbers could be ratings, quantities, or identifiers
    elif detected_type == "number":
        txt = raw.lower()
        if "%" in txt:
            distribution[SemanticType.NUMBER] = 0.6
            distribution[SemanticType.RATING] = 0.4
        elif "." in txt:
            distribution[SemanticType.NUMBER] = 0.5
            distribution[SemanticType.RATING] = 0.4
            distribution[SemanticType.PRICE] = 0.1
        else:
            distribution[SemanticType.NUMBER] = 0.8
            distribution[SemanticType.CODE] = 0.1
            distribution[SemanticType.IDENTIFIER] = 0.1

    # Dates could also be text
    elif detected_type == "date":
        distribution[SemanticType.DATE] = 0.85
        distribution[SemanticType.TEXT] = 0.15

    return distribution


def compute_entropy(distribution: Dict[SemanticType, float]) -> float:
    """Compute Shannon entropy of a probability distribution.

    Higher entropy = more ambiguous.
    """
    import math
    total = sum(distribution.values())
    if total == 0:
        return 0.0

    entropy = 0.0
    for prob in distribution.values():
        p = prob / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def resolve_ambiguity_with_context(
    state: AmbiguityState,
    neighbors: List[SemanticToken],
    structural_pattern: Tuple[str, ...],
) -> AmbiguityState:
    """Try to resolve ambiguity using contextual evidence.

    Uses:
    - Neighbor types (price near date, code near code)
    - Structural patterns (repeated type sequences)
    - Positional context (first/last in sequence)
    """
    if state.is_resolved:
        return state

    updated = deepcopy(state)
    possibilities = dict(updated.possibilities)

    # Evidence from neighbors
    for neighbor in neighbors:
        ntype = neighbor.primary_type

        # Price near date: both more likely
        if ntype == SemanticType.DATE and SemanticType.DATE in possibilities:
            possibilities[SemanticType.DATE] = possibilities.get(SemanticType.DATE, 0) * 1.2
        if ntype == SemanticType.PRICE and SemanticType.PRICE in possibilities:
            possibilities[SemanticType.PRICE] = possibilities.get(SemanticType.PRICE, 0) * 1.2
        if ntype == SemanticType.CODE and SemanticType.CODE in possibilities:
            possibilities[SemanticType.CODE] = possibilities.get(SemanticType.CODE, 0) * 1.1

    # Evidence from structural pattern
    if structural_pattern:
        # If pattern has many codes, codes are more likely
        code_count = sum(1 for t in structural_pattern if "code" in t)
        if code_count >= 2 and SemanticType.CODE in possibilities:
            possibilities[SemanticType.CODE] = possibilities.get(SemanticType.CODE, 0) * 1.15

    # Normalize
    total = sum(possibilities.values())
    if total > 0:
        for k in possibilities:
            possibilities[k] /= total

    # Check if resolved (one type dominates)
    max_type = max(possibilities, key=possibilities.get)
    max_conf = possibilities[max_type]

    if max_conf >= 0.85:
        updated.is_resolved = True
        updated.resolved_type = max_type
        updated.resolution_evidence.append(f"dominance_threshold:{max_conf:.2f}")

    updated.possibilities = possibilities
    return updated


def build_ambiguity_profile(record: SemanticRecord) -> AmbiguityProfile:
    """Build an ambiguity profile for a complete record."""
    profile = AmbiguityProfile()
    total_entropy = 0.0

    for idx, token in enumerate(record.tokens):
        dist = token.type_distribution or {token.primary_type: 0.85}
        entropy = compute_entropy(dist)
        is_resolved = entropy < 0.5

        state = AmbiguityState(
            token_idx=idx,
            possibilities=dist,
            is_resolved=is_resolved,
            resolved_type=token.primary_type if is_resolved else None,
        )
        profile.token_states[idx] = state
        total_entropy += entropy

        if is_resolved:
            profile.resolution_count += 1
        else:
            profile.unresolved_count += 1

    profile.overall_entropy = total_entropy / max(len(record.tokens), 1)
    return profile
