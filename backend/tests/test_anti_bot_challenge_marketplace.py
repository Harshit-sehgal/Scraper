from __future__ import annotations

from app.anti_bot_engine import AntiBotEngine


class TestChallengeDetection:
    def _engine(self) -> AntiBotEngine:
        return AntiBotEngine()

    def test_detect_challenges_returns_zero_for_clean_html(self) -> None:
        engine = self._engine()
        score = engine.detect_challenges("<html><body>normal content</body></html>")
        assert score == 0.0

    def test_detect_challenges_detects_cloudflare(self) -> None:
        engine = self._engine()
        score = engine.detect_challenges("<html>Checking your browser before accessing. cf-browser-verification</html>")
        assert score >= 0.9

    def test_detect_challenge_platform_identifies_cloudflare(self) -> None:
        engine = self._engine()
        platform = engine.detect_challenge_platform("<html>cf-challenge-platform content here</html>")
        assert platform == "cloudflare"

    def test_detect_challenge_platform_ok_for_clean(self) -> None:
        engine = self._engine()
        platform = engine.detect_challenge_platform("<html>normal page</html>")
        assert platform == "ok"

    def test_detect_challenge_platform_identifies_captcha(self) -> None:
        engine = self._engine()
        platform = engine.detect_challenge_platform("<html>g-recaptcha widget here</html>")
        assert platform == "captcha"

    def test_detect_challenge_platform_identifies_incapsula(self) -> None:
        engine = self._engine()
        platform = engine.detect_challenge_platform("<html>incapsula protection</html>")
        assert platform == "incapsula"

    def test_detect_challenges_score_increases_with_headers(self) -> None:
        engine = self._engine()
        score_no_hdr = engine.detect_challenges("<html>normal</html>")
        score_with_hdr = engine.detect_challenges(
            "<html>normal</html>",
            headers={"Server": "cloudflare"},
        )
        assert score_with_hdr >= score_no_hdr
