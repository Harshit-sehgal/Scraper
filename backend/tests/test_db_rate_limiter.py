import time

from app.rate_limiter import DatabaseSlidingWindowCounter, RateLimiterMiddleware


def _cleanup_rate_limit_key(key: str) -> None:
    """Remove test data from the active backend's rate_limits table."""
    from app.config import settings

    backend = settings.STORAGE_BACKEND
    if backend == "postgres":
        try:
            from app.postgres_repository import _conn, _execute

            with _conn() as conn:
                _execute(conn, "DELETE FROM rate_limits WHERE key = %s", (key,))
        except Exception:
            pass
    else:
        try:
            from app.job_store import _DB_LOCK, _get_connection

            with _DB_LOCK:
                conn = _get_connection()
                try:
                    conn.execute("DELETE FROM rate_limits WHERE key = ?", (key,))
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            pass


def _generate_test_key() -> str:
    """Generate a unique test key to avoid collisions with other tests."""
    import os

    return f"_test_sliding_window_{os.urandom(4).hex()}_"


def test_db_sliding_window_counter_sqlite() -> None:
    """Verify that DatabaseSlidingWindowCounter behaves correctly using SQLite storage.

    Uses a randomly generated unique key to avoid colliding with other tests that share
    the same rate_limits table. Cleans up test data before and after from the
    active backend (SQLite or Postgres).
    """
    test_key = _generate_test_key()
    _cleanup_rate_limit_key(test_key)
    counter = DatabaseSlidingWindowCounter(max_requests=3, window_seconds=2.0, key=test_key)

    try:
        # Verify initial limit state
        assert counter.remaining() == 3
        assert counter.reset_in() == 0.0

        # First request
        assert counter.allow() is True
        assert counter.remaining() == 2

        # Second and third requests
        assert counter.allow() is True
        assert counter.allow() is True
        assert counter.remaining() == 0

        # Fourth request should be blocked
        assert counter.allow() is False

        # Wait for the window to reset
        time.sleep(2.1)
        assert counter.remaining() == 3
        assert counter.allow() is True
        assert counter.remaining() == 2
    finally:
        # Clean up test data from the correct backend
        _cleanup_rate_limit_key(test_key)


def test_rate_limiter_middleware_db_backed_selection() -> None:
    """Verify that RateLimiterMiddleware selects the database-backed counter when configured."""
    from unittest.mock import patch

    middleware = RateLimiterMiddleware(global_limit="5 / minute", per_ip=True)

    # We patch settings.RATE_LIMIT_DB_BACKED to True
    with patch("app.config.settings.RATE_LIMIT_DB_BACKED", True):
        # Create a counter via _get_or_create_counter (which checks DB_BACKED)
        counter = middleware._get_or_create_counter("_test_key", 5, 60.0)
        assert isinstance(counter, DatabaseSlidingWindowCounter)


def test_rate_limiter_middleware_in_memory_selection() -> None:
    """Verify that RateLimiterMiddleware uses in-memory counter when DB_BACKED is False."""
    from unittest.mock import patch

    middleware = RateLimiterMiddleware(global_limit="5 / minute", per_ip=True)

    with patch("app.config.settings.RATE_LIMIT_DB_BACKED", False):
        counter = middleware._get_or_create_counter("_test_key_inmem", 5, 60.0)
        assert isinstance(counter, SlidingWindowCounter)


from app.rate_limiter import SlidingWindowCounter


def test_dual_layer_keys_are_different() -> None:
    """Verify that aggregate and per-IP keys are distinct for the same route+method+ip."""
    middleware = RateLimiterMiddleware(global_limit="100/minute", per_ip=True, per_ip_limit="10/minute")
    agg_key = middleware._get_aggregate_key("/api/jobs", "POST")
    ip_key = middleware._get_per_ip_key("/api/jobs", "POST", "1.2.3.4")
    assert agg_key != ip_key
    # _get_route_key("/api/jobs") returns "jobs"
    assert agg_key == "_global:jobs:POST"
    assert ip_key == "jobs:POST:1.2.3.4"


def test_db_sliding_window_counter_fallback() -> None:
    """Verify that DatabaseSlidingWindowCounter falls back to in-memory behavior on DB errors."""
    import os
    from unittest.mock import patch

    test_key = _generate_test_key()

    # Force postgres storage backend and mock database connection to fail
    with (
        patch.dict(os.environ, {"DATAFORGE_STORAGE_BACKEND": "postgres"}),
        patch("app.postgres_repository._conn", side_effect=Exception("Database connection failure")),
    ):
        counter = DatabaseSlidingWindowCounter(max_requests=2, window_seconds=2.0, key=test_key)

        # Verify it falls back to in-memory, checking limit functionality
        assert counter.remaining() == 2
        assert counter.allow() is True
        assert counter.remaining() == 1
        assert counter.allow() is True
        assert counter.remaining() == 0
        assert counter.allow() is False
        assert counter.reset_in() > 0.0
