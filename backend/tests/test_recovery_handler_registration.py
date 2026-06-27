"""Recovery handler registration — verify handlers are always registered.

Ensures that register_all_recovery_handlers is called regardless of the
ENABLE_EXPERIMENTAL_ROUTES setting.
"""

from __future__ import annotations

from unittest.mock import patch

from app.recovery_strategies import RecoveryAction, get_recovery_executor


class TestRecoveryHandlerRegistration:
    """Verify recovery handlers are always registered."""

    def test_rich_handlers_registered_by_default(self) -> None:
        """After register_all_recovery_handlers, the executor must use the
        rich handlers from recovery_handlers.py (not the stub builtins)."""
        from app.recovery_handlers import register_all_recovery_handlers

        # Get a fresh executor
        from app.recovery_strategies import RecoveryExecutor, _register_builtin_handlers

        executor = RecoveryExecutor()
        _register_builtin_handlers(executor)

        # Before: handler comes from recovery_strategies (builtins)
        builtin_handler = executor.action_handlers.get(RecoveryAction.ROTATE_PROXY)
        assert builtin_handler is not None
        assert getattr(builtin_handler, "__module__", "") == "app.recovery_strategies"

        # After: handler comes from recovery_handlers (rich)
        register_all_recovery_handlers()
        executor = get_recovery_executor()
        rich_handler = executor.action_handlers.get(RecoveryAction.ROTATE_PROXY)
        assert rich_handler is not None
        assert getattr(rich_handler, "__module__", "") == "app.recovery_handlers"

    def test_all_actions_have_handlers(self) -> None:
        """All RecoveryAction enum values must have registered handlers."""
        executor = get_recovery_executor()
        for action in RecoveryAction:
            handler = executor.action_handlers.get(action)
            assert handler is not None, f"RecoveryAction.{action.name} must have a handler"

    def test_init_recovery_framework_no_guard(self) -> None:
        """init_recovery_framework must NOT be gated behind ENABLE_EXPERIMENTAL_ROUTES."""
        from app.experimental_startup import init_recovery_framework

        # Even with experimental routes disabled, registration should proceed.
        with (
            patch("app.recovery_handlers.register_all_recovery_handlers") as mock_reg,
            patch("app.experimental_startup.experimental_subsystems_enabled", return_value=False),
        ):
            init_recovery_framework()
            mock_reg.assert_called_once()
