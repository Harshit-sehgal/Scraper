"""Unit tests for app.utils.rate_limit — rate-limit awareness utilities."""

import time
from unittest.mock import patch

from app.utils.rate_limit import (
    _RATE_LIMIT_STATE,
    get_cooldown_seconds,
    is_rate_limit_error,
    mark_rate_limited,
    parse_retry_after,
    reset_rate_limit_state,
)

# ── is_rate_limit_error ──────────────────────────────────────────────────


class TestIsRateLimitError:
    def test_status_429(self):
        assert is_rate_limit_error(status_code=429) is True

    def test_status_503(self):
        assert is_rate_limit_error(status_code=503) is True

    def test_status_200_not_rate_limited(self):
        assert is_rate_limit_error(status_code=200) is False

    def test_none_status(self):
        assert is_rate_limit_error(status_code=None) is False

    def test_header_retry_after(self):
        assert is_rate_limit_error(headers={"Retry-After": "120"}) is True

    def test_header_x_ratelimit_remaining(self):
        assert is_rate_limit_error(headers={"X-RateLimit-Remaining": "0"}) is True

    def test_header_x_rate_limit(self):
        assert is_rate_limit_error(headers={"X-Rate-Limit": "100"}) is True

    def test_no_matching_header(self):
        assert is_rate_limit_error(headers={"Content-Type": "text/html"}) is False

    def test_body_rate_limit(self):
        assert is_rate_limit_error(body="You have exceeded the rate limit.") is True

    def test_body_too_many_requests(self):
        assert is_rate_limit_error(body="Error: Too many requests") is True

    def test_body_try_again_later(self):
        assert is_rate_limit_error(body="Please try again later") is True

    def test_body_quota_exceeded(self):
        assert is_rate_limit_error(body="API quota exceeded") is True

    def test_body_request_limit(self):
        assert is_rate_limit_error(body="Request limit reached") is True

    def test_body_throttled(self):
        assert is_rate_limit_error(body="Your requests are being throttled") is True

    def test_body_no_match(self):
        assert is_rate_limit_error(body="Everything is fine") is False

    def test_all_none(self):
        assert is_rate_limit_error() is False

    def test_combined_body_overrides_ok_status(self):
        assert is_rate_limit_error(status_code=200, body="rate limit exceeded") is True


# ── parse_retry_after ────────────────────────────────────────────────────


class TestParseRetryAfter:
    def test_none_headers(self):
        assert parse_retry_after(None) is None

    def test_empty_headers(self):
        assert parse_retry_after({}) is None

    def test_missing_key(self):
        assert parse_retry_after({"Content-Type": "text/html"}) is None

    def test_integer_seconds(self):
        assert parse_retry_after({"Retry-After": "120"}) == 120.0

    def test_float_seconds(self):
        assert parse_retry_after({"Retry-After": "30.5"}) == 30.5

    def test_lowercase_header(self):
        assert parse_retry_after({"retry-after": "60"}) == 60.0

    def test_http_date_format(self):
        import datetime
        from email.utils import format_datetime

        future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=120)
        date_str = format_datetime(future)
        result = parse_retry_after({"Retry-After": date_str})
        assert result is not None
        assert 115.0 <= result <= 125.0

    def test_unparseable_value(self):
        assert parse_retry_after({"Retry-After": "not-a-number-or-date"}) is None


# ── get_cooldown_seconds / mark_rate_limited / reset ─────────────────────


class TestCooldownState:
    def setup_method(self):
        _RATE_LIMIT_STATE.clear()

    def teardown_method(self):
        _RATE_LIMIT_STATE.clear()

    def test_no_cooldown_by_default(self):
        assert get_cooldown_seconds("example.com") == 0.0

    def test_mark_with_explicit_retry_after(self):
        mark_rate_limited("example.com", retry_after=60.0)
        cd = get_cooldown_seconds("example.com")
        assert 55.0 <= cd <= 61.0

    def test_mark_without_retry_after_uses_backoff(self):
        mark_rate_limited("example.com")
        cd = get_cooldown_seconds("example.com")
        assert cd > 0.0

    def test_max_cooldown_cap(self):
        mark_rate_limited("example.com", retry_after=1000.0, max_cooldown=100.0)
        cd = get_cooldown_seconds("example.com")
        assert cd <= 101.0

    def test_reset_specific_domain(self):
        mark_rate_limited("a.com", retry_after=60.0)
        mark_rate_limited("b.com", retry_after=60.0)
        reset_rate_limit_state("a.com")
        assert get_cooldown_seconds("a.com") == 0.0
        assert get_cooldown_seconds("b.com") > 0.0

    def test_reset_all(self):
        mark_rate_limited("a.com", retry_after=60.0)
        mark_rate_limited("b.com", retry_after=60.0)
        reset_rate_limit_state()
        assert get_cooldown_seconds("a.com") == 0.0
        assert get_cooldown_seconds("b.com") == 0.0

    def test_eviction_on_large_state(self):
        now = time.time()
        for i in range(1002):
            _RATE_LIMIT_STATE[f"domain_{i}"] = now - 10  # all expired
        mark_rate_limited("new.com", retry_after=30.0)
        assert len(_RATE_LIMIT_STATE) < 1002

    def test_cooldown_decreases_over_time(self):
        mark_rate_limited("example.com", retry_after=5.0)
        cd1 = get_cooldown_seconds("example.com")
        with patch("app.utils.rate_limit.time") as mock_time:
            mock_time.time.return_value = time.time() + 3
            cd2 = get_cooldown_seconds("example.com")
        assert cd2 < cd1
