"""Unit Tests for Transaction Context.

Tests the ContextVar-based transaction context for the semantic substrate.
"""

from __future__ import annotations

from app.transaction_context import (
    active_transaction,
    get_active_transaction,
    is_in_transaction,
)


class TestTransactionContext:
    """Tests for get_active_transaction() and is_in_transaction()."""

    def test_default_is_none(self):
        """By default, no active transaction."""
        assert get_active_transaction() is None

    def test_default_not_in_transaction(self):
        """By default, is_in_transaction returns False."""
        assert is_in_transaction() is False

    def test_after_set_active(self):
        """After setting a transaction, get_active_transaction returns the data."""
        token = active_transaction.set({"key": "value"})
        try:
            assert get_active_transaction() == {"key": "value"}
            assert is_in_transaction() is True
        finally:
            active_transaction.reset(token)

    def test_after_reset_returns_none(self):
        """After resetting the context var, returns None."""
        token = active_transaction.set({"temp": "data"})
        active_transaction.reset(token)
        assert get_active_transaction() is None
        assert is_in_transaction() is False

    def test_nested_context(self):
        """Setting a new transaction within one works correctly."""
        token1 = active_transaction.set({"level": 1})
        token2 = active_transaction.set({"level": 2})
        try:
            assert get_active_transaction() == {"level": 2}
        finally:
            active_transaction.reset(token2)
            assert get_active_transaction() == {"level": 1}
            active_transaction.reset(token1)
            assert get_active_transaction() is None

    def test_empty_dict_is_valid(self):
        """An empty dict is a valid transaction context."""
        token = active_transaction.set({})
        try:
            assert get_active_transaction() == {}
            assert is_in_transaction() is True
        finally:
            active_transaction.reset(token)
