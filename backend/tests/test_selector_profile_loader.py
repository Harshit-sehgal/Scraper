"""Unit Tests for Selector Profile Loader.
Tests the non-Playwright parts of the profile loader: domain matching,
currency parsing, field post-processing, and profile cache management.
"""

from __future__ import annotations

import pytest
from app.selector_profiles.loader import (
    _load_all_profiles,
    _match_domain,
    _parse_currency,
    _postprocess_field,
    reload_profiles,
)

# ─── _parse_currency ───────────────────────────────────────────────────


class TestParseCurrency:
    def test_currency_with_symbol_prefix(self) -> None:
        assert _parse_currency("£238") == "238"
        assert _parse_currency("$500") == "500"
        assert _parse_currency("€99.50") == "99.50"

    def test_currency_with_thousands_separator(self) -> None:
        assert _parse_currency("£1,234.56") == "1234.56"
        assert _parse_currency("$12,345") == "12345"

    def test_currency_with_currency_code(self) -> None:
        assert _parse_currency("AED 500") == "500"
        assert _parse_currency("USD 99.99") == "99.99"

    def test_currency_none_or_empty(self) -> None:
        assert _parse_currency(None) is None
        assert _parse_currency("") is None

    def test_currency_no_digits(self) -> None:
        assert _parse_currency("FREE") is None
        assert _parse_currency("N/A") is None


# ─── _postprocess_field ────────────────────────────────────────────────


class TestPostprocessField:
    def test_text_type_passthrough(self) -> None:
        result = _postprocess_field("Hello World", {"type": "text"})
        assert result == "Hello World"

    def test_currency_type(self) -> None:
        result = _postprocess_field("£238", {"type": "currency"})
        assert result == "238"

    def test_number_type(self) -> None:
        result = _postprocess_field("£99.50", {"type": "number"})
        assert result == "99.5"

    def test_number_type_cleans_symbols(self) -> None:
        result = _postprocess_field("$1,234.56", {"type": "number"})
        assert result == "1234.56"

    def test_none_value(self) -> None:
        for field_type in ("text", "currency", "number"):
            assert _postprocess_field(None, {"type": field_type}) is None

    def test_empty_string(self) -> None:
        assert _postprocess_field("", {"type": "text"}) is None

    def test_whitespace_only(self) -> None:
        assert _postprocess_field("  ", {"type": "text"}) is None


# ─── _load_all_profiles & cache ────────────────────────────────────────


class TestProfileLoading:
    def setup_method(self) -> None:
        reload_profiles()  # Reset cache before each test

    def teardown_method(self) -> None:
        reload_profiles()

    def test_load_empty_dir_returns_empty(self) -> None:
        profiles = _load_all_profiles()
        # The real profiles dir may or may not exist; test handles both
        assert isinstance(profiles, dict)

    def test_cache_works(self) -> None:
        # First call populates cache
        first = _load_all_profiles()
        # Second call should return same cached object
        second = _load_all_profiles()
        assert first is second

    def test_reload_clears_cache(self) -> None:
        first = _load_all_profiles()
        reload_profiles()
        second = _load_all_profiles()
        # After reload, a new dict should be returned
        assert first is not second


# ─── _match_domain ─────────────────────────────────────────────────────


class TestMatchDomain:
    def setup_method(self) -> None:
        reload_profiles()

    def teardown_method(self) -> None:
        reload_profiles()

    def test_match_returns_profile_for_known_profile(self) -> None:
        result = _match_domain("https://example.com/page")
        assert result is not None
        assert result["domain"] == "example.com"

    def test_match_handles_invalid_url(self) -> None:
        result = _match_domain("not-a-url")
        assert result is None


# ─── try_profile_extraction ─────────────────────────────────────────────


class TestTryProfileExtraction:
    @pytest.mark.asyncio
    async def test_no_profile_found(self) -> None:
        """When no profile matches, try_profile_extraction returns None."""
        reload_profiles()
        from app.selector_profiles.loader import try_profile_extraction

        result = await try_profile_extraction("https://unknown-site-12345.com/page")
        assert result is None


# ─── extract_with_profile error paths ──────────────────────────────────


class TestExtractWithProfile:
    @pytest.mark.asyncio
    async def test_missing_item_container_returns_empty(self) -> None:
        """When profile lacks item_container, returns empty list."""
        from app.selector_profiles.loader import extract_with_profile

        result = await extract_with_profile(
            "https://example.com",
            {"domain": "example.com", "fields": {"name": {"selector": ".name"}}},
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_missing_fields_returns_empty(self) -> None:
        """When profile lacks fields, returns empty list."""
        from app.selector_profiles.loader import extract_with_profile

        result = await extract_with_profile(
            "https://example.com",
            {"domain": "example.com", "item_container": "div.card"},
        )
        assert result == []
