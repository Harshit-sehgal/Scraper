"""Golden-corpus metrics: field-level F1, diagnosis cards, trend tracking.

E3.2/E3.3 support for the live golden dataset:

- :func:`field_level_f1` — per-field precision/recall/F1 between the
  extracted records and the versioned expected output.
- :func:`write_diagnosis_card` — a failing site produces a diagnosis
  card (JSON + markdown) using the ``failure_classification`` module,
  never a silent red.
- :func:`record_trend` / :func:`read_trend` — append per-site F1 to a
  committed ``trend.jsonl`` so weekly CI can alert on a >5pt drop
  versus the previous run of the same site.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GOLDEN_DATASET_DIR = Path(__file__).resolve().parents[1] / "tests" / "golden_dataset"
TREND_PATH = GOLDEN_DATASET_DIR / "trend.jsonl"
DIAGNOSIS_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "golden_dataset" / "diagnosis"
DROP_ALERT_POINTS = 5.0
TREND_KEEP_PER_SITE = 10


def field_level_f1(extracted: list[dict], expected: list[dict], fields: list[str]) -> dict[str, dict[str, float]]:
    """Per-field precision/recall/F1 between extracted and expected records.

    A field counts as present when the record has a non-empty value for
    that field. Field scores are computed over the union of records on
    both sides.
    """
    result: dict[str, dict[str, float]] = {}
    for field in fields:
        extracted_set = {str(r.get(field, "")).strip() for r in extracted}
        expected_set = {str(r.get(field, "")).strip() for r in expected}
        true_positives = len(extracted_set & expected_set)
        false_positives = len(extracted_set - expected_set)
        false_negatives = len(expected_set - extracted_set)
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 0.0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) else 0.0
        result[field] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
        }
    return result


def write_diagnosis_card(
    site_id: str,
    url: str,
    f1_result: dict[str, Any],
    fields: list[str],
    extracted: list[dict],
    expected: list[dict],
    diagnosis_dir: Path = DIAGNOSIS_DIR,
) -> Path:
    """Write a diagnosis card for a failing site and return its path.

    The card records the failure category from ``app.failure_classification``
    plus field-level F1, so a human can read the exact failure taxonomy.
    """
    from app.failure_classification import classify_failure

    classification = classify_failure(extraction_result={"records": extracted, "schema_fields": fields})
    card: dict[str, Any] = {
        "site_id": site_id,
        "url": url,
        "generated_at": datetime.now(UTC).isoformat(),
        "record_f1": f1_result.get("f1"),
        "record_precision": f1_result.get("precision"),
        "record_recall": f1_result.get("recall"),
        "failure_category": classification.category.value,
        "failure_confidence": classification.confidence,
        "recovery_strategy": classification.recovery_strategy,
        "signals": classification.signals,
        "field_level_f1": field_level_f1(extracted, expected, fields),
        "extracted_count": len(extracted),
        "expected_count": len(expected),
    }
    diagnosis_dir.mkdir(parents=True, exist_ok=True)
    card_path = diagnosis_dir / f"{site_id}.json"
    card_path.write_text(json.dumps(card, indent=2) + "\n")
    return card_path


def record_trend(site_id: str, f1: float, path: Path = TREND_PATH) -> dict[str, Any]:
    """Append an F1 observation to the trend file and return trend info.

    Returns ``{"previous_f1": ..., "drop": ...}`` where ``previous_f1``
    is the most recent prior entry for the same site (None on first
    observation) and ``drop`` is ``previous_f1 - f1`` (0 when unknown).
    """
    entries = read_trend(path)
    previous = None
    for entry in reversed(entries):
        if entry.get("site_id") == site_id:
            previous = float(entry["f1"])
            break
    record = {
        "site_id": site_id,
        "f1": round(float(f1), 4),
        "observed_at": datetime.now(UTC).isoformat(),
    }
    entries.append(record)
    entries = _prune_trend(entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return {
        "previous_f1": previous,
        "drop": round(previous - float(f1), 4) if previous is not None else 0.0,
    }


def read_trend(path: Path = TREND_PATH) -> list[dict[str, Any]]:
    """Read trend entries (oldest first); tolerant of missing/corrupt files."""
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _prune_trend(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the last TREND_KEEP_PER_SITE entries per site."""
    by_site: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for entry in entries:
        site = str(entry.get("site_id", ""))
        if site not in by_site:
            by_site[site] = []
            order.append(site)
        by_site[site].append(entry)
    pruned: list[dict[str, Any]] = []
    for site in order:
        pruned.extend(by_site[site][-TREND_KEEP_PER_SITE:])
    return pruned
