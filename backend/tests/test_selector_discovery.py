"""Unit Tests for Selector Discovery.

Tests _analyze_page_data_type, build_selector_prompt, and discover_selectors
with mocked HTML analysis and LLM calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models import SchemaField, FieldType
from app.selector_discovery import (
    _analyze_page_data_type,
    build_selector_prompt,
    discover_selectors,
)


class TestAnalyzePageDataType:
    """Tests for _analyze_page_data_type()."""

    def test_returns_structure_profile(self):
        html = "<html><body><table><tr><td>data</td></tr></table></body></html>"
        schema = [SchemaField(name="title", field_type=FieldType.STRING)]
        result = _analyze_page_data_type(html, schema)
        assert "structure_type" in result
        assert "structure_confidence" in result
        assert "headers" in result
        assert "patterns_detected" in result


class TestBuildSelectorPrompt:
    """Tests for build_selector_prompt()."""

    def test_basic_prompt_structure(self):
        snippet = "<div class='item'><h2>Title</h2></div>"
        schema = [SchemaField(name="title", field_type=FieldType.STRING, description="Product title")]
        prompt = build_selector_prompt(snippet, schema)
        assert "LLM" not in prompt  # Should not contain raw prompt instructions
        assert "title" in prompt
        assert "Product title" in prompt

    def test_with_page_analysis(self):
        snippet = "<div>data</div>"
        schema = [SchemaField(name="price", field_type=FieldType.FLOAT)]
        analysis = {
            "structure_type": "card",
            "structure_confidence": 0.85,
            "headers": ["Price", "Name"],
            "patterns_detected": {"currencies": True, "dates": False, "ratings": False, "codes": False, "phones": False, "emails": False},
        }
        prompt = build_selector_prompt(snippet, schema, page_analysis=analysis)
        assert "CARD" in prompt
        assert "price" in prompt
        assert "Price" in prompt  # headers
        assert "currencies" in prompt  # patterns

    def test_with_solidified_motifs(self):
        snippet = "<div>data</div>"
        schema = [SchemaField(name="name", field_type=FieldType.STRING)]
        motifs = [{"field": "name", "selector": "h2.title", "confidence": 0.9}]
        with patch("app.selector_discovery.MotifFeedbackEngine") as MockEngine:
            mock_instance = MockEngine.return_value
            mock_instance.build_motif_context.return_value = "\nMotif hint: use h2.title\n"
            prompt = build_selector_prompt(snippet, schema, solidified_motifs=motifs)
            assert "Motif hint" in prompt
            mock_instance.build_motif_context.assert_called_once_with(motifs, schema)

    def test_without_solidified_motifs(self):
        snippet = "<div>data</div>"
        schema = [SchemaField(name="x", field_type=FieldType.STRING)]
        prompt = build_selector_prompt(snippet, schema, solidified_motifs=None)
        assert "Motif" not in prompt
        assert "x" in prompt

    def test_with_empty_schema(self):
        snippet = "<div>data</div>"
        prompt = build_selector_prompt(snippet, [])
        assert "USER SCHEMA:" in prompt
        assert "JSON" in prompt

    def test_contains_extraction_rules(self):
        snippet = "<span>data</span>"
        schema = [SchemaField(name="rating", field_type=FieldType.FLOAT)]
        prompt = build_selector_prompt(snippet, schema)
        assert "EXTRACTION RULES" in prompt
        assert "Return ONLY JSON" in prompt
        assert "item_container" in prompt

    def test_contains_exclusions(self):
        snippet = "<nav>menu</nav>"
        schema = [SchemaField(name="title", field_type=FieldType.STRING)]
        prompt = build_selector_prompt(snippet, schema)
        assert "EXCLUSIONS" in prompt
        assert "Navigation" in prompt
        assert "Copyright" in prompt


class TestDiscoverSelectors:
    """Tests for discover_selectors()."""

    @pytest.mark.asyncio
    async def test_successful_extraction(self):
        mock_selectors = {"item_container": "div.item", "fields": {"name": "h2"}}
        with (
            patch("app.selector_discovery.clean_html_for_selectors", return_value="<div>cleaned</div>"),
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock, return_value=mock_selectors),
        ):
            result = await discover_selectors(
                "<html><div class='item'><h2>Name</h2></div></html>",
                [SchemaField(name="name", field_type=FieldType.STRING)],
            )
            assert result == mock_selectors

    @pytest.mark.asyncio
    async def test_llm_returns_non_dict_falls_back_to_empty(self):
        with (
            patch("app.selector_discovery.clean_html_for_selectors", return_value="<div>cleaned</div>"),
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock, return_value="not a dict"),
        ):
            result = await discover_selectors("<html>...</html>", [SchemaField(name="x", field_type=FieldType.STRING)])
            assert result == {}

    @pytest.mark.asyncio
    async def test_llm_raises_exception_returns_empty(self):
        with (
            patch("app.selector_discovery.clean_html_for_selectors", return_value="<div>cleaned</div>"),
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock, side_effect=ValueError("API error")),
        ):
            result = await discover_selectors("<html>...</html>", [SchemaField(name="x", field_type=FieldType.STRING)])
            assert result == {}

    @pytest.mark.asyncio
    async def test_with_solidified_motifs(self):
        mock_selectors = {"item_container": "div.card", "fields": {"title": "h3"}}
        motifs = [{"field": "title", "selector": "h3", "confidence": 0.8}]
        with (
            patch("app.selector_discovery.clean_html_for_selectors", return_value="<div>cleaned</div>"),
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock, return_value=mock_selectors),
        ):
            result = await discover_selectors(
                "<html><div class='card'><h3>Title</h3></div></html>",
                [SchemaField(name="title", field_type=FieldType.STRING)],
                solidified_motifs=motifs,
            )
            assert result == mock_selectors
