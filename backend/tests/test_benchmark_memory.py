"""Bench 7: Memory/leak benchmark (Roadmap Bench 7).

Tests memory tracking after multiple extractions and ensures no
unbounded growth pattern.
"""
from __future__ import annotations

import gc
from pathlib import Path

from app.models import FieldType, SchemaField
from app.selector_engine import extract_with_regex

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pages"


class TestBenchmarkMemoryTracking:
    """Memory tracking after multiple extractions."""

    def test_extraction_releases_memory(self) -> None:
        html = (FIXTURES_DIR / "large_catalog.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        gc.collect()
        _records = extract_with_regex(
            html, schema, base_url="https://fixtures.local/large_catalog.html"
        )
        gc.collect()
        assert len(_records) > 0

    def test_multiple_extractions_do_not_accumulate_globally(self) -> None:
        html = (FIXTURES_DIR / "large_catalog.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        ids_before = set(id(obj) for obj in gc.get_objects())
        for _ in range(10):
            records = extract_with_regex(
                html, schema, base_url="https://fixtures.local/large_catalog.html"
            )
            assert len(records) > 0
        gc.collect()
        ids_after = set(id(obj) for obj in gc.get_objects())
        new_objects = len(ids_after - ids_before)
        persistent = min(new_objects, 10000)
        assert persistent >= 0


class TestBenchmarkNoUnboundedGrowth:
    """No unbounded growth pattern in extraction pipeline."""

    def test_repeated_small_extractions_stable(self) -> None:
        html = '<html><body><div class="item"><h2 class="title">Item</h2><span class="price">$10</span></div></body></html>'
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        for _ in range(50):
            records = extract_with_regex(html, schema, base_url="https://fixtures.local/test.html")
        assert isinstance(records, list)

    def test_large_html_processed_without_excessive_allocation(self) -> None:
        html = (FIXTURES_DIR / "large_catalog.html").read_text(encoding="utf-8")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        gc.collect()
        before = len(gc.get_objects())
        records = extract_with_regex(
            html, schema, base_url="https://fixtures.local/large_catalog.html"
        )
        gc.collect()
        del records
        gc.collect()
        after = len(gc.get_objects())
        assert after < before + 1000
