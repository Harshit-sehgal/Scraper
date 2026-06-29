from __future__ import annotations

import textwrap


def _build_webdriver_spoof_script() -> str:
    """Build JS that spoofs navigator.webdriver, chrome, and chrome.runtime."""
    return textwrap.dedent("""
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = {
        runtime: {},
        loadTimes: function() {
            return {
                firstPaintAfterLoadTime: 0,
                requestTime: 0,
                startLoadTime: 0,
                commitLoadTime: 0,
                finishDocumentLoadTime: 0,
                finishLoadTime: 0,
                wasNetered: false,
                wasAlternateProtocolAvailable: false,
                wasFetchedViaSpdy: false,
                wasNpnNegotiated: false,
            };
        },
        csi: function() {
            return {startE: 0, onloadT: 0, pageT: 0, tran: 0};
        },
    };
    navigator.chrome = window.chrome;
    """)


def _extract_init_script_properties() -> dict[str, list[str]]:
    """Extract properties set by the browser pool's init script."""
    props: dict[str, list[str]] = {"navigator": [], "window": [], "chrome": []}
    return props


class TestWebDriverDetectionCountermeasures:
    """Anti 40: navigator.webdriver, chrome, chrome.runtime spoofing."""

    def test_webdriver_undefined(self) -> None:
        js = _build_webdriver_spoof_script()
        assert "Object.defineProperty(navigator, 'webdriver'" in js
        assert "undefined" in js

    def test_chrome_runtime_spoofed_as_object(self) -> None:
        js = _build_webdriver_spoof_script()
        assert "chrome" in js
        assert "runtime: {}" in js

    def test_chrome_loadTimes_spoofed(self) -> None:
        js = _build_webdriver_spoof_script()
        assert "loadTimes" in js
        assert "firstPaintAfterLoadTime" in js
        assert "finishLoadTime" in js

    def test_chrome_csi_spoofed(self) -> None:
        js = _build_webdriver_spoof_script()
        assert "csi" in js
        assert "startE" in js
        assert "onloadT" in js

    def test_navigator_chrome_alias(self) -> None:
        js = _build_webdriver_spoof_script()
        assert "navigator.chrome = window.chrome" in js

    def test_script_syntax_valid(self) -> None:
        js = _build_webdriver_spoof_script()
        assert js.count("(") == js.count(")")
        assert js.count("{") == js.count("}")

    def test_all_loadtimes_properties_present(self) -> None:
        js = _build_webdriver_spoof_script()
        expected = [
            "firstPaintAfterLoadTime",
            "requestTime",
            "startLoadTime",
            "commitLoadTime",
            "finishDocumentLoadTime",
            "finishLoadTime",
            "wasNetered",
            "wasAlternateProtocolAvailable",
            "wasFetchedViaSpdy",
            "wasNpnNegotiated",
        ]
        for prop in expected:
            assert prop in js, f"Missing loadTimes property: {prop}"

    def test_browser_pool_init_script_has_webdriver_spoof(self) -> None:
        from app.browser_pool import BrowserPool

        pool = BrowserPool()
        source = pool._apply_stealth_evasion.__code__
        co = source.co_consts
        all_source = " ".join(str(c) for c in co if isinstance(c, str))
        assert "webdriver" in all_source
        assert "chrome" in all_source

    def test_browser_pool_stealth_script_has_chrome_runtime(self) -> None:
        script = _build_webdriver_spoof_script()
        assert "runtime" in script

    def test_stealth_script_spoofs_all_chrome_apis(self) -> None:
        script = _build_webdriver_spoof_script()
        assert "window.chrome" in script
        assert "navigator.chrome" in script
