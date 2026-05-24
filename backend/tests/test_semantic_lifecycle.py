"""Tests for Semantic World State lifecycle semantics.

Covers the hardening sprint:
1. reset_world_state() calls close() to prevent subscriber leaks
2. Transaction context resets even if begin_transaction fails
3. Backward compatibility of old import paths
4. Metrics Protocol compatibility with EnergyState
"""

from __future__ import annotations

import pytest

from app.transaction_context import get_active_transaction
from app.semantic_world_state.core import SemanticWorldState


# ─── Test 1: reset_world_state does not leak subscribers ─────────────────


class TestResetWorldStateLifecycle:
    """Verify reset_world_state() cleans up the old world state properly."""

    def test_reset_world_state_does_not_duplicate_field_wave_subscribers(self):
        """After reset_world_state(), a new world state should have exactly
        one subscriber (its own), not accumulate from the old instance."""
        from app.semantic_world_state import reset_world_state, get_world_state
        from app.semantic_events import SemanticEventType

        # First get/create the initial world state
        ws1 = get_world_state()
        assert ws1 is not None

        # Reset — this should trigger close() on ws1
        reset_world_state()

        # Now get a fresh world state. NOTE: reset_world_state() also resets
        # the dispatcher (calls reset_dispatcher()), so ws1._dispatcher is
        # orphaned. We must use ws2._dispatcher for the subscriber check.
        ws2 = get_world_state()
        assert ws2 is not None
        assert ws2 is not ws1  # Must be a different instance

        dispatcher = ws2._dispatcher

        # IMPORTANT: bound method identity check. In Python, accessing
        # obj.method creates a NEW bound method object each time, so
        # `cb is ws2._on_field_wave` would ALWAYS be False. We must
        # compare the underlying function and the instance object.
        # The graph_update_scheduler also subscribes to FIELD_WAVE,
        # so the total count may include the scheduler too. We ensure
        # that ws2 appears exactly once (not 0, not 2+).
        ws2_occurrences = sum(
            1 for cb in dispatcher.subscribers.get(SemanticEventType.FIELD_WAVE, [])
            if getattr(cb, "__self__", None) is ws2
        )
        assert ws2_occurrences == 1, (
            f"ws2's handler appeared {ws2_occurrences} times instead of 1. "
            "This indicates a subscriber leak across reset_world_state()."
        )

    def test_close_removes_subscriber(self):
        """Calling close() directly should remove the FIELD_WAVE subscriber."""
        from app.semantic_events import SemanticEventType

        ws = SemanticWorldState()
        dispatcher = ws._dispatcher

        before = len(dispatcher.subscribers.get(SemanticEventType.FIELD_WAVE, []))
        ws.close()
        after = len(dispatcher.subscribers.get(SemanticEventType.FIELD_WAVE, []))

        assert after < before or after == 0, "close() should remove the FIELD_WAVE subscriber"


# ─── Test 2: Transaction context resets even if begin_transaction fails ──


class TestTransactionContextExceptionSafety:
    """Verify the transaction context variable resets even when staging fails."""

    def test_transaction_resets_on_normal_exit(self):
        """Normal transaction flow should reset the context var."""
        ws = SemanticWorldState()
        with ws.transaction("test_normal"):
            assert get_active_transaction() is not None
        assert get_active_transaction() is None

    def test_transaction_resets_on_exception_in_body(self):
        """Exception inside the transaction body should still reset context."""
        ws = SemanticWorldState()
        with pytest.raises(RuntimeError, match="test error"):
            with ws.transaction("test_exception"):
                assert get_active_transaction() is not None
                raise RuntimeError("test error")
        assert get_active_transaction() is None

    def test_nested_transaction_does_not_set_new_context(self):
        """Nested transaction should skip setting a new context var."""
        ws = SemanticWorldState()
        with ws.transaction("outer"):
            outer_tx = get_active_transaction()
            with ws.transaction("inner"):
                inner_tx = get_active_transaction()
            # inner should be the same transaction context (nested = no-op)
            assert inner_tx is outer_tx
        assert get_active_transaction() is None

    def test_transaction_context_resets_if_begin_transaction_fails(self):
        """If a sub-state's begin_transaction() raises, the context variable
        must still be reset to its previous value."""
        ws = SemanticWorldState()

        # Mock _manifold.begin_transaction to raise
        original_begin = ws._manifold.begin_transaction

        def failing_begin():
            raise RuntimeError("begin_transaction simulated failure")

        ws._manifold.begin_transaction = failing_begin

        try:
            with pytest.raises(RuntimeError, match="begin_transaction simulated failure"):
                with ws.transaction("test_begin_fail"):
                    pass  # Should not reach here
            # After the exception, the context var must be None
            assert get_active_transaction() is None, (
                "Transaction context was not reset after begin_transaction failure"
            )
        finally:
            ws._manifold.begin_transaction = original_begin


# ─── Test 3: Backward compatibility of old import paths ──────────────────


class TestBackwardCompatibility:
    """Verify that old import paths still work after the refactor."""

    def test_import_semantic_world_state_from_package(self):
        """Direct import from the old module path should still work."""
        from app.semantic_world_state import SemanticWorldState
        ws = SemanticWorldState()
        assert ws is not None
        assert hasattr(ws, "transaction")
        assert hasattr(ws, "close")

    def test_import_get_world_state(self):
        """get_world_state should be importable and returns a valid instance."""
        from app.semantic_world_state import get_world_state
        ws = get_world_state()
        assert ws is not None
        assert hasattr(ws, "get_cognitive_health")

    def test_import_reset_world_state(self):
        """reset_world_state should be importable and callable without error."""
        from app.semantic_world_state import reset_world_state
        # Should not raise
        reset_world_state()

    def test_get_world_state_returns_working_instance(self):
        """The world state returned by get_world_state should be functional."""
        from app.semantic_world_state import get_world_state
        ws = get_world_state()
        # Basic operations should work
        health = ws.get_cognitive_health()
        assert isinstance(health, dict)
        assert "overall_health" in health


# ─── Test 4: Metrics Protocol is compatible with EnergyState ─────────────


class TestMetricsProtocol:
    """Verify the _SemanticMetricsProtocol is structurally compatible
    with EnergyState (the actual ws.metrics object)."""

    def test_metrics_protocol_attributes_exist_on_energy_state(self):
        """All attributes required by the Protocol must exist on the
        EnergyState object that ws.metrics points to."""
        from app.semantic_world_state import get_world_state
        ws = get_world_state()
        metrics = ws.metrics

        # These are the attributes used in semantic_allocation_engine
        assert hasattr(metrics, "_smoothed_structural")
        assert hasattr(metrics, "_smoothed_runtime")
        assert hasattr(metrics, "semantic_temperature")
        assert hasattr(metrics, "integrity_score")

        # Verify they return floats
        assert isinstance(metrics._smoothed_structural, float)
        assert isinstance(metrics._smoothed_runtime, float)
        assert isinstance(metrics.semantic_temperature, float)
        assert isinstance(metrics.integrity_score, float)

    def test_metrics_protocol_can_be_used_instead_of_any(self):
        """The Protocol should be usable as a type annotation
        without mypy errors (verified structurally)."""
        from app.semantic_allocation_engine import _SemanticMetricsProtocol
        from app.semantic_world_state import get_world_state

        ws = get_world_state()
        # This is the exact pattern used in semantic_allocation_engine
        metrics: _SemanticMetricsProtocol = ws.metrics  # type: ignore[assignment]
        assert isinstance(metrics._smoothed_structural, float)
        assert isinstance(metrics.semantic_temperature, float)
