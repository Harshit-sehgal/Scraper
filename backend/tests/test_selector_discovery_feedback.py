"""Tests for selector discovery analysis — failure feedback metadata.

Verifies that ``discover_selectors`` returns structured failure information
when discovery fails, so callers can adapt recovery strategy.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app import selector_discovery_analysis as sda_module
from app.selector_discovery_analysis import (
    _analyze_page_data_type,
    _build_css_for_element,
    build_selector_prompt,
    discover_selectors,
)


def _schema_field(name="title", field_type="text", description=""):
    f = MagicMock()
    f.name = name
    f.field_type = MagicMock(value=field_type)
    f.description = description
    return f


class TestEmptyHtmlReturnsFailureMetadata:
    """Empty or minimal HTML returns structured failure."""

    @pytest.mark.asyncio
    async def test_empty_html_returns_no_dom_elements(self):
        result = await discover_selectors("", [_schema_field()])
        assert result.get("failure_category") == "no_dom_elements"
        assert "failure_reason" in result

    @pytest.mark.asyncio
    async def test_too_short_html_returns_no_dom_elements(self):
        result = await discover_selectors("<p>hi</p>", [_schema_field()])
        assert result.get("failure_category") == "no_dom_elements"

    @pytest.mark.asyncio
    async def test_whitespace_only_html_returns_no_dom_elements(self):
        result = await discover_selectors("   \n  \t   ", [_schema_field()])
        assert result.get("failure_category") == "no_dom_elements"


class TestLLMErrorReturnsFailureMetadata:
    """When LLM raises an error and DOM fallback fails, failure_category is llm_error."""

    @pytest.mark.asyncio
    async def test_llm_exception_with_dom_failure(self):
        html = "<html><body><div>Hello World with enough text for selector discovery</div></body></html>"
        with (
            patch.object(sda_module, "_discover_selectors_from_dom", return_value=None),
            patch(
                "app.selector_discovery.clean_html_for_selectors",
                return_value="<div>Hello content for discovery</div>",
            ),
            patch(
                "app.selector_discovery.llm_json",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM timeout"),
            ),
        ):
            result = await discover_selectors(html, [_schema_field()])
        assert result.get("failure_category") == "llm_error"
        assert "LLM" in result.get("failure_reason", "")


class TestLLMEmptyResultReturnsMetadata:
    """When LLM returns result but no item_container, failure_category is llm_empty_result."""

    @pytest.mark.asyncio
    async def test_llm_returns_dict_without_container(self):
        html = "<html><body><div>Hello World with enough text for selector discovery</div></body></html>"
        with (
            patch.object(sda_module, "_discover_selectors_from_dom", return_value=None),
            patch(
                "app.selector_discovery.clean_html_for_selectors",
                return_value="<div>Hello content for discovery</div>",
            ),
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock, return_value={"fields": {"title": ".title"}}),
        ):
            result = await discover_selectors(html, [_schema_field()])
        assert result.get("failure_category") == "llm_empty_result"
        assert "item_container" in result.get("failure_reason", "")


class TestDOMFallbackFailure:
    """When LLM returns empty dict and DOM also fails."""

    @pytest.mark.asyncio
    async def test_both_fail_returns_dom_no_repeating_structure(self):
        html = "<html><body><div>Single element, no repeating structure</div></body></html>"
        with (
            patch.object(sda_module, "_discover_selectors_from_dom", return_value=None),
            patch("app.selector_discovery.clean_html_for_selectors", return_value="<div>Single element</div>"),
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock, return_value={}),
        ):
            result = await discover_selectors(html, [_schema_field()])
        assert result.get("failure_category") == "dom_no_repeating_structure"


class TestCleanedHTMLEmpty:
    """When clean_html_for_selectors returns empty or tiny output."""

    @pytest.mark.asyncio
    async def test_cleaned_html_empty(self):
        html = "<html><body><script>var x=1;</script></body></html>"
        with patch("app.selector_discovery.clean_html_for_selectors", return_value=""):
            result = await discover_selectors(html, [_schema_field()])
        assert result.get("failure_category") == "no_dom_elements"


class TestSuccessPathPassesThrough:
    """When LLM returns a valid container, result passes through without failure metadata."""

    @pytest.mark.asyncio
    async def test_llm_returns_container(self):
        html = "<html><body><div class='item'>Data</div></body></html>"
        llm_result = {"item_container": ".item", "fields": {"title": ".item .title"}}
        with (
            patch("app.selector_discovery.clean_html_for_selectors", return_value=html),
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock, return_value=llm_result),
        ):
            result = await discover_selectors(html, [_schema_field()])
        assert result.get("item_container") == ".item"
        assert "failure_category" not in result

    @pytest.mark.asyncio
    async def test_dom_fallback_succeeds(self):
        html = "<html><body><div class='item'>Data</div></body></html>"
        dom_result = {"item_container": ".item", "fields": {}, "_discovery_method": "dom_fallback"}
        with (
            patch("app.selector_discovery.clean_html_for_selectors", return_value=html),
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock, return_value={}),
            patch.object(sda_module, "_discover_selectors_from_dom", return_value=dom_result),
        ):
            result = await discover_selectors(html, [_schema_field()])
        assert result.get("item_container") == ".item"
        assert "failure_category" not in result


class TestBuildSelectorPrompt:
    """build_selector_prompt produces a well-formed prompt."""

    def test_includes_schema_fields(self):
        prompt = build_selector_prompt("<div>test</div>", [_schema_field("price", "currency")])
        assert "price" in prompt
        assert "currency" in prompt

    def test_includes_structure_type(self):
        analysis = {"structure_type": "table", "structure_confidence": 0.9, "patterns_detected": {}}
        prompt = build_selector_prompt("<div>test</div>", [], page_analysis=analysis)
        assert "TABLE" in prompt


class TestAnalyzePageDataType:
    """_analyze_page_data_type returns expected keys."""

    def test_returns_structure_keys(self):
        html = "<html><body><table><tr><td>data</td></tr></table></body></html>"
        result = _analyze_page_data_type(html, [])
        assert "structure_type" in result
        assert "structure_confidence" in result
        assert "patterns_detected" in result


class TestBuildCssForElement:
    """_build_css_for_element creates valid CSS selectors."""

    def test_element_with_id(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup('<div id="main">x</div>', "html.parser")
        el = soup.find("div")
        assert _build_css_for_element(el) == "#main"

    def test_element_with_class(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup('<div class="item">x</div>', "html.parser")
        el = soup.find("div")
        assert _build_css_for_element(el) == ".item"

    def test_element_with_no_id_or_class(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<div>x</div>", "html.parser")
        el = soup.find("div")
        assert _build_css_for_element(el) is None
