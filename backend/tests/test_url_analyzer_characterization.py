"""Characterization tests for analyze_url_for_fields.

These tests mock HTTP, LLM, and profiler dependencies to pin the current
orchestration behavior of the 564-LOC function before refactoring the
response-dict building and early-return paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _stale_url() -> str:
    return "https://www.example.com/search/results/session123token456"


def _landing_page_html() -> str:
    return """<html><body>
        <div class="hero-banner"><h1>Welcome</h1></div>
        <form action="/search" method="POST">
            <input type="text" name="from" id="from" />
            <input type="text" name="to" id="to" />
            <input type="date" name="departdate" id="departdate" />
            <button type="submit">Search</button>
        </form>
    </body></html>"""


def _results_page_html() -> str:
    return """<html><body>
        <div class="item"><h2>Item A</h2><span class="price">$29.99</span></div>
        <div class="item"><h2>Item B</h2><span class="price">$39.99</span></div>
        <div class="item"><h2>Item C</h2><span class="price">$49.99</span></div>
    </body></html>"""


def _mock_base_mocks(monkeypatch=None):
    """Return a dict of common mocks for all tests."""
    from app.page_profiler import StructureProfile, ValuePatterns

    mocks = {}
    mocks["fetch_page_content"] = MagicMock(
        return_value=(_results_page_html(), 200, "playwright_full", 0)
    )
    mocks["detect_anti_bot"] = MagicMock(return_value=0.1)
    mocks["detect_page_structure"] = MagicMock(
        return_value=StructureProfile(
            structure_type="cards",
            structure_confidence=0.85,
            headers=[],
            container_selector="div.item",
        )
    )
    mocks["detect_value_patterns"] = MagicMock(
        return_value=ValuePatterns(currencies=["$29.99"], dates=[])
    )
    mocks["llm_json"] = AsyncMock(
        return_value=[
            {"name": "title", "type": "string", "confidence": 0.9},
            {"name": "price", "type": "currency", "confidence": 0.8},
        ]
    )
    return mocks


class TestAnalyzeUrlForFieldsDirect:
    """Scenario: Direct URL — no redirect, search params, or session issues."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_all_expected_keys(self) -> None:
        """The response dict must contain all documented top-level keys."""
        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("app.scrape_telemetry.detect_anti_bot") as mock_anti_bot,
            patch("app.selector_discovery.detect_page_structure") as mock_structure,
            patch("app.page_profiler.detect_value_patterns") as mock_patterns,
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock) as mock_llm,
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            from app.page_profiler import StructureProfile, ValuePatterns
            from app.selector_discovery import analyze_url_for_fields

            url = "https://example.com/products"

            # Mock httpx redirect check — no redirect
            resp_no_redirect = MagicMock()
            resp_no_redirect.url = url
            resp_no_redirect.status_code = 200
            resp_no_redirect.is_redirect = False
            resp_no_redirect.headers = {}

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp_no_redirect)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            mock_fetch.return_value = (_results_page_html(), 200, "playwright_full", 0)
            mock_anti_bot.return_value = 0.1
            mock_structure.return_value = StructureProfile(
                structure_type="cards",
                structure_confidence=0.85,
                headers=[],
                container_selector="div.item",
            )
            mock_patterns.return_value = ValuePatterns(
                currencies=["$29.99", "$39.99"], dates=[]
            )
            mock_llm.return_value = [
                {"name": "title", "type": "string", "confidence": 0.9},
                {"name": "price", "type": "currency", "confidence": 0.8},
            ]

            result = await analyze_url_for_fields(url)

            # Top-level keys
            expected_keys = {
                "url", "redirect_info", "acquisition_lineage", "user_message",
                "session_detection", "canonical_url", "acquisition_mode",
                "acquisition_config", "content_quality", "empty_check",
                "search_form", "search_recovery", "page_structure",
                "structure_confidence", "estimated_record_count", "item_container",
                "fetch_method", "fetch_time_ms", "anti_bot_score",
                "browser_state_evidence", "suggested_fields",
            }
            assert expected_keys.issubset(result.keys()), f"Missing keys: {expected_keys - result.keys()}"

    @pytest.mark.asyncio
    async def test_suggested_fields_ordered_by_confidence(self) -> None:
        """Fields must be sorted by confidence descending."""
        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("app.scrape_telemetry.detect_anti_bot") as mock_anti_bot,
            patch("app.selector_discovery.detect_page_structure") as mock_structure,
            patch("app.page_profiler.detect_value_patterns") as mock_patterns,
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock) as mock_llm,
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            from app.page_profiler import StructureProfile, ValuePatterns
            from app.selector_discovery import analyze_url_for_fields

            url = "https://example.com/products"

            resp = MagicMock()
            resp.url = url
            resp.status_code = 200
            resp.is_redirect = False
            resp.headers = {}

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            mock_fetch.return_value = (_results_page_html(), 200, "playwright_full", 0)
            mock_anti_bot.return_value = 0.1
            mock_structure.return_value = StructureProfile(
                structure_type="table", structure_confidence=0.9,
                headers=[], container_selector="div.item",
            )
            mock_patterns.return_value = ValuePatterns()
            mock_llm.return_value = [
                {"name": "b", "type": "string", "confidence": 0.5},
                {"name": "a", "type": "string", "confidence": 0.9},
                {"name": "c", "type": "string", "confidence": 0.7},
            ]

            result = await analyze_url_for_fields(url)
            confidences = [f["confidence"] for f in result["suggested_fields"]]
            assert confidences == sorted(confidences, reverse=True), (
                f"Fields not sorted by confidence: {confidences}"
            )

    @pytest.mark.asyncio
    async def test_suggested_fields_truncated_to_max_fields(self) -> None:
        """The number of suggested fields must not exceed the config limit."""
        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("app.scrape_telemetry.detect_anti_bot") as mock_anti_bot,
            patch("app.selector_discovery.detect_page_structure") as mock_structure,
            patch("app.page_profiler.detect_value_patterns") as mock_patterns,
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock) as mock_llm,
            patch("httpx.AsyncClient") as mock_httpx,
            patch("app.config.settings.URL_ANALYZER_MAX_FIELDS", 20),
        ):
            from app.page_profiler import StructureProfile, ValuePatterns
            from app.selector_discovery import analyze_url_for_fields

            url = "https://example.com/products"

            resp = MagicMock()
            resp.url = url
            resp.status_code = 200
            resp.is_redirect = False
            resp.headers = {}

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            mock_fetch.return_value = (_results_page_html(), 200, "playwright_full", 0)
            mock_anti_bot.return_value = 0.1
            mock_structure.return_value = StructureProfile(
                structure_type="cards", structure_confidence=0.8,
                headers=[], container_selector="div.item",
            )
            mock_patterns.return_value = ValuePatterns()
            many_fields = [
                {"name": f"field_{i}", "type": "string", "confidence": 0.9}
                for i in range(50)
            ]
            mock_llm.return_value = many_fields

            result = await analyze_url_for_fields(url)
            assert len(result["suggested_fields"]) <= 20, (
                f"Got {len(result['suggested_fields'])} fields, expected ≤20"
            )


class TestAnalyzeUrlForFieldsFetchFailure:
    """Scenario: Fetch failure — should return error dict with minimal keys."""

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_error_dict(self) -> None:
        """When fetch_page_content raises, the response must be an error dict."""
        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            from app.selector_discovery import analyze_url_for_fields

            url = "https://example.com/products"

            resp = MagicMock()
            resp.url = url
            resp.status_code = 200
            resp.is_redirect = False
            resp.headers = {}

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            mock_fetch.side_effect = ValueError("Connection refused")

            result = await analyze_url_for_fields(url)

            assert "error" in result
            assert "Failed to fetch URL" in result["error"]
            assert result["suggested_fields"] == []
            assert result["page_structure"] == "unknown"
            assert result["structure_confidence"] == 0.0
            assert result["estimated_record_count"] == 0
            assert result["item_container"] is None

    @pytest.mark.asyncio
    async def test_fetch_failure_includes_acquisition_lineage(self) -> None:
        """Error path must still produce an acquisition lineage."""
        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            from app.selector_discovery import analyze_url_for_fields

            url = "https://example.com/products"

            resp = MagicMock()
            resp.url = url
            resp.status_code = 200
            resp.is_redirect = False
            resp.headers = {}

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            mock_fetch.side_effect = ValueError("Connection refused")

            result = await analyze_url_for_fields(url)
            assert "acquisition_lineage" in result
            assert result["acquisition_lineage"]["original_url"] == url
            assert result["acquisition_lineage"]["state"] == "direct"

    @pytest.mark.asyncio
    async def test_fetch_failure_has_user_message(self) -> None:
        """Error path must include a user-facing message."""
        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            from app.selector_discovery import analyze_url_for_fields

            url = "https://example.com/products"

            resp = MagicMock()
            resp.url = url
            resp.status_code = 200
            resp.is_redirect = False
            resp.headers = {}

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            mock_fetch.side_effect = ValueError("Connection refused")

            result = await analyze_url_for_fields(url)
            assert result["user_message"]
            assert "Failed to fetch" in result["user_message"]


class TestAnalyzeUrlForFieldsEmptyPage:
    """Scenario: Page fetched but appears empty (< 100 chars HTML)."""

    @pytest.mark.asyncio
    async def test_empty_page_returns_empty_dict(self) -> None:
        """Empty page (< 100 chars) should return empty response with error."""
        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            from app.selector_discovery import analyze_url_for_fields

            url = "https://example.com/empty"

            resp = MagicMock()
            resp.url = url
            resp.status_code = 200
            resp.is_redirect = False
            resp.headers = {}

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            mock_fetch.return_value = ("   ", 100, "playwright_full", 0)

            result = await analyze_url_for_fields(url)

            assert "error" in result
            assert "empty" in result["error"].lower()
            assert result["suggested_fields"] == []
            assert result["empty_check"]["is_empty"] is True
            assert result["empty_check"]["empty_type"] == "blank"


class TestAnalyzeUrlForFieldsWithMissingContainerValues:
    """Scenario: Container values < 3 — fallback to scanning visible text."""

    @pytest.mark.asyncio
    async def test_container_fallback_scans_visible_text(self) -> None:
        """When container yields < 3 values, fall back to full-page text scan."""
        from app.page_profiler import StructureProfile, ValuePatterns

        # HTML designed so the visible-text fallback generates ~20 tokens
        sparse_html = (
            "<html><body>"
            '<div class="sparse">A</div>'
            '<div class="sparse">B</div>'
            "Just a few visible words on the page"
            "</body></html>"
        )

        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("app.scrape_telemetry.detect_anti_bot") as mock_anti_bot,
            patch("app.selector_discovery.detect_page_structure") as mock_structure,
            patch("app.page_profiler.detect_value_patterns") as mock_patterns,
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock) as mock_llm,
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            from app.selector_discovery import analyze_url_for_fields

            url = "https://example.com/sparse"

            resp = MagicMock()
            resp.url = url
            resp.status_code = 200
            resp.is_redirect = False
            resp.headers = {}

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            mock_fetch.return_value = (sparse_html, 200, "playwright_full", 0)
            mock_anti_bot.return_value = 0.1
            mock_structure.return_value = StructureProfile(
                structure_type="cards",
                structure_confidence=0.5,
                headers=["A", "B"],
                container_selector="div.sparse",
            )
            mock_patterns.return_value = ValuePatterns()
            mock_llm.return_value = [
                {"name": "description", "type": "string", "confidence": 0.7},
            ]

            result = await analyze_url_for_fields(url)
            # Verify fallback doesn't crash and shape is correct
            assert isinstance(result["suggested_fields"], list)
            assert result["page_structure"] == "cards"


class TestAnalyzeUrlForFieldsLLMFallback:
    """Scenario: LLM returns no fields — fall back to value pattern detection."""

    @pytest.mark.asyncio
    async def test_empty_llm_result_falls_back_to_patterns(self) -> None:
        """When LLM returns no fields, pattern-based fallback should fill in."""
        from app.page_profiler import StructureProfile, ValuePatterns

        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("app.scrape_telemetry.detect_anti_bot") as mock_anti_bot,
            patch("app.selector_discovery.detect_page_structure") as mock_structure,
            patch("app.page_profiler.detect_value_patterns") as mock_patterns,
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock) as mock_llm,
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            from app.selector_discovery import analyze_url_for_fields

            url = "https://example.com/products"

            resp = MagicMock()
            resp.url = url
            resp.status_code = 200
            resp.is_redirect = False
            resp.headers = {}

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            mock_fetch.return_value = (_results_page_html(), 200, "playwright_full", 0)
            mock_anti_bot.return_value = 0.1
            mock_structure.return_value = StructureProfile(
                structure_type="cards",
                structure_confidence=0.85,
                headers=[],
                container_selector="div.item",
            )
            mock_patterns.return_value = ValuePatterns(
                currencies=["$29.99", "$39.99"],
                dates=["2026-01-01"],
            )
            # LLM returns null/empty
            mock_llm.return_value = None

            result = await analyze_url_for_fields(url)

            # Should get pattern-based fields instead
            assert len(result["suggested_fields"]) > 0, (
                "Should have pattern-based fields when LLM returns nothing"
            )
            types = {f["type"] for f in result["suggested_fields"]}
            assert "currency" in types


class TestAnalyzeUrlForFieldsAcquisitionLineage:
    """Verify acquisition lineage enrichement and telemetry."""

    @pytest.mark.asyncio
    async def test_acquisition_lineage_has_data_evidence_score(self) -> None:
        """Lineage must contain data_evidence_score."""
        from app.page_profiler import StructureProfile, ValuePatterns

        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("app.scrape_telemetry.detect_anti_bot") as mock_anti_bot,
            patch("app.selector_discovery.detect_page_structure") as mock_structure,
            patch("app.page_profiler.detect_value_patterns") as mock_patterns,
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock) as mock_llm,
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            from app.selector_discovery import analyze_url_for_fields

            url = "https://example.com/products"

            resp = MagicMock()
            resp.url = url
            resp.status_code = 200
            resp.is_redirect = False
            resp.headers = {}

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            mock_fetch.return_value = (_results_page_html(), 200, "playwright_full", 0)
            mock_anti_bot.return_value = 0.1
            mock_structure.return_value = StructureProfile(
                structure_type="cards",
                structure_confidence=0.85,
                headers=[],
                container_selector="div.item",
            )
            mock_patterns.return_value = ValuePatterns(
                currencies=["$29.99"], dates=[]
            )
            mock_llm.return_value = [
                {"name": "title", "type": "string", "confidence": 0.9},
            ]

            result = await analyze_url_for_fields(url)
            lineage = result["acquisition_lineage"]
            assert "data_evidence_score" in lineage, (
                "Lineage must have data_evidence_score"
            )
            assert isinstance(lineage["data_evidence_score"], (int, float))
            assert lineage["data_evidence_score"] >= 0
