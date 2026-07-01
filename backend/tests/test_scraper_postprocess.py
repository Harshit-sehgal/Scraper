"""Tests for scraper_postprocess - post-extraction processing pipeline."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from app.models import SchemaField


@pytest.fixture(autouse=True)
def _mock_dependencies() -> Iterator[dict[str, MagicMock]]:
    """Mock all heavyweight external dependencies to avoid real IO."""
    deps: dict[str, MagicMock] = {}
    with (
        patch("app.scraper_postprocess._boost_contacts_with_page_html", return_value=[]),
        patch("app.scraper_postprocess.process_raw_records", side_effect=lambda r, *a, **kw: r),
        patch("app.llm_bridge.get_llm_call_count", return_value=0),
        patch("app.scrape_telemetry.get_scrape_telemetry"),
        patch("app.scraper_adapt._run_crawl_frontier_link_discovery"),
        patch("app.browser_network_capture.clear"),
    ):
        yield deps


@pytest.fixture
def schema() -> list[SchemaField]:
    return [
        SchemaField(name="title", field_type="string"),
        SchemaField(name="price", field_type="string"),
    ]


@pytest.fixture
def mock_ext_result() -> MagicMock:
    result = MagicMock()
    result.method = "ai_discovery"
    result.selector_success = True
    result.selectors = {"fields": {"title": {"selector": "h1"}}}
    return result


async def _run_minimal(
    url: str, html: str, schema: list[SchemaField], results: list[dict], ext_result: MagicMock
) -> tuple[list[dict], list[str]]:
    from app.extraction_provenance import ProvenanceBuilder
    from app.scraper_postprocess import run_post_extraction_processing

    builder = ProvenanceBuilder(url=url)
    return await run_post_extraction_processing(
        url=url,
        html=html,
        schema_fields=schema,
        min_record_score=0.0,
        results=results,
        ext_result=ext_result,
        fetch_method="playwright_full",
        fetch_ms=100.0,
        provenance_builder=builder,
        classification=None,
        domain="example.com",
        new_motifs=0,
        solidified_motifs_count=0,
        anti_bot_score=0.0,
        js_render_delay=0.0,
        token_density=0.0,
        retry_count=0,
    )


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_variant_expansion_hook(schema: list[SchemaField], mock_ext_result: MagicMock) -> None:
    """Variant extraction expands product records with select/option variants."""
    html = """<html><body><h1>T-Shirt</h1>
    <select class="size-select"><option>S</option><option selected>M</option><option>L</option></select>
    <span class="price">$29.99</span>
    </body></html>"""
    results = [{"title": "T-Shirt", "price": "29.99"}]

    processed, warnings = await _run_minimal(
        url="https://example.com/product",
        html=html,
        schema=schema,
        results=results,
        ext_result=mock_ext_result,
    )

    assert len(processed) == 3
    option_values = {r.get("option") for r in processed}
    assert option_values == {"S", "M", "L"}
    assert warnings == []


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_no_variant_expansion_without_select(schema: list[SchemaField], mock_ext_result: MagicMock) -> None:
    """Standard pages without variant selectors are unchanged."""
    html = "<html><body><h1>Plain Product</h1><p>$19.99</p></body></html>"
    results = [{"title": "Plain Product", "price": "19.99"}]

    processed, warnings = await _run_minimal(
        url="https://example.com/plain",
        html=html,
        schema=schema,
        results=results,
        ext_result=mock_ext_result,
    )

    assert len(processed) == 1
    assert processed[0]["title"] == "Plain Product"
    assert "option" not in processed[0]
