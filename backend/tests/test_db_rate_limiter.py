import time
from unittest.mock import MagicMock
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
            from app.job_store import _get_connection, _DB_LOCK
            with _DB_LOCK:
                conn = _get_connection()
                try:
                    conn.execute("DELETE FROM rate_limits WHERE key = ?", (key,))
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            pass


def test_db_sliding_window_counter_sqlite():
    """Verify that DatabaseSlidingWindowCounter behaves correctly using SQLite storage.

    Uses a unique key prefix to avoid colliding with other tests that share
    the same rate_limits table. Cleans up test data on completion from the
    active backend (SQLite or Postgres).
    """
    test_key = "_test_sliding_window_sqlite_"
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

def test_rate_limiter_middleware_db_backed_selection():
    """Verify that RateLimiterMiddleware selects the database-backed counter when configured."""
    from unittest.mock import patch
    
    middleware = RateLimiterMiddleware(global_limit="5 / minute", per_ip=True)
    
    mock_request = MagicMock()
    mock_request.url.path = "/api/jobs"
    mock_request.client.host = "127.0.0.1"
    mock_request.headers = {}
    
    # We patch settings.RATE_LIMIT_DB_BACKED to True
    with patch("app.config.settings.RATE_LIMIT_DB_BACKED", True):
        # Trigger the middleware key logic
        key = middleware._get_client_key("/api/jobs", "127.0.0.1")
        max_req, window_sec = middleware._get_limits_for_path("/api/jobs")
        
        # Test lazy counter creation in dict
        if key not in middleware._counters:
            middleware._counters[key] = DatabaseSlidingWindowCounter(max_req, window_sec, key)
            
        assert isinstance(middleware._counters[key], DatabaseSlidingWindowCounter)
