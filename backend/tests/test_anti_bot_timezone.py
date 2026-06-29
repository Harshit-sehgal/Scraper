from __future__ import annotations

import re

from app.anti_bot_engine import AntiBotEngine
from app.config import settings


class TestTimezoneLocaleAlignment:
    """Anti 13: Coordinated timezone/locale/accept-language."""

    KNOWN_TIMEZONES = {
        "America/New_York",
        "America/Chicago",
        "America/Los_Angeles",
        "Europe/London",
        "Europe/Berlin",
        "Asia/Singapore",
        "Asia/Tokyo",
        "Australia/Sydney",
    }

    def test_timezone_from_known_pool(self) -> None:
        engine = AntiBotEngine()
        samples: set[str] = set()
        for _ in range(100):
            profile = engine.get_stealth_profile("example.com")
            samples.add(profile["timezone"])
        for tz in samples:
            assert tz in self.KNOWN_TIMEZONES, f"Unexpected timezone: {tz}"

    def test_locale_from_settings(self) -> None:
        engine = AntiBotEngine()
        profile = engine.get_stealth_profile("example.com")
        assert profile["locale"] == settings.STEALTH_DEFAULT_LOCALE

    def test_accept_language_from_settings(self) -> None:
        engine = AntiBotEngine()
        profile = engine.get_stealth_profile("example.com")
        assert profile["extra_headers"]["Accept-Language"] == settings.STEALTH_ACCEPT_LANGUAGE

    def test_locale_and_accept_language_consistent(self) -> None:
        engine = AntiBotEngine()
        profile = engine.get_stealth_profile("example.com")
        locale = profile["locale"]
        accept = profile["extra_headers"]["Accept-Language"]
        assert locale.split("-")[0] in accept or locale.lower() in accept.lower()

    def test_all_known_timezones_eventually_selected(self) -> None:
        engine = AntiBotEngine()
        seen: set[str] = set()
        for _ in range(500):
            profile = engine.get_stealth_profile("example.com")
            seen.add(profile["timezone"])
            if seen == self.KNOWN_TIMEZONES:
                break
        assert seen == self.KNOWN_TIMEZONES, f"Not all timezones seen: missing {self.KNOWN_TIMEZONES - seen}"

    def test_timezone_id_format(self) -> None:
        engine = AntiBotEngine()
        for _ in range(50):
            profile = engine.get_stealth_profile("example.com")
            tz = profile["timezone"]
            assert re.match(r"^[A-Za-z]+/[A-Za-z_]+$", tz), f"Bad timezone format: {tz}"

    def test_platform_matches_ua_os(self) -> None:
        engine = AntiBotEngine()
        profile = engine.get_stealth_profile("example.com")
        ua = profile["user_agent"]
        platform = profile["platform"]
        if "Windows" in ua:
            assert platform == "Win32"
        elif "Mac" in ua:
            assert platform == "MacIntel"
        else:
            assert platform == "Linux x86_64"

    def test_stealth_context_options_include_timezone(self) -> None:
        from app.browser_pool import BrowserPool

        pool = BrowserPool()
        opts = pool._build_stealth_context_options("example.com")
        assert "timezone_id" in opts
        assert opts["timezone_id"] in self.KNOWN_TIMEZONES

    def test_default_context_has_first_timezone(self) -> None:
        from app.browser_pool import BrowserPool

        pool = BrowserPool()
        opts = pool._build_default_context_options()
        first_tz = settings.STEALTH_TIMEZONE_POOL.split(",")[0]
        assert opts["timezone_id"] == first_tz

    def test_navigator_languages_from_settings(self) -> None:
        langs = settings.STEALTH_NAVIGATOR_LANGUAGES.split(",")
        assert len(langs) >= 2
        assert "en-US" in langs
        assert "en" in langs
