"""
Confidence Engine
===================
Multi-level confidence scoring that considers:

1. Token confidence - How confident we are in each token's classification
2. Field confidence - How confident we are in each mapped field
3. Relationship confidence - How coherent the relationships are
4. Row cohesion confidence - How internally consistent a record is
5. Structural consistency confidence - How well a row fits the dataset pattern
6. Dataset-level consistency confidence - Cross-row agreement

Core principle: Confidence is multi-dimensional, not a single number.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.semantic_ir import (
    DatasetIR,
    RelationshipEdge,
    SemanticRecord,
    SemanticToken,
    SemanticType,
)


@dataclass
class ConfidenceReport:
    """Multi-level confidence breakdown."""
    token_confidences: Dict[int, float] = field(default_factory=dict)
    field_confidences: Dict[str, float] = field(default_factory=dict)
    relationship_confidence: float = 0.0
    row_cohesion: float = 0.0
    structural_consistency: float = 0.0
    dataset_consistency: float = 1.0
    overall: float = 0.0
    evidence: List[str] = field(default_factory=list)


def compute_token_confidence(token: SemanticToken) -> float:
    """Compute confidence for a single token.

    Based on:
    - Primary type confidence
    - Entropy of type distribution (lower entropy = higher confidence)
    - Extraction method reliability
    - Signal strength
    """
    # Primary type confidence
    primary_conf = token.type_distribution.get(token.primary_type, 0.5)

    # Entropy bonus: lower entropy = more certain
    dist = token.type_distribution
    if len(dist) <= 1:
        entropy_bonus = 0.1
    else:
        total = sum(dist.values())
        entropy = 0.0
        for p in dist.values():
            if p > 0:
                entropy -= (p / total) * math.log2(p / total)
        max_entropy = math.log2(max(len(dist), 2))
        entropy_bonus = (1.0 - (entropy / max_entropy)) * 0.1 if max_entropy > 0 else 0.1

    # Method reliability
    method_reliability = {
        "pattern": 0.95,
        "split": 0.7,
        "whitespace": 0.5,
        "dom": 0.85,
    }
    method_conf = method_reliability.get(token.extraction_method, 0.5)

    confidence = (primary_conf * 0.5) + (entropy_bonus * 0.2) + (method_conf * 0.3)
    return min(confidence, 1.0)


def compute_relationship_confidence(relationships: List[RelationshipEdge]) -> float:
    """Compute overall relationship confidence for a record."""
    if not relationships:
        return 0.0
    avg_conf = sum(r.confidence for r in relationships) / len(relationships)
    density = min(len(relationships) / 5.0, 1.0)  # more relationships = better
    return (avg_conf * 0.7) + (density * 0.3)


def compute_row_cohesion(tokens: List[SemanticToken], relationships: List[RelationshipEdge]) -> float:
    """Compute how internally cohesive a record is.

    High cohesion: meaningful types present, strong relationships, diverse types
    Low cohesion: all text, no relationships, single type
    """
    if not tokens:
        return 0.0

    # Meaningful ratio
    meaningful = len([t for t in tokens if t.primary_type not in (SemanticType.TEXT, SemanticType.NUMBER)])
    meaningful_ratio = meaningful / max(len(tokens), 1)

    # Type diversity
    types = set(t.primary_type for t in tokens if t.primary_type not in (SemanticType.TEXT, SemanticType.NUMBER))
    diversity = min(len(types) / 4.0, 1.0)

    # Relationship density
    rel_density = len(relationships) / max(len(tokens), 1)

    cohesion = (meaningful_ratio * 0.4) + (diversity * 0.3) + (min(rel_density, 1.0) * 0.3)
    return min(cohesion, 1.0)


def compute_structural_consistency(
    signature: Tuple[str, ...],
    dataset: DatasetIR
) -> float:
    """Compute how well a record's structure matches the dataset.

    Common patterns get high consistency.
    Novel patterns get low consistency.
    """
    if not dataset.structural_memory:
        return 0.5  # No baseline yet

    total = sum(dataset.structural_memory.values())
    if total == 0:
        return 0.5

    count = dataset.structural_memory.get(signature, 0)
    frequency = count / total

    # Also check similarity to known patterns
    similarity_bonus = 0.0
    for known_sig, _known_count in dataset.structural_memory.items():
        if known_sig == signature:
            continue
        sim = _signature_similarity(signature, known_sig)
        if sim > 0.5:
            similarity_bonus = max(similarity_bonus, sim * 0.2)

    consistency = min(frequency + similarity_bonus, 1.0)
    return max(consistency, 0.1)  # floor at 0.1


def _signature_similarity(a: Tuple[str, ...], b: Tuple[str, ...]) -> float:
    """Compute Jaccard similarity between two type signatures."""
    set_a, set_b = set(a), set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def compute_record_confidence(
    record: SemanticRecord,
    dataset: Optional[DatasetIR] = None
) -> ConfidenceReport:
    """Compute full multi-level confidence for a record."""
    report = ConfidenceReport()

    # Token-level
    for i, token in enumerate(record.tokens):
        report.token_confidences[i] = compute_token_confidence(token)

    # Field-level
    for f_name, _value in record.mapped_fields.items():
        conf = record.mapped_confidences.get(f_name, 0.5)
        report.field_confidences[f_name] = conf

    # Relationship-level
    report.relationship_confidence = compute_relationship_confidence(record.relationships)

    # Row cohesion
    report.row_cohesion = compute_row_cohesion(record.tokens, record.relationships)

    # Structural consistency
    if dataset:
        report.structural_consistency = compute_structural_consistency(
            record.structural_signature, dataset
        )

    # Overall (weighted average)
    weights = {
        "token": 0.15,
        "field": 0.25,
        "relationship": 0.15,
        "cohesion": 0.25,
        "structural": 0.20,
    }

    avg_token_conf = sum(report.token_confidences.values()) / max(len(report.token_confidences), 1)
    avg_field_conf = sum(report.field_confidences.values()) / max(len(report.field_confidences), 1)

    report.overall = (
        avg_token_conf * weights["token"] +
        avg_field_conf * weights["field"] +
        report.relationship_confidence * weights["relationship"] +
        report.row_cohesion * weights["cohesion"] +
        report.structural_consistency * weights["structural"]
    )

    report.evidence = [
        f"tokens={len(record.tokens)}",
        f"relationships={len(record.relationships)}",
        f"cohesion={report.row_cohesion:.2f}",
        f"structural={report.structural_consistency:.2f}",
    ]

    return report


def compute_global_coherence(records: List[SemanticRecord]) -> float:
    """Compute global coherence across all records in a dataset.

    Measures:
    - Pattern convergence (do most rows share a common pattern?)
    - Confidence consistency (are confidences stable across rows?)
    - Relationship density (are relationships present across rows?)
    """
    if not records:
        return 0.0

    # Pattern convergence
    signatures = [r.structural_signature for r in records if r.structural_signature]
    if signatures:
        most_common = Counter(signatures).most_common(1)
        convergence = most_common[0][1] / len(signatures) if most_common else 0.0
    else:
        convergence = 0.0

    # Average confidence
    avg_conf = sum(r.overall_confidence for r in records) / len(records)

    # Coherence = convergence + average confidence
    coherence = (convergence * 0.5) + (avg_conf * 0.5)
    return min(coherence, 1.0)
