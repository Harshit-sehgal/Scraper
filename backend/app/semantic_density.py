"""
Semantic Density Engine
=========================
Computes information density, semantic richness, and navigation entropy.

Core principle: High-density regions contain real data.
Low-density regions are navigation, UI, or noise.

This replaces keyword-based noise filtering with structural density analysis.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
import math

from app.semantic_ir import (
    SemanticToken, SemanticType, SemanticRecord, SemanticRegion,
    SemanticGraph, RecordType, Span,
)


@dataclass
class DensityProfile:
    """Complete density profile for a record or region."""
    semantic_density: float = 0.0  # 0.0-1.0
    type_diversity: float = 0.0    # 0.0-1.0
    information_entropy: float = 0.0
    structural_richness: float = 0.0
    is_navigation: bool = False
    is_data: bool = False
    evidence: List[str] = field(default_factory=list)


# Type information weights (how informative each type is)
TYPE_INFORMATION_WEIGHT: Dict[SemanticType, float] = {
    SemanticType.PRICE: 1.0,
    SemanticType.PHONE: 0.95,
    SemanticType.EMAIL: 0.95,
    SemanticType.URL: 0.90,
    SemanticType.DATE: 0.85,
    SemanticType.RATING: 0.80,
    SemanticType.LOCATION: 0.75,
    SemanticType.CODE: 0.70,
    SemanticType.DURATION: 0.70,
    SemanticType.ORGANIZATION: 0.65,
    SemanticType.NAME: 0.60,
    SemanticType.IDENTIFIER: 0.55,
    SemanticType.NUMBER: 0.30,
    SemanticType.TEXT: 0.10,
}


def compute_semantic_density(tokens: List[SemanticToken]) -> float:
    """Compute semantic density of a token sequence.

    High density = many high-information types (prices, dates, codes, etc.)
    Low density = mostly text, numbers, or noise
    """
    if not tokens:
        return 0.0

    # Weighted information sum
    total_weight = sum(
        TYPE_INFORMATION_WEIGHT.get(t.primary_type, 0.1)
        for t in tokens
    )

    # Normalize by length
    density = total_weight / len(tokens)

    return min(density, 1.0)


def compute_type_diversity(tokens: List[SemanticToken]) -> float:
    """Compute type diversity as fraction of possible meaningful types."""
    if not tokens:
        return 0.0

    meaningful_types = {
        SemanticType.PRICE, SemanticType.DATE, SemanticType.CODE,
        SemanticType.RATING, SemanticType.LOCATION, SemanticType.DURATION,
        SemanticType.PHONE, SemanticType.EMAIL, SemanticType.ORGANIZATION,
        SemanticType.NAME, SemanticType.IDENTIFIER,
    }

    present = set(t.primary_type for t in tokens if t.primary_type in meaningful_types)
    diversity = len(present) / len(meaningful_types)

    return min(diversity * 3, 1.0)  # Scale up since we rarely see all types


def compute_information_entropy(tokens: List[SemanticToken]) -> float:
    """Compute Shannon entropy of type distribution.

    High entropy = many different types (likely real data)
    Low entropy = few types repeating (likely navigation/noise)
    """
    if not tokens:
        return 0.0

    type_counts: Dict[SemanticType, int] = {}
    for t in tokens:
        type_counts[t.primary_type] = type_counts.get(t.primary_type, 0) + 1

    total = len(tokens)
    entropy = 0.0
    for count in type_counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)

    max_entropy = math.log2(max(len(type_counts), 2))
    return entropy / max_entropy if max_entropy > 0 else 0.0


def compute_structural_richness(tokens: List[SemanticToken]) -> float:
    """Compute structural richness based on type transitions.

    Rich structures have many type changes (alternating price, date, code).
    Poor structures have few type changes (text, text, text).
    """
    if len(tokens) < 2:
        return 0.0

    transitions = sum(
        1 for i in range(len(tokens) - 1)
        if tokens[i].primary_type != tokens[i + 1].primary_type
    )
    max_transitions = len(tokens) - 1
    return transitions / max_transitions if max_transitions > 0 else 0.0


def compute_density_profile(
    tokens: List[SemanticToken],
) -> DensityProfile:
    """Compute full density profile for a token sequence."""
    density = compute_semantic_density(tokens)
    diversity = compute_type_diversity(tokens)
    entropy = compute_information_entropy(tokens)
    richness = compute_structural_richness(tokens)

    return DensityProfile(
        semantic_density=density,
        type_diversity=diversity,
        information_entropy=entropy,
        structural_richness=richness,
        is_navigation=density < 0.25,
        is_data=density >= 0.35,
        evidence=[
            f"density={density:.2f}",
            f"diversity={diversity:.2f}",
            f"entropy={entropy:.2f}",
            f"richness={richness:.2f}",
        ],
    )


def classify_by_density(tokens: List[SemanticToken]) -> RecordType:
    """Classify a record type purely by density analysis.

    This is a universal alternative to keyword-based classification.
    """
    profile = compute_density_profile(tokens)

    if profile.semantic_density >= 0.5:
        return RecordType.ENTITY
    elif profile.semantic_density >= 0.3:
        return RecordType.ENTITY  # Low confidence entity
    elif profile.semantic_density <= 0.15 and profile.type_diversity < 0.1:
        return RecordType.NAVIGATION
    else:
        return RecordType.UNKNOWN


def compute_region_density(region: SemanticRegion) -> DensityProfile:
    """Compute density profile for a specific region."""
    return compute_density_profile(region.tokens)
