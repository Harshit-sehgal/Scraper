"""Unit Tests for Selector Discovery.

Tests _analyze_page_data_type, build_selector_prompt, and discover_selectors
with mocked HTML analysis and LLM calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models import SchemaField, FieldType
from app.page_profiler import ValuePatterns
from app.selector_discovery import (
    _analyze_page_data_type,
    _classify_value,
    _value_patterns_to_field_types,
    build_selector_prompt,
    build_url_analysis_prompt,
    discover_selectors,
)


class TestAnalyzePageDataType:
    """Tests for _analyze_page_data_type()."""

    def test_returns_structure_profile(self):
        html = "<html><body><table><tr><td>data</td></tr></table></body></html>"
        schema = [SchemaField(name="title", field_type=FieldType.STRING, description="", required=False)]
        result = _analyze_page_data_type(html, schema)
        assert "structure_type" in result
        assert "structure_confidence" in result
        assert "headers" in result
        assert "patterns_detected" in result


class TestBuildSelectorPrompt:
    """Tests for build_selector_prompt()."""

    def test_basic_prompt_structure(self):
        snippet = "<div class='item'><h2>Title</h2></div>"
        schema = [SchemaField(name="title", field_type=FieldType.STRING, description="Product title", required=False)]
        prompt = build_selector_prompt(snippet, schema)
        assert "LLM" not in prompt  # Should not contain raw prompt instructions
        assert "title" in prompt
        assert "Product title" in prompt

    def test_with_page_analysis(self):
        snippet = "<div>data</div>"
        schema = [SchemaField(name="price", field_type=FieldType.FLOAT, description="", required=False)]
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
        schema = [SchemaField(name="name", field_type=FieldType.STRING, description="", required=False)]
        motifs = [{"field": "name", "selector": "h2.title", "confidence": 0.9}]
        with patch("app.selector_discovery.MotifFeedbackEngine") as MockEngine:
            mock_instance = MockEngine.return_value
            mock_instance.build_motif_context.return_value = "\nMotif hint: use h2.title\n"
            prompt = build_selector_prompt(snippet, schema, solidified_motifs=motifs)
            assert "Motif hint" in prompt
            mock_instance.build_motif_context.assert_called_once_with(motifs, schema)

    def test_without_solidified_motifs(self):
        snippet = "<div>data</div>"
        schema = [SchemaField(name="x", field_type=FieldType.STRING, description="", required=False)]
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
        schema = [SchemaField(name="rating", field_type=FieldType.FLOAT, description="", required=False)]
        prompt = build_selector_prompt(snippet, schema)
        assert "EXTRACTION RULES" in prompt
        assert "Return ONLY JSON" in prompt
        assert "item_container" in prompt

    def test_contains_exclusions(self):
        snippet = "<nav>menu</nav>"
        schema = [SchemaField(name="title", field_type=FieldType.STRING, description="", required=False)]
        prompt = build_selector_prompt(snippet, schema)
        assert "EXCLUSIONS" in prompt
        assert "Navigation" in prompt
        assert "Copyright" in prompt


class TestClassifyValue:
    """Tests for _classify_value()."""

    def test_currency(self):
        assert _classify_value("£450") == "currency"
        assert _classify_value("$1,200") == "currency"

    def test_date(self):
        assert _classify_value("30-05-2026") == "date"
        assert _classify_value("2026-05-30") == "date"

    def test_time(self):
        assert _classify_value("10:00 PM") == "time"
        assert _classify_value("14:30") == "time"

    def test_code(self):
        assert _classify_value("LHR") == "code"
        assert _classify_value("BA123") == "string"  # Not 3-letter code
        assert _classify_value("SKU-12345") == "code"

    def test_email(self):
        assert _classify_value("test@example.com") == "email"

    def test_phone(self):
        assert _classify_value("+1-555-1234") == "phone"

    def test_empty_string(self):
        assert _classify_value("") == "string"

    def test_plain_text(self):
        assert _classify_value("British Airways") == "string"
        assert _classify_value("Economy") == "string"


class TestBuildUrlAnalysisPrompt:
    """Tests for build_url_analysis_prompt()."""

    def test_basic_structure(self):
        """Prompt should include value types, JSON format, and estimated_record_count."""
        values = ["British Airways", "£450", "30-05-2026", "10:00 PM", "LHR"]
        prompt = build_url_analysis_prompt(
            values,
            {"structure_type": "cards", "structure_confidence": 0.85},
        )
        assert "Return ONLY JSON" in prompt
        assert "estimated_record_count" in prompt
        assert "CARDS" in prompt
        assert "85%" in prompt
        assert "British Airways" in prompt
        assert "type: currency" in prompt
        assert "type: date" in prompt

    def test_no_raw_html(self):
        """Prompt should NOT contain raw HTML or markup tags."""
        values = ["test", "data"]
        prompt = build_url_analysis_prompt(
            values,
            {"structure_type": "table", "structure_confidence": 0.9},
        )
        assert "<" not in prompt  # No HTML tags
        assert ">" not in prompt

    def test_examples_include_domain_field_names(self):
        """Prompt examples should demonstrate mapping to descriptive field names."""
        values = ["British Airways", "BA123"]
        prompt = build_url_analysis_prompt(
            values,
            {"structure_type": "cards", "structure_confidence": 0.8},
        )
        assert "airline_name" in prompt
        assert "departure_airport" in prompt
        assert "flight_number" in prompt

    def test_values_passed_as_is(self):
        """All provided values should appear in the prompt."""
        values = ["value1", "value2", "value3"]
        prompt = build_url_analysis_prompt(
            values,
            {"structure_type": "list", "structure_confidence": 0.7},
        )
        for val in values:
            assert val in prompt

    def test_never_use_type_names_as_field_names(self):
        """Prompt should explicitly instruct LLM to avoid type names."""
        values = ["10:00 PM"]
        prompt = build_url_analysis_prompt(
            values,
            {"structure_type": "cards", "structure_confidence": 0.9},
        )
        assert "NEVER use type names" in prompt
        assert "airline_name" in prompt  # good example
        assert "departure_time" in prompt  # good example


class TestValuePatternsToFieldTypes:
    """Tests for _value_patterns_to_field_types()."""

    def test_currency_pattern(self):
        patterns = ValuePatterns()
        patterns.currencies = ["£"]
        result = _value_patterns_to_field_types(patterns)
        types = [r["type"] for r in result]
        assert "currency" in types

    def test_date_pattern(self):
        patterns = ValuePatterns()
        patterns.dates = ["2024-01-01"]
        result = _value_patterns_to_field_types(patterns)
        types = [r["type"] for r in result]
        assert "date" in types

    def test_code_3letter_or_airport(self):
        patterns = ValuePatterns()
        patterns.codes_3letter = ["LHR"]
        result = _value_patterns_to_field_types(patterns)
        types = [r["type"] for r in result]
        assert "code" in types

        # Also test airport_codes works
        patterns2 = ValuePatterns()
        patterns2.airport_codes = ["JFK"]
        result2 = _value_patterns_to_field_types(patterns2)
        types2 = [r["type"] for r in result2]
        assert "code" in types2

    def test_multiple_patterns(self):
        patterns = ValuePatterns()
        patterns.currencies = ["$"]
        patterns.dates = ["2024-06-15"]
        patterns.phones = ["+1-555-1234"]
        patterns.ratings = ["4.5"]
        result = _value_patterns_to_field_types(patterns)
        assert len(result) >= 4
        types = [r["type"] for r in result]
        assert "currency" in types
        assert "date" in types
        assert "phone" in types
        assert "rating" in types

    def test_empty_patterns_returns_empty(self):
        patterns = ValuePatterns()
        result = _value_patterns_to_field_types(patterns)
        assert result == []

    def test_no_hardcoded_field_names_in_output(self):
        """The function should return types, not guessed field names."""
        patterns = ValuePatterns()
        patterns.currencies = ["£"]
        patterns.dates = ["2024-01-01"]
        patterns.codes_3letter = ["LHR"]
        patterns.durations = ["5h 30m"]
        patterns.emails = ["test@example.com"]
        result = _value_patterns_to_field_types(patterns)
        for r in result:
            # Verify no domain-specific field names in the output
            assert "name" not in r  # Should not have guessed field names
            assert "type" in r       # Should only have type + confidence + example + description
        desc = r.get("description", "").lower()
        # Descriptions should not suggest specific field names like 'origin' or 'destination'
        assert "origin" not in desc
        assert "destination" not in desc


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
                [SchemaField(name="name", field_type=FieldType.STRING, description="", required=False)],
            )
            assert result == mock_selectors

    @pytest.mark.asyncio
    async def test_llm_returns_non_dict_falls_back_to_empty(self):
        with (
            patch("app.selector_discovery.clean_html_for_selectors", return_value="<div>cleaned</div>"),
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock, return_value="not a dict"),
        ):
            result = await discover_selectors("<html>...</html>",                [SchemaField(name="x", field_type=FieldType.STRING, description="", required=False)])
            assert result == {}

    @pytest.mark.asyncio
    async def test_llm_raises_exception_returns_empty(self):
        with (
            patch("app.selector_discovery.clean_html_for_selectors", return_value="<div>cleaned</div>"),
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock, side_effect=ValueError("API error")),
        ):
            result = await discover_selectors("<html>...</html>",                [SchemaField(name="x", field_type=FieldType.STRING, description="", required=False)])
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
                [SchemaField(name="title", field_type=FieldType.STRING, description="", required=False)],
                solidified_motifs=motifs,
            )
            assert result == mock_selectors
