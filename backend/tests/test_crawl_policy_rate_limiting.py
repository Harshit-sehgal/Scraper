"""Tests for per-domain rate limiting in CrawlPolicyEngine (Roadmap Comp 2).

Verifies concurrency budgets, request pacing, retry ceilings,
exponential cooldown, and page budgets via the public API.
"""

from __future__ import annotations

import time

import pytest
from app.crawl_policy import CrawlPolicyEngine


@pytest.fixture
def policy() -> CrawlPolicyEngine:
    """Fresh policy engine with minimal defaults for test isolation."""
    eng = CrawlPolicyEngine()
    eng._max_global_concurrency = 10
    eng._max_concurrency = 3
    eng._default_delay = 0.0
    eng._respect_robots = False
    eng._max_retries = 2
    eng._cooldown_seconds = 1.0
    eng._max_cooldown_seconds = 8.0
    eng._cooldown_multiplier = 2.0
    eng._max_pages_per_domain = 5
    eng._domains.clear()
    eng._global_active_fetches = 0
    return eng


class TestConcurrencyBudget:
    """Per-domain and global concurrency limits via check_domain()."""

    @pytest.mark.asyncio
    async def test_check_domain_allows_first_request(self, policy: CrawlPolicyEngine) -> None:
        result = await policy.check_domain("https://example.com/page1")
        assert result is None

    @pytest.mark.asyncio
    async def test_check_domain_increments_active_fetches(self, policy: CrawlPolicyEngine) -> None:
        await policy.check_domain("https://example.com/page1")
        state = policy.get_domain_state("example.com")
        assert state is not None
        assert state["active_fetches"] >= 1

    @pytest.mark.asyncio
    async def test_record_result_decrements_active_fetches(self, policy: CrawlPolicyEngine) -> None:
        await policy.check_domain("https://example.com/page1")
        policy.record_result("https://example.com/page1", success=True)
        state = policy.get_domain_state("example.com")
        assert state is not None
        assert state["active_fetches"] == 0

    @pytest.mark.asyncio
    async def test_per_domain_concurrency_limit(self, policy: CrawlPolicyEngine) -> None:
        policy._max_concurrency = 2
        assert await policy.check_domain("https://example.com/1") is None
        assert await policy.check_domain("https://example.com/2") is None
        result = await policy.check_domain("https://example.com/3")
        assert result is not None
        assert "concurrency" in result.lower()

    @pytest.mark.asyncio
    async def test_release_frees_concurrency_slot(self, policy: CrawlPolicyEngine) -> None:
        policy._max_concurrency = 1
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=True)
        assert await policy.check_domain("https://example.com/2") is None

    @pytest.mark.asyncio
    async def test_different_domains_independent_budgets(self, policy: CrawlPolicyEngine) -> None:
        policy._max_concurrency = 1
        assert await policy.check_domain("https://example.com/1") is None
        assert await policy.check_domain("https://other.org/1") is None

    @pytest.mark.asyncio
    async def test_global_concurrency_cap(self, policy: CrawlPolicyEngine) -> None:
        policy._max_global_concurrency = 2
        assert await policy.check_domain("https://a.com/1") is None
        assert await policy.check_domain("https://b.com/1") is None
        result = await policy.check_domain("https://c.com/1")
        assert result is not None
        assert "global" in result.lower()

    @pytest.mark.asyncio
    async def test_global_release_frees_capacity(self, policy: CrawlPolicyEngine) -> None:
        policy._max_global_concurrency = 2
        assert await policy.check_domain("https://a.com/1") is None
        assert await policy.check_domain("https://b.com/1") is None
        policy.record_result("https://a.com/1", success=True)
        assert await policy.check_domain("https://c.com/1") is None

    @pytest.mark.asyncio
    async def test_internal_hosts_bypass_checks(self, policy: CrawlPolicyEngine) -> None:
        assert await policy.check_domain("http://localhost:8000/test") is None
        assert await policy.check_domain("http://127.0.0.1:8000/test") is None


class TestRequestPacing:
    """Minimum delay between requests to the same domain."""

    @pytest.mark.asyncio
    async def test_no_delay_with_zero_default(self, policy: CrawlPolicyEngine) -> None:
        result = await policy.check_domain("https://example.com/1")
        assert result is None
        policy.record_result("https://example.com/1", success=True)
        result = await policy.check_domain("https://example.com/2")
        assert result is None

    @pytest.mark.asyncio
    async def test_delay_respected_when_set(self, policy: CrawlPolicyEngine) -> None:
        policy._default_delay = 10.0
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=True)
        result = await policy.check_domain("https://example.com/2")
        assert result is not None
        assert "delay" in result.lower()

    @pytest.mark.asyncio
    async def test_delay_allows_after_wait(self, policy: CrawlPolicyEngine) -> None:
        policy._default_delay = 0.01
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=True)
        time.sleep(0.02)
        result = await policy.check_domain("https://example.com/2")
        assert result is None

    @pytest.mark.asyncio
    async def test_different_domains_no_delay(self, policy: CrawlPolicyEngine) -> None:
        policy._default_delay = 10.0
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=True)
        assert await policy.check_domain("https://other.org/1") is None


class TestRetryCeilingAndCooldown:
    """Exponential cooldown after consecutive failures."""

    @pytest.mark.asyncio
    async def test_first_failure_no_cooldown(self, policy: CrawlPolicyEngine) -> None:
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=False)
        state = policy.get_domain_state("example.com")
        assert state is not None
        assert state["consecutive_failures"] == 1
        assert state["cooldown"] == 0.0

    @pytest.mark.asyncio
    async def test_cooldown_activates_after_max_retries(self, policy: CrawlPolicyEngine) -> None:
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=False)
        policy.record_result("https://example.com/1", success=False)
        state = policy.get_domain_state("example.com")
        assert state is not None
        assert state["consecutive_failures"] == 2
        assert state["cooldown"] > 0.0

    @pytest.mark.asyncio
    async def test_cooldown_blocks_check_domain(self, policy: CrawlPolicyEngine) -> None:
        policy._cooldown_seconds = 60.0
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=False)
        policy.record_result("https://example.com/1", success=False)
        result = await policy.check_domain("https://example.com/2")
        assert result is not None
        assert "cooldown" in result.lower()

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self, policy: CrawlPolicyEngine) -> None:
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=False)
        policy.record_result("https://example.com/1", success=False)
        policy.record_result("https://example.com/1", success=True)
        state = policy.get_domain_state("example.com")
        assert state["consecutive_failures"] == 0

    @pytest.mark.asyncio
    async def test_success_clears_cooldown(self, policy: CrawlPolicyEngine) -> None:
        policy._cooldown_seconds = 60.0
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=False)
        policy.record_result("https://example.com/1", success=False)
        assert policy.get_domain_state("example.com")["cooldown"] > 0.0
        policy.record_result("https://example.com/1", success=True)
        state = policy.get_domain_state("example.com")
        assert state["cooldown"] == 0.0

    @pytest.mark.asyncio
    async def test_exponential_cooldown_growth(self, policy: CrawlPolicyEngine) -> None:
        policy._cooldown_multiplier = 2.0
        policy._cooldown_seconds = 1.0
        policy._max_cooldown_seconds = 10.0
        policy._max_retries = 1
        # Use all failures in a single batch — no check_domain in between
        # because cooldown will block subsequent check_domain calls.
        assert await policy.check_domain("https://example.com/0") is None
        policy.record_result("https://example.com/0", success=False)
        policy.record_result("https://example.com/0", success=False)
        state = policy.get_domain_state("example.com")
        assert state["consecutive_failures"] == 2

    @pytest.mark.asyncio
    async def test_cooldown_capped_at_max(self, policy: CrawlPolicyEngine) -> None:
        policy._cooldown_seconds = 10.0
        policy._max_cooldown_seconds = 30.0
        policy._cooldown_multiplier = 10.0
        policy._max_retries = 1
        assert await policy.check_domain("https://example.com/0") is None
        policy.record_result("https://example.com/0", success=False)
        state = policy.get_domain_state("example.com")
        assert state["cooldown"] <= 30.0 + 1.0

    @pytest.mark.asyncio
    async def test_total_fetches_increments(self, policy: CrawlPolicyEngine) -> None:
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=True)
        assert await policy.check_domain("https://example.com/2") is None
        policy.record_result("https://example.com/2", success=True)
        state = policy.get_domain_state("example.com")
        assert state["total_fetches"] == 2

    @pytest.mark.asyncio
    async def test_health_score_starts_at_one(self, policy: CrawlPolicyEngine) -> None:
        score = policy.get_domain_health_score("example.com")
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_health_score_drops_with_failures(self, policy: CrawlPolicyEngine) -> None:
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=False)
        policy.record_result("https://example.com/1", success=False)
        score = policy.get_domain_health_score("example.com")
        assert score < 1.0
        assert score >= 0.0

    @pytest.mark.asyncio
    async def test_health_score_recovers_after_success(self, policy: CrawlPolicyEngine) -> None:
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=False)
        policy.record_result("https://example.com/1", success=False)
        low_score = policy.get_domain_health_score("example.com")
        policy.record_result("https://example.com/1", success=True)
        recovered_score = policy.get_domain_health_score("example.com")
        assert recovered_score > low_score


class TestPageBudget:
    """Per-domain page fetch limit."""

    @pytest.mark.asyncio
    async def test_check_domain_allows_within_budget(self, policy: CrawlPolicyEngine) -> None:
        policy._max_pages_per_domain = 3
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=True)
        assert await policy.check_domain("https://example.com/2") is None
        policy.record_result("https://example.com/2", success=True)

    @pytest.mark.asyncio
    async def test_check_domain_blocks_at_budget_limit(self, policy: CrawlPolicyEngine) -> None:
        policy._max_pages_per_domain = 2
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=True)
        assert await policy.check_domain("https://example.com/2") is None
        policy.record_result("https://example.com/2", success=True)
        result = await policy.check_domain("https://example.com/3")
        assert result is not None
        assert "budget" in result.lower()

    @pytest.mark.asyncio
    async def test_page_budget_separate_per_domain(self, policy: CrawlPolicyEngine) -> None:
        policy._max_pages_per_domain = 1
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=True)
        assert await policy.check_domain("https://other.org/1") is None

    @pytest.mark.asyncio
    async def test_page_budget_is_exceeded_by_total_fetches(self, policy: CrawlPolicyEngine) -> None:
        policy._max_pages_per_domain = 2
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=True)
        assert await policy.check_domain("https://example.com/2") is None
        policy.record_result("https://example.com/2", success=True)
        result = await policy.check_domain("https://example.com/3")
        assert result is not None
        assert "budget" in result.lower()

    @pytest.mark.asyncio
    async def test_first_fetch_domain_with_budget_one_allowed(self, policy: CrawlPolicyEngine) -> None:
        policy._max_pages_per_domain = 1
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=True)
        result = await policy.check_domain("https://example.com/2")
        assert result is not None
        assert "budget" in result.lower()


class TestObservability:
    """Observability methods."""

    @pytest.mark.asyncio
    async def test_get_all_domain_states_empty_when_no_domains(self, policy: CrawlPolicyEngine) -> None:
        states = policy.get_all_domain_states()
        assert "_global" in states
        assert states["_global"]["tracked_domains"] == 0

    @pytest.mark.asyncio
    async def test_get_all_domain_states_includes_active_domains(self, policy: CrawlPolicyEngine) -> None:
        await policy.check_domain("https://example.com/1")
        states = policy.get_all_domain_states()
        assert "example.com" in states
        assert states["_global"]["tracked_domains"] >= 1

    @pytest.mark.asyncio
    async def test_get_all_domain_states_global_summary(self, policy: CrawlPolicyEngine) -> None:
        states = policy.get_all_domain_states()
        g = states["_global"]
        assert "active_fetches" in g
        assert "max_concurrency" in g
        assert "tracked_domains" in g

    @pytest.mark.asyncio
    async def test_get_domain_state_returns_none_for_unknown(self, policy: CrawlPolicyEngine) -> None:
        assert policy.get_domain_state("unknown.com") is None

    @pytest.mark.asyncio
    async def test_get_domain_health_score_unknown_is_one(self, policy: CrawlPolicyEngine) -> None:
        assert policy.get_domain_health_score("unknown.com") == 1.0

    @pytest.mark.asyncio
    async def test_reset_domain_clears_state(self, policy: CrawlPolicyEngine) -> None:
        assert await policy.check_domain("https://example.com/1") is None
        policy.record_result("https://example.com/1", success=False)
        policy.reset_domain("example.com")
        assert policy.get_domain_state("example.com") is None

    @pytest.mark.asyncio
    async def test_invalid_url_returns_error(self, policy: CrawlPolicyEngine) -> None:
        result = await policy.check_domain("")
        assert result is not None
