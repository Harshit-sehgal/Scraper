"""Rate limiter SQLite persistence — verify DB-backed counters survive restarts.

Tests that ``DatabaseSlidingWindowCounter`` persists counters to SQLite
so that rate limit state survives process/container recreation.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from app.rate_limiter import (
    DatabaseSlidingWindowCounter,
    SlidingWindowCounter,
)

# The rate limiter imports ``settings`` via ``from app.config import settings``
# inside each method, so we must patch at the config module level.
_SETTINGS_PATCH = "app.config.settings"


def _sqlite_settings() -> MagicMock:
    """Return a mock settings with STORAGE_BACKEND='sqlite'."""
    mock = MagicMock()
    mock.STORAGE_BACKEND = "sqlite"
    mock.RATE_LIMIT_DB_BACKED = True
    return mock


class TestDatabaseSlidingWindowCounterCreation:
    """Verify DatabaseSlidingWindowCounter initialises correctly."""

    def test_inherits_max_and_window(self) -> None:
        """Counter must store the max_requests and window_seconds."""
        counter = DatabaseSlidingWindowCounter(10, 60.0, "test_key")
        assert counter.max_requests == 10
        assert counter.window_seconds == 60.0
        assert counter.key == "test_key"

    def test_fallback_counter_created(self) -> None:
        """Counter must have an in-memory fallback for DB failure."""
        counter = DatabaseSlidingWindowCounter(5, 30.0, "fb_key")
        assert isinstance(counter._fallback_counter, SlidingWindowCounter)
        assert counter._fallback_counter.max_requests == 5

    def test_not_initialized_by_default(self) -> None:
        """Counter must not hit the DB at construction time."""
        counter = DatabaseSlidingWindowCounter(10, 60.0, "lazy_key")
        assert counter._initialized is False


class TestDatabaseSlidingWindowCounterAllow:
    """Verify allow() inserts into SQLite when DB-backed."""

    def test_allow_returns_true_within_limit(self) -> None:
        """First request within limit must return True."""
        counter = DatabaseSlidingWindowCounter(5, 60.0, "allow:within")
        with patch(_SETTINGS_PATCH, _sqlite_settings()):
            result = counter.allow()
        assert result is True

    def test_allow_returns_false_at_limit(self) -> None:
        """Request exceeding limit must return False."""
        key = f"allow:atlimit:{time.time()}"
        counter = DatabaseSlidingWindowCounter(2, 60.0, key)
        with patch(_SETTINGS_PATCH, _sqlite_settings()):
            counter.allow()  # 1st
            counter.allow()  # 2nd
            result = counter.allow()  # 3rd — over limit
        assert result is False

    def test_allow_falls_back_on_db_error(self) -> None:
        """When SQLite raises, allow() must fall back to in-memory counter."""
        counter = DatabaseSlidingWindowCounter(10, 60.0, "allow:fallback")
        with (
            patch(_SETTINGS_PATCH, _sqlite_settings()),
            patch("app.job_store._get_connection", side_effect=OSError("db gone")),
        ):
            result = counter.allow()
        # Should still return a valid boolean (fallback behavior)
        assert isinstance(result, bool)


class TestDatabaseSlidingWindowCounterRemaining:
    """Verify remaining() queries SQLite for current count."""

    def test_remaining_returns_max_minus_count(self) -> None:
        """After N requests, remaining() must return max - N."""
        key = f"rem:count:{time.time()}"
        counter = DatabaseSlidingWindowCounter(10, 60.0, key)
        with patch(_SETTINGS_PATCH, _sqlite_settings()):
            counter.allow()
            counter.allow()
            rem = counter.remaining()
        assert rem == 8  # 10 - 2

    def test_remaining_falls_back_on_db_error(self) -> None:
        """When SQLite raises, remaining() must return fallback value."""
        counter = DatabaseSlidingWindowCounter(10, 60.0, "rem:fallback")
        with (
            patch(_SETTINGS_PATCH, _sqlite_settings()),
            patch("app.job_store._get_connection", side_effect=OSError("db gone")),
        ):
            rem = counter.remaining()
        # Falls back to in-memory counter which hasn't seen any requests
        assert rem >= 0


class TestDatabaseSlidingWindowCounterIsExpired:
    """Verify is_expired() checks recent DB entries."""

    def test_expired_when_no_recent_entries(self, monkeypatch) -> None:
        """Counter with no entries must report as expired."""
        counter = DatabaseSlidingWindowCounter(10, 0.001, "exp:gone")
        # window is 0.001s — anything recorded is long expired
        # Use a controllable clock to skip the real 20ms sleep that was
        # both slow and flaky (under CI load the 0.001s window could be
        # borderline missed).
        original_time = time.time
        post_record_time = [0.0]
        monkeypatch.setattr(
            "time.time",
            lambda: post_record_time[0] or original_time() + 0.02,
        )
        with patch(_SETTINGS_PATCH, _sqlite_settings()):
            counter.allow()
            post_record_time[0] = original_time() + 0.02
            assert counter.is_expired() is True

    def test_not_expired_within_window(self) -> None:
        """Counter with fresh entries must not report as expired."""
        key = f"exp:fresh:{time.time()}"
        counter = DatabaseSlidingWindowCounter(10, 600.0, key)
        with patch(_SETTINGS_PATCH, _sqlite_settings()):
            counter.allow()
            assert counter.is_expired() is False


class TestDatabaseSlidingWindowCounterResetIn:
    """Verify reset_in() returns correct seconds."""

    def test_reset_in_within_window(self) -> None:
        """reset_in() must return a value <= window_seconds."""
        key = f"reset:active:{time.time()}"
        counter = DatabaseSlidingWindowCounter(10, 60.0, key)
        with patch(_SETTINGS_PATCH, _sqlite_settings()):
            counter.allow()
            ri = counter.reset_in()
        assert 0 <= ri <= 60.0

    def test_reset_in_zero_when_empty(self) -> None:
        """reset_in() must return 0 when the counter has no entries."""
        # Use a unique key that hasn't been used
        counter = DatabaseSlidingWindowCounter(10, 60.0, "reset:empty:never_used")
        with patch(_SETTINGS_PATCH, _sqlite_settings()):
            # Don't call allow() — counter is empty
            ri = counter.reset_in()
        assert ri == 0.0


class TestPruneAll:
    """Verify DatabaseSlidingWindowCounter.prune_all() cleans old rows."""

    def test_prune_all_returns_int(self) -> None:
        """prune_all() must return an int (remaining row count)."""
        with patch(_SETTINGS_PATCH, _sqlite_settings()):
            result = DatabaseSlidingWindowCounter.prune_all()
        assert isinstance(result, int)

    def test_prune_all_removes_old_entries(self, monkeypatch) -> None:
        """After pruning, old entries must be gone."""
        key = f"prune:old:{time.time()}"
        counter = DatabaseSlidingWindowCounter(10, 0.001, key)
        # Skip the real 20ms sleep with a controllable clock — was both slow
        # and (under CI load) borderline: the 0.001s window plus a 20ms sleep
        # is the same shape of flakiness as test_db_sliding_window_counter_sqlite.
        original_time = time.time
        post_record_time = [original_time()]
        monkeypatch.setattr(
            "time.time",
            lambda: post_record_time[0],
        )
        with patch(_SETTINGS_PATCH, _sqlite_settings()):
            counter.allow()
            post_record_time[0] = original_time() + 0.02
            DatabaseSlidingWindowCounter.prune_all(max_age_seconds=0.01)
        # Counter should be expired after pruning
        with patch(_SETTINGS_PATCH, _sqlite_settings()):
            assert counter.is_expired() is True


class TestPersistenceAcrossInstances:
    """Verify counters survive process restart (new instance reads same DB)."""

    def test_new_instance_sees_prior_count(self) -> None:
        """A freshly constructed counter with the same key must see
        the rows written by a prior instance (SQLite persistence)."""
        key = f"persist:restart:{time.time()}"
        settings_mock = _sqlite_settings()

        # Instance 1: write 3 requests
        c1 = DatabaseSlidingWindowCounter(5, 60.0, key)
        with patch(_SETTINGS_PATCH, settings_mock):
            c1.allow()
            c1.allow()
            c1.allow()

        # Instance 2 (simulates restart): same key, same DB
        c2 = DatabaseSlidingWindowCounter(5, 60.0, key)
        with patch(_SETTINGS_PATCH, settings_mock):
            assert c2.remaining() == 2  # 5 - 3 from prior instance
            assert c2.allow() is True  # 4th request — still within limit
            assert c2.allow() is True  # 5th request — still within limit
            assert c2.allow() is False  # 6th — rejected
