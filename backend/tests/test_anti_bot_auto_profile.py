from __future__ import annotations

import pytest
from app.anti_bot_engine import AntiBotEngine


class TestAutoProfileSelection:
    def _engine(self) -> AntiBotEngine:
        return AntiBotEngine()

    def test_should_not_evolve_with_empty_history(self) -> None:
        engine = self._engine()
        assert engine.should_evolve_to_stealth("new-domain.com") is False

    def test_should_evolve_with_high_scores(self) -> None:
        engine = self._engine()
        engine.record_block("hard.com", 0.95)
        engine.record_block("hard.com", 0.85)
        engine.record_block("hard.com", 0.90)
        assert engine.should_evolve_to_stealth("hard.com") is True

    def test_should_not_evolve_with_low_scores(self) -> None:
        engine = self._engine()
        engine.record_block("easy.com", 0.1)
        engine.record_block("easy.com", 0.2)
        assert engine.should_evolve_to_stealth("easy.com") is False

    def test_should_evolve_when_mean_exceeds_threshold(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.anti_bot_engine.settings.ANTIBOT_STEALTH_ESCALATION_MEAN", 0.3)
        engine = self._engine()
        engine.record_block("medium.com", 0.35)
        engine.record_block("medium.com", 0.40)
        assert engine.should_evolve_to_stealth("medium.com") is True

    def test_domain_specific_cookie_ttl_shorter_with_hard_blocks(self) -> None:
        engine = self._engine()
        default_ttl = engine._domain_specific_cookie_ttl("stable.com", default=24)
        assert default_ttl == 24
        engine.record_block("attacked.com", 0.95)
        engine.record_block("attacked.com", 0.90)
        reduced_ttl = engine._domain_specific_cookie_ttl("attacked.com", default=24)
        assert reduced_ttl < 24
