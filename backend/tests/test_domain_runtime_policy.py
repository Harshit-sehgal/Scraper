"""Tests for DomainRuntimePolicy — per-domain concurrency, cooldown, and failure tracking."""

from app.domain_runtime_policy import (
    DomainRuntimePolicy,
    get_domain_runtime_policy,
    reset_domain_runtime_policy,
)


def _make_url(domain: str = "example.com") -> str:
    return f"https://{domain}/page"


class TestDomainRuntimePolicy:
    """Unit tests for DomainRuntimePolicy."""

    def test_get_or_create_creates_entry(self):
        policy = DomainRuntimePolicy()
        url = _make_url()
        entry = policy.get_or_create(url)
        assert entry.domain == "example.com"
        assert entry.max_parallel == 2
        assert entry.recent_failures == 0
        assert entry.cooldown_until == 0.0

    def test_get_or_create_reuses_entry(self):
        policy = DomainRuntimePolicy()
        url = _make_url()
        e1 = policy.get_or_create(url)
        e2 = policy.get_or_create(url)
        assert e1 is e2

    def test_record_success_resets_failures(self):
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.record_failure(url)
        policy.record_failure(url)
        assert policy.get_or_create(url).recent_failures == 2
        policy.record_success(url)
        assert policy.get_or_create(url).recent_failures == 0

    def test_record_failure_triggers_cooldown_after_limit(self):
        policy = DomainRuntimePolicy()
        url = _make_url()
        # Default cooldown limit is 3
        policy.record_failure(url)
        assert policy.can_fetch(url)
        policy.record_failure(url)
        assert policy.can_fetch(url)
        policy.record_failure(url)
        assert not policy.can_fetch(url)

    def test_cooldown_expires(self):
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.record_failure(url)
        policy.record_failure(url)
        policy.record_failure(url)
        assert not policy.can_fetch(url)
        # Fast-forward past cooldown
        entry = policy.get_or_create(url)
        entry.cooldown_until = 0.0
        assert policy.can_fetch(url)

    def test_record_failure_rate_limit_counter(self):
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.record_failure(url, failure_type="429 rate_limit")
        entry = policy.get_or_create(url)
        assert entry.recent_rate_limits == 1
        assert entry.recent_antibot_blocks == 0

    def test_record_failure_antibot_counter(self):
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.record_failure(url, failure_type="anti_bot_blocked")
        entry = policy.get_or_create(url)
        assert entry.recent_antibot_blocks == 1
        assert entry.recent_rate_limits == 0

    def test_set_reduce_concurrency(self):
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.set_reduce_concurrency(url)
        assert policy.get_or_create(url).max_parallel == 1
        policy.set_reduce_concurrency(url)
        assert policy.get_or_create(url).max_parallel == 1  # min 1

    def test_set_abort_domain(self):
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.set_abort_domain(url)
        assert not policy.can_fetch(url)
        assert policy.remaining_cooldown(url) > 0

    def test_can_fetch_true_for_new_domain(self):
        policy = DomainRuntimePolicy()
        assert policy.can_fetch(_make_url("fresh.com"))

    def test_remaining_cooldown_zero_when_not_cooling(self):
        policy = DomainRuntimePolicy()
        assert policy.remaining_cooldown(_make_url("example.com")) == 0.0

    def test_remaining_cooldown_positive_during_cooldown(self):
        policy = DomainRuntimePolicy()
        url = _make_url()
        policy.set_abort_domain(url)
        remaining = policy.remaining_cooldown(url)
        assert remaining > 0.0

    def test_recommended_action_default(self):
        policy = DomainRuntimePolicy()
        url = _make_url("fresh.com")
        assert policy.recommended_action(url) == "inspect_failure_telemetry"

    def test_recommended_action_rate_limited(self):
        policy = DomainRuntimePolicy()
        url = _make_url("rate.com")
        for _ in range(3):
            policy.record_failure(url, failure_type="429")
        # After 3 failures, domain enters cooldown
        action = policy.recommended_action(url)
        assert "retry_later" in action

    def test_recommended_action_antibot(self):
        policy = DomainRuntimePolicy()
        url = _make_url("antibot.com")
        for _ in range(3):
            policy.record_failure(url, failure_type="anti_bot_blocked")
        action = policy.recommended_action(url)
        assert "authorized_access" in action or "retry_later" in action

    def test_get_summary_returns_dict(self):
        policy = DomainRuntimePolicy()
        policy.record_failure(_make_url("test.com"))
        policy.record_success(_make_url("ok.com"))
        summary = policy.get_summary()
        assert "test.com" in summary
        assert "ok.com" in summary
        assert "max_parallel" in summary["test.com"]
        assert "recent_failures" in summary["test.com"]

    def test_global_singleton(self):
        reset_domain_runtime_policy()
        p1 = get_domain_runtime_policy()
        p2 = get_domain_runtime_policy()
        assert p1 is p2

    def test_reset_clears_entries(self):
        reset_domain_runtime_policy()
        policy = get_domain_runtime_policy()
        policy.record_failure(_make_url("a.com"))
        assert len(policy.get_summary()) == 1
        reset_domain_runtime_policy()
        fresh = get_domain_runtime_policy()
        assert len(fresh.get_summary()) == 0

    def test_multiple_domains_tracked_independently(self):
        policy = DomainRuntimePolicy()
        policy.record_failure(_make_url("a.com"))
        policy.record_failure(_make_url("a.com"))
        policy.record_failure(_make_url("a.com"))
        policy.record_failure(_make_url("b.com"))
        policy.record_success(_make_url("b.com"))
        assert not policy.can_fetch(_make_url("a.com"))
        assert policy.can_fetch(_make_url("b.com"))
