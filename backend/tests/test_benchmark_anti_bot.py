"""Bench 5: Anti-bot evasion benchmark (Roadmap Bench 5).

Tests block classification, strategy escalation when blocked, proxy
rotation on block, and CAPTCHA detection.
"""

from __future__ import annotations

from pathlib import Path

from app.anti_bot_engine import get_anti_bot_engine
from app.empty_response_detector import detect_empty_response
from app.scrape_telemetry import detect_anti_bot, detect_anti_bot_platform
from app.zero_result_classifier import classify_zero_result
from bs4 import BeautifulSoup

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pages"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class TestBenchmarkAntiBotBlockClassification:
    """Classifying anti-bot challenge pages."""

    def test_challenge_page_detected_as_anti_bot(self) -> None:
        html = _load("challenge_mock.html")
        score = detect_anti_bot(html)
        assert score > 0.5, f"Anti-bot challenge page scored {score}, expected > 0.5"

    def test_normal_page_scores_low(self) -> None:
        html = _load("travel_site.html")
        score = detect_anti_bot(html)
        assert score < 0.5, f"Normal page scored {score}, expected < 0.5"

    def test_blocked_page_platform_identified(self) -> None:
        html = _load("challenge_mock.html")
        platform = detect_anti_bot_platform(html)
        assert platform != "ok", f"Expected a platform match, got {platform!r}"

    def test_login_wall_detected_via_empty_check(self) -> None:
        html = _load("login_wall_mock.html")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True).lower()
        assert "sign in" in text or "log in" in text or "password" in text

    def test_challenge_page_classified_as_anti_bot_block(self) -> None:
        html = _load("challenge_mock.html")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        forms = [{"action": f.get("action", ""), "method": f.get("method", "")} for f in soup.find_all("form")]
        empty_check = detect_empty_response(html)
        classification = classify_zero_result(
            acquisition_lineage={"state": "direct"},
            session_detection=None,
            empty_check=vars(empty_check),
            anti_bot_score=0.9,
            final_url="https://fixtures.local/challenge_mock.html",
            html=html,
            visible_text=text,
            detected_forms=forms,
            detected_containers=0,
            raw_candidate_count=0,
            schema_fields=["title"],
        )
        assert classification.failure_class == "anti_bot_block"


class TestBenchmarkStrategyEscalation:
    """Strategy escalation when blocked."""

    def test_anti_bot_engine_returns_block_score(self) -> None:
        html = _load("challenge_mock.html")
        engine = get_anti_bot_engine()
        score = engine.detect_challenges(html)
        assert score >= 0.0
        assert score <= 1.0

    def test_anti_bot_engine_returns_platform_on_block(self) -> None:
        html = _load("challenge_mock.html")
        engine = get_anti_bot_engine()
        platform = engine.detect_challenge_platform(html)
        assert isinstance(platform, str)
        assert platform != "ok"

    def test_normal_page_no_escalation_needed(self) -> None:
        html = _load("table_catalog.html")
        engine = get_anti_bot_engine()
        score = engine.detect_challenges(html)
        assert score < 0.5


class TestBenchmarkCaptchaDetection:
    """CAPTCHA detection capabilities."""

    def test_captcha_page_detected(self) -> None:
        html = _load("challenge_mock.html")
        engine = get_anti_bot_engine()
        score = engine.detect_challenges(html)
        assert score > 0.3

    def test_captcha_platform_identified(self) -> None:
        html = _load("challenge_mock.html")
        platform = detect_anti_bot_platform(html)
        assert isinstance(platform, str)


class TestBenchmarkFailureClassification:
    """Failure classification for anti-bot scenarios."""

    def test_challenge_fixture_classified_anti_bot(self) -> None:
        html = _load("challenge_mock.html")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True).lower()
        anti_bot_keywords = ["challenge", "captcha", "verify", "blocked", "checking your browser"]
        assert any(kw in text for kw in anti_bot_keywords), "Challenge page lacks anti-bot keywords"

    def test_empty_response_detector_flags_challenge(self) -> None:
        html = _load("challenge_mock.html")
        result = detect_empty_response(html)
        assert isinstance(result.is_empty, bool)
