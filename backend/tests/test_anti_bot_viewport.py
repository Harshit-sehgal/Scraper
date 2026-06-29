from __future__ import annotations

from app.anti_bot_engine import AntiBotEngine
from app.config import settings


class TestViewportRandomization:
    """Anti 9: Viewport rotation from common sizes."""

    KNOWN_WIDTHS = {1280, 1366, 1440, 1536, 1600, 1920}
    KNOWN_HEIGHTS = {720, 768, 800, 900, 1024, 1080}

    def test_viewport_returns_dict_with_width_and_height(self) -> None:
        engine = AntiBotEngine()
        profile = engine.get_stealth_profile("example.com")
        vp = profile["viewport"]
        assert isinstance(vp, dict)
        assert "width" in vp
        assert "height" in vp

    def test_viewport_from_known_widths(self) -> None:
        engine = AntiBotEngine()
        samples: set[int] = set()
        for _ in range(100):
            profile = engine.get_stealth_profile("example.com")
            samples.add(profile["viewport"]["width"])
        for w in samples:
            assert w in self.KNOWN_WIDTHS, f"Unexpected width: {w}"

    def test_viewport_from_known_heights(self) -> None:
        engine = AntiBotEngine()
        samples: set[int] = set()
        for _ in range(100):
            profile = engine.get_stealth_profile("example.com")
            samples.add(profile["viewport"]["height"])
        for h in samples:
            assert h in self.KNOWN_HEIGHTS, f"Unexpected height: {h}"

    def test_all_known_widths_eventually_selected(self) -> None:
        engine = AntiBotEngine()
        seen: set[int] = set()
        for _ in range(500):
            profile = engine.get_stealth_profile("example.com")
            seen.add(profile["viewport"]["width"])
            if seen == self.KNOWN_WIDTHS:
                break
        assert seen == self.KNOWN_WIDTHS, f"Not all widths seen: missing {self.KNOWN_WIDTHS - seen}"

    def test_all_known_heights_eventually_selected(self) -> None:
        engine = AntiBotEngine()
        seen: set[int] = set()
        for _ in range(500):
            profile = engine.get_stealth_profile("example.com")
            seen.add(profile["viewport"]["height"])
            if seen == self.KNOWN_HEIGHTS:
                break
        assert seen == self.KNOWN_HEIGHTS, f"Not all heights seen: missing {self.KNOWN_HEIGHTS - seen}"

    def test_viewport_width_positive_int(self) -> None:
        engine = AntiBotEngine()
        for _ in range(50):
            profile = engine.get_stealth_profile("example.com")
            assert profile["viewport"]["width"] > 0
            assert isinstance(profile["viewport"]["width"], int)

    def test_viewport_height_positive_int(self) -> None:
        engine = AntiBotEngine()
        for _ in range(50):
            profile = engine.get_stealth_profile("example.com")
            assert profile["viewport"]["height"] > 0
            assert isinstance(profile["viewport"]["height"], int)

    def test_device_scale_factor_from_known_values(self) -> None:
        known = {1.0, 1.25, 1.5, 2.0}
        engine = AntiBotEngine()
        samples: set[float] = set()
        for _ in range(100):
            profile = engine.get_stealth_profile("example.com")
            samples.add(profile["device_scale_factor"])
        for dsf in samples:
            assert dsf in known, f"Unexpected device_scale_factor: {dsf}"

    def test_viewport_settings_loaded_from_config(self) -> None:
        widths = [int(x) for x in settings.STEALTH_VIEWPORT_WIDTHS.split(",")]
        heights = [int(x) for x in settings.STEALTH_VIEWPORT_HEIGHTS.split(",")]
        assert self.KNOWN_WIDTHS.issuperset(widths), f"Unexpected widths: {widths}"
        assert self.KNOWN_HEIGHTS.issuperset(heights), f"Unexpected heights: {heights}"
