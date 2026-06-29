"""Tests for DomainRuntimePolicy — per-domain concurrency, cooldown, and failure tracking."""

import pytest
from app.domain_runtime_policy import (
    DomainRuntimePolicy,
    get_domain_runtime_policy,
    reset_domain_runtime_policy,
)


def _make_url(domain: str = "example.com") -> str:
    return f"https://{domain}/page"


class TestDomainRuntimePolicy:
    """Unit tests for DomainRuntimePolicy."""

    def test_get_or_create_creates_entry(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url()
        entry = policy.get_or_create(url)
        assert entry.domain == "example.com"
        assert entry.max_parallel == 2
        assert entry.recent_failures == 0
        assert entry.cooldown_until == 0.0

    def test_get_or_create_reuses_entry(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url()
        e1 = policy.get_or_create(url)
        e2 = policy.get_or_create(url)
        assert e1 is e2

    def test_record_success_resets_failures(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.record_failure(url)
        policy.record_failure(url)
        assert policy.get_or_create(url).recent_failures == 2
        policy.record_success(url)
        assert policy.get_or_create(url).recent_failures == 0

    def test_record_failure_triggers_cooldown_after_limit(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url()
        # With weighted failures: 2 strong failures (1.0 each) = 2.0 >= 2.0 threshold
        policy.record_failure(url, failure_type="blocked")
        assert policy.can_fetch(url), "1 strong failure should not trigger cooldown"
        policy.record_failure(url, failure_type="blocked")
        assert not policy.can_fetch(url), "2 strong failures should trigger cooldown"

    def test_cooldown_expires(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.record_failure(url, failure_type="blocked")
        policy.record_failure(url, failure_type="blocked")
        assert not policy.can_fetch(url)
        # Fast-forward past cooldown
        entry = policy.get_or_create(url)
        entry.cooldown_until = 0.0
        assert policy.can_fetch(url)

    def test_record_failure_rate_limit_counter(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.record_failure(url, failure_type="429 rate_limit")
        entry = policy.get_or_create(url)
        assert entry.recent_rate_limits == 1
        assert entry.recent_antibot_blocks == 0

    def test_record_failure_antibot_counter(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.record_failure(url, failure_type="anti_bot_blocked")
        entry = policy.get_or_create(url)
        assert entry.recent_antibot_blocks == 1
        assert entry.recent_rate_limits == 0

    def test_set_reduce_concurrency(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.set_reduce_concurrency(url)
        assert policy.get_or_create(url).max_parallel == 1
        policy.set_reduce_concurrency(url)
        assert policy.get_or_create(url).max_parallel == 1  # min 1

    def test_set_abort_domain(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.set_abort_domain(url)
        assert not policy.can_fetch(url)
        assert policy.remaining_cooldown(url) > 0

    def test_can_fetch_true_for_new_domain(self) -> None:
        policy = DomainRuntimePolicy()
        assert policy.can_fetch(_make_url("fresh.com"))

    def test_remaining_cooldown_zero_when_not_cooling(self) -> None:
        policy = DomainRuntimePolicy()
        assert policy.remaining_cooldown(_make_url("example.com")) == 0.0

    def test_remaining_cooldown_positive_during_cooldown(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.set_abort_domain(url)
        remaining = policy.remaining_cooldown(url)
        assert remaining > 0.0

    def test_recommended_action_default(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url("fresh.com")
        assert policy.recommended_action(url) == "inspect_failure_telemetry"

    def test_recommended_action_rate_limited(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url("rate.com")
        for _ in range(3):
            policy.record_failure(url, failure_type="429")
        # After 3 failures, domain enters cooldown
        action = policy.recommended_action(url)
        assert "retry_later" in action

    def test_recommended_action_antibot(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url("antibot.com")
        for _ in range(3):
            policy.record_failure(url, failure_type="anti_bot_blocked")
        action = policy.recommended_action(url)
        assert "authorized_access" in action or "retry_later" in action

    def test_get_summary_returns_dict(self) -> None:
        policy = DomainRuntimePolicy()
        policy.record_failure(_make_url("test.com"))
        policy.record_success(_make_url("ok.com"))
        summary = policy.get_summary()
        assert "test.com" in summary
        assert "ok.com" in summary
        assert "max_parallel" in summary["test.com"]
        assert "recent_failures" in summary["test.com"]

    def test_global_singleton(self) -> None:
        reset_domain_runtime_policy()
        p1 = get_domain_runtime_policy()
        p2 = get_domain_runtime_policy()
        assert p1 is p2

    def test_reset_clears_entries(self) -> None:
        reset_domain_runtime_policy()
        policy = get_domain_runtime_policy()
        policy.record_failure(_make_url("a.com"))
        assert len(policy.get_summary()) == 1
        reset_domain_runtime_policy()
        fresh = get_domain_runtime_policy()
        assert len(fresh.get_summary()) == 0

    def test_multiple_domains_tracked_independently(self) -> None:
        policy = DomainRuntimePolicy()
        # a.com gets 2 strong failures → cooldown
        policy.record_failure(_make_url("a.com"), failure_type="blocked")
        policy.record_failure(_make_url("a.com"), failure_type="blocked")
        # b.com gets 1 strong failure + 1 success → no cooldown
        policy.record_failure(_make_url("b.com"), failure_type="blocked")
        policy.record_success(_make_url("b.com"))
        assert not policy.can_fetch(_make_url("a.com")), "a.com should be in cooldown"
        assert policy.can_fetch(_make_url("b.com")), "b.com should not be in cooldown"


class TestDomainCooldownIntegration:
    """Tests for domain cooldown preventing future scrape attempts."""

    def test_cooldown_blocks_consecutive_scrapes(self) -> None:
        """After hitting the failure pressure threshold, can_fetch returns False."""
        policy = DomainRuntimePolicy()
        url = _make_url("blocked-domain.com")
        policy.record_failure(url, failure_type="blocked")  # +1.0
        policy.record_failure(url, failure_type="blocked")  # +1.0 → 2.0 >= 2.0
        assert not policy.can_fetch(url), "Cooldown should block further fetch attempts after 2 strong failures"

    def test_cooldown_expires_and_allows_scrape(self) -> None:
        """After cooldown expires, can_fetch returns True again."""
        policy = DomainRuntimePolicy()
        url = _make_url("recovered-domain.com")
        policy.record_failure(url, failure_type="blocked")
        policy.record_failure(url, failure_type="blocked")
        # Simulate cooldown expiration
        entry = policy.get_or_create(url)
        entry.cooldown_until = 0.0
        assert policy.can_fetch(url), "After cooldown expires, URL should be fetchable again"

    def test_success_resets_cooldown(self) -> None:
        """A successful fetch resets the failure counter, preventing cooldown."""
        policy = DomainRuntimePolicy()
        url = _make_url("success-reset.com")
        # Use strong failures for reliable pressure
        policy.record_failure(url, failure_type="blocked")  # +1.0
        policy.record_failure(url, failure_type="blocked")  # +1.0 → should trigger cooldown (2.0)
        policy.record_success(url)  # -0.5 → 1.5
        assert policy.can_fetch(url), "Success should reduce failure pressure below threshold"
        # Two more strong failures should retrigger cooldown
        policy.record_failure(url, failure_type="blocked")  # +1.0 → 2.5
        assert not policy.can_fetch(url), "Additional failures after success reset should trigger cooldown"

    def test_recommended_action_during_cooldown(self) -> None:
        """recommended_action returns truthful retry_later during cooldown."""
        policy = DomainRuntimePolicy()
        url = _make_url("cooling-domain.com")
        policy.record_failure(url, failure_type="timeout")  # +1.0
        policy.record_failure(url, failure_type="timeout")  # +1.0 → 2.0
        action = policy.recommended_action(url)
        assert "retry_later" in action, f"Expected retry_later in recommended_action, got: {action}"

    def test_recommended_action_during_antibot_cooldown(self) -> None:
        """recommended_action includes authorized_access hint during anti-bot cooldown."""
        policy = DomainRuntimePolicy()
        url = _make_url("antibot-cooling.com")
        for _ in range(3):
            policy.record_failure(url, failure_type="anti_bot_blocked")
        action = policy.recommended_action(url)
        assert "authorized_access" in action, f"Expected authorized_access hint in recommended_action, got: {action}"

    def test_get_summary_includes_cooldown_remaining(self) -> None:
        """get_summary should report positive cooldown_remaining for cooling domains."""
        policy = DomainRuntimePolicy()
        url = _make_url("cooling-summary.com")
        policy.record_failure(url, failure_type="timeout")  # +1.0
        policy.record_failure(url, failure_type="timeout")  # +1.0 → 2.0
        summary = policy.get_summary()
        domain_key = "cooling-summary.com"
        assert domain_key in summary
        assert summary[domain_key]["cooldown_remaining"] > 0.0

    def test_reduce_concurrency_on_new_domain(self) -> None:
        """set_reduce_concurrency creates entry if needed and reduces max_parallel."""
        policy = DomainRuntimePolicy()
        policy.set_reduce_concurrency("https://new-domain.com/page")
        entry = policy.get_or_create("https://new-domain.com/page")
        assert entry.max_parallel == 1
        assert entry.domain == "new-domain.com"

    def test_weak_failures_do_not_trigger_cooldown(self) -> None:
        """5 selector_mismatch failures (5 * 0.2 = 1.0) should not trigger cooldown."""
        policy = DomainRuntimePolicy()
        url = _make_url("weak-fails.com")
        for _ in range(5):
            policy.record_failure(url, failure_type="selector_mismatch")
        assert policy.can_fetch(url) is True

    def test_record_success_clears_cooldown_below_threshold(self) -> None:
        """record_success only clears cooldown when pressure drops below threshold."""
        import time as time_module

        policy = DomainRuntimePolicy()
        url = _make_url("boundary.com")
        policy.record_failure(url, failure_type="timeout")  # +1.0
        policy.record_failure(url, failure_type="timeout")  # +1.0 → 2.0, cooldown
        entry = policy.get_or_create(url)
        assert entry.cooldown_until > time_module.monotonic()
        # One success reduces pressure to 1.5 (< 2.0) → cooldown clears
        policy.record_success(url)
        assert entry.cooldown_until == 0.0


class TestFailureWeight:
    """Parametrized tests for _get_failure_weight."""

    @pytest.mark.parametrize(
        "failure_type, expected_weight",
        [
            ("429", 1.0),
            ("rate_limit", 1.0),
            ("anti_bot", 1.0),
            ("captcha", 1.0),
            ("blocked", 1.0),
            ("timeout", 1.0),
            ("access_denied", 1.0),
            ("robots_denied", 1.0),
            ("empty_shell", 0.5),
            ("session_expired", 0.5),
            ("browser_crash", 0.5),
            ("render_starvation", 0.5),
            ("zero_records_extracted", 0.2),
            ("selector_mismatch", 0.2),
            ("low_quality_records", 0.2),
            ("unknown_error", 0.5),
            ("", 0.5),
        ],
    )
    def test_get_failure_weight(self, failure_type: str, expected_weight: float) -> None:
        policy = DomainRuntimePolicy()
        assert policy._get_failure_weight(failure_type) == expected_weight


class TestRecommendedActionBranches:
    """Tests for recommended_action edge cases."""

    def test_antibot_blocks_without_cooldown(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url("antibot-nocooldown.com")
        entry = policy.get_or_create(url)
        entry.recent_antibot_blocks = 3
        entry.recent_rate_limits = 0
        entry.cooldown_until = 0.0
        action = policy.recommended_action(url)
        assert "use_authorized_access" in action, f"Expected authorized_access hint, got: {action}"

    def test_rate_limits_without_cooldown(self) -> None:
        policy = DomainRuntimePolicy()
        url = _make_url("ratelimit-nocooldown.com")
        entry = policy.get_or_create(url)
        entry.recent_antibot_blocks = 0
        entry.recent_rate_limits = 3
        entry.cooldown_until = 0.0
        action = policy.recommended_action(url)
        assert "retry_later_or_reduce_request_rate" in action, f"Expected rate-limit hint, got: {action}"
