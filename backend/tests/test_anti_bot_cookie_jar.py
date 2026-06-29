from __future__ import annotations

import time

from app.anti_bot_engine import AntiBotEngine
from app.browser_pool import _parse_cookie_string_for_playwright


class TestCookieParsing:
    """Anti 37: Cookie string parsing for Playwright."""

    def test_parse_simple_cookie(self) -> None:
        cookies = _parse_cookie_string_for_playwright("session=abc123", "example.com")
        assert len(cookies) == 1
        assert cookies[0]["name"] == "session"
        assert cookies[0]["value"] == "abc123"
        assert cookies[0]["domain"] == "example.com"

    def test_parse_multiple_cookies(self) -> None:
        cookies = _parse_cookie_string_for_playwright("a=1; b=2; c=3", "test.com")
        assert len(cookies) == 3
        assert cookies[0]["name"] == "a"
        assert cookies[1]["name"] == "b"
        assert cookies[2]["name"] == "c"

    def test_parse_handles_cookie_prefix(self) -> None:
        cookies = _parse_cookie_string_for_playwright("Cookie: token=xyz; path=/", "site.com")
        assert len(cookies) >= 1
        assert any(c["name"] == "token" for c in cookies)

    def test_empty_string_returns_empty_list(self) -> None:
        assert _parse_cookie_string_for_playwright("", "example.com") == []

    def test_whitespace_only_returns_empty(self) -> None:
        assert _parse_cookie_string_for_playwright("   ", "example.com") == []

    def test_malformed_pair_skipped(self) -> None:
        cookies = _parse_cookie_string_for_playwright("valid=1; badformat; another=2", "ex.com")
        assert len(cookies) == 2
        assert all(c["name"] in ("valid", "another") for c in cookies)

    def test_samesite_defaults_to_lax(self) -> None:
        cookies = _parse_cookie_string_for_playwright("key=val", "ex.com")
        assert cookies[0]["sameSite"] == "Lax"

    def test_secure_is_auto_detected(self) -> None:
        cookies = _parse_cookie_string_for_playwright("key=val", "https://shop.example.com")
        assert cookies[0]["secure"] is True

    def test_path_defaults_to_root(self) -> None:
        cookies = _parse_cookie_string_for_playwright("key=val", "ex.com")
        assert cookies[0]["path"] == "/"

    def test_cookie_jar_expiration_check(self) -> None:
        engine = AntiBotEngine()
        engine.update_cookies("fresh.com", "session=live")
        assert not engine.should_refresh_cookies("fresh.com", max_age_hours=24)

    def test_cookie_jar_expired_returns_true(self) -> None:
        engine = AntiBotEngine()
        engine._last_cookie_update["stale.com"] = time.time() - 48 * 3600
        assert engine.should_refresh_cookies("stale.com", max_age_hours=24)

    def test_cookie_jar_no_entry_returns_true(self) -> None:
        engine = AntiBotEngine()
        assert engine.should_refresh_cookies("unknown.com")

    def test_parse_handles_spaced_values(self) -> None:
        cookies = _parse_cookie_string_for_playwright("key=val with spaces", "ex.com")
        assert len(cookies) == 1
        assert cookies[0]["value"] == "val with spaces"

    def test_value_with_equals_sign(self) -> None:
        cookies = _parse_cookie_string_for_playwright("token=base64==data", "ex.com")
        assert len(cookies) == 1
        assert cookies[0]["value"] == "base64==data"

    def test_domain_based_ttl_variation(self) -> None:
        engine = AntiBotEngine()
        engine.record_block("hard.example", 0.95)
        engine.record_block("hard.example", 0.95)
        ttl = engine._domain_specific_cookie_ttl("hard.example", default=24)
        assert ttl < 24, "Hard-blocked domains should get shorter TTL"
