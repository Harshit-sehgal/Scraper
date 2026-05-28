"""
Extraction Accuracy Framework — Measuring interpretative quality.

Evaluates scraper output against ground-truth "golden" datasets using
statistical precision, recall, and conformity metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any

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
    
    # Advanced metrics added to resolve the "truth gap" and punish false-positives
    field_recall: float = 0.0
    field_precision: float = 0.0
    record_precision: float = 0.0
    extra_record_rate: float = 0.0
    schema_compliance: float = 0.0
    
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
    total_expected_fields = sum(len([k for k in r.keys() if not k.startswith("_")]) for r in expected)
    expected_keys = {k for r in expected for k in r.keys() if not k.startswith("_")}
    
    field_hits = {k: 0 for r in expected for k in r.keys() if not k.startswith("_")}
    field_totals = {k: 0 for r in expected for k in r.keys() if not k.startswith("_")}
    
    # Count total extracted fields (excluding metadata keys)
    total_extracted_fields = sum(len([k for k in r.keys() if not k.startswith("_") and k != "record_score"]) for r in extracted)
    
    matched_records_count = 0
    
    # Local copies to track matched records
    available_extracted = list(extracted)
    
    for exp_rec in expected:
        exp_non_meta = {k: v for k, v in exp_rec.items() if not k.startswith("_")}
        for k in exp_non_meta.keys():
            field_totals[k] = field_totals.get(k, 0) + 1
            
        best_match_idx = -1
        best_score = -1
        
        for i, ext_rec in enumerate(available_extracted):
            score = 0
            for k, v in exp_non_meta.items():
                if k in ext_rec and _values_match(ext_rec[k], v):
                    score += 1
            if score > best_score:
                best_score = score
                best_match_idx = i
        
        # A record is considered a match if it has at least one correct field
        if best_match_idx >= 0 and best_score > 0:
            matched_rec = available_extracted.pop(best_match_idx)
            true_positives += best_score
            matched_records_count += 1
            for k, v in exp_non_meta.items():
                if k in matched_rec and _values_match(matched_rec[k], v):
                    field_hits[k] = field_hits.get(k, 0) + 1

    # 2. Precision & Recall Calculation (Rigorous, Punishing False-Positives)
    field_recall = true_positives / total_expected_fields if total_expected_fields > 0 else 0.0
    field_precision = true_positives / total_extracted_fields if total_extracted_fields > 0 else 0.0
    
    metrics.recall = field_recall
    metrics.precision = field_precision
    
    if metrics.precision + metrics.recall > 0:
        metrics.f1_score = 2 * (metrics.precision * metrics.recall) / (metrics.precision + metrics.recall)
    
    # Set advanced metrics
    metrics.field_recall = field_recall
    metrics.field_precision = field_precision
    metrics.record_precision = matched_records_count / len(extracted) if extracted else 0.0
    metrics.extra_record_rate = (len(extracted) - matched_records_count) / len(extracted) if extracted else 0.0

    # 3. Schema Compliance
    compliant_fields = 0
    total_non_metadata_fields = 0
    for r in extracted:
        non_meta_keys = [k for k in r.keys() if not k.startswith("_") and k != "record_score"]
        total_non_metadata_fields += len(non_meta_keys)
        for k in non_meta_keys:
            if k in expected_keys:
                compliant_fields += 1
                
    metrics.schema_compliance = compliant_fields / total_non_metadata_fields if total_non_metadata_fields > 0 else 0.0
    metrics.schema_conformity = metrics.schema_compliance

    # 4. Completeness & Schema Conformity
    metrics.completeness = min(1.0, len(extracted) / max(1, len(expected)))
    
    # Per-field accuracy
    for k in field_totals:
        if field_totals[k] > 0:
            metrics.field_accuracy[k] = round(field_hits[k] / field_totals[k], 3)

    # 5. Duplicate Rate
    unique_count = len({_record_hash(r) for r in extracted})
    metrics.duplicate_rate = 1.0 - (unique_count / len(extracted)) if extracted else 0.0

    # 6. Hallucination Detection (Indicators)
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
    
    if s1 == s2:
        return True
        
    # Currency-aware matching: strip symbols and commas
    import re
    def _strip_currency(s: str) -> str:
        return re.sub(r"[^\d.]", "", s)
        
    clean1 = _strip_currency(s1)
    clean2 = _strip_currency(s2)
    if clean1 and clean2 and clean1 == clean2:
        return True
        
    # Partial match for longer strings
    if len(s1) > 10 and len(s2) > 10:
        if s1 in s2 or s2 in s1:
            return True
            
    return False


def _record_hash(record: Dict[str, Any]) -> str:
    """Stable hash for a record to detect duplicates."""
    # Filter out metadata
    data = {k: v for k, v in record.items() if not k.startswith("_") and k != "record_score"}
    return str(sorted(data.items()))
