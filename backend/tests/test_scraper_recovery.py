"""Tests for scraper recovery integration — strategy → executor chain.

Verifies the RecoveryStrategist → RecoveryExecutor → AttemptContext pipeline
so that failed scrapes get meaningful recovery actions applied.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.failure_classification import FailureCategory, FailureClassification

# ═══════════════════════════════════════════════════════════════════════════════
# RecoveryStrategist — plan generation
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecoveryStrategist:
    def test_every_failure_category_has_recovery_path(self) -> None:
        """Every FailureCategory must have a RECOVERY_PATHS entry."""
        from app.recovery_strategies import RecoveryStrategist

        paths = RecoveryStrategist.RECOVERY_PATHS
        for category in FailureCategory:
            assert category in paths, f"Missing recovery path for {category}"

    def test_generates_plan_for_selector_decay(self) -> None:
        from app.recovery_strategies import RecoveryAction, RecoveryStrategist

        strategist = RecoveryStrategist()
        classification = _make_classification(FailureCategory.SELECTOR_DECAY, confidence=0.85)
        plan = strategist.generate_recovery_plan(classification, attempt_number=1)

        assert plan.failure_category == FailureCategory.SELECTOR_DECAY
        assert plan.primary_action == RecoveryAction.FORCE_REDISCOVERY
        assert RecoveryAction.ESCALATE_TO_LLM in plan.secondary_actions
        assert plan.max_retry_attempts == 2
        assert plan.parameters.get("bypass_memory") is True

    def test_escalates_on_second_attempt(self) -> None:
        from app.recovery_strategies import RecoveryAction, RecoveryStrategist

        strategist = RecoveryStrategist()
        classification = _make_classification(FailureCategory.ANTI_BOT_BLOCK, confidence=0.9)
        plan = strategist.generate_recovery_plan(classification, attempt_number=2)

        # On attempt 2, primary should be the first escalation action
        assert plan.primary_action == RecoveryAction.BACKOFF_AND_SLOW

    def test_unknown_failure_falls_back(self) -> None:
        from app.recovery_strategies import RecoveryAction, RecoveryStrategist

        strategist = RecoveryStrategist()
        classification = _make_classification(FailureCategory.UNKNOWN, confidence=0.3)
        plan = strategist.generate_recovery_plan(classification, attempt_number=1)

        assert plan.primary_action == RecoveryAction.BACKOFF_AND_SLOW
        assert RecoveryAction.SKIP_DOMAIN in plan.secondary_actions

    def test_plan_to_dict_serializable(self) -> None:
        from app.recovery_strategies import RecoveryStrategist

        strategist = RecoveryStrategist()
        classification = _make_classification(FailureCategory.TIMEOUT, confidence=0.6)
        plan = strategist.generate_recovery_plan(classification, attempt_number=1)
        d = plan.to_dict()

        assert d["failure_category"] == "timeout"
        assert d["primary_action"] == "increase_timeout"
        assert "secondary_actions" in d
        assert "parameters" in d

    @patch("app.recovery_strategies.RecoveryStrategist._tune_parameters", return_value={"tuned": True})
    def test_domain_info_triggers_parameter_tuning(self, _mock_tune: MagicMock) -> None:
        from app.recovery_strategies import RecoveryAction, RecoveryStrategist

        strategist = RecoveryStrategist()
        classification = _make_classification(FailureCategory.ANTI_BOT_BLOCK, confidence=0.9)
        domain_info = {"anti_bot_risk": 0.9, "failure_rate": 0.8}

        plan = strategist.generate_recovery_plan(classification, attempt_number=1, domain_info=domain_info)
        assert plan.primary_action == RecoveryAction.ROTATE_PROXY


# ═══════════════════════════════════════════════════════════════════════════════
# RecoveryExecutor — handler execution
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecoveryExecutor:
    @pytest.mark.asyncio
    async def test_increase_hydration_wait_handler(self) -> None:
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        executor = RecoveryExecutor()
        _register_all_handlers(executor)
        ctx = AttemptContext(hydration_wait_ms=2000)

        handler = executor.action_handlers[RecoveryAction.INCREASE_HYDRATION_WAIT]
        result = await handler({"extra_delay_ms": 5000}, {}, ctx)

        assert result is True
        assert ctx.hydration_wait_ms == 7000  # 2000 + 5000

    @pytest.mark.asyncio
    async def test_increase_timeout_handler(self) -> None:
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        executor = RecoveryExecutor()
        _register_all_handlers(executor)
        ctx = AttemptContext()

        handler = executor.action_handlers[RecoveryAction.INCREASE_TIMEOUT]
        result = await handler({"timeout_ms": 40000}, {}, ctx)

        assert result is True
        assert ctx.timeout_ms == 40000

    @pytest.mark.asyncio
    async def test_rotate_proxy_handler(self) -> None:
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        executor = RecoveryExecutor()
        _register_all_handlers(executor)
        ctx = AttemptContext()

        handler = executor.action_handlers[RecoveryAction.ROTATE_PROXY]
        result = await handler({}, {"url": "http://example.com"}, ctx)

        assert result is True
        assert ctx.proxy_profile == "rotated"

    @pytest.mark.asyncio
    async def test_force_rediscovery_handler(self) -> None:
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        executor = RecoveryExecutor()
        _register_all_handlers(executor)
        ctx = AttemptContext()

        handler = executor.action_handlers[RecoveryAction.FORCE_REDISCOVERY]
        result = await handler({}, {}, ctx)

        assert result is True
        assert ctx.bypass_selector_memory is True
        assert ctx.force_llm_discovery is True

    @pytest.mark.asyncio
    async def test_lower_score_threshold_handler(self) -> None:
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        executor = RecoveryExecutor()
        _register_all_handlers(executor)
        ctx = AttemptContext()

        handler = executor.action_handlers[RecoveryAction.LOWER_SCORE_THRESHOLD]
        result = await handler(
            {"score_multiplier": 0.8},
            {"min_record_score": 50.0},
            ctx,
        )

        assert result is True
        assert ctx.min_record_score_override == 40.0

    @pytest.mark.asyncio
    async def test_skip_url_handler(self) -> None:
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        executor = RecoveryExecutor()
        _register_all_handlers(executor)
        ctx = AttemptContext()

        handler = executor.action_handlers[RecoveryAction.SKIP_URL]
        result = await handler({}, {}, ctx)

        assert result is True
        assert ctx.skip_url is True

    @pytest.mark.asyncio
    async def test_skip_domain_handler(self) -> None:
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        executor = RecoveryExecutor()
        _register_all_handlers(executor)
        ctx = AttemptContext()

        handler = executor.action_handlers[RecoveryAction.SKIP_DOMAIN]
        result = await handler({}, {"url": "http://blocked.example.com"}, ctx)

        assert result is True
        assert ctx.skip_domain == "http://blocked.example.com"

    @pytest.mark.asyncio
    async def test_abort_domain_handler(self) -> None:
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        executor = RecoveryExecutor()
        _register_all_handlers(executor)
        ctx = AttemptContext()

        handler = executor.action_handlers[RecoveryAction.ABORT_DOMAIN]
        result = await handler({}, {"url": "http://blocked.example.com"}, ctx)

        assert result is True
        assert ctx.abort_domain is True

    @pytest.mark.asyncio
    async def test_http_fallback_handler(self) -> None:
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        executor = RecoveryExecutor()
        _register_all_handlers(executor)
        ctx = AttemptContext()

        handler = executor.action_handlers[RecoveryAction.USE_HTTPX_FALLBACK]
        result = await handler({}, {}, ctx)

        assert result is True
        assert ctx.prefer_httpx is True

    @pytest.mark.asyncio
    async def test_execute_with_primary_success(self) -> None:
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
            RecoveryPlan,
        )

        executor = RecoveryExecutor()
        _register_all_handlers(executor)

        plan = RecoveryPlan(
            failure_category=FailureCategory.ANTI_BOT_BLOCK,
            primary_action=RecoveryAction.ROTATE_PROXY,
            should_escalate=False,
        )
        ctx = AttemptContext()
        result = await executor.execute(plan, {"url": "http://example.com"}, ctx)

        assert result is True
        assert ctx.proxy_profile == "rotated"

    @pytest.mark.asyncio
    async def test_execute_escalates_on_primary_failure(self) -> None:
        """When primary handler is missing, executor tries secondary actions."""
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
            RecoveryPlan,
        )

        executor = RecoveryExecutor()
        _register_all_handlers(executor)
        ctx = AttemptContext()

        plan = RecoveryPlan(
            failure_category=FailureCategory.SELECTOR_DECAY,
            primary_action=RecoveryAction.FORCE_REDISCOVERY,
            secondary_actions=[RecoveryAction.ROTATE_PROXY],
            should_escalate=True,
        )
        # Remove the primary handler to force escalation
        del executor.action_handlers[RecoveryAction.FORCE_REDISCOVERY]

        result = await executor.execute(plan, {}, ctx)

        assert result is True
        assert ctx.proxy_profile == "rotated"

    @pytest.mark.asyncio
    async def test_execute_returns_false_when_all_handlers_fail(self) -> None:
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
            RecoveryPlan,
        )

        executor = RecoveryExecutor()
        _register_all_handlers(executor)

        plan = RecoveryPlan(
            failure_category=FailureCategory.HTTP_ERROR,
            primary_action=RecoveryAction.SKIP_URL,
            secondary_actions=[RecoveryAction.SKIP_DOMAIN],
            should_escalate=True,
        )
        # Remove both handlers
        del executor.action_handlers[RecoveryAction.SKIP_URL]
        del executor.action_handlers[RecoveryAction.SKIP_DOMAIN]

        result = await executor.execute(plan, {"url": "http://example.com"}, AttemptContext())
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# AttemptContext — mutation support
# ═══════════════════════════════════════════════════════════════════════════════


class TestAttemptContext:
    def test_default_values(self) -> None:
        from app.recovery_strategies import AttemptContext

        ctx = AttemptContext()
        assert ctx.timeout_ms is None
        assert ctx.bypass_selector_memory is False
        assert ctx.force_llm_discovery is False
        assert ctx.prefer_httpx is False
        assert ctx.skip_url is False
        assert ctx.skip_domain is None
        assert ctx.abort_domain is False

    def test_can_set_override_fields(self) -> None:
        from app.recovery_strategies import AttemptContext

        ctx = AttemptContext(
            timeout_ms=5000,
            bypass_selector_memory=True,
            min_record_score_override=35.0,
        )
        assert ctx.timeout_ms == 5000
        assert ctx.bypass_selector_memory is True
        assert ctx.min_record_score_override == 35.0


# ═══════════════════════════════════════════════════════════════════════════════
# RecoveryPlan — serialization
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecoveryPlan:
    def test_to_dict(self) -> None:
        from app.recovery_strategies import RecoveryAction, RecoveryPlan

        plan = RecoveryPlan(
            failure_category=FailureCategory.ANTI_BOT_BLOCK,
            primary_action=RecoveryAction.ROTATE_PROXY,
            secondary_actions=[RecoveryAction.BACKOFF_AND_SLOW],
            max_retry_attempts=3,
            backoff_seconds=10.0,
            reason="Test reason",
        )
        d = plan.to_dict()
        assert d["failure_category"] == "anti_bot_block"
        assert d["primary_action"] == "rotate_proxy"
        assert d["secondary_actions"] == ["backoff_and_slow"]
        assert d["max_retry_attempts"] == 3


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_classification(category: FailureCategory, confidence: float = 0.8) -> FailureClassification:
    return FailureClassification(
        category=category,
        confidence=confidence,
        signals=[{"error_message": "test"}],
        recovery_strategy="retry",
    )


def _register_all_handlers(executor) -> None:
    """Register all built-in handlers on an executor instance."""
    from app.recovery_strategies import _BUILTIN_HANDLERS

    for action, handler in _BUILTIN_HANDLERS.items():
        executor.register_handler(action, handler)
