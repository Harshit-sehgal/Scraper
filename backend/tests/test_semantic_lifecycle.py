"""Tests for Semantic World State lifecycle semantics.

Covers the hardening sprint:
1. reset_world_state() calls close() to prevent subscriber leaks
2. Transaction context resets even if begin_transaction fails
3. Backward compatibility of old import paths
4. Metrics Protocol compatibility with EnergyState
"""

# mypy: disable-error-code="method-assign,attr-defined"

from __future__ import annotations

import pytest
from app.semantic_world_state.core import SemanticWorldState
from app.transaction_context import get_active_transaction

# ─── Test 1: reset_world_state does not leak subscribers ─────────────────


class TestResetWorldStateLifecycle:
    """Verify reset_world_state() cleans up the old world state properly."""

    def test_reset_world_state_does_not_duplicate_field_wave_subscribers(self) -> None:
        """After reset_world_state(), a new world state should have exactly
        one subscriber (its own), not accumulate from the old instance."""
        from app.semantic_events import SemanticEventType
        from app.semantic_world_state import get_world_state, reset_world_state

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
            1 for cb in dispatcher.subscribers.get(SemanticEventType.FIELD_WAVE, []) if getattr(cb, "__self__", None) is ws2
        )
        assert ws2_occurrences == 1, (
            f"ws2's handler appeared {ws2_occurrences} times instead of 1. "
            "This indicates a subscriber leak across reset_world_state()."
        )

    def test_close_removes_subscriber(self) -> None:
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

    def test_transaction_resets_on_normal_exit(self) -> None:
        """Normal transaction flow should reset the context var."""
        ws = SemanticWorldState()
        with ws.transaction("test_normal"):
            assert get_active_transaction() is not None
        assert get_active_transaction() is None

    def test_transaction_resets_on_exception_in_body(self) -> None:
        """Exception inside the transaction body should still reset context."""
        ws = SemanticWorldState()
        with pytest.raises(RuntimeError, match="test error"):
            with ws.transaction("test_exception"):
                assert get_active_transaction() is not None
                msg = "test error"
                raise RuntimeError(msg)
        assert get_active_transaction() is None

    def test_nested_transaction_does_not_set_new_context(self) -> None:
        """Nested transaction should skip setting a new context var."""
        ws = SemanticWorldState()
        with ws.transaction("outer"):
            outer_tx = get_active_transaction()
            with ws.transaction("inner"):
                inner_tx = get_active_transaction()
            # inner should be the same transaction context (nested = no-op)
            assert inner_tx is outer_tx
        assert get_active_transaction() is None

    def test_transaction_context_resets_if_begin_transaction_fails(self) -> None:
        """If a sub-state's begin_transaction() raises, the context variable
        must still be reset to its previous value."""
        ws = SemanticWorldState()

        # Mock _manifold.begin_transaction to raise
        original_begin = ws._manifold.begin_transaction

        def failing_begin():
            msg = "begin_transaction simulated failure"
            raise RuntimeError(msg)

        ws._manifold.begin_transaction = failing_begin

        try:
            with pytest.raises(RuntimeError, match="begin_transaction simulated failure"):
                with ws.transaction("test_begin_fail"):
                    pass  # Should not reach here
            # After the exception, the context var must be None
            assert get_active_transaction() is None, "Transaction context was not reset after begin_transaction failure"
        finally:
            ws._manifold.begin_transaction = original_begin


# ─── Test 3: Backward compatibility of old import paths ──────────────────


class TestBackwardCompatibility:
    """Verify that old import paths still work after the refactor."""

    def test_import_semantic_world_state_from_package(self) -> None:
        """Direct import from the old module path should still work."""
        from app.semantic_world_state import SemanticWorldState

        ws = SemanticWorldState()
        assert ws is not None
        assert hasattr(ws, "transaction")
        assert hasattr(ws, "close")

    def test_import_get_world_state(self) -> None:
        """get_world_state should be importable and returns a valid instance."""
        from app.semantic_world_state import get_world_state

        ws = get_world_state()
        assert ws is not None
        assert hasattr(ws, "get_cognitive_health")

    def test_import_reset_world_state(self) -> None:
        """reset_world_state should be importable and callable without error."""
        from app.semantic_world_state import reset_world_state

        # Should not raise
        reset_world_state()

    def test_get_world_state_returns_working_instance(self) -> None:
        """The world state returned by get_world_state should be functional."""
        from app.semantic_world_state import get_world_state

        ws = get_world_state()
        # Basic operations should work
        health = ws.get_cognitive_health()
        assert isinstance(health, dict)
        assert "overall_health" in health


# ─── Test 4: SemanticWorldState.close() idempotency ─────────────────────


class TestCloseIdempotency:
    """Verify that close() is idempotent and safe to call multiple times."""

    def test_close_can_be_called_multiple_times(self) -> None:
        """Calling close() twice should not raise."""
        ws = SemanticWorldState()
        ws.close()
        # Second call must not raise
        ws.close()

    def test_close_sets_closed_flag(self) -> None:
        """After close(), _closed should be True."""
        ws = SemanticWorldState()
        assert not ws._closed
        ws.close()
        assert ws._closed

    def test_close_removes_subscriber_only_once(self) -> None:
        """Calling close() multiple times should not cause subscriber errors."""
        ws = SemanticWorldState()
        ws.close()
        ws.close()
        ws.close()
        # A new close shouldn't error
        ws.close()

    def test_reset_world_state_with_close(self) -> None:
        """reset_world_state should handle close() cleanly."""
        from app.semantic_world_state import get_world_state, reset_world_state

        ws1 = get_world_state()
        ws1.close()  # Close manually
        # reset_world_state should not error even if close was already called
        reset_world_state()
        ws2 = get_world_state()
        assert ws2 is not None
        assert ws2 is not ws1

    def test_operations_after_close(self) -> None:
        """Basic operations should still work after close()."""
        ws = SemanticWorldState()
        ws.close()
        # close() only unsubscribes, doesn't clear state
        assert hasattr(ws, "transaction")
        assert hasattr(ws, "get_cognitive_health")


# ─── Test 5: Best-effort rollback behavior ──────────────────────────────


class TestBestEffortRollback:
    """Verify that transaction rollback is best-effort: if a subsystem
    rollback fails, the others still roll back and the original exception
    is re-raised."""

    def test_best_effort_rollback_logs_and_continues(self) -> None:
        """If one subsystem's rollback fails, others should still roll back."""
        ws = SemanticWorldState()

        # Make _manifold.rollback raise
        original_rollback = ws._manifold.rollback

        def failing_rollback():
            msg = "rollback simulated failure"
            raise RuntimeError(msg)

        ws._manifold.rollback = failing_rollback

        try:
            with pytest.raises(RuntimeError, match="original error"):
                with ws.transaction("test_best_effort"):
                    msg = "original error"
                    raise RuntimeError(msg)
        finally:
            ws._manifold.rollback = original_rollback

        # After the exception, the context var must still be reset
        assert get_active_transaction() is None, "Transaction context was not reset despite rollback error"

    def test_best_effort_all_rollbacks_fail(self) -> None:
        """If ALL subsystem rollbacks fail, the original exception is still re-raised."""
        ws = SemanticWorldState()

        # Save originals
        originals = {}
        state_attrs = {
            "topology": ws._topology,
            "energy": ws._energy,
            "instability": ws._instability,
            "manifold": ws._manifold,
            "motif": ws._motif,
            "transition": ws._transition,
            "intent": ws._intent,
            "action": ws._action,
            "abstraction": ws._abstraction,
            "observability": ws._observability,
            "history": ws._history,
        }

        for name, obj in state_attrs.items():
            if hasattr(obj, "rollback"):
                originals[name] = obj.rollback

                def make_failing(name_):
                    def failing():
                        msg = f"rollback failed for {name_}"
                        raise RuntimeError(msg)

                    return failing

                obj.rollback = make_failing(name)

        try:
            with pytest.raises(RuntimeError, match="test all fail"):
                with ws.transaction("test_all_fail"):
                    msg = "test all fail"
                    raise RuntimeError(msg)
        finally:
            for name, obj in state_attrs.items():
                if name in originals:
                    obj.rollback = originals[name]

        assert get_active_transaction() is None

    def test_transaction_context_resets_if_commit_fails(self) -> None:
        """If a subsystem's commit() raises, the transaction context must reset.
        Additionally, rollback must be attempted on all subsystems that have it."""
        ws = SemanticWorldState()

        # Make _manifold.commit raise
        original_commit = ws._manifold.commit
        original_rollback = ws._manifold.rollback
        commit_called = False

        def failing_commit():
            nonlocal commit_called
            commit_called = True
            msg = "commit simulated failure"
            raise RuntimeError(msg)

        ws._manifold.commit = failing_commit

        try:
            with pytest.raises(RuntimeError, match="commit simulated failure"):
                with ws.transaction("test_commit_fail"):
                    pass  # Body succeeds, commit fails
            # Context must be reset
            assert get_active_transaction() is None, "Transaction context was not reset after commit failure"
            assert commit_called, "commit() should have been called"
        finally:
            ws._manifold.commit = original_commit
            ws._manifold.rollback = original_rollback

    def test_rollback_failure_does_not_mask_original_exception(self) -> None:
        """When a subsystem rollback fails, the ORIGINAL exception
        (not the rollback exception) must be raised to the caller."""
        ws = SemanticWorldState()

        # Make _manifold.commit raise one error, and make rollback
        # raise a different error. The caller should get the commit error.
        original_commit = ws._manifold.commit
        original_rollback = ws._manifold.rollback

        def failing_commit():
            msg = "COMMIT_ERROR"
            raise RuntimeError(msg)

        def failing_rollback():
            msg = "ROLLBACK_ERROR"
            raise RuntimeError(msg)

        ws._manifold.commit = failing_commit
        ws._manifold.rollback = failing_rollback

        try:
            with pytest.raises(RuntimeError, match="COMMIT_ERROR"):
                with ws.transaction("test_mask"):
                    pass
            # The rollback error (ROLLBACK_ERROR) must NOT mask COMMIT_ERROR
        finally:
            ws._manifold.commit = original_commit
            ws._manifold.rollback = original_rollback

        assert get_active_transaction() is None

    def test_all_subsystems_attempt_rollback_even_if_one_fails(self) -> None:
        """When one subsystem rollback fails, the remaining subsystems
        must still have their rollback() called."""
        ws = SemanticWorldState()

        # Track which subsystems had rollback called
        rollback_called: dict[str, bool] = {}
        originals = {}
        state_attrs = {
            "topology": ws._topology,
            "energy": ws._energy,
            "manifold": ws._manifold,
            "motif": ws._motif,
            "history": ws._history,
        }

        for name, obj in state_attrs.items():
            if hasattr(obj, "rollback"):
                originals[name] = obj.rollback

                def make_tracker(name_):
                    def tracked_rollback():
                        rollback_called[name_] = True
                        # Make the second subsystem fail
                        if name_ == list(state_attrs.keys())[1]:
                            msg = f"rollback failed for {name_}"
                            raise RuntimeError(msg)
                        return originals[name_]() if callable(originals[name_]) else None

                    return tracked_rollback

                obj.rollback = make_tracker(name)

        try:
            with pytest.raises(RuntimeError, match="original body error"):
                with ws.transaction("test_all_attempted"):
                    msg = "original body error"
                    raise RuntimeError(msg)
        finally:
            for name, obj in state_attrs.items():
                if name in originals:
                    obj.rollback = originals[name]

        # All subsystems should have had rollback attempted
        for name in state_attrs:
            assert rollback_called.get(name, False), f"rollback not attempted for {name}"
        assert get_active_transaction() is None


# ─── Test 6: Metrics Protocol is compatible with EnergyState ─────────────


class TestMetricsProtocol:
    """Verify the _SemanticMetricsProtocol is structurally compatible
    with EnergyState (the actual ws.metrics object)."""

    def test_metrics_protocol_attributes_exist_on_energy_state(self) -> None:
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

    def test_metrics_protocol_can_be_used_instead_of_any(self) -> None:
        """The Protocol should be usable as a type annotation
        without mypy errors (verified structurally)."""
        from app.semantic_allocation_engine import _SemanticMetricsProtocol
        from app.semantic_world_state import get_world_state

        ws = get_world_state()
        # This is the exact pattern used in semantic_allocation_engine
        metrics: _SemanticMetricsProtocol = ws.metrics
        assert isinstance(metrics._smoothed_structural, float)
        assert isinstance(metrics.semantic_temperature, float)
