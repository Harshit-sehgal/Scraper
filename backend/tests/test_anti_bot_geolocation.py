from __future__ import annotations

import textwrap


def _build_geolocation_spoof_js(
    latitude: float = 40.7128,
    longitude: float = -74.0060,
    accuracy: float = 10.0,
) -> str:
    """Build JS to spoof navigator.geolocation."""
    return textwrap.dedent(f"""
    (function() {{
        const geo = {{latitude: {latitude}, longitude: {longitude}, accuracy: {accuracy}}};
        navigator.geolocation.getCurrentPosition = function(success) {{
            success({{coords: geo, timestamp: Date.now()}});
        }};
        navigator.geolocation.watchPosition = function(success) {{
            success({{coords: geo, timestamp: Date.now()}});
            return 0;
        }};
    }})();
    """)


def _extract_geolocation_from_profile(profile: dict) -> dict | None:
    """Extract geolocation coordinates from a stealth profile."""
    return profile.get("geolocation") or profile.get("geo")


class TestGeolocationSpoofing:
    """Anti 12: navigator.geolocation spoofing."""

    def test_spoof_js_generated(self) -> None:
        js = _build_geolocation_spoof_js()
        assert "getCurrentPosition" in js
        assert "40.7128" in js
        assert "longitude: -74.006" in js

    def test_spoof_js_contains_watch_position(self) -> None:
        js = _build_geolocation_spoof_js()
        assert "watchPosition" in js

    def test_spoof_js_contains_accuracy(self) -> None:
        js = _build_geolocation_spoof_js(accuracy=50.0)
        assert "accuracy: 50.0" in js

    def test_spoof_js_valid_syntax(self) -> None:
        js = _build_geolocation_spoof_js()
        assert js.count("(") == js.count(")")
        assert js.count("{") == js.count("}")

    def test_different_coordinates(self) -> None:
        js1 = _build_geolocation_spoof_js(51.5074, -0.1278)
        js2 = _build_geolocation_spoof_js(35.6762, 139.6503)
        assert "51.5074" in js1
        assert "35.6762" in js2
        assert js1 != js2

    def test_profile_geolocation_extraction(self) -> None:
        profile = {"viewport": {"width": 1920}, "geo": {"lat": 40.71, "lng": -74.00}}
        geo = _extract_geolocation_from_profile(profile)
        assert geo is not None
        assert geo["lat"] == 40.71

    def test_profile_missing_geolocation(self) -> None:
        profile = {"viewport": {"width": 1920}}
        assert _extract_geolocation_from_profile(profile) is None

    def test_stealth_context_has_geolocation_support(self) -> None:
        from app.browser_pool import BrowserPool

        pool = BrowserPool()
        opts = pool._build_stealth_context_options("example.com")
        assert isinstance(opts, dict)
        assert "geolocation" in opts
        geo = opts["geolocation"]
        assert "latitude" in geo
        assert "longitude" in geo
        assert "accuracy" in geo
        assert -90 <= geo["latitude"] <= 90
        assert -180 <= geo["longitude"] <= 180
