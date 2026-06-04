from app.config import settings
from app.rate_limiter import RateLimiterMiddleware


def test_job_create_limit_comes_from_settings(monkeypatch):
    # Override settings directly
    monkeypatch.setattr(settings, "RATE_LIMIT_JOB_CREATE", "1/minute")
    rl = RateLimiterMiddleware(global_limit="600/minute")
    max_req, window_sec = rl._get_limits_for_path("/api/jobs")
    assert (max_req, window_sec) == (1, 60.0)


def test_discover_limit_comes_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_DISCOVER", "5/minute")
    rl = RateLimiterMiddleware(global_limit="600/minute")
    max_req, window_sec = rl._get_limits_for_path("/api/discover")
    assert (max_req, window_sec) == (5, 60.0)
