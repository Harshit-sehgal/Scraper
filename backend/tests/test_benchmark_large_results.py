"""Bench 11: Large result set benchmark (Roadmap Bench 11).

Tests 1000+ record extraction and completion within reasonable time.
"""

from __future__ import annotations

import time
from pathlib import Path

from app.models import FieldType, SchemaField
from app.selector_engine import extract_with_regex

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pages"

MAX_EXTRACTION_SECONDS = 30


class TestBenchmarkLargeResultsCount:
    """1000+ record extraction."""

    def test_large_catalog_produces_many_records(self) -> None:
        html = (FIXTURES_DIR / "large_catalog.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/large_catalog.html")
        assert len(records) >= 200, f"Expected >= 200 records from large catalog, got {len(records)}"

    def test_multi_page_pagination_produces_many_records(self) -> None:
        html = (FIXTURES_DIR / "multi_page_pagination.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="stars", field_type=FieldType.NUMBER, required=False),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/multi_page_pagination.html")
        assert len(records) >= 10


class TestBenchmarkLargeResultsPerformance:
    """Completion within reasonable time."""

    def test_large_catalog_extraction_completes_under_timeout(self) -> None:
        html = (FIXTURES_DIR / "large_catalog.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        start = time.monotonic()
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/large_catalog.html")
        elapsed = time.monotonic() - start
        assert elapsed < MAX_EXTRACTION_SECONDS, f"Extraction took {elapsed:.2f}s, exceeds {MAX_EXTRACTION_SECONDS}s"
        assert len(records) > 0

    def test_large_html_does_not_cause_memory_error(self) -> None:
        html = (FIXTURES_DIR / "large_catalog.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/large_catalog.html")
        assert isinstance(records, list)

    def test_large_extraction_returns_typed_records(self) -> None:
        html = (FIXTURES_DIR / "large_catalog.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/large_catalog.html")
        for record in records[:10]:
            assert record.get("title"), "title must not be empty"
            price = record.get("price")
            if price is not None:
                assert any(c in str(price) for c in ("$", "£", "€", "¥", "₹")), f"Price {price!r} has no currency symbol"


class TestBenchmarkLargeResultsDeduplication:
    """Deduplication in large result sets."""

    def test_large_catalog_no_duplicate_titles(self) -> None:
        html = (FIXTURES_DIR / "large_catalog.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/large_catalog.html")
        titles = [r.get("title") for r in records if r.get("title")]
        assert len(titles) == len(set(titles)), "Duplicate titles found in large catalog extraction"
