from __future__ import annotations

from app.anti_bot_engine import AntiBotEngine


class TestSessionPersistence:
    def _fresh_engine(self) -> AntiBotEngine:
        return AntiBotEngine()

    def test_update_cookies_persists_to_cache(self) -> None:
        engine = self._fresh_engine()
        engine.update_cookies("example.com", "session=abc123")
        assert engine.get_cookies("example.com") == "session=abc123"

    def test_get_cookies_returns_empty_for_unknown_domain(self) -> None:
        engine = self._fresh_engine()
        assert engine.get_cookies("unknown.com") == ""

    def test_should_refresh_cookies_true_for_unknown(self) -> None:
        engine = self._fresh_engine()
        assert engine.should_refresh_cookies("new-domain.com") is True

    def test_should_refresh_cookies_false_when_recent(self) -> None:
        engine = self._fresh_engine()
        engine.update_cookies("recent.com", "token=xyz")
        assert engine.should_refresh_cookies("recent.com", max_age_hours=24) is False

    def test_cookies_persist_across_operations(self) -> None:
        engine = self._fresh_engine()
        engine.update_cookies("multi.com", "data=persist")
        assert engine.get_cookies("multi.com") == "data=persist"
        engine.update_cookies("multi.com", "data=updated")
        assert engine.get_cookies("multi.com") == "data=updated"

    def test_record_block_history(self) -> None:
        engine = self._fresh_engine()
        engine.record_block("blocked.com", 0.95)
        engine.record_block("blocked.com", 0.85)
        assert engine.should_evolve_to_stealth("blocked.com") is True
