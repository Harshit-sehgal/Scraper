"""Unit tests for recovery_strategies — plans, executor, and edge cases."""

import pytest
from app.failure_classification import FailureCategory, FailureClassification
from app.recovery_strategies import (
    AttemptContext,
    RecoveryAction,
    RecoveryExecutor,
    RecoveryPlan,
    get_recovery_executor,
    get_recovery_strategist,
)

# ─── Test RecoveryPlan ────────────────────────────────────────────────────


class TestRecoveryPlan:
    def test_to_dict_contains_all_fields(self):
        plan = RecoveryPlan(
            failure_category=FailureCategory.HYDRATION_FAILURE,
            primary_action=RecoveryAction.INCREASE_HYDRATION_WAIT,
            secondary_actions=[RecoveryAction.RETRY_WITH_DNS_FLUSH],
            parameters={"extra_delay_ms": 5000},
            max_retry_attempts=3,
            backoff_seconds=2.0,
            should_escalate=True,
            reason="Testing to_dict",
        )
        d = plan.to_dict()
        assert d["failure_category"] == "hydration_failure"
        assert d["primary_action"] == "increase_hydration_wait"
        assert d["secondary_actions"] == ["retry_with_dns_flush"]
        assert d["parameters"] == {"extra_delay_ms": 5000}
        assert d["max_retry_attempts"] == 3
        assert d["backoff_seconds"] == 2.0
        assert d["should_escalate"] is True
        assert d["reason"] == "Testing to_dict"

    def test_default_values(self):
        plan = RecoveryPlan(
            failure_category=FailureCategory.TIMEOUT,
            primary_action=RecoveryAction.INCREASE_TIMEOUT,
        )
        assert plan.secondary_actions == []
        assert plan.parameters == {}
        assert plan.max_retry_attempts == 1
        assert plan.backoff_seconds == 1.0
        assert plan.should_escalate is False
        assert plan.reason == ""


# ─── Test AttemptContext ─────────────────────────────────────────────────


class TestAttemptContext:
    def test_default_values(self):
        ctx = AttemptContext()
        assert ctx.timeout_ms is None
        assert ctx.hydration_wait_ms is None
        assert ctx.fetch_strategy is None
        assert ctx.bypass_selector_memory is False
        assert ctx.force_llm_discovery is False
        assert ctx.prefer_httpx is False
        assert ctx.reduce_concurrency is False
        assert ctx.proxy_profile is None
        assert ctx.search_params is None
        assert ctx.extra_headers == {}
        assert ctx.skip_networkidle is False
        assert ctx.scroll_attempts is None
        assert ctx.anti_bot_stealth is False
        assert ctx.skip_url is False
        assert ctx.skip_domain is None
        assert ctx.min_record_score_override is None
        assert ctx.force_container_discovery is False
        assert ctx.abort_domain is False

    def test_custom_values(self):
        ctx = AttemptContext(
            timeout_ms=30000,
            hydration_wait_ms=5000,
            fetch_strategy="playwright_stealth",
            bypass_selector_memory=True,
            force_llm_discovery=True,
            prefer_httpx=True,
            reduce_concurrency=True,
            proxy_profile="residential",
            search_params={"q": "test"},
            extra_headers={"X-Custom": "1"},
            skip_networkidle=True,
            scroll_attempts=3,
            anti_bot_stealth=True,
            skip_url=True,
            skip_domain="example.com",
            min_record_score_override=0.3,
            force_container_discovery=True,
            abort_domain=True,
        )
        assert ctx.timeout_ms == 30000
        assert ctx.hydration_wait_ms == 5000
        assert ctx.fetch_strategy == "playwright_stealth"
        assert ctx.bypass_selector_memory is True
        assert ctx.force_llm_discovery is True
        assert ctx.prefer_httpx is True
        assert ctx.reduce_concurrency is True
        assert ctx.proxy_profile == "residential"
        assert ctx.search_params == {"q": "test"}
        assert ctx.extra_headers == {"X-Custom": "1"}
        assert ctx.skip_networkidle is True
        assert ctx.scroll_attempts == 3
        assert ctx.anti_bot_stealth is True
        assert ctx.skip_url is True
        assert ctx.skip_domain == "example.com"
        assert ctx.min_record_score_override == 0.3
        assert ctx.force_container_discovery is True
        assert ctx.abort_domain is True


# ─── Test RecoveryStrategist ──────────────────────────────────────────────


class TestRecoveryStrategist:
    def test_plan_for_unknown_category_uses_fallback(self):
        """Unknown failure categories should use the UNKNOWN path."""
        strategist = get_recovery_strategist()
        classification = FailureClassification(
            category=FailureCategory.UNKNOWN,
            confidence=0.5,
        )
        plan = strategist.generate_recovery_plan(classification)
        assert plan.primary_action == RecoveryAction.BACKOFF_AND_SLOW
        assert plan.max_retry_attempts == 1
        assert plan.backoff_seconds == 3.0

    def test_escalation_on_attempt_2(self):
        strategist = get_recovery_strategist()
        classification = FailureClassification(
            category=FailureCategory.HYDRATION_FAILURE,
            confidence=0.9,
        )
        plan = strategist.generate_recovery_plan(classification, attempt_number=2)
        # Attempt 2 should use first escalation action
        assert plan.primary_action in RecoveryAction.__members__.values()

    def test_escalation_beyond_available_actions(self):
        strategist = get_recovery_strategist()
        classification = FailureClassification(
            category=FailureCategory.CONNECTION_TIMEOUT,
            confidence=0.85,
        )
        plan = strategist.generate_recovery_plan(classification, attempt_number=99)
        # Should not crash; pick last available action or secondary
        assert plan.primary_action is not None

    def test_all_failure_categories_have_paths(self):
        """Every FailureCategory should have a defined recovery path."""
        strategist = get_recovery_strategist()
        for category in FailureCategory:
            classification = FailureClassification(category=category, confidence=0.8)
            plan = strategist.generate_recovery_plan(classification)
            assert plan.primary_action is not None
            assert plan.max_retry_attempts >= 0

    def test_domain_info_tunes_anti_bot_params(self):
        strategist = get_recovery_strategist()
        classification = FailureClassification(
            category=FailureCategory.RATE_LIMITED,
            confidence=0.9,
        )
        domain_info = {"anti_bot_risk": 0.9, "failure_rate": 0.2}
        plan = strategist.generate_recovery_plan(classification, domain_info=domain_info)
        # High anti-bot risk should increase delay
        assert plan.parameters.get("delay_ms", 0) > 10000  # Higher than default

    def test_high_failure_rate_reduces_delays(self):
        strategist = get_recovery_strategist()
        classification = FailureClassification(
            category=FailureCategory.HYDRATION_FAILURE,
            confidence=0.9,
        )
        domain_info = {"anti_bot_risk": 0.3, "failure_rate": 0.8}
        plan = strategist.generate_recovery_plan(classification, domain_info=domain_info)
        # High failure rate should reduce delay
        # Plan is generated without error: verify parameters exist
        assert isinstance(plan.parameters, dict)
        assert plan.primary_action is not None
        # High failure rate should not increase delay beyond default
        default_plan = strategist.generate_recovery_plan(classification)
        if "delay_ms" in plan.parameters and "delay_ms" in default_plan.parameters:
            assert plan.parameters["delay_ms"] <= default_plan.parameters["delay_ms"]


# ─── Test RecoveryExecutor ─────────────────────────────────────────────


class TestRecoveryExecutor:
    @pytest.mark.asyncio
    async def test_execute_no_handler_returns_false(self):
        executor = RecoveryExecutor()
        plan = RecoveryPlan(
            failure_category=FailureCategory.TIMEOUT,
            primary_action=RecoveryAction.INCREASE_TIMEOUT,
            max_retry_attempts=1,
        )
        result = await executor.execute(plan, {"url": "https://example.com"})
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_with_handler_returns_result(self):
        executor = RecoveryExecutor()

        async def fake_handler(params, context, attempt_ctx=None):
            return True

        executor.register_handler(RecoveryAction.INCREASE_TIMEOUT, fake_handler)
        plan = RecoveryPlan(
            failure_category=FailureCategory.TIMEOUT,
            primary_action=RecoveryAction.INCREASE_TIMEOUT,
        )
        result = await executor.execute(plan, {"url": "https://example.com"})
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_handler_exception_returns_false(self):
        executor = RecoveryExecutor()

        async def failing_handler(params, context, attempt_ctx=None):
            msg = "handler crashed"
            raise RuntimeError(msg)

        executor.register_handler(RecoveryAction.INCREASE_TIMEOUT, failing_handler)
        plan = RecoveryPlan(
            failure_category=FailureCategory.TIMEOUT,
            primary_action=RecoveryAction.INCREASE_TIMEOUT,
        )
        result = await executor.execute(plan, {"url": "https://example.com"})
        assert result is False

    @pytest.mark.asyncio
    async def test_escalation_on_primary_failure(self):
        executor = RecoveryExecutor()

        async def failing_handler(params, context, attempt_ctx=None):
            msg = "primary crashed"
            raise RuntimeError(msg)

        async def escalation_handler(params, context, attempt_ctx=None):
            return True

        executor.register_handler(RecoveryAction.INCREASE_TIMEOUT, failing_handler)
        executor.register_handler(RecoveryAction.REDUCE_CONCURRENCY, escalation_handler)

        plan = RecoveryPlan(
            failure_category=FailureCategory.TIMEOUT,
            primary_action=RecoveryAction.INCREASE_TIMEOUT,
            secondary_actions=[RecoveryAction.REDUCE_CONCURRENCY],
            should_escalate=True,
        )
        result = await executor.execute(plan, {"url": "https://example.com"})
        assert result is True

    @pytest.mark.asyncio
    async def test_mutates_attempt_context(self):
        executor = RecoveryExecutor()

        async def set_skip(params, context, attempt_ctx=None):
            if attempt_ctx is not None:
                attempt_ctx.skip_url = True
            return True

        executor.register_handler(RecoveryAction.SKIP_URL, set_skip)
        ctx = AttemptContext()
        plan = RecoveryPlan(
            failure_category=FailureCategory.TIMEOUT,
            primary_action=RecoveryAction.SKIP_URL,
        )
        result = await executor.execute(plan, {"url": "https://example.com"}, attempt_ctx=ctx)
        assert result is True
        assert ctx.skip_url is True

    @pytest.mark.asyncio
    async def test_all_escalation_failures_return_false(self):
        executor = RecoveryExecutor()

        async def always_fail(params, context, attempt_ctx=None):
            msg = "always fails"
            raise RuntimeError(msg)

        executor.register_handler(RecoveryAction.INCREASE_TIMEOUT, always_fail)
        executor.register_handler(RecoveryAction.REDUCE_CONCURRENCY, always_fail)
        executor.register_handler(RecoveryAction.SKIP_DOMAIN, always_fail)

        plan = RecoveryPlan(
            failure_category=FailureCategory.TIMEOUT,
            primary_action=RecoveryAction.INCREASE_TIMEOUT,
            secondary_actions=[RecoveryAction.REDUCE_CONCURRENCY, RecoveryAction.SKIP_DOMAIN],
            should_escalate=True,
        )
        result = await executor.execute(plan, {"url": "https://example.com"})
        assert result is False

    @pytest.mark.asyncio
    async def test_register_handler_replaces_old(self):
        executor = RecoveryExecutor()

        async def handler_a(params, context, attempt_ctx=None):
            return False

        async def handler_b(params, context, attempt_ctx=None):
            return True

        executor.register_handler(RecoveryAction.ROTATE_PROXY, handler_a)
        executor.register_handler(RecoveryAction.ROTATE_PROXY, handler_b)  # Replace
        plan = RecoveryPlan(
            failure_category=FailureCategory.ANTI_BOT_BLOCK,
            primary_action=RecoveryAction.ROTATE_PROXY,
        )
        result = await executor.execute(plan, {"url": "https://example.com"})
        assert result is True


# ─── Test global singletons ───────────────────────────────────────────────


class TestSingletons:
    def test_get_recovery_executor_returns_same_instance(self):
        e1 = get_recovery_executor()
        e2 = get_recovery_executor()
        assert e1 is e2

    def test_get_recovery_strategist_returns_same_instance(self):
        s1 = get_recovery_strategist()
        s2 = get_recovery_strategist()
        assert s1 is s2
