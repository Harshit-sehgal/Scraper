from __future__ import annotations

from unittest.mock import patch

import pytest
from app.anti_bot_engine import AntiBotEngine
from app.config import settings


class TestHeaderVariation:
    """Anti 8: Request header randomization across multiple calls."""

    def _collect_headers(self, n: int = 50) -> list[dict[str, str]]:
        engine = AntiBotEngine()
        return [engine.get_stealth_profile("example.com")["extra_headers"] for _ in range(n)]

    def test_accept_header_present(self) -> None:
        headers = self._collect_headers(1)[0]
        assert "Accept" in headers
        assert "text/html" in headers["Accept"]

    def test_accept_language_from_settings(self) -> None:
        headers = self._collect_headers(1)[0]
        assert headers.get("Accept-Language") == settings.STEALTH_ACCEPT_LANGUAGE

    def test_accept_encoding_present(self) -> None:
        headers = self._collect_headers(1)[0]
        assert "Accept-Encoding" in headers
        assert "gzip" in headers["Accept-Encoding"]

    def test_sec_ch_ua_present_on_chromium(self) -> None:
        engine = AntiBotEngine()
        profile = engine.get_stealth_profile("example.com")
        ua = profile["user_agent"]
        if "Chrome" in ua and "Firefox" not in ua:
            hdrs = profile["extra_headers"]
            assert "Sec-Ch-Ua" in hdrs
            assert "Chromium" in hdrs["Sec-Ch-Ua"]
            assert "Google Chrome" in hdrs["Sec-Ch-Ua"]

    def test_sec_ch_ua_absent_on_firefox(self) -> None:
        ua_ff = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
        with patch.object(settings, "STEALTH_UA_POOL", ua_ff):
            engine = AntiBotEngine()
            profile = engine.get_stealth_profile("ff.example.com")
            hdrs = profile["extra_headers"]
            assert "Sec-Ch-Ua" not in hdrs
            assert "Sec-Ch-Ua-Mobile" not in hdrs
            assert "Sec-Ch-Ua-Platform" not in hdrs

    def test_sec_ch_ua_platform_windows(self) -> None:
        ua_win = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Chrome/122.0.0.0 Safari/537.36"
        with patch.object(settings, "STEALTH_UA_POOL", ua_win):
            engine = AntiBotEngine()
            profile = engine.get_stealth_profile("win.example.com")
            assert '"Windows"' in profile["extra_headers"]["Sec-Ch-Ua-Platform"]

    def test_sec_ch_ua_platform_macos(self) -> None:
        ua_mac = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; Chrome/122.0.0.0 Safari/537.36"
        with patch.object(settings, "STEALTH_UA_POOL", ua_mac):
            engine = AntiBotEngine()
            profile = engine.get_stealth_profile("mac.example.com")
            assert '"macOS"' in profile["extra_headers"]["Sec-Ch-Ua-Platform"]

    def test_sec_fetch_headers_present(self) -> None:
        headers = self._collect_headers(1)[0]
        assert headers.get("Sec-Fetch-Dest") == "document"
        assert headers.get("Sec-Fetch-Mode") == "navigate"
        assert headers.get("Sec-Fetch-Site") == "none"

    def test_upgrade_insecure_requests_present(self) -> None:
        headers = self._collect_headers(1)[0]
        assert headers.get("Upgrade-Insecure-Requests") == "1"

    @pytest.mark.parametrize(
        "header_name",
        [
            "Accept",
            "Accept-Language",
            "Accept-Encoding",
            "Sec-Fetch-Dest",
            "Sec-Fetch-Mode",
            "Sec-Fetch-Site",
            "Upgrade-Insecure-Requests",
        ],
    )
    def test_critical_headers_always_present(self, header_name: str) -> None:
        headers = self._collect_headers(1)[0]
        assert header_name in headers, f"Missing header: {header_name}"

    def test_chrome_version_in_sec_ch_ua(self) -> None:
        engine = AntiBotEngine()
        profile = engine.get_stealth_profile("ver.example.com")
        hdrs = profile["extra_headers"]
        if "Sec-Ch-Ua" in hdrs:
            import re

            versions = re.findall(r'v="(\d+)"', hdrs["Sec-Ch-Ua"])
            assert len(versions) >= 3, "Sec-Ch-Ua should have 3+ entries"
            # Chromium and Google Chrome should share the same version
            assert versions[0] == versions[-1], "Chromium and Chrome versions must match"
