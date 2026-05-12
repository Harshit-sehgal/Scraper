"""
Global Graph Coherence Engine
===============================
Computes and maintains dataset-wide semantic consistency.

Core principle: Individual records should not be evaluated in isolation.
The most coherent interpretation emerges from dataset-wide patterns.

If 95% of rows follow [text][price][date], anomalous rows should:
- lose confidence
- get repaired
- or get rejected
"""

from dataclasses import dataclass, field
from typing import List, Tuple
from collections import Counter

from app.semantic_ir import (
    SemanticRecord, SemanticGraph, DatasetIR,
)


@dataclass
class GlobalCoherenceReport:
    """Report of global coherence analysis."""
    pattern_convergence: float = 0.0
    confidence_consistency: float = 0.0
    structural_agreement: float = 0.0
    anomaly_count: int = 0
    harmony_score: float = 0.0
    dominant_pattern: Tuple[str, ...] = field(default_factory=tuple)
    evidence: List[str] = field(default_factory=list)


def compute_global_coherence(dataset: DatasetIR) -> GlobalCoherenceReport:
    """Compute global coherence across all records in a dataset."""
    if not dataset.records:
        return GlobalCoherenceReport()

    report = GlobalCoherenceReport()

    # 1. Pattern convergence
    signatures = [
        r.structural_signature for r in dataset.records
        if r.structural_signature
    ]
    if signatures:
        counter = Counter(signatures)
        most_common = counter.most_common(1)
        report.dominant_pattern = most_common[0][0] if most_common else ()
        report.pattern_convergence = most_common[0][1] / len(signatures) if most_common else 0.0

    # 2. Confidence consistency
    confidences = [r.overall_confidence for r in dataset.records]
    if confidences:
        avg_conf = sum(confidences) / len(confidences)
        variance = sum((c - avg_conf) ** 2 for c in confidences) / len(confidences)
        report.confidence_consistency = 1.0 - min(variance, 1.0)

    # 3. Structural agreement
    if signatures:
        # How many records share the dominant pattern vs. deviate
        total = len(signatures)
        dominant_count = counter.most_common(1)[0][1] if counter.most_common(1) else 0
        report.structural_agreement = dominant_count / total

    # 4. Anomaly detection
    if report.dominant_pattern:
        for record in dataset.records:
            if (record.structural_signature and
                    record.structural_signature != report.dominant_pattern):
                similarity = _signature_similarity(
                    record.structural_signature, report.dominant_pattern
                )
                if similarity < 0.3:
                    report.anomaly_count += 1
                    _mark_as_anomaly(record)

    # 5. Harmony score (overall)
    report.harmony_score = (
        report.pattern_convergence * 0.3 +
        report.confidence_consistency * 0.3 +
        report.structural_agreement * 0.4
    )

    report.evidence = [
        f"dominant:{report.dominant_pattern}",
        f"convergence:{report.pattern_convergence:.2f}",
        f"anomalies:{report.anomaly_count}",
        f"harmony:{report.harmony_score:.2f}",
    ]

    return report


def _signature_similarity(a: Tuple[str, ...], b: Tuple[str, ...]) -> float:
    """Compute Jaccard similarity between two type signatures."""
    set_a, set_b = set(a), set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _mark_as_anomaly(record: SemanticRecord):
    """Mark a record as anomalous and reduce its confidence."""
    record.structural_confidence *= 0.5
    record.evidence.append("anomaly:structural_deviation")


def compute_cross_record_consistency(graphs: List[SemanticGraph]) -> float:
    """Compute cross-record consistency from a list of semantic graphs."""
    if not graphs:
        return 0.0

    # Region type sequence consistency
    sequences = [
        tuple(r.region_type.value for r in g.regions)
        for g in graphs if g.regions
    ]
    if not sequences:
        return 0.0

    counter = Counter(sequences)
    most_common = counter.most_common(1)
    convergence = most_common[0][1] / len(sequences) if most_common else 0.0

    # Structural coherence
    coherence_scores = [g.coherence_score for g in graphs if g.coherence_score > 0]
    avg_coherence = sum(coherence_scores) / len(coherence_scores) if coherence_scores else 0.0

    return (convergence * 0.5) + (avg_coherence * 0.5)


def enhance_dataset_with_global_coherence(dataset: DatasetIR) -> DatasetIR:
    """Enhance a dataset by computing and applying global coherence."""
    report = compute_global_coherence(dataset)
    dataset.global_coherence = report.harmony_score

    # Apply anomaly penalties
    for record in dataset.records:
        if record.structural_signature and report.dominant_pattern:
            if record.structural_signature != report.dominant_pattern:
                similarity = _signature_similarity(
                    record.structural_signature, report.dominant_pattern
                )
                if similarity < 0.3:
                    penalty = (1.0 - report.pattern_convergence) * 0.3
                    record.overall_confidence *= (1.0 - penalty)

    return dataset
