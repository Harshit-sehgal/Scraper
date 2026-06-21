"""Three-way integration test for URL acquisition pipeline.

Tests the full analyze_url_for_fields flow through three scenarios:
1. Direct URL — no redirect, no session issues
2. Session-expired URL — redirect detected, no recovery (awaiting search params)
3. Recovered URL — session expired but search form recovery succeeds

Verifies that acquisition_lineage, session_detection, canonical_url,
empty_check, and acquisition telemetry are all wired correctly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.acquisition_telemetry import AcquisitionTelemetryCollector
from app.page_profiler import StructureProfile, ValuePatterns

# ── HTML fixtures ──────────────────────────────────────────────────────

DIRECT_PAGE = """
<html><body>
<div class="result-item">
    <span class="name">Product A</span>
    <span class="price">$29.99</span>
    <span class="date">2026-05-20</span>
</div>
<div class="result-item">
    <span class="name">Product B</span>
    <span class="price">$49.99</span>
    <span class="date">2026-05-21</span>
</div>
<div class="result-item">
    <span class="name">Product C</span>
    <span class="price">$19.99</span>
    <span class="date">2026-05-22</span>
</div>
<div class="result-item">
    <span class="name">Product D</span>
    <span class="price">$39.99</span>
    <span class="date">2026-05-23</span>
</div>
<div class="result-item">
    <span class="name">Product E</span>
    <span class="price">$59.99</span>
    <span class="date">2026-05-24</span>
</div>
</body></html>
"""

LANDING_PAGE = """
<html><body>
<div class="hero-banner"><h1>Find Cheap Flights</h1></div>
<form action="/search" method="POST">
    <input type="text" name="from" id="from" placeholder="Departure city" />
    <input type="text" name="to" id="to" placeholder="Arrival city" />
    <input type="date" name="departdate" id="departdate" />
    <button type="submit">Search Flights</button>
</form>
</body></html>
"""

FRESH_RESULTS = """
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

SESSION_EXPIRED_PAGE = """
<html><body>
<div class="hero-banner"><h1>Welcome to Example Airlines</h1></div>
<form action="/search" method="POST">
    <input type="text" name="from" id="from" placeholder="From" />
    <input type="text" name="to" id="to" placeholder="To" />
    <button type="submit">Search</button>
</form>
</body></html>
"""


class TestThreeWayAcquisition:
    """Three-way integration test: direct, session-expired, and recovered URLs."""

    @pytest.mark.asyncio
    async def test_direct_url_acquisition(self) -> None:
        """Scenario 1: Direct URL — no redirect, no session issues.

        Expected: AcquisitionState.DIRECT, no session detection,
        canonical_url == original_url, empty_check shows not empty.
        """
        url = "https://example.com/data"
        telemetry = AcquisitionTelemetryCollector()

        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("app.scrape_telemetry.detect_anti_bot") as mock_anti_bot,
            patch("app.page_profiler.detect_page_structure") as mock_structure,
            patch("app.page_profiler.detect_value_patterns") as mock_patterns,
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock) as mock_llm,
            patch("httpx.AsyncClient") as mock_httpx_client,
            patch("app.acquisition_telemetry.get_acquisition_telemetry", return_value=telemetry),
        ):
            mock_resp = MagicMock()
            mock_resp.url = url
            mock_resp.status_code = 200
            mock_resp.is_redirect = False
            mock_resp.headers = {}
            mock_resp.text = DIRECT_PAGE

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = mock_client

            mock_fetch.return_value = (DIRECT_PAGE, 200, "playwright_full", 0)
            mock_anti_bot.return_value = 0.1
            mock_structure.return_value = StructureProfile(
                structure_type="table",
                structure_confidence=0.9,
                headers=[],
                container_selector=".result-item",
            )
            mock_patterns.return_value = ValuePatterns(
                currencies=["$29.99", "$49.99"],
                dates=["2026-05-20"],
            )
            mock_llm.return_value = [
                {"name": "name", "type": "string", "confidence": 0.9},
                {"name": "price", "type": "currency", "confidence": 0.9},
            ]

            from app.selector_discovery import analyze_url_for_fields

            result = await analyze_url_for_fields(url)

            # Verify acquisition lineage
            lineage = result["acquisition_lineage"]
            assert lineage["state"] == "direct"
            assert lineage["original_url"] == url

            # Verify session detection
            assert result["session_detection"]["is_session_bound"] is False
            assert result["session_detection"]["ephemeral_params"] == []

            # Verify canonical URL
            assert result["canonical_url"] == url

            # Verify empty check
            assert result["empty_check"]["is_empty"] is False

            # Verify telemetry was recorded
            summary = telemetry.get_summary()
            assert summary["total_acquisitions"] == 1
            assert summary["state_distribution"]["direct"] == 1

    @pytest.mark.asyncio
    async def test_session_expired_awaiting_params(self) -> None:
        """Scenario 2: Session-expired URL — redirect detected, form found, no search params.

        Expected: AcquisitionState.AWAITING_SEARCH_PARAMS, session_bound detected,
        canonical_url has ephemeral params stripped.
        """
        stale_url = "https://www.example.com/search/results/abc123session456"
        homepage_url = "https://www.example.com/"
        telemetry = AcquisitionTelemetryCollector()

        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("app.scrape_telemetry.detect_anti_bot") as mock_anti_bot,
            patch("app.page_profiler.detect_page_structure") as mock_structure,
            patch("app.page_profiler.detect_value_patterns") as mock_patterns,
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock) as mock_llm,
            patch("httpx.AsyncClient") as mock_httpx_client,
            patch(
                "app.selector_discovery._detect_redirect",
                return_value={
                    "redirected": True,
                    "redirect_type": "session_expired",
                    "message": "URL redirected to homepage — the search session likely expired.",
                    "original_url": stale_url,
                    "final_url": homepage_url,
                },
            ),
            patch("app.url_safety.validate_public_http_url", return_value=None),
            patch("app.acquisition_telemetry.get_acquisition_telemetry", return_value=telemetry),
            patch("app.selector_discovery.detect_session_params") as mock_session,
        ):
            mock_resp = MagicMock()
            mock_resp.url = homepage_url
            mock_resp.status_code = 200
            mock_resp.is_redirect = False
            mock_resp.headers = {}
            mock_resp.text = SESSION_EXPIRED_PAGE

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = mock_client

            mock_fetch.return_value = (SESSION_EXPIRED_PAGE, 200, "playwright_full", 0)
            mock_anti_bot.return_value = 0.1
            mock_structure.return_value = StructureProfile(
                structure_type="landing_page",
                structure_confidence=0.7,
                headers=[],
                container_selector="body",
            )
            mock_patterns.return_value = ValuePatterns()
            mock_llm.return_value = [
                {"name": "search_field", "type": "string", "confidence": 0.5},
            ]

            # Session detection identifies the URL as session-bound
            mock_session.return_value = {
                "is_session_bound": True,
                "ephemeral_params": ["abc123session456"],
                "canonical_url": "https://www.example.com/search/results/",
                "confidence": 0.8,
            }

            # No search_params provided — no recovery attempted
            from app.selector_discovery import analyze_url_for_fields

            result = await analyze_url_for_fields(stale_url, acquisition_mode="aggressive")

            # Verify acquisition lineage — awaiting search params
            lineage = result["acquisition_lineage"]
            assert lineage["state"] == "awaiting_search_params"

            # Verify session detection
            assert result["session_detection"]["is_session_bound"] is True

            # Verify canonical URL (ephemeral params stripped)
            assert result["canonical_url"] == "https://www.example.com/search/results/"

            # Verify empty check
            assert result["empty_check"]["is_empty"] is True

            # Verify telemetry
            summary = telemetry.get_summary()
            assert summary["state_distribution"]["awaiting_search_params"] == 1

    @pytest.mark.asyncio
    async def test_recovered_url_acquisition(self) -> None:
        """Scenario 3: Session-expired URL with successful search form recovery.

        Expected: AcquisitionState.RECOVERED, canonical_url == recovered_url,
        empty_check shows not empty (fresh results page).
        """
        stale_url = "https://www.example.com/search/results/abc123session456"
        fresh_url = "https://www.example.com/search?from=NYC&to=LHR&departdate=2026-06-15"
        telemetry = AcquisitionTelemetryCollector()

        with (
            patch("app.html_utils.fetch_page_content") as mock_fetch,
            patch("app.scrape_telemetry.detect_anti_bot") as mock_anti_bot,
            patch("app.page_profiler.detect_page_structure") as mock_structure,
            patch("app.page_profiler.detect_value_patterns") as mock_patterns,
            patch("app.selector_discovery.llm_json", new_callable=AsyncMock) as mock_llm,
            patch("httpx.AsyncClient") as mock_httpx_client,
            patch("app.selector_discovery._try_form_search_recovery", new_callable=AsyncMock) as mock_recovery,
            patch("app.selector_discovery._detect_search_form") as mock_form_detect,
            patch(
                "app.selector_discovery._detect_redirect",
                return_value={
                    "redirected": True,
                    "redirect_type": "session_expired",
                    "message": "URL redirected to homepage — the search session likely expired.",
                    "original_url": stale_url,
                    "final_url": "https://www.example.com/",
                },
            ),
            patch("app.url_safety.validate_public_http_url", return_value=None),
            patch("app.acquisition_telemetry.get_acquisition_telemetry", return_value=telemetry),
            patch("app.selector_discovery.detect_session_params") as mock_session,
        ):
            mock_resp = MagicMock()
            mock_resp.url = "https://www.example.com/"
            mock_resp.status_code = 200
            mock_resp.is_redirect = False
            mock_resp.headers = {}
            mock_resp.text = LANDING_PAGE

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = mock_client

            # Initial fetch returns landing page (after redirect)
            mock_fetch.return_value = (LANDING_PAGE, 500, "playwright_full", 0)
            mock_anti_bot.return_value = 0.1

            mock_structure.return_value = StructureProfile(
                structure_type="cards",
                structure_confidence=0.8,
                headers=[],
                container_selector=".flight-result",
            )
            mock_patterns.return_value = ValuePatterns(
                currencies=["$450", "$520"],
                dates=["2026-06-15"],
            )
            mock_llm.return_value = [
                {"name": "origin", "type": "string", "confidence": 0.9},
                {"name": "destination", "type": "string", "confidence": 0.9},
                {"name": "price", "type": "currency", "confidence": 0.9},
            ]

            mock_form_detect.return_value = {
                "detected": True,
                "action": "/search",
                "method": "POST",
                "fields": [
                    {"name": "from", "id": "from", "type": "text", "placeholder": "Departure city"},
                    {"name": "to", "id": "to", "type": "text", "placeholder": "Arrival city"},
                    {"name": "departdate", "id": "departdate", "type": "date"},
                ],
                "search_fields": [
                    {"name": "from", "id": "from", "type": "text", "placeholder": "Departure city"},
                    {"name": "to", "id": "to", "type": "text", "placeholder": "Arrival city"},
                ],
            }

            mock_recovery.return_value = {
                "success": True,
                "fresh_url": fresh_url,
                "fresh_html": FRESH_RESULTS,
                "form_detected": True,
                "form_info": mock_form_detect.return_value,
                "error": None,
            }

            # Session detection identifies the URL as session-bound
            mock_session.return_value = {
                "is_session_bound": True,
                "ephemeral_params": ["abc123session456"],
                "canonical_url": "https://www.example.com/search/results/",
                "confidence": 0.8,
            }

            from app.selector_discovery import analyze_url_for_fields

            result = await analyze_url_for_fields(
                stale_url,
                search_params={"origin": "NYC", "destination": "LHR"},
                acquisition_mode="aggressive",
            )

            # Verify acquisition lineage
            lineage = result["acquisition_lineage"]
            assert lineage["state"] == "recovered"
            assert lineage["recovered_url"] == fresh_url

            # Verify canonical URL points to recovered URL
            assert result["canonical_url"] == fresh_url

            # Verify session detection
            assert result["session_detection"]["is_session_bound"] is True

            # Verify empty check on the fresh results page
            assert result["empty_check"]["is_empty"] is False

            # Verify telemetry
            summary = telemetry.get_summary()
            assert summary["recovery_attempts"] == 1
            assert summary["recovery_successes"] == 1
            assert summary["recovery_success_rate"] == 1.0
