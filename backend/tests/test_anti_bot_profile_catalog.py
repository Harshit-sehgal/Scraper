from __future__ import annotations

from app.anti_bot_engine import AntiBotEngine


class TestProfileCatalog:
    def _engine(self) -> AntiBotEngine:
        return AntiBotEngine()

    def test_get_stealth_profile_returns_all_required_keys(self) -> None:
        engine = self._engine()
        profile = engine.get_stealth_profile("example.com")
        assert isinstance(profile, dict)
        assert "user_agent" in profile
        assert "extra_headers" in profile
        assert "viewport" in profile
        assert "cookie_string" in profile
        assert "timezone" in profile
        assert "locale" in profile
        assert "platform" in profile

    def test_stealth_profile_includes_user_agent(self) -> None:
        engine = self._engine()
        profile = engine.get_stealth_profile("example.com")
        ua = profile["user_agent"]
        assert isinstance(ua, str)
        assert len(ua) > 10

    def test_stealth_profile_includes_viewport(self) -> None:
        engine = self._engine()
        profile = engine.get_stealth_profile("example.com")
        vp = profile["viewport"]
        assert isinstance(vp, dict)
        assert "width" in vp
        assert "height" in vp
        assert vp["width"] > 0
        assert vp["height"] > 0

    def test_stealth_profile_includes_extra_headers(self) -> None:
        engine = self._engine()
        profile = engine.get_stealth_profile("example.com")
        headers = profile["extra_headers"]
        assert isinstance(headers, dict)
        assert "Accept" in headers
        assert "Accept-Language" in headers

    def test_stealth_profile_platform_matches_ua(self) -> None:
        engine = self._engine()
        profile = engine.get_stealth_profile("example.com")
        platform = profile["platform"]
        ua = profile["user_agent"]
        if "Windows" in ua:
            assert platform == "Win32"
        elif "Mac" in ua:
            assert platform == "MacIntel"
        else:
            assert "Linux" in platform

    def test_stealth_profile_default_cookie_string_empty(self) -> None:
        engine = self._engine()
        profile = engine.get_stealth_profile("new-domain.org")
        assert profile["cookie_string"] == ""
