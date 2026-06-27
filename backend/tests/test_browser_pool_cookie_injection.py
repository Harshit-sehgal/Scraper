"""Browser pool cookie injection — verify persisted cookies reach Playwright contexts.

Tests that _parse_cookie_string_for_playwright correctly parses cookie strings
and that the browser pool injection path works.
"""

from __future__ import annotations

from app.browser_pool import _parse_cookie_string_for_playwright


class TestCookieStringParsing:
    """Verify cookie string parsing for Playwright add_cookies format."""

    def test_standard_cookie_string(self) -> None:
        """Standard 'key=val; key2=val2' must produce two cookie dicts."""
        result = _parse_cookie_string_for_playwright(
            "cf_clearance=abc123; session_id=xyz789",
            "example.com",
        )
        assert len(result) == 2
        assert result[0]["name"] == "cf_clearance"
        assert result[0]["value"] == "abc123"
        assert result[0]["domain"] == "example.com"
        assert result[0]["path"] == "/"
        assert result[0]["secure"] is True
        assert result[1]["name"] == "session_id"
        assert result[1]["value"] == "xyz789"

    def test_single_cookie(self) -> None:
        """Single cookie must be parsed correctly."""
        result = _parse_cookie_string_for_playwright(
            "cf_clearance=abc123",
            "example.com",
        )
        assert len(result) == 1
        assert result[0]["name"] == "cf_clearance"

    def test_empty_string_returns_empty(self) -> None:
        """Empty cookie string must return empty list."""
        result = _parse_cookie_string_for_playwright("", "example.com")
        assert result == []

    def test_whitespace_only_returns_empty(self) -> None:
        """Whitespace-only cookie string must return empty list."""
        result = _parse_cookie_string_for_playwright("   ", "example.com")
        assert result == []

    def test_cookie_prefix_stripped(self) -> None:
        """'Cookie:' prefix must be stripped if present."""
        result = _parse_cookie_string_for_playwright(
            "Cookie: cf_clearance=abc123",
            "example.com",
        )
        assert len(result) == 1
        assert result[0]["name"] == "cf_clearance"

    def test_malformed_pairs_skipped(self) -> None:
        """Pairs without '=' must be silently skipped."""
        result = _parse_cookie_string_for_playwright(
            "cf_clearance=abc123; bad_entry; session_id=xyz",
            "example.com",
        )
        assert len(result) == 2
        names = [c["name"] for c in result]
        assert "cf_clearance" in names
        assert "session_id" in names

    def test_empty_name_skipped(self) -> None:
        """Pairs with empty name (like '=value') must be skipped."""
        result = _parse_cookie_string_for_playwright(
            "=value; cf_clearance=abc",
            "example.com",
        )
        assert len(result) == 1
        assert result[0]["name"] == "cf_clearance"

    def test_localhost_not_secure(self) -> None:
        """Cookies for localhost must not set secure=True."""
        result = _parse_cookie_string_for_playwright(
            "session=abc",
            "localhost",
        )
        assert len(result) == 1
        assert result[0]["secure"] is False

    def test_samesite_lax(self) -> None:
        """All parsed cookies must have sameSite='Lax'."""
        result = _parse_cookie_string_for_playwright(
            "a=1; b=2",
            "example.com",
        )
        for cookie in result:
            assert cookie["sameSite"] == "Lax"

    def test_trailing_semicolons_handled(self) -> None:
        """Trailing semicolons must not produce empty entries."""
        result = _parse_cookie_string_for_playwright(
            "cf_clearance=abc123; ; ",
            "example.com",
        )
        assert len(result) == 1
        assert result[0]["name"] == "cf_clearance"
