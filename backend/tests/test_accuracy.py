"""
Extraction Accuracy Measurement — Evaluating extraction precision and recall against ground truth.

This tool measures the actual data quality of the scraper components by comparing
extracted output against a "golden" expected output dataset.
"""

import json
from typing import List, Dict, Any

def calculate_accuracy(extracted: List[Dict[str, Any]], expected: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calculate Precision, Recall, and F1-score based on exact field matches."""
    if not extracted and not expected:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not expected:
        return {"precision": 0.0, "recall": 1.0, "f1": 0.0}
    if not extracted:
        return {"precision": 1.0, "recall": 0.0, "f1": 0.0}

    # We flatten records into sets of tuples: (record_index, field_name, value)
    # To handle order-independence of records, we just try to find the best match for each expected record
    # For a simpler metric, we just check if the expected record is a subset of ANY extracted record.
    
    true_positives = 0
    total_expected_fields = 0
    total_extracted_fields = 0

    for exp_rec in expected:
        # Find the extracted record that has the most matching fields
        best_match_score = 0
        best_match_rec = None
        
        for ext_rec in extracted:
            score = 0
            for k, v in exp_rec.items():
                if k in ext_rec and ext_rec[k] == v:
                    score += 1
            if score > best_match_score:
                best_match_score = score
                best_match_rec = ext_rec
                
        true_positives += best_match_score
        total_expected_fields += len(exp_rec.keys())

    for ext_rec in extracted:
        # Don't count internal metadata fields like _key or record_score
        valid_keys = [k for k in ext_rec.keys() if not k.startswith("_") and k != "record_score" and ext_rec[k] is not None]
        total_extracted_fields += len(valid_keys)

    precision = true_positives / total_extracted_fields if total_extracted_fields > 0 else 0.0
    recall = true_positives / total_expected_fields if total_expected_fields > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3)
    }

def test_accuracy_calculation():
    golden = [
        {"name": "Alice", "age": "30"},
        {"name": "Bob", "age": "25"}
    ]
    
    # Perfect match
    extracted_perfect = [
        {"name": "Alice", "age": "30"},
        {"name": "Bob", "age": "25"}
    ]
    res = calculate_accuracy(extracted_perfect, golden)
    assert res["f1"] == 1.0
    
    # Partial match (missing age for Alice, extra field for Bob)
    extracted_partial = [
        {"name": "Alice"},
        {"name": "Bob", "age": "25", "city": "NY"}
    ]
    res2 = calculate_accuracy(extracted_partial, golden)
    assert res2["recall"] == 0.75 # 3/4 expected fields found
    assert res2["precision"] == 0.75 # 3/4 extracted fields match
    
    # Empty extraction
    res3 = calculate_accuracy([], golden)
    assert res3["recall"] == 0.0
