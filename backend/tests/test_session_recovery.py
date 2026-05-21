"""Regression tests for session-aware URL acquisition and recovery.

These tests verify that when a session-bound URL expires and redirects to
a homepage/landing page, the system:
1. Detects the redirect as session_expired
2. Detects the search form on the landing page
3. Maps search params to form fields
4. Submits the form to recover a fresh session
5. Reports correct metadata (redirect_info says recovery succeeded,
   NOT that the session is still expired)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.selector_discovery import (
    _detect_redirect,
    _detect_search_form,
    _map_search_params_to_fields,
)


# ── HTML fixtures ──────────────────────────────────────────────────────

LANDING_PAGE_WITH_SEARCH_FORM = """
<html><body>
<div class="hero-banner"><h1>Find Cheap Flights</h1></div>
<form action="/search" method="POST">
    <input type="text" name="from" id="from" placeholder="Departure city or airport" />
    <input type="text" name="to" id="to" placeholder="Arrival city or airport" />
    <input type="date" name="departdate" id="departdate" placeholder="Departure date" />
    <input type="date" name="returndate" id="returndate" placeholder="Return date" />
    <select name="cabinclass"><option>Economy</option><option>Business</option></select>
    <button type="submit">Search Flights</button>
</form>
</body></html>
"""

FRESH_RESULTS_PAGE = """
<html><body>
<div class="flight-result">
    <span class="origin">New York (JFK)</span>
    <span class="destination">London (LHR)</span>
    <span class="price">$450</span>
    <span class="date">2026-06-15</span>
</div>
<div class="flight-result">
    <span class="origin">New York (JFK)</span>
    <span class="destination">London (LHR)</span>
    <span class="price">$520</span>
    <span class="date">2026-06-16</span>
</div>
<div class="flight-result">
    <span class="origin">New York (JFK)</span>
    <span class="destination">London (LHR)</span>
    <span class="price">$380</span>
    <span class="date">2026-06-17</span>
</div>
</body></html>
"""


class TestSessionExpiredRedirectDetection:
    """Verify that session-expired redirects are correctly classified."""

    def test_deep_path_to_homepage_is_session_expired(self):
        """A deep URL with session token redirecting to homepage = session expired."""
        result = _detect_redirect(
            "https://www.example.com/search/results/abc123session456",
            "https://www.example.com/",
        )
        assert result["redirected"] is True
        assert result["redirect_type"] == "session_expired"
        assert "expired" in result["message"].lower()

    def test_deep_path_to_shallow_path_is_session_expired(self):
        """A deep search URL redirecting to a shallow path = session expired."""
        result = _detect_redirect(
            "https://example.com/flights/search/abc123def",
            "https://example.com/flights",
        )
        assert result["redirected"] is True
        assert result["redirect_type"] == "session_expired"

    def test_stable_url_no_redirect(self):
        """A URL that doesn't redirect should report no redirect."""
        result = _detect_redirect(
            "https://example.com/flights/LAX-LHR",
            "https://example.com/flights/LAX-LHR",
        )
        assert result["redirected"] is False
        assert result["redirect_type"] == "none"


class TestSearchFormDetection:
    """Verify that search forms are detected on landing pages."""

    def test_detects_flight_search_form(self):
        form = _detect_search_form(LANDING_PAGE_WITH_SEARCH_FORM)
        assert form["detected"] is True
        assert form["action"] == "/search"
        assert form["method"] == "POST"
        assert len(form["search_fields"]) >= 3  # from, to, departdate at minimum

    def test_no_form_on_empty_page(self):
        html = "<html><body><p>No form here</p></body></html>"
        form = _detect_search_form(html)
        assert form["detected"] is False

    def test_form_fields_have_names(self):
        form = _detect_search_form(LANDING_PAGE_WITH_SEARCH_FORM)
        field_names = [f["name"] for f in form["fields"]]
        assert "from" in field_names
        assert "to" in field_names


class TestSearchParamMapping:
    """Verify that user-provided search params map to form fields."""

    def test_maps_origin_destination(self):
        form = _detect_search_form(LANDING_PAGE_WITH_SEARCH_FORM)
        mapped = _map_search_params_to_fields(
            {"origin": "NYC", "destination": "LHR"},
            form["fields"],
        )
        # "origin" should map to the "from" field (via variant matching)
        assert "from" in mapped
        assert mapped["from"] == "NYC"
        # "destination" should map to the "to" field
        assert "to" in mapped
        assert mapped["to"] == "LHR"

    def test_maps_departure_date(self):
        form = _detect_search_form(LANDING_PAGE_WITH_SEARCH_FORM)
        mapped = _map_search_params_to_fields(
            {"departure_date": "2026-06-15"},
            form["fields"],
        )
        # "departure_date" should map to "departdate" field
        assert "departdate" in mapped
        assert mapped["departdate"] == "2026-06-15"

    def test_empty_params_returns_empty(self):
        form = _detect_search_form(LANDING_PAGE_WITH_SEARCH_FORM)
        mapped = _map_search_params_to_fields({}, form["fields"])
        assert mapped == {}


class TestSessionRecoveryMetadata:
    """Regression tests for the session-recovery metadata bug.

    The bug: after successful search-form recovery, redirect_info still
    reported session_expired instead of showing recovery succeeded.

    After the fix, redirect_info should reflect that recovery worked.
    """

    @pytest.mark.asyncio
    async def test_recovery_updates_redirect_info(self):
        """After successful form recovery, redirect_info must say recovery
        succeeded, NOT that the session is still expired.

        This is the core regression test for the metadata bug.
        """
        stale_url = "https://www.example.com/search/results/abc123session456"
        fresh_url = "https://www.example.com/search?from=NYC&to=LHR&departdate=2026-06-15"

        with patch("app.html_utils.fetch_page_content") as mock_fetch, \
             patch("app.scrape_telemetry.detect_anti_bot") as mock_anti_bot, \
             patch("app.page_profiler.detect_page_structure") as mock_structure, \
             patch("app.page_profiler.detect_value_patterns") as mock_patterns, \
             patch("app.llm_bridge.llm_json") as mock_llm, \
             patch("app.selector_discovery._try_form_search_recovery") as mock_recovery, \
             patch("app.selector_discovery._detect_search_form") as mock_form_detect, \
             patch("httpx.AsyncClient") as mock_httpx_client:

            from app.selector_discovery import analyze_url_for_fields
            from app.page_profiler import StructureProfile, ValuePatterns

            # Mock the initial httpx redirect check
            mock_resp = AsyncMock()
            mock_resp.url = "https://www.example.com/"
            mock_resp.status_code = 200
            mock_resp.text = LANDING_PAGE_WITH_SEARCH_FORM

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = mock_client

            # Initial fetch returns the landing page (after redirect)
            mock_fetch.return_value = (
                LANDING_PAGE_WITH_SEARCH_FORM,
                500,
                "playwright_full",
                0,
            )

            mock_anti_bot.return_value = 0.1

            mock_structure.return_value = StructureProfile(
                structure_type="landing_page",
                structure_confidence=0.8,
                headers=[],
                container_selector="div.flight-result",
            )

            mock_patterns.return_value = ValuePatterns(
                currencies=["$450"],
                dates=["2026-06-15"],
            )

            mock_llm.return_value = [
                {"name": "origin", "type": "string", "confidence": 0.9},
                {"name": "destination", "type": "string", "confidence": 0.9},
                {"name": "price", "type": "currency", "confidence": 0.9},
            ]

            # Search form is detected
            mock_form_detect.return_value = {
                "detected": True,
                "action": "/search",
                "method": "POST",
                "fields": [
                    {"name": "from", "id": "from", "type": "text", "placeholder": "Departure city"},
                    {"name": "to", "id": "to", "type": "text", "placeholder": "Arrival city"},
                    {"name": "departdate", "id": "departdate", "type": "date", "placeholder": "Departure date"},
                ],
                "search_fields": [
                    {"name": "from", "id": "from", "type": "text", "placeholder": "Departure city"},
                    {"name": "to", "id": "to", "type": "text", "placeholder": "Arrival city"},
                ],
            }

            # Recovery succeeds — returns fresh results page
            mock_recovery.return_value = {
                "success": True,
                "fresh_url": fresh_url,
                "fresh_html": FRESH_RESULTS_PAGE,
                "form_detected": True,
                "form_info": mock_form_detect.return_value,
                "error": None,
            }

            result = await analyze_url_for_fields(
                stale_url,
                search_params={"origin": "NYC", "destination": "LHR"},
            )

            # ── Core assertions for the metadata bug ──
            # redirect_info must NOT say session_expired after recovery
            assert result["redirect_info"]["redirected"] is False
            assert result["redirect_info"]["redirect_type"] == "none"
            assert "recovered" in result["redirect_info"]["message"].lower()
            # fetch_method must reflect search_form_post
            assert result["fetch_method"] == "search_form_post"
            # The final URL must be different from the stale session URL
            assert result["redirect_info"]["final_url"] != stale_url

    @pytest.mark.asyncio
    async def test_no_recovery_without_search_params(self):
        """When no search_params are provided, recovery should not be attempted
        even if a redirect and search form are detected."""
        stale_url = "https://www.example.com/search/results/abc123session456"

        with patch("app.html_utils.fetch_page_content") as mock_fetch, \
             patch("app.scrape_telemetry.detect_anti_bot") as mock_anti_bot, \
             patch("app.page_profiler.detect_page_structure") as mock_structure, \
             patch("app.page_profiler.detect_value_patterns") as mock_patterns, \
             patch("app.llm_bridge.llm_json") as mock_llm, \
             patch("app.selector_discovery._detect_search_form") as mock_form_detect, \
             patch("httpx.AsyncClient") as mock_httpx_client:

            from app.selector_discovery import analyze_url_for_fields
            from app.page_profiler import StructureProfile, ValuePatterns

            # Mock the initial httpx redirect check
            mock_resp = AsyncMock()
            mock_resp.url = "https://www.example.com/"
            mock_resp.status_code = 200
            mock_resp.text = LANDING_PAGE_WITH_SEARCH_FORM

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = mock_client

            mock_fetch.return_value = (
                LANDING_PAGE_WITH_SEARCH_FORM,
                500,
                "playwright_full",
                0,
            )

            mock_anti_bot.return_value = 0.1

            mock_structure.return_value = StructureProfile(
                structure_type="landing_page",
                structure_confidence=0.8,
                headers=[],
                container_selector="body",
            )

            mock_patterns.return_value = ValuePatterns()

            mock_llm.return_value = [
                {"name": "search_field", "type": "string", "confidence": 0.5},
            ]

            mock_form_detect.return_value = {
                "detected": True,
                "action": "/search",
                "method": "POST",
                "fields": [
                    {"name": "from", "id": "from", "type": "text", "placeholder": "From"},
                    {"name": "to", "id": "to", "type": "text", "placeholder": "To"},
                ],
                "search_fields": [
                    {"name": "from", "id": "from", "type": "text", "placeholder": "From"},
                ],
            }

            # Call WITHOUT search_params
            result = await analyze_url_for_fields(stale_url)

            # No recovery attempted — search_recovery should be None
            assert result["search_recovery"] is None
            # redirect_info should still show the redirect
            assert result["redirect_info"]["redirected"] is True
            assert result["redirect_info"]["redirect_type"] == "session_expired"