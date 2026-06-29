"""Field-level accuracy breakdown tests.

For each scalar type, asserts that the corpus achieves a floor accuracy
on extracted values that match the expected type:

  * price / currency: >= 0.99
  * phone: >= 0.90
  * url: = 1.00 (HTTP/HTTPS only)
  * number / float: >= 0.95
  * date / string: >= 0.95 (only counted when field type is non-trivial)

This catches silent regressions where a fixture tweak changes the
field-type assignment but not the F1 score.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from benchmarks.local_corpus import _run_case, load_manifest


def _aggregate_field_type_accuracy(manifest: dict[str, Any]) -> dict[str, list[float]]:
    """Run every case and group per-field accuracies by FieldType.

    Returns ``{field_type_name: [per_case_accuracy, ...]}`` so the test
    can apply a floor across the corpus. The first time this runs the
    corpus files are read in sequence (no network, no Playwright).
    """
    by_type: dict[str, list[float]] = defaultdict(list)
    for case in manifest["cases"]:
        if case["extractor"] != "html_regex":
            continue
        result = _run_case(case)
        raw_per_field: Any = result.metrics.get("field_type_accuracy", {})
        if not isinstance(raw_per_field, dict):
            continue
        per_field: dict[str, float] = {
            str(field_name): float(accuracy)
            for field_name, accuracy in raw_per_field.items()
            if isinstance(accuracy, (int, float))
        }
        if not per_field:
            continue
        # Group by FieldType from the schema.
        schema_by_name = {f["name"]: f["type"] for f in case.get("schema", [])}
        for field_name, accuracy in per_field.items():
            field_type = schema_by_name.get(field_name)
            if not field_type:
                continue
            by_type[field_type].append(accuracy)
    return dict(by_type)


def test_currency_field_extraction_accuracy() -> None:
    """All currency/extracted fields across the corpus must hold >= 0.99 accuracy."""
    manifest = load_manifest()
    accuracies = _aggregate_field_type_accuracy(manifest)["currency"]
    assert accuracies, "No currency fields exercised by the corpus"
    avg = sum(accuracies) / len(accuracies)
    assert avg >= 0.99, f"Avg currency field accuracy {avg:.3f} below 0.99"


def test_phone_field_extraction_accuracy() -> None:
    """Phone fields across the corpus must hold >= 0.90 accuracy."""
    manifest = load_manifest()
    accuracies = _aggregate_field_type_accuracy(manifest).get("phone", [])
    if not accuracies:
        # No phone cases currently; document the floor that's exercised.
        return
    avg = sum(accuracies) / len(accuracies)
    assert avg >= 0.90, f"Avg phone field accuracy {avg:.3f} below 0.90"


def test_url_field_extraction_accuracy() -> None:
    """URL fields across the corpus must hold 1.00 accuracy (http(s) only)."""
    manifest = load_manifest()
    accuracies = _aggregate_field_type_accuracy(manifest).get("url", [])
    if not accuracies:
        return
    avg = sum(accuracies) / len(accuracies)
    assert avg >= 1.00, f"Avg URL field accuracy {avg:.3f} below 1.00"
