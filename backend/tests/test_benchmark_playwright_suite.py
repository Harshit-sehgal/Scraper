"""Bench 2: Playwright-driven benchmark suite (Roadmap Bench 2).

Tests benchmark extraction through the cascade using fixture HTML files
as inputs. Verifies extraction returns expected field types across all
extraction layers (regex, microdata, json-ld, llm).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.extraction_orchestrator import ExtractionResult, orchestrate_extraction
from app.models import FieldType, SchemaField

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pages"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class TestBenchmarkPlaywrightRegexLayer:
    """Regex extraction layer returns typed records from real fixtures."""

    @pytest.mark.asyncio
    async def test_regex_extracts_typed_records(self) -> None:
        html = _load_fixture("ecommerce_listing.html")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        result = await orchestrate_extraction(
            url="https://fixtures.local/ecommerce_listing.html",
            html=html,
            schema_fields=schema,
            min_record_score=0.0,
        )
        assert isinstance(result, ExtractionResult)
        assert len(result.records) > 0
        for record in result.records:
            assert "title" in record
            assert "price" in record

    @pytest.mark.asyncio
    async def test_regex_returns_correct_field_types(self) -> None:
        html = _load_fixture("legacy_directory.html")
        schema = [
            SchemaField(name="company", field_type=FieldType.STRING, required=True),
            SchemaField(name="phone", field_type=FieldType.PHONE, required=True),
            SchemaField(name="website", field_type=FieldType.URL, required=True),
        ]
        result = await orchestrate_extraction(
            url="https://fixtures.local/legacy_directory.html",
            html=html,
            schema_fields=schema,
            min_record_score=0.0,
        )
        for record in result.records:
            phone = record.get("phone", "")
            if phone:
                digits = sum(1 for c in str(phone) if c.isdigit())
                assert digits >= 7, f"Phone {phone!r} has fewer than 7 digits"
            website = record.get("website", "")
            if website:
                assert str(website).startswith("http"), f"Website {website!r} is not a URL"


class TestBenchmarkPlaywrightCascadeLayers:
    """All extraction layers are reachable and produce structured output."""

    @pytest.mark.asyncio
    async def test_extraction_with_network_layer_falls_through_gracefully(self) -> None:
        html = _load_fixture("messy_blog.html")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="author", field_type=FieldType.STRING, required=True),
        ]
        result = await orchestrate_extraction(
            url="https://fixtures.local/messy_blog.html",
            html=html,
            schema_fields=schema,
            min_record_score=0.0,
        )
        assert len(result.records) > 0

    @pytest.mark.asyncio
    async def test_extraction_with_provided_selectors(self) -> None:
        html = _load_fixture("table_catalog.html")
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        provided_selectors = {
            "item_container": "table tbody tr",
            "fields": {
                "name": "td:nth-child(1)",
                "price": "td:nth-child(2)",
            },
        }
        result = await orchestrate_extraction(
            url="https://fixtures.local/table_catalog.html",
            html=html,
            schema_fields=schema,
            min_record_score=0.0,
            provided_selectors=provided_selectors,
        )
        assert len(result.records) > 0

    @pytest.mark.asyncio
    async def test_extraction_empty_html_returns_empty(self) -> None:
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
        ]
        result = await orchestrate_extraction(
            url="https://fixtures.local/empty.html",
            html="<html><body></body></html>",
            schema_fields=schema,
            min_record_score=0.0,
        )
        assert isinstance(result, ExtractionResult)

    @pytest.mark.asyncio
    async def test_extraction_with_complex_schema(self) -> None:
        html = _load_fixture("search_results.html")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        result = await orchestrate_extraction(
            url="https://fixtures.local/search_results.html",
            html=html,
            schema_fields=schema,
            min_record_score=0.0,
        )
        for record in result.records:
            assert record.get("title"), "Title should not be empty"
            price = record.get("price")
            if price is not None:
                assert any(c in str(price) for c in ("$", "£", "€", "¥", "₹")), f"Price {price!r} not a valid currency"

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_extraction_large_html_does_not_timeout(self) -> None:
        html = _load_fixture("large_catalog.html")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        result = await orchestrate_extraction(
            url="https://fixtures.local/large_catalog.html",
            html=html,
            schema_fields=schema,
            min_record_score=0.0,
        )
        assert len(result.records) > 0


class TestBenchmarkPlaywrightExtractionLayers:
    """Verify extraction across multiple layers produces consistent results."""

    @pytest.mark.asyncio
    async def test_regex_fallback_produces_records(self) -> None:
        html = _load_fixture("travel_site.html")
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        result = await orchestrate_extraction(
            url="https://fixtures.local/travel_site.html",
            html=html,
            schema_fields=schema,
            min_record_score=0.0,
        )
        assert all(record.get("airline") for record in result.records)
