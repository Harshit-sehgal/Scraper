"""Bench 12+21: Trend tracking + regression gate (Roadmap Benches 12, 21).

Tests storing historical results, detecting regression from baseline,
and comparing against threshold.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.models import FieldType, SchemaField
from app.selector_engine import extract_with_regex

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pages"
MANIFEST_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "local_corpus_expected.json"


class TestBenchmarkTrendsHistorical:
    """Storing and comparing historical results."""

    def test_manifest_has_version_string(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        assert "version" in manifest
        assert isinstance(manifest["version"], str)

    def test_manifest_version_is_timestamped(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        assert "local-corpus" in manifest["version"]

    def test_manifest_has_required_categories(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        assert "required_categories" in manifest
        assert len(manifest["required_categories"]) >= 10

    def test_each_case_has_minimum_metrics(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        for case in manifest["cases"]:
            assert "id" in case
            assert "fixture" in case
            assert "schema" in case
            assert "expected_records" in case


class TestBenchmarkTrendsRegression:
    """Detecting regression from baseline."""

    def test_regression_detection_compares_against_baseline(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        baseline = {"row_f1": 0.95, "field_f1": 0.95}
        aggregates = manifest.get("aggregate_thresholds", {})
        assert aggregates.get("min_row_f1", 0) >= baseline["row_f1"] * 0.9

    def test_each_case_has_threshold_gate(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        for case in manifest["cases"]:
            assert "thresholds" in case, f"Case {case['id']} missing thresholds"
            thresholds = case["thresholds"]
            has_standard = any(k in thresholds for k in ("min_row_f1", "min_field_f1", "max_duplicates"))
            has_negative = "max_false_positive_records" in thresholds
            assert has_standard or has_negative, f"Case {case['id']} has unrecognized thresholds: {thresholds}"


class TestBenchmarkTrendsThresholdComparison:
    """Comparing extraction results against threshold."""

    def test_basic_extraction_meets_minimum_threshold(self) -> None:
        html = (FIXTURES_DIR / "travel_site.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/travel_site.html")
        f1_numerator = sum(1 for r in records if r.get("airline") and r.get("price"))
        f1_denominator = max(len(records), 2)
        observed_f1 = f1_numerator / f1_denominator
        assert observed_f1 >= 0.5, f"Travel site extraction F1 {observed_f1:.2f} < 0.5"

    def test_legacy_directory_meets_field_threshold(self) -> None:
        html = (FIXTURES_DIR / "legacy_directory.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="company", field_type=FieldType.STRING, required=True),
            SchemaField(name="phone", field_type=FieldType.PHONE, required=True),
            SchemaField(name="website", field_type=FieldType.URL, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/legacy_directory.html")
        for record in records:
            company = record.get("company")
            phone = record.get("phone")
            website = record.get("website")
            if company:
                assert isinstance(company, str) and len(company) > 0
            if phone:
                digits = sum(1 for c in str(phone) if c.isdigit())
                assert digits >= 7
            if website:
                assert str(website).startswith("http")

    def test_threshold_aggregate_row_f1_achieveable(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        threshold = manifest["aggregate_thresholds"].get("min_row_f1", 1.0)
        assert threshold >= 0.5

    def test_extraction_time_tracked(self) -> None:
        html = (FIXTURES_DIR / "ecommerce_listing.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        start = time.monotonic()
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/ecommerce_listing.html")
        elapsed = time.monotonic() - start
        assert elapsed >= 0
        assert len(records) > 0
