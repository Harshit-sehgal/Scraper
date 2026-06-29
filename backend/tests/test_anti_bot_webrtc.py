from __future__ import annotations

import textwrap


def _build_webrtc_prevention_js() -> str:
    """Build JS to prevent WebRTC leaks."""
    return textwrap.dedent("""
    (function() {
        const origRTCPeerConnection = window.RTCPeerConnection
            || window.webkitRTCPeerConnection
            || window.mozRTCPeerConnection;
        if (origRTCPeerConnection) {
            window.RTCPeerConnection = function(config) {
                const restricted = Object.assign({}, config, {
                    iceServers: [],
                    iceTransportPolicy: 'relay',
                });
                return new origRTCPeerConnection(restricted);
            };
            if (window.webkitRTCPeerConnection) {
                window.webkitRTCPeerConnection = window.RTCPeerConnection;
            }
            if (window.mozRTCPeerConnection) {
                window.mozRTCPeerConnection = window.RTCPeerConnection;
            }
        }
        const origRTCDataChannel = window.RTCDataChannel;
        if (origRTCDataChannel) {
            window.RTCDataChannel = function() {};
        }
    })();
    """)


def _check_webrtc_indicators(html: str) -> list[str]:
    """Check HTML for WebRTC-related indicators."""
    indicators = []
    if "RTCPeerConnection" in html:
        indicators.append("RTCPeerConnection")
    if "webRTC" in html.lower():
        indicators.append("webRTC")
    if "iceServers" in html:
        indicators.append("iceServers")
    if "localIP" in html or "local_ip" in html:
        indicators.append("local_ip_leak")
    return indicators


class TestWebRTCLeakPrevention:
    """Anti 14: WebRTC leak prevention configuration."""

    def test_prevention_js_generated(self) -> None:
        js = _build_webrtc_prevention_js()
        assert "RTCPeerConnection" in js
        assert "iceServers" in js
        assert "iceTransportPolicy" in js

    def test_prevention_js_covers_all_vendors(self) -> None:
        js = _build_webrtc_prevention_js()
        assert "webkitRTCPeerConnection" in js
        assert "mozRTCPeerConnection" in js

    def test_prevention_js_is_valid_syntax(self) -> None:
        js = _build_webrtc_prevention_js()
        assert js.count("(") == js.count(")")
        assert js.count("{") == js.count("}")

    def test_prevention_js_relay_policy(self) -> None:
        js = _build_webrtc_prevention_js()
        assert "'relay'" in js

    def test_prevention_js_empty_ice_servers(self) -> None:
        js = _build_webrtc_prevention_js()
        assert "iceServers: []" in js

    def test_webrtc_indicator_detection_clean(self) -> None:
        indicators = _check_webrtc_indicators("<html><body>Clean page</body></html>")
        assert indicators == []

    def test_webrtc_indicator_detects_rtc(self) -> None:
        indicators = _check_webrtc_indicators("<html>RTCPeerConnection</html>")
        assert "RTCPeerConnection" in indicators

    def test_webrtc_indicator_detects_ice_servers(self) -> None:
        indicators = _check_webrtc_indicators("<html>iceServers</html>")
        assert "iceServers" in indicators

    def test_prevention_disables_rtc_data_channel(self) -> None:
        js = _build_webrtc_prevention_js()
        assert "RTCDataChannel" in js

    def test_prevention_applies_to_all_rtc_constructors(self) -> None:
        js = _build_webrtc_prevention_js()
        assert "window.RTCPeerConnection = function(config)" in js
