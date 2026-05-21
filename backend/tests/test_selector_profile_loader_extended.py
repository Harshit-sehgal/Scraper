"""Extended Unit Tests for Selector Profile Loader.

Covers remaining uncovered lines: real JSON profile loading, domain matching
with profiles, force-reload, error handling, and try_profile_extraction
when a matching profile is found.
"""

from __future__ import annotations

import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from app.selector_profiles.loader import (
    _parse_currency,
    _postprocess_field,
    reload_profiles,
    _match_domain,
    _load_all_profiles,
)


# ─── Real JSON profile loading ─────────────────────────────────────────


class TestRealProfileLoading:
    def setup_method(self):
        reload_profiles()

    def teardown_method(self):
        reload_profiles()

    def test_load_from_temp_profile_dir(self):
        """Load profiles from a temporary directory with real JSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = {
                "domain": "test-site.com",
                "description": "Test site",
                "item_container": "div.card",
                "fields": {
                    "name": {"selector": ".title", "type": "text"},
                },
            }
            with open(Path(tmpdir) / "test_site.json", "w") as f:
                json.dump(profile, f)

            with patch("app.selector_profiles.loader._PROFILES_DIR", Path(tmpdir)):
                reload_profiles()  # Clear cache WITHIN patch context
                profiles = _load_all_profiles()
                assert "test-site.com" in profiles
                assert profiles["test-site.com"]["domain"] == "test-site.com"
                assert profiles["test-site.com"]["fields"]["name"]["selector"] == ".title"

    def test_load_skips_missing_domain(self):
        """Profile without 'domain' field should be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_profile = {
                "description": "No domain here",
                "item_container": "div.card",
                "fields": {},
            }
            with open(Path(tmpdir) / "bad.json", "w") as f:
                json.dump(bad_profile, f)

            with patch("app.selector_profiles.loader._PROFILES_DIR", Path(tmpdir)):
                reload_profiles()  # Clear cache within patch context
                profiles = _load_all_profiles()
                # The bad profile should be skipped (no 'domain' key)
                assert len(profiles) == 0

    def test_load_handles_invalid_json(self):
        """Invalid JSON file should be logged and skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(Path(tmpdir) / "corrupt.json", "w") as f:
                f.write("this is not json")

            with patch("app.selector_profiles.loader._PROFILES_DIR", Path(tmpdir)):
                reload_profiles()  # Clear cache within patch context
                profiles = _load_all_profiles()
                assert len(profiles) == 0

    def test_load_profiles_dir_not_found(self):
        """When profiles dir does not exist, returns empty cache (lines 71-72)."""
        with patch("app.selector_profiles.loader._PROFILES_DIR", Path("/tmp/nonexistent_profiles_dir_xyz")):
            reload_profiles()
            profiles = _load_all_profiles()
            assert len(profiles) == 0
            assert isinstance(profiles, dict)

    def test_load_multiple_profiles(self):
        """Multiple valid JSON files all get loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i, domain in enumerate(["site-a.com", "site-b.com", "site-c.com"]):
                profile = {"domain": domain, "fields": {"f1": {"selector": ".s1"}}}
                with open(Path(tmpdir) / f"site_{i}.json", "w") as f:
                    json.dump(profile, f)

            with patch("app.selector_profiles.loader._PROFILES_DIR", Path(tmpdir)):
                reload_profiles()  # Clear cache within patch context
                profiles = _load_all_profiles()
                assert len(profiles) == 3
                for domain in ["site-a.com", "site-b.com", "site-c.com"]:
                    assert domain in profiles


# ─── _match_domain with profiles loaded ────────────────────────────────


class TestMatchDomainWithProfiles:
    def setup_method(self):
        reload_profiles()

    def teardown_method(self):
        reload_profiles()

    def test_match_exact_domain(self):
        """Exact domain match returns the profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = {"domain": "example.com", "fields": {"n": {"selector": ".n"}}}
            with open(Path(tmpdir) / "example.json", "w") as f:
                json.dump(profile, f)

            with patch("app.selector_profiles.loader._PROFILES_DIR", Path(tmpdir)):
                reload_profiles()  # Clear cache within patch context
                result = _match_domain("https://example.com/page")
                assert result is not None
                assert result["domain"] == "example.com"

    def test_match_subdomain(self):
        """Subdomain match works (domain in hostname)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = {"domain": "example.com", "fields": {"n": {"selector": ".n"}}}
            with open(Path(tmpdir) / "example.json", "w") as f:
                json.dump(profile, f)

            with patch("app.selector_profiles.loader._PROFILES_DIR", Path(tmpdir)):
                reload_profiles()  # Clear cache within patch context
                result = _match_domain("https://www.example.com/page")
                assert result is not None
                assert result["domain"] == "example.com"

    def test_no_match(self):
        """URL not matching any domain returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = {"domain": "example.com", "fields": {"n": {"selector": ".n"}}}
            with open(Path(tmpdir) / "example.json", "w") as f:
                json.dump(profile, f)

            with patch("app.selector_profiles.loader._PROFILES_DIR", Path(tmpdir)):
                reload_profiles()
                result = _match_domain("https://other-site.com/page")
                assert result is None

    def test_match_invalid_url(self):
        """Invalid URL returns None (urlparse gives empty hostname)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = {"domain": "example.com", "fields": {"n": {"selector": ".n"}}}
            with open(Path(tmpdir) / "example.json", "w") as f:
                json.dump(profile, f)

            with patch("app.selector_profiles.loader._PROFILES_DIR", Path(tmpdir)):
                reload_profiles()
                result = _match_domain("not-a-valid-url")
                assert result is None


# ─── reload_profiles ───────────────────────────────────────────────────


class TestReloadProfiles:
    def test_reload_clears_and_reloads(self):
        """reload_profiles clears the cache and reloads fresh."""
        profiles = _load_all_profiles()
        # After reload, a new call should get a fresh dict
        reload_profiles()
        profiles2 = _load_all_profiles()
        assert profiles is not profiles2


# ─── _parse_currency edge cases ────────────────────────────────────────


class TestParseCurrencyEdgeCases:
    def test_string_with_only_letters_no_digits(self):
        """Non-numeric string after symbol stripping returns None."""
        assert _parse_currency("FREE") is None
        assert _parse_currency("N/A") is None
        assert _parse_currency("Contact for price") is None

    def test_string_with_text_and_trailing_digits(self):
        """Text with embedded digits extracts the number."""
        assert _parse_currency("Price is 99 only") == "99"
        assert _parse_currency("Total: 49.95 USD") == "49.95"

    def test_string_with_leading_zeros(self):
        assert _parse_currency("$0.99") == "0.99"
        assert _parse_currency("AED 00500") == "00500"

    def test_string_trailing_text(self):
        """Numbers followed by text after symbol."""
        assert _parse_currency("$199 USD") == "199"

    def test_string_only_symbols(self):
        """Only currency symbols, no digits."""
        assert _parse_currency("£££") is None
        assert _parse_currency("$$") is None


# ─── _postprocess_field number type exception path ─────────────────────


class TestPostprocessFieldExtended:
    def test_number_type_exception_path(self):
        """Non-numeric text with number type returns raw text (except handler, lines 147-148)."""
        result = _postprocess_field("N/A", {"type": "number"})
        assert result == "N/A"

    def test_number_type_invalid_float(self):
        """Text that has symbols but no digits still returns raw text."""
        result = _postprocess_field("£££", {"type": "number"})
        assert result == "£££"

    def test_currency_type_empty_parse_fallback(self):
        """Currency type with no digits returns original text."""
        result = _postprocess_field("FREETEXT", {"type": "currency"})
        assert result == "FREETEXT"

    def test_text_type_default(self):
        """Default type (no type key) returns text as-is."""
        result = _postprocess_field("Hello World", {"selector": ".x"})
        assert result == "Hello World"


# ─── try_profile_extraction with matching profile ──────────────────────


@pytest.mark.asyncio
class TestTryProfileExtractionFound:
    async def test_profile_found_delegates_to_extract(self):
        """When profile matches, extract_with_profile should be called."""
        with (
            patch("app.selector_profiles.loader._match_domain") as mock_match,
            patch("app.selector_profiles.loader.extract_with_profile",
                  new_callable=AsyncMock) as mock_extract,
        ):
            mock_match.return_value = {
                "domain": "example.com",
                "item_container": "div.card",
                "fields": {"name": {"selector": ".title"}},
            }
            mock_extract.return_value = [{"name": "Item1"}]

            from app.selector_profiles.loader import try_profile_extraction
            result = await try_profile_extraction("https://example.com/page")
            assert result == [{"name": "Item1"}]
            mock_extract.assert_called_once()

    async def test_profile_found_uses_correct_url(self):
        """The URL passed to extract_with_profile should be the original URL."""
        with (
            patch("app.selector_profiles.loader._match_domain") as mock_match,
            patch("app.selector_profiles.loader.extract_with_profile",
                  new_callable=AsyncMock) as mock_extract,
        ):
            mock_match.return_value = {"domain": "example.com", "fields": {}}
            mock_extract.return_value = []

            from app.selector_profiles.loader import try_profile_extraction
            await try_profile_extraction("https://example.com/page", max_wait=30)
            mock_extract.assert_called_once_with(
                "https://example.com/page",
                {"domain": "example.com", "fields": {}},
                max_wait=30,
            )


# ─── extract_with_profile (Playwright-mocked) ─────────────────────────


class AsyncPWCtx:
    """Helper: proper async context manager for mocking `async with async_playwright()`.
    
    `__aenter__`/`__aexit__` must be defined on the class (not instance) for
    Python's `async with` protocol to discover them on the type.
    """
    def __init__(self, mock_playwright):
        self._pw = mock_playwright

    async def __aenter__(self):
        return self._pw

    async def __aexit__(self, *args):
        pass


def _make_pw_mocks(mock_playwright):
    """Build the full async_playwright factory mock."""
    pw_ctx = AsyncPWCtx(mock_playwright)
    mock_factory = MagicMock(return_value=pw_ctx)
    return mock_factory, pw_ctx


def _make_page_mock(evaluate_return=None, goto_side_effect=None,
                     wait_for_selector_return=None, wait_for_selector_side_effect=None,
                     container_count: int = 2):
    """Build a mock page with configurable async methods."""
    m = MagicMock()
    m.goto = AsyncMock(side_effect=goto_side_effect) if goto_side_effect else AsyncMock()
    if wait_for_selector_side_effect:
        m.wait_for_selector = AsyncMock(side_effect=wait_for_selector_side_effect)
    elif wait_for_selector_return is not None:
        m.wait_for_selector = AsyncMock(return_value=wait_for_selector_return)
    else:
        m.wait_for_selector = AsyncMock(return_value=True)
    m.evaluate = AsyncMock(return_value=evaluate_return if evaluate_return is not None else [])
    loc_mock = MagicMock()
    loc_mock.count = AsyncMock(return_value=container_count)
    m.locator = MagicMock(return_value=loc_mock)
    m.route = AsyncMock()  # page.route() must be awaitable
    return m


def _make_browser_chain(mock_page):
    """Build mock_context, mock_browser, mock_chromium from a mock_page."""
    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()

    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_chromium = MagicMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw = MagicMock()
    mock_pw.chromium = mock_chromium

    return mock_pw


class TestExtractWithProfilePlaywright:
    """Tests extract_with_profile by mocking Playwright internals."""

    @pytest.mark.asyncio
    async def test_missing_container_and_fields(self):
        """Already tested above — both missing container and fields returns []."""
        from app.selector_profiles.loader import extract_with_profile
        result = await extract_with_profile(
            "https://example.com",
            {"domain": "example.com"},
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_max_wait_defaults_from_settings(self):
        """max_wait=None should use settings.PROFILE_MAX_WAIT."""
        from app.selector_profiles.loader import extract_with_profile
        profile = {"domain": "example.com", "item_container": "div.x", "fields": {"n": {"selector": ".n"}}}

        mock_page = _make_page_mock()
        mock_pw = _make_browser_chain(mock_page)
        mock_factory, _pw_ctx = _make_pw_mocks(mock_pw)

        with patch("app.selector_profiles.loader.async_playwright", mock_factory):
            with patch("app.selector_profiles.loader.settings.PROFILE_MAX_WAIT", 15):
                result = await extract_with_profile(
                    "https://example.com",
                    profile,
                    max_wait=None,
                )
                assert result == []
                # Verify default was used from settings (15s → 15000ms)
                mock_page.wait_for_selector.assert_called_once_with(
                    "div.x", timeout=15000
                )

    @pytest.mark.asyncio
    async def test_extract_with_playwright_success(self):
        """Full extraction flow with Playwright mocking returns post-processed records."""
        from app.selector_profiles.loader import extract_with_profile
        profile = {
            "domain": "example.com",
            "item_container": "div.card",
            "wait_for": "div.card",
            "fields": {
                "name": {"selector": ".title", "type": "text"},
                "price": {"selector": ".price", "type": "currency"},
            },
        }

        mock_page = _make_page_mock(evaluate_return=[
            {"name": "Alpha", "price": "£238"},
            {"name": "Beta", "price": "$99.50"},
        ])
        mock_pw = _make_browser_chain(mock_page)
        mock_factory, _pw_ctx = _make_pw_mocks(mock_pw)

        with patch("app.selector_profiles.loader.async_playwright", mock_factory):
            result = await extract_with_profile(
                "https://example.com",
                profile,
                max_wait=10,
            )

            assert len(result) == 2
            assert result[0]["name"] == "Alpha"
            assert result[0]["price"] == "238"  # Post-processed currency
            assert result[1]["name"] == "Beta"
            assert result[1]["price"] == "99.50"  # Post-processed

            # Verify Playwright was called correctly
            mock_factory.assert_called_once()
            mock_pw.chromium.launch.assert_called_once()
            mock_pw.chromium.launch.await_count == 1
            mock_page.goto.assert_called_once()
            mock_page.wait_for_selector.assert_called_once_with("div.card", timeout=10000)

    @pytest.mark.asyncio
    async def test_goto_timeout_fallback(self):
        """When networkidle times out, falls back to domcontentloaded."""
        from app.selector_profiles.loader import extract_with_profile
        profile = {
            "domain": "example.com",
            "item_container": "div.card",
            "fields": {"n": {"selector": ".n"}},
        }

        mock_page = _make_page_mock(
            evaluate_return=[{"n": "valuable"}],
            goto_side_effect=[
                Exception("Timeout 30000ms exceeded"),  # networkidle fails
                None,  # domcontentloaded succeeds
            ],
        )
        mock_pw = _make_browser_chain(mock_page)
        mock_factory, _pw_ctx = _make_pw_mocks(mock_pw)

        with patch("app.selector_profiles.loader.async_playwright", mock_factory):
            result = await extract_with_profile(
                "https://example.com",
                profile,
                max_wait=10,
            )

            assert len(result) == 1
            assert result[0]["n"] == "valuable"
            # goto called twice: first with networkidle (fails), then domcontentloaded
            assert mock_page.goto.call_count == 2

    @pytest.mark.asyncio
    async def test_wait_for_selector_timeout_returns_empty(self):
        """When wait_for_selector times out, returns empty list."""
        from app.selector_profiles.loader import extract_with_profile
        profile = {
            "domain": "example.com",
            "item_container": "div.card",
            "wait_for": ".slow-loader",
            "fields": {"n": {"selector": ".n"}},
        }

        mock_page = _make_page_mock(
            wait_for_selector_side_effect=Exception("Timeout exceeded"),
        )
        mock_pw = _make_browser_chain(mock_page)
        mock_factory, _pw_ctx = _make_pw_mocks(mock_pw)

        with patch("app.selector_profiles.loader.async_playwright", mock_factory):
            result = await extract_with_profile(
                "https://example.com",
                profile,
                max_wait=10,
            )

            assert result == []
            assert mock_page.wait_for_selector.call_count == 1

    @pytest.mark.asyncio
    async def test_fatal_error_returns_empty(self):
        """When Playwright encounters an unexpected error, returns empty."""
        from app.selector_profiles.loader import extract_with_profile
        profile = {
            "domain": "example.com",
            "item_container": "div.card",
            "fields": {"n": {"selector": ".n"}},
        }

        mock_pw = MagicMock()
        mock_pw.chromium = MagicMock()
        mock_pw.chromium.launch = AsyncMock(side_effect=RuntimeError("Browser crash"))

        mock_factory, _pw_ctx = _make_pw_mocks(mock_pw)

        with patch("app.selector_profiles.loader.async_playwright", mock_factory):
            result = await extract_with_profile(
                "https://example.com",
                profile,
                max_wait=10,
            )
            assert result == []

    @pytest.mark.asyncio
    async def test_route_filter_blocks_media(self):
        """Verify the route filter function blocks images/media/fonts."""
        from app.selector_profiles.loader import extract_with_profile
        profile = {
            "domain": "example.com",
            "item_container": "div.card",
            "fields": {"n": {"selector": ".n"}},
        }

        mock_page = _make_page_mock()
        mock_pw = _make_browser_chain(mock_page)
        mock_factory, _pw_ctx = _make_pw_mocks(mock_pw)

        abort_mock = AsyncMock()
        continue_mock = AsyncMock()

        def make_route(resource_type):
            route = MagicMock()
            route.request.resource_type = resource_type
            route.abort = abort_mock
            route.continue_ = continue_mock
            return route

        with patch("app.selector_profiles.loader.async_playwright", mock_factory):
            await extract_with_profile(
                "https://example.com",
                profile,
                max_wait=10,
            )

            # Capture the route filter function
            route_call = mock_page.route.call_args
            assert route_call is not None
            assert route_call[0][0] == "**/*"
            route_filter = route_call[0][1]

            # Test the filter function with blocked resource types
            await route_filter(make_route("image"))
            abort_mock.assert_called()
            abort_mock.reset_mock()

            await route_filter(make_route("media"))
            abort_mock.assert_called()
            abort_mock.reset_mock()

            await route_filter(make_route("font"))
            abort_mock.assert_called()
            abort_mock.reset_mock()

            # Test allowed resource type passes through
            await route_filter(make_route("document"))
            continue_mock.assert_called()
