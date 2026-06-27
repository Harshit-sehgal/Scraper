"""Anti-bot feedback loop — verify record_block/record_success are wired correctly.

Verifies that:
1. When anti_bot score >= hard block threshold, record_block() is called
2. When extraction succeeds, record_success() is called
3. The feedback loop activates adaptive behaviors (stealth escalation, etc.)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.config import settings
from app.anti_bot_engine import AntiBotEngine


class TestAntiBotFeedbackLoop:
    """Verify the anti-bot engine's record_block/record_success work correctly."""

    def test_record_block_stores_history(self) -> None:
        """record_block must store the score in _block_history."""
        engine = AntiBotEngine.__new__(AntiBotEngine)
        engine._block_history = {}
        engine._ua_history = {}
        engine._proxy_manager = MagicMock()
        engine._proxy_manager.enabled = False

        engine.record_block("example.com", 0.95)
        assert "example.com" in engine._block_history
        assert 0.95 in engine._block_history["example.com"]

    def test_record_block_triggers_proxy_failure_on_hard_block(self) -> None:
        """record_block must call proxy_manager.record_failure for hard blocks."""
        engine = AntiBotEngine.__new__(AntiBotEngine)
        engine._block_history = {}
        engine._ua_history = {}
        engine._proxy_manager = MagicMock()
        engine._proxy_manager.enabled = True

        engine.record_block("example.com", 0.95)
        engine._proxy_manager.record_failure.assert_called_once_with(domain="example.com")

    def test_record_block_no_proxy_failure_on_soft_block(self) -> None:
        """record_block must NOT call proxy_manager.record_failure for soft blocks."""
        engine = AntiBotEngine.__new__(AntiBotEngine)
        engine._block_history = {}
        engine._ua_history = {}
        engine._proxy_manager = MagicMock()
        engine._proxy_manager.enabled = True

        # Score below hard block threshold
        engine.record_block("example.com", 0.3)
        engine._proxy_manager.record_failure.assert_not_called()

    def test_record_block_no_proxy_failure_when_disabled(self) -> None:
        """record_block must not call proxy_manager when proxy rotation is disabled."""
        engine = AntiBotEngine.__new__(AntiBotEngine)
        engine._block_history = {}
        engine._ua_history = {}
        engine._proxy_manager = MagicMock()
        engine._proxy_manager.enabled = False

        engine.record_block("example.com", 0.95)
        engine._proxy_manager.record_failure.assert_not_called()

    def test_record_success_calls_proxy_success(self) -> None:
        """record_success must call proxy_manager.record_success when enabled."""
        engine = AntiBotEngine.__new__(AntiBotEngine)
        engine._ua_history = {}
        engine._proxy_manager = MagicMock()
        engine._proxy_manager.enabled = True

        engine.record_success("example.com")
        engine._proxy_manager.record_success.assert_called_once_with(domain="example.com")

    def test_record_success_noop_when_disabled(self) -> None:
        """record_success must not call proxy_manager when proxy rotation is disabled."""
        engine = AntiBotEngine.__new__(AntiBotEngine)
        engine._ua_history = {}
        engine._proxy_manager = MagicMock()
        engine._proxy_manager.enabled = False

        engine.record_success("example.com")
        engine._proxy_manager.record_success.assert_not_called()

    def test_block_history_bounded(self) -> None:
        """Block history must be bounded to ANTIBOT_BLOCK_HISTORY_SIZE."""
        engine = AntiBotEngine.__new__(AntiBotEngine)
        engine._block_history = {}
        engine._ua_history = {}
        engine._proxy_manager = MagicMock()
        engine._proxy_manager.enabled = False

        max_size = settings.ANTIBOT_BLOCK_HISTORY_SIZE
        for i in range(max_size + 5):
            engine.record_block("example.com", 0.5 + (i * 0.01))

        assert len(engine._block_history["example.com"]) <= max_size

    def test_stealth_escalation_after_blocks(self) -> None:
        """should_evolve_to_stealth must return True after sufficient hard blocks."""
        engine = AntiBotEngine.__new__(AntiBotEngine)
        engine._block_history = {}
        engine._ua_history = {}
        engine._proxy_manager = MagicMock()
        engine._proxy_manager.enabled = False

        # Initially, no stealth escalation
        assert not engine.should_evolve_to_stealth("example.com")

        # Record enough hard blocks to trigger escalation
        for _ in range(3):
            engine.record_block("example.com", 0.95)

        # Now it should want to escalate
        assert engine.should_evolve_to_stealth("example.com")