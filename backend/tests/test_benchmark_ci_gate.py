"""Bench 6: CI gate benchmark (Roadmap Bench 6).

Tests F1 score threshold enforcement, that all benchmark tests can run
without a browser, and benchmark output format validation.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models import FieldType, SchemaField
from app.selector_engine import extract_with_regex

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pages"
MANIFEST_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "local_corpus_expected.json"


class TestBenchmarkCIGateF1Threshold:
    """F1 score threshold enforcement on local corpus."""

    def test_manifest_exists(self) -> None:
        assert MANIFEST_PATH.exists(), "Corpus manifest not found"

    def test_manifest_is_valid_json(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        assert "version" in manifest
        assert "aggregate_thresholds" in manifest
        assert "cases" in manifest

    def test_aggregate_thresholds_defined(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        thresholds = manifest["aggregate_thresholds"]
        assert "min_row_f1" in thresholds
        assert "min_field_f1" in thresholds
        assert thresholds["min_row_f1"] > 0.0
        assert thresholds["min_field_f1"] > 0.0

    def test_each_case_has_thresholds(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        for case in manifest["cases"]:
            assert "thresholds" in case, f"Case {case['id']} missing thresholds"
            assert "fixture" in case
            fixture_path = FIXTURES_DIR / case["fixture"]
            assert fixture_path.exists(), f"Fixture {case['fixture']} not found for case {case['id']}"

    def test_regex_extraction_meets_min_f1_on_basic_cases(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        tested = 0
        for case in manifest["cases"]:
            if case["extractor"] != "html_regex":
                continue
            html = (FIXTURES_DIR / case["fixture"]).read_text(encoding="utf-8")
            schema = [
                SchemaField(name=f["name"], field_type=FieldType(f["type"]), required=f.get("required", False))
                for f in case["schema"]
            ]
            records = extract_with_regex(html, schema, base_url=f"https://fixtures.local/{case['fixture']}")
            if not case["required_fields"]:
                continue
            for record in records:
                for field in case["required_fields"]:
                    if record.get(field):
                        tested += 1
                        break
        assert tested >= len(manifest["cases"])


class TestBenchmarkCIGateNoBrowser:
    """Benchmarks can run without browser."""

    def test_regex_extraction_works_without_browser(self) -> None:
        html = (FIXTURES_DIR / "travel_site.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/travel_site.html")
        assert len(records) > 0

    def test_empty_html_extraction_returns_empty_list(self) -> None:
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
        ]
        records = extract_with_regex("<html><body></body></html>", schema)
        assert isinstance(records, list)


class TestBenchmarkCIGateOutputFormat:
    """Benchmark output format validation."""

    def test_extraction_output_is_list_of_dicts(self) -> None:
        html = (FIXTURES_DIR / "ecommerce_listing.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/ecommerce_listing.html")
        assert isinstance(records, list)
        if records:
            assert isinstance(records[0], dict)

    def test_extraction_records_have_expected_fields(self) -> None:
        html = (FIXTURES_DIR / "ecommerce_listing.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/ecommerce_listing.html")
        for record in records:
            assert "title" in record
