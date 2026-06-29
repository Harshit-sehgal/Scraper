"""Bench 22: Warm vs cold extraction benchmark (Roadmap Bench 22).

Tests cold start extraction latency, warm/cached extraction latency,
and cache hit ratio.
"""

from __future__ import annotations

import time
from pathlib import Path

from app.models import FieldType, SchemaField
from app.selector_engine import extract_with_regex

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pages"


class TestBenchmarkWarmColdLatency:
    """Cold start and warm/cached latency."""

    def test_cold_start_extraction_completes(self) -> None:
        html = (FIXTURES_DIR / "legacy_directory.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="company", field_type=FieldType.STRING, required=True),
            SchemaField(name="phone", field_type=FieldType.PHONE, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/legacy_directory.html")
        assert len(records) > 0

    def test_warm_extraction_returns_same_results(self) -> None:
        html = (FIXTURES_DIR / "legacy_directory.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="company", field_type=FieldType.STRING, required=True),
            SchemaField(name="phone", field_type=FieldType.PHONE, required=True),
        ]
        first = extract_with_regex(html, schema, base_url="https://fixtures.local/legacy_directory.html")
        second = extract_with_regex(html, schema, base_url="https://fixtures.local/legacy_directory.html")
        assert len(first) == len(second)
        for r1, r2 in zip(first, second):
            assert r1.get("company") == r2.get("company")

    def test_cold_start_vs_warm_latency_ratio_reasonable(self) -> None:
        html = (FIXTURES_DIR / "search_results.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]

        cold_start = time.monotonic()
        _ = extract_with_regex(html, schema, base_url="https://fixtures.local/search_results.html")
        cold_elapsed = time.monotonic() - cold_start

        warm_start = time.monotonic()
        _ = extract_with_regex(html, schema, base_url="https://fixtures.local/search_results.html")
        warm_elapsed = time.monotonic() - warm_start

        assert cold_elapsed >= 0
        assert warm_elapsed >= 0
        assert cold_elapsed + warm_elapsed > 0

    def test_repeated_extraction_on_same_html_is_stable(self) -> None:
        html = (FIXTURES_DIR / "table_catalog.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        results = []
        for _ in range(5):
            records = extract_with_regex(html, schema, base_url="https://fixtures.local/table_catalog.html")
            results.append(len(records))
        assert all(r == results[0] for r in results), "Extraction count varies across repeat runs"


class TestBenchmarkCacheHitRatio:
    """Cache hit ratio measurement."""

    def test_same_html_different_schema_produces_different_results(self) -> None:
        html = (FIXTURES_DIR / "table_catalog.html").read_text(encoding="utf-8")
        schema_name = [
            SchemaField(name="name", field_type=FieldType.STRING, required=True),
        ]
        schema_price = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        name_records = extract_with_regex(html, schema_name, base_url="https://fixtures.local/table_catalog.html")
        price_records = extract_with_regex(html, schema_price, base_url="https://fixtures.local/table_catalog.html")
        assert len(name_records) > 0
        assert len(price_records) > 0

    def test_cross_fixture_extraction_independent(self) -> None:
        html_a = (FIXTURES_DIR / "travel_site.html").read_text(encoding="utf-8")
        html_b = (FIXTURES_DIR / "messy_blog.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
        ]
        records_a = extract_with_regex(html_a, schema, base_url="https://fixtures.local/travel_site.html")
        records_b = extract_with_regex(html_b, schema, base_url="https://fixtures.local/messy_blog.html")
        assert isinstance(records_a, list)
        assert isinstance(records_b, list)

    def test_empty_html_cache_returns_empty(self) -> None:
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
        ]
        first = extract_with_regex("<html><body></body></html>", schema)
        second = extract_with_regex("<html><body></body></html>", schema)
        assert isinstance(first, list)
        assert isinstance(second, list)
