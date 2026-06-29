from __future__ import annotations

from unittest.mock import patch

from app.anti_bot_engine import AntiBotEngine
from app.config import settings


class TestProfilePersistence:
    """Anti 16: Consistent fingerprints per domain."""

    def test_ua_history_tracked_per_domain(self) -> None:
        engine = AntiBotEngine()
        ua_a = engine.get_stealth_profile("alpha.example")["user_agent"]
        ua_b = engine.get_stealth_profile("beta.example")["user_agent"]
        assert "alpha.example" in engine._ua_history
        assert "beta.example" in engine._ua_history

    def test_ua_not_reused_within_history(self) -> None:
        engine = AntiBotEngine()
        seen: list[str] = []
        for _ in range(min(5, len(settings.STEALTH_UA_POOL.split(",")))):
            profile = engine.get_stealth_profile("unique.test")
            seen.append(profile["user_agent"])
        assert len(set(seen)) == len(seen), "UA was reused within history window"

    def test_ua_history_capped_at_five(self) -> None:
        with patch.object(settings, "ANTIBOT_UA_HISTORY_SIZE", 3):
            engine = AntiBotEngine()
            for _ in range(10):
                engine.get_stealth_profile("capped.test")
            assert len(engine._ua_history["capped.test"]) <= 3

    def test_different_domains_get_different_fingerprints(self) -> None:
        engine = AntiBotEngine()
        p1 = engine.get_stealth_profile("site-a.example")
        p2 = engine.get_stealth_profile("site-b.example")
        assert p1["viewport"] != p2["viewport"] or p1["timezone"] != p2["timezone"]

    def test_fingerprint_includes_all_required_fields(self) -> None:
        engine = AntiBotEngine()
        profile = engine.get_stealth_profile("fields.test")
        required = {
            "user_agent",
            "extra_headers",
            "viewport",
            "cookie_string",
            "timezone",
            "locale",
            "platform",
            "device_scale_factor",
        }
        assert required.issubset(profile.keys()), f"Missing fields: {required - profile.keys()}"

    def test_same_domain_consistent_shape(self) -> None:
        engine = AntiBotEngine()
        for _ in range(10):
            profile = engine.get_stealth_profile("consistent.test")
            assert isinstance(profile["viewport"], dict)
            assert "width" in profile["viewport"]
            assert "height" in profile["viewport"]

    def test_ua_rotation_never_empty(self) -> None:
        engine = AntiBotEngine()
        for _ in range(50):
            profile = engine.get_stealth_profile("ua.test")
            assert profile["user_agent"], "UA must not be empty"

    def test_profile_platform_consistent_with_ua(self) -> None:
        engine = AntiBotEngine()
        for _ in range(20):
            profile = engine.get_stealth_profile("plat.test")
            ua = profile["user_agent"]
            plat = profile["platform"]
            if "Windows" in ua:
                assert plat == "Win32"
            elif "Mac" in ua:
                assert plat == "MacIntel"
            elif "Linux" in ua or "X11" in ua:
                assert plat == "Linux x86_64"
            else:
                assert plat in ("Win32", "MacIntel", "Linux x86_64")
