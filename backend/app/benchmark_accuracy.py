"""
Extraction Accuracy Framework — Measuring interpretative quality.

Evaluates scraper output against ground-truth "golden" datasets using
statistical precision, recall, and conformity metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AccuracyMetrics:
    domain: str = "unknown"
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    completeness: float = 0.0
    schema_conformity: float = 0.0
    duplicate_rate: float = 0.0
    hallucination_rate: float = 0.0
    field_accuracy: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_extraction_accuracy(
    extracted: List[Dict[str, Any]], 
    expected: List[Dict[str, Any]],
    domain: str = "unknown"
) -> AccuracyMetrics:
    """Calculate deep accuracy metrics for a set of extracted records."""
    if not expected:
        return AccuracyMetrics(domain=domain, precision=1.0 if not extracted else 0.0)
    
    if not extracted:
        return AccuracyMetrics(domain=domain, recall=0.0)

    metrics = AccuracyMetrics(domain=domain)
    
    # 1. Record Matching & Field Accuracy
    true_positives = 0
    total_expected_fields = sum(len(r) for r in expected)
    total_extracted_fields = 0
    
    field_hits = {k: 0 for r in expected for k in r.keys()}
    field_totals = {k: 0 for r in expected for k in r.keys()}
    
    # Local copies to track matched records
    available_extracted = list(extracted)
    
    for exp_rec in expected:
        for k in exp_rec.keys():
            field_totals[k] = field_totals.get(k, 0) + 1
            
        best_match_idx = -1
        best_score = -1
        
        for i, ext_rec in enumerate(available_extracted):
            score = 0
            for k, v in exp_rec.items():
                if k in ext_rec and _values_match(ext_rec[k], v):
                    score += 1
            if score > best_score:
                best_score = score
                best_match_idx = i
        
        if best_match_idx >= 0:
            matched_rec = available_extracted.pop(best_match_idx)
            true_positives += best_score
            for k, v in exp_rec.items():
                if k in matched_rec and _values_match(matched_rec[k], v):
                    field_hits[k] = field_hits.get(k, 0) + 1

    # 2. Precision & Recall Calculation
    for ext_rec in extracted:
        # Don't count metadata fields
        valid_keys = [k for k in ext_rec.keys() if not k.startswith("_") and k != "record_score" and ext_rec[k] is not None]
        total_extracted_fields += len(valid_keys)

    metrics.precision = true_positives / total_extracted_fields if total_extracted_fields > 0 else 0.0
    metrics.recall = true_positives / total_expected_fields if total_expected_fields > 0 else 0.0
    
    if metrics.precision + metrics.recall > 0:
        metrics.f1_score = 2 * (metrics.precision * metrics.recall) / (metrics.precision + metrics.recall)

    # 3. Completeness & Schema Conformity
    metrics.completeness = min(1.0, len(extracted) / len(expected))
    
    # Per-field accuracy
    for k in field_totals:
        if field_totals[k] > 0:
            metrics.field_accuracy[k] = round(field_hits[k] / field_totals[k], 3)

    # 4. Duplicate Rate
    unique_count = len({_record_hash(r) for r in extracted})
    metrics.duplicate_rate = 1.0 - (unique_count / len(extracted)) if extracted else 0.0

    # 5. Hallucination Detection (Indicators)
    # Very basic: look for common placeholder strings or "I don't know" phrases from LLM
    hallucinations = 0
    for r in extracted:
        for v in r.values():
            if isinstance(v, str) and any(p in v.lower() for p in ["i'm sorry", "cannot determine", "not found in html", "unknown"]):
                hallucinations += 1
    metrics.hallucination_rate = hallucinations / total_extracted_fields if total_extracted_fields > 0 else 0.0

    return metrics


def _values_match(v1: Any, v2: Any) -> bool:
    """Fuzzy-ish value matching for accuracy measurement."""
    if v1 == v2:
        return True
    if v1 is None or v2 is None:
        return False
    
    s1, s2 = str(v1).strip().lower(), str(v2).strip().lower()
    # Normalize whitespace
    s1 = " ".join(s1.split())
    s2 = " ".join(s2.split())
    
    return s1 == s2


def _record_hash(record: Dict[str, Any]) -> str:
    """Stable hash for a record to detect duplicates."""
    # Filter out metadata
    data = {k: v for k, v in record.items() if not k.startswith("_") and k != "record_score"}
    return str(sorted(data.items()))
