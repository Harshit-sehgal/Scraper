"""Unit tests for ``app.utils.rate_limit`` - rate-limit detection and cooldown utilities."""

from __future__ import annotations

import time
from unittest.mock import patch

from app.utils.rate_limit import (
    get_cooldown_seconds,
    is_rate_limit_error,
    mark_rate_limited,
    parse_retry_after,
)


class TestIsRateLimitError:
    def test_status_code_429(self) -> None:
        assert is_rate_limit_error(status_code=429) is True

    def test_status_code_503(self) -> None:
        assert is_rate_limit_error(status_code=503) is True

    def test_status_code_200(self) -> None:
        assert is_rate_limit_error(status_code=200) is False

    def test_no_args_returns_false(self) -> None:
        assert is_rate_limit_error() is False

    def test_retry_after_header_detected(self) -> None:
        assert is_rate_limit_error(headers={"Retry-After": "30"}) is True

    def test_x_ratelimit_remaining_header_detected(self) -> None:
        assert is_rate_limit_error(headers={"X-RateLimit-Remaining": "0"}) is True

    def test_x_rate_limit_header_detected(self) -> None:
        assert is_rate_limit_error(headers={"X-Rate-Limit-Limit": "100"}) is True

    def test_case_insensitive_header(self) -> None:
        assert is_rate_limit_error(headers={"retry-after": "30"}) is True

    def test_body_pattern_rate_limit(self) -> None:
        assert is_rate_limit_error(body="rate limit exceeded") is True

    def test_body_pattern_too_many_requests(self) -> None:
        assert is_rate_limit_error(body="Too Many Requests") is True

    def test_body_pattern_try_again(self) -> None:
        assert is_rate_limit_error(body="Please try again later") is True

    def test_body_pattern_quota(self) -> None:
        assert is_rate_limit_error(body="Quota exceeded") is True

    def test_body_pattern_throttle(self) -> None:
        assert is_rate_limit_error(body="Request throttled") is True

    def test_no_match_returns_false(self) -> None:
        assert is_rate_limit_error(body="Server error") is False
        assert is_rate_limit_error(headers={"Content-Type": "text/html"}) is False


class TestParseRetryAfter:
    def test_none_when_no_headers(self) -> None:
        assert parse_retry_after() is None

    def test_none_when_empty_dict(self) -> None:
        assert parse_retry_after({}) is None

    def test_none_when_header_missing(self) -> None:
        assert parse_retry_after({"Content-Type": "text/html"}) is None

    def test_parsed_as_float_seconds(self) -> None:
        result = parse_retry_after({"Retry-After": "120"})
        assert result is not None
        assert abs(result - 120.0) < 0.01

    def test_lowercase_header_key(self) -> None:
        result = parse_retry_after({"retry-after": "30"})
        assert result is not None
        assert abs(result - 30.0) < 0.01

    def test_http_date_format(self) -> None:
        from email.utils import formatdate

        future = formatdate(time.time() + 60, usegmt=True)
        result = parse_retry_after({"Retry-After": future})
        assert result is not None
        assert result > 50.0
        assert result < 70.0

    def test_expired_http_date_returns_zero(self) -> None:
        from email.utils import formatdate

        past = formatdate(time.time() - 60, usegmt=True)
        result = parse_retry_after({"Retry-After": past})
        assert result is not None
        assert result == 0.0

    def test_unparseable_returns_none(self) -> None:
        assert parse_retry_after({"Retry-After": "garbage"}) is None


class TestMarkRateLimitedAndCooldown:
    def setup_method(self) -> None:
        from app.utils.rate_limit import _RATE_LIMIT_STATE

        _RATE_LIMIT_STATE.clear()

    def test_cooldown_zero_when_not_marked(self) -> None:
        assert get_cooldown_seconds("example.com") == 0.0

    def test_cooldown_after_marking_with_retry_after(self) -> None:
        mark_rate_limited("example.com", retry_after=10.0)
        remaining = get_cooldown_seconds("example.com")
        assert remaining > 0.0
        assert remaining <= 10.5

    def test_cooldown_respects_max_cooldown_cap(self) -> None:
        mark_rate_limited("example.com", retry_after=9999.0, max_cooldown=60.0)
        remaining = get_cooldown_seconds("example.com")
        assert remaining <= 61.0

    def test_exponential_backoff_when_no_retry_after(self) -> None:
        mark_rate_limited("example.com")
        first = get_cooldown_seconds("example.com")
        assert first >= 25.0

        mark_rate_limited("example.com")
        second = get_cooldown_seconds("example.com")
        assert second > first - 1.0

    def test_different_domains_independent(self) -> None:
        mark_rate_limited("domain-a.com", retry_after=5.0)
        mark_rate_limited("domain-b.com", retry_after=30.0)
        a_cooldown = get_cooldown_seconds("domain-a.com")
        b_cooldown = get_cooldown_seconds("domain-b.com")
        assert abs(a_cooldown - b_cooldown) > 5.0

    def test_cooldown_expires_over_time(self) -> None:
        mark_rate_limited("fast-expire", retry_after=0.001, max_cooldown=0.1)
        time.sleep(0.15)
        assert get_cooldown_seconds("fast-expire") == 0.0

    def test_large_state_eviction(self) -> None:
        from app.utils.rate_limit import _RATE_LIMIT_STATE

        for i in range(1005):
            mark_rate_limited(f"domain-{i}.com", retry_after=0.001, max_cooldown=0.1)
        assert len(_RATE_LIMIT_STATE) <= 1005

    def test_mark_rate_limited_is_idempotent(self) -> None:
        mark_rate_limited("example.com", retry_after=10.0)
        first = get_cooldown_seconds("example.com")
        mark_rate_limited("example.com", retry_after=10.0)
        second = get_cooldown_seconds("example.com")
        assert second >= first - 1.0

    @patch("app.utils.rate_limit._RATE_LIMIT_STATE", {})
    def test_thread_safety(self) -> None:
        import threading

        errors: list[Exception] = []

        def worker() -> None:
            try:
                for _ in range(20):
                    mark_rate_limited("shared-domain.com", retry_after=0.5)
                    get_cooldown_seconds("shared-domain.com")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
