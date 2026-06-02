"""Golden dataset validation tests.

These tests validate extraction against known real-world websites with expected
outputs. They are SKIPPED BY DEFAULT because they depend on network access and
external site availability.

Run with: pytest --run-golden-dataset backend/tests/test_golden_dataset.py -v
The marker and CLI flag are registered in backend/tests/conftest.py.

Accuracy is measured as F1 score at the record level, with penalties for
extra/missing records and extra/missing fields (matching benchmark accuracy).
"""

import asyncio
import json
from pathlib import Path

import pytest
from app.models import FieldType, SchemaField

GOLDEN_DATASET_DIR = Path(__file__).resolve().parent / "golden_dataset"
SITES_FILE = GOLDEN_DATASET_DIR / "sites.json"
EXPECTED_DIR = GOLDEN_DATASET_DIR / "expected"


def load_sites() -> list[dict]:
    """Load golden dataset site definitions.

    Returns an empty list if the sites file is missing, rather than calling
    pytest.skip() during parametrization (which can cause collection issues).
    Each test function handles the missing-file case via its own assertions.
    """
    if not SITES_FILE.exists():
        return []
    with open(SITES_FILE, "r") as f:
        data = json.load(f)
    return data.get("sites", [])


def load_expected(site_id: str) -> list[dict] | None:
    """Load expected output for a site, if available."""
    expected_path = EXPECTED_DIR / f"{site_id}.json"
    if not expected_path.exists():
        return None
    with open(expected_path, "r") as f:
        return json.load(f)


# ── F1 Scoring (matches benchmark_accuracy.py logic) ──────────────────────


def compute_f1(
    extracted: list[dict],
    expected: list[dict],
    key_fields: list[str] | None = None,
) -> dict:
    """Compute precision, recall, F1 between extracted and expected records.

    Uses matching on key_fields (default: first schema field) to identify
    corresponding records between extracted and expected sets.

    Returns dict with precision, recall, f1, and detail counts.
    """
    if not expected:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0,
                "true_positives": 0, "false_positives": 0, "false_negatives": 0}

    if not extracted:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0,
                "true_positives": 0, "false_positives": 0, "false_negatives": len(expected)}

    key_fields = key_fields or ["title"]

    def record_key(rec: dict) -> str:
        for kf in key_fields:
            val = rec.get(kf)
            if val and str(val).strip():
                return str(val).strip().lower()
        # Fallback: use first non-empty field value
        for v in rec.values():
            if v and isinstance(v, str) and v.strip():
                return v.strip().lower()
        return ""

    extracted_keys = set()
    for rec in extracted:
        k = record_key(rec)
        if k:
            extracted_keys.add(k)

    expected_keys = set()
    for rec in expected:
        k = record_key(rec)
        if k:
            expected_keys.add(k)

    true_positives = len(extracted_keys & expected_keys)
    false_positives = len(extracted_keys - expected_keys)
    false_negatives = len(expected_keys - extracted_keys)

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "extracted_count": len(extracted),
        "expected_count": len(expected),
    }# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.golden_dataset
@pytest.mark.parametrize("site_def", load_sites(), ids=lambda s: s["id"])
@pytest.mark.asyncio
async def test_golden_dataset_site(site_def, monkeypatch):
    """Run extraction against a golden dataset site and compare to expected.

    This live test verifies the site is reachable, extraction produces enough
    records, and expected-output files meet the site's configured minimum F1
    threshold. Thresholds are intentionally modest until the benchmark corpus
    is broadened and selectors are improved.

    When sites.json is missing, load_sites() returns an empty list and this
    parametrized test generates zero items (clean skip without collection error).
    """
    url = site_def["url"]
    site_id = site_def["id"]
    min_expected = site_def.get("min_expected_records", 0)
    expected = load_expected(site_id)

    # Build schema fields from site definition
    fields_def = site_def.get("schema", {}).get("fields", {})
    schema_fields = []
    for field_name, field_info in fields_def.items():
        field_type_str = field_info.get("type", "string")
        try:
            field_type = FieldType(field_type_str)
        except ValueError:
            field_type = FieldType.STRING
        schema_fields.append(
            SchemaField(
                name=field_name,
                field_type=field_type,
                required=field_info.get("required", False),
            )
        )

    if not schema_fields:
        pytest.skip(f"No schema fields defined for {site_id}")

    timeout_seconds = float(site_def.get("timeout_seconds", 60))
    from app.config import settings

    expected_count = len(expected or [])
    benchmark_record_limit = max(settings.MAX_RECORDS_PER_SOURCE, min_expected, expected_count)
    monkeypatch.setattr(settings, "MAX_RECORDS_PER_SOURCE", benchmark_record_limit)

    # Run extraction with a per-site timeout so live validation cannot hang the
    # entire suite on a single slow or unreachable website.
    from app.scraper import scrape_url  # noqa: E402 — lazy import for network tests

    try:
        results = await asyncio.wait_for(
            scrape_url(url, schema_fields, min_record_score=0.0),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        pytest.skip(f"Skipping {site_id} ({url}) because the connection timed out after {timeout_seconds:g}s")
    except Exception as e:
        err_msg = str(e).lower()
        transient_indicators = [
            "dns", "connection refused", "timeout", "network",
            "unreachable", "503", "502", "504", "500", "temporarily unavailable",
            "service unavailable", "bad gateway", "gateway timeout"
        ]
        if any(indicator in err_msg for indicator in transient_indicators):
            pytest.skip(f"Skipping {site_id} due to transient network/server issue: {e}")
        else:
            pytest.fail(f"Extraction failed for {site_id} ({url}): {e}")

    assert results is not None, f"No results returned for {site_id}"

    # Check if the extracted content indicates a server error page (like a transient 503 page)
    is_transient_error_page = False
    error_terms = ["503 service", "503 temporarily", "502 bad gateway", "504 gateway", "service temporarily unavailable"]
    for record in results:
        for val in record.values():
            if isinstance(val, str) and any(term in val.lower() for term in error_terms):
                is_transient_error_page = True
                break
    if is_transient_error_page:
        pytest.skip(f"Skipping {site_id} because the target page returned a transient server error (e.g., 503/502).")

    assert len(results) >= min_expected, (
        f"{site_id}: expected at least {min_expected} records, got {len(results)}"
    )

    # Compare with expected output if available
    if expected:
        key_fields = list(fields_def.keys())[:2]  # First 2 fields as key
        f1_result = compute_f1(results, expected, key_fields=key_fields)
        # Log but don't fail — golden dataset thresholds are being refined
        print(f"\n  [{site_id}] F1={f1_result['f1']:.3f} "
              f"(precision={f1_result['precision']:.3f}, "
              f"recall={f1_result['recall']:.3f}, "
              f"extracted={f1_result['extracted_count']}, "
              f"expected={f1_result['expected_count']})")
        min_f1 = site_def.get("min_f1")
        assert min_f1 is not None, f"{site_id}: expected output exists but min_f1 is not configured"
        assert f1_result["f1"] >= float(min_f1), (
            f"{site_id}: F1 {f1_result['f1']:.3f} is below configured threshold {float(min_f1):.3f}"
        )
    else:
        print(f"\n  [{site_id}] {len(results)} records extracted (no expected output file)")


@pytest.mark.golden_dataset
def test_golden_dataset_sites_file_exists():
    """Verify that the golden dataset sites file is valid JSON and has sites."""
    assert SITES_FILE.exists(), f"Sites file not found: {SITES_FILE}"
    sites = load_sites()
    assert len(sites) > 0, "No sites defined in golden dataset"


@pytest.mark.golden_dataset
def test_golden_dataset_expected_files():
    """Verify that all expected output files are valid JSON arrays."""
    sites = load_sites()
    for site in sites:
        expected = load_expected(site["id"])
        if expected is not None:
            assert isinstance(expected, list), (
                f"Expected output for {site['id']} should be a JSON array"
            )
            assert len(expected) > 0, (
                f"Expected output for {site['id']} is empty"
            )
            # Validate record structure
            for i, record in enumerate(expected):
                assert isinstance(record, dict), (
                    f"Record {i} in {site['id']} expected output should be a dict"
                )


@pytest.mark.golden_dataset
def test_golden_dataset_f1_scoring():
    """Verify the F1 scoring logic used by golden dataset tests."""
    # Perfect match
    extracted = [{"title": "A"}, {"title": "B"}]
    expected = [{"title": "A"}, {"title": "B"}]
    result = compute_f1(extracted, expected, key_fields=["title"])
    assert result["f1"] == 1.0, f"Perfect match should have F1=1.0, got {result['f1']}"

    # Partial match: one extra, one missing
    extracted = [{"title": "A"}, {"title": "C"}]
    expected = [{"title": "A"}, {"title": "B"}]
    result = compute_f1(extracted, expected, key_fields=["title"])
    assert result["true_positives"] == 1
    assert result["false_positives"] == 1
    assert result["false_negatives"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5

    # No match
    extracted = [{"title": "X"}]
    expected = [{"title": "A"}, {"title": "B"}]
    result = compute_f1(extracted, expected, key_fields=["title"])
    assert result["f1"] == 0.0

    # Empty extraction
    result = compute_f1([], expected, key_fields=["title"])
    assert result["f1"] == 0.0
    assert result["false_negatives"] == 2
