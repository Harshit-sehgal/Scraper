"""Tests for app.anti_bot_engine — classification accuracy and retry policy.

These are focused regressions for the scraper-quality hardening in this
pass:

1. Header cookies must classify to their correct platform (``_abck``
   → akamai, ``_px`` → perimeterx, ``datadome`` → datadome,
   ``incap_ses`` → incapsula). Previously every anti-bot cookie name
   was reported as ``"captcha"`` which masked platform-specific signals
   from observability metrics.

2. ``get_retry_policy`` must apply bounded jitter (±25 % of the
   configured delay) so concurrent scrapers don't retry in lockstep
   and amplify the burst pattern.

3. Detection must remain status-agnostic but a Cloudflare/Server header
   challenge still classifies as the right platform even when there is
   no body match.
"""

from __future__ import annotations

import pytest
from app.anti_bot_engine import AntiBotEngine

# ─── Header cookie classification ──────────────────────────────────────


class TestHeaderCookieClassification:
    """Cookie names must map to their specific anti-bot platform."""

    def _engine(self) -> AntiBotEngine:
        return AntiBotEngine()

    def test_akamai_cookie_classifies_as_akamai(self) -> None:
        engine = self._engine()
        result = engine.detect_challenge_platform(
            "<html>normal page</html>",
            headers={"Set-Cookie": "akamai_bot_detector=_abck=value; path=/"},
        )
        assert result == "akamai"

    @pytest.mark.parametrize(
        ("cookie_value", "expected_platform"),
        [
            ("_px=abc123; path=/", "perimeterx"),
            ("datadome=foo; path=/", "datadome"),
            ("incap_ses_1234=value; path=/", "incapsula"),
        ],
    )
    def test_cookie_disambiguation(self, cookie_value: str, expected_platform: str) -> None:
        engine = self._engine()
        result = engine.detect_challenge_platform(
            "<html>normal page</html>",
            headers={"Set-Cookie": cookie_value},
        )
        assert result == expected_platform

    def test_cloudflare_server_header_classifies_even_without_cookie(self) -> None:
        engine = self._engine()
        result = engine.detect_challenge_platform(
            "<html>plain body</html>",
            headers={"Server": "cloudflare"},
        )
        assert result == "cloudflare"

    def test_unknown_signals_return_ok(self) -> None:
        engine = self._engine()
        # No headers at all → "ok"
        assert engine.detect_challenge_platform("<html></html>") == "ok"
        # Unrelated cookie → "ok"
        assert engine.detect_challenge_platform("<html></html>", headers={"Set-Cookie": "session_id=abc"}) == "ok"


# ─── Retry policy jitter ───────────────────────────────────────────────


class TestRetryPolicyJitter:
    """``get_retry_policy`` must add jitter to delays, bounded to ±25 %."""

    def test_hard_block_delay_jittered_within_bounds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.anti_bot_engine.settings.ANTIBOT_HARD_BLOCK_DELAY", 100)
        monkeypatch.setattr("app.anti_bot_engine.settings.ANTIBOT_HARD_BLOCK_THRESHOLD", 0.8)
        monkeypatch.setattr("app.anti_bot_engine.settings.PROXY_ROTATION_ENABLED", False)
        engine = AntiBotEngine()
        samples = [engine.get_retry_policy("https://target.example/x", last_score=0.95)["delay"] for _ in range(200)]
        # Bounds: 100 * 0.75 = 75 .. 100 * 1.25 = 125
        assert min(samples) >= 70, f"jitter below bound: {min(samples)}"
        assert max(samples) <= 130, f"jitter above bound: {max(samples)}"

    def test_medium_challenge_delay_jittered_within_bounds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.anti_bot_engine.settings.ANTIBOT_MEDIUM_CHALLENGE_DELAY", 40)
        monkeypatch.setattr("app.anti_bot_engine.settings.PROXY_ROTATION_ENABLED", False)
        engine = AntiBotEngine()
        samples = [engine.get_retry_policy("https://target.example/x", last_score=0.6)["delay"] for _ in range(200)]
        assert min(samples) >= 28
        assert max(samples) <= 52

    def test_low_score_keeps_zero_delay(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.anti_bot_engine.settings.PROXY_ROTATION_ENABLED", False)
        engine = AntiBotEngine()
        for _ in range(20):
            policy = engine.get_retry_policy("https://target.example/x", last_score=0.1)
            assert policy["delay"] == 0
            assert policy["action"] == "continue"

    def test_no_lockstep_across_workers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.anti_bot_engine.settings.ANTIBOT_HARD_BLOCK_DELAY", 100)
        monkeypatch.setattr("app.anti_bot_engine.settings.ANTIBOT_HARD_BLOCK_THRESHOLD", 0.8)
        monkeypatch.setattr("app.anti_bot_engine.settings.PROXY_ROTATION_ENABLED", False)
        engine = AntiBotEngine()
        delays = {engine.get_retry_policy("https://target.example/x", last_score=0.95)["delay"] for _ in range(100)}
        # At least 5 distinct delays across 100 random samples is the
        # expected spread for ±25 % jitter.
        assert len(delays) >= 5
