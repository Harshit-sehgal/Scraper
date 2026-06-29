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
        assert plan.primary_action == RecoveryAction.HARVEST_CF_CLEARANCE

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
        assert ctx.skip_domain == "blocked.example.com"

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
# CAPTCHA solve + CF harvester recovery handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestSolveCaptchaHandler:
    """handle_solve_captcha delegates to the CAPTCHA solver singleton.

    When the solver is disabled (_NoOpSolver), the handler returns False
    so the executor escalates to the next recovery action (typically
    ROTATE_PROXY).  When the solver returns a token, it is injected into
    attempt_ctx.cookies for the next scrape attempt.
    """

    @pytest.mark.asyncio
    async def test_captcha_recovery_returns_false_when_solver_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        monkeypatch.setattr(settings, "CAPTCHA_SOLVER_ENABLED", False)
        # Reset solver so it picks up the setting
        from app.captcha_solver import reset_captcha_solver

        reset_captcha_solver()

        executor = RecoveryExecutor()
        _register_all_handlers(executor)

        handler = executor.action_handlers[RecoveryAction.SOLVE_CAPTCHA]
        ctx = AttemptContext()
        result = await handler(
            {},
            {"url": "https://example.com/page", "site_key": "abc123"},
            ctx,
        )
        # _NoOpSolver returns None → handler returns False
        assert result is False

    @pytest.mark.asyncio
    async def test_captcha_recovery_injects_token_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import AsyncMock

        from app.config import settings
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        monkeypatch.setattr(settings, "CAPTCHA_SOLVER_ENABLED", True)
        monkeypatch.setattr(settings, "CAPTCHA_API_KEY", "test-key")
        monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "2captcha")

        # Patch the solver factory to return a mock solver
        mock_solver = AsyncMock()
        mock_solver.solve = AsyncMock(return_value="solved-token-xyz")

        from app.captcha_solver import reset_captcha_solver

        reset_captcha_solver()

        executor = RecoveryExecutor()
        _register_all_handlers(executor)

        with patch("app.captcha_solver.get_captcha_solver", return_value=mock_solver):
            handler = executor.action_handlers[RecoveryAction.SOLVE_CAPTCHA]
            ctx = AttemptContext()
            result = await handler(
                {},
                {
                    "url": "https://example.com",
                    "site_key": "site-key-abc",
                    "captcha_type": "recaptcha",
                },
                ctx,
            )

        # Solver succeeded → token injected
        assert result is True
        assert ctx.cookies.get("captcha_token") == "solved-token-xyz"

    @pytest.mark.asyncio
    async def test_captcha_recovery_no_url_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        monkeypatch.setattr(settings, "CAPTCHA_SOLVER_ENABLED", True)
        from app.captcha_solver import reset_captcha_solver

        reset_captcha_solver()

        executor = RecoveryExecutor()
        _register_all_handlers(executor)

        handler = executor.action_handlers[RecoveryAction.SOLVE_CAPTCHA]
        ctx = AttemptContext()
        result = await handler({}, {}, ctx)
        assert result is False


class TestHarvestCfClearanceHandler:
    """handle_harvest_cf_clearance delegates to the CF harvester.

    When CF_HARVESTER_ENABLED=False (default), the harvester itself
    short-circuits and returns None, so the handler returns False and
    the executor escalates.  On success, cookies are injected into
    attempt_ctx.cookies.
    """

    @pytest.mark.asyncio
    async def test_cf_harvest_recovery_returns_false_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", False)

        executor = RecoveryExecutor()
        _register_all_handlers(executor)

        handler = executor.action_handlers[RecoveryAction.HARVEST_CF_CLEARANCE]
        ctx = AttemptContext()
        result = await handler(
            {},
            {"url": "https://example.com", "domain": "example.com"},
            ctx,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_cf_harvest_recovery_injects_cookies_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import AsyncMock

        from app.config import settings
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)

        executor = RecoveryExecutor()
        _register_all_handlers(executor)

        mock_harvest = AsyncMock(return_value="cf_clearance=abc123; other=x")

        with patch("app.cf_harvester.harvest_cf_clearance", mock_harvest):
            handler = executor.action_handlers[RecoveryAction.HARVEST_CF_CLEARANCE]
            ctx = AttemptContext()
            result = await handler(
                {},
                {"url": "https://example.com", "domain": "example.com"},
                ctx,
            )

        assert result is True
        assert ctx.cookies.get("cf_clearance") == "abc123"

    @pytest.mark.asyncio
    async def test_cf_harvest_returns_false_on_harvest_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import AsyncMock

        from app.config import settings
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)

        executor = RecoveryExecutor()
        _register_all_handlers(executor)

        # harvest_cf_clearance returns None → handler returns False
        mock_harvest = AsyncMock(return_value=None)

        with patch("app.cf_harvester.harvest_cf_clearance", mock_harvest):
            handler = executor.action_handlers[RecoveryAction.HARVEST_CF_CLEARANCE]
            ctx = AttemptContext()
            result = await handler(
                {},
                {"url": "https://example.com", "domain": "example.com"},
                ctx,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_cf_harvest_no_url_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings
        from app.recovery_strategies import (
            AttemptContext,
            RecoveryAction,
            RecoveryExecutor,
        )

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)

        executor = RecoveryExecutor()
        _register_all_handlers(executor)

        handler = executor.action_handlers[RecoveryAction.HARVEST_CF_CLEARANCE]
        ctx = AttemptContext()
        result = await handler({}, {}, ctx)
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


class TestScopedSelectorCleanup:
    """Verify that scrape_url_with_recovery calls force_cleanup_for (scoped) instead of force_cleanup()."""

    @pytest.mark.asyncio
    async def test_selector_decay_triggers_scoped_cleanup(self) -> None:
        """SELECTOR_DECAY classification must call force_cleanup_for with the failing URL."""
        from unittest.mock import AsyncMock, patch

        from app.scraper_recovery_integration import scrape_url_with_recovery

        mock_selector_memory = MagicMock()
        mock_selector_memory.force_cleanup_for = MagicMock(
            return_value={"selectors_deleted": 1, "deleted_domains": ["example.com"]}
        )

        mock_strategist = MagicMock()
        mock_plan = MagicMock()
        mock_plan.primary_action.value = "backoff_and_slow"
        mock_plan.max_retry_attempts = 1
        mock_strategist.generate_recovery_plan.return_value = mock_plan

        mock_classifier = MagicMock()
        mock_classifier.return_value = MagicMock(
            category=FailureCategory.SELECTOR_DECAY,
            confidence=0.85,
            to_dict=lambda: {"category": "selector_decay", "confidence": 0.85},
        )

        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value=True)

        mock_domain_intel = MagicMock()
        mock_domain_intel.get_intelligence.return_value = MagicMock(to_dict=dict)

        with (
            patch("app.scraper_recovery_integration.get_selector_memory", return_value=mock_selector_memory),
            patch("app.scraper_recovery_integration.get_recovery_strategist", return_value=mock_strategist),
            patch("app.scraper_recovery_integration.classify_failure", mock_classifier),
            patch("app.scraper_recovery_integration.get_recovery_executor", return_value=mock_executor),
            patch("app.scraper_recovery_integration.get_domain_intelligence", return_value=mock_domain_intel),
            patch("app.scrape_telemetry.get_scrape_telemetry"),
            patch("app.crawl_state.get_crawl_state"),
            patch("app.acquisition_telemetry.get_acquisition_telemetry"),
            patch("app.scraper_recovery_integration.AcquisitionLineage"),
        ):
            results, stats = await scrape_url_with_recovery(
                url="https://example.com/products/42",
                schema_fields=[],
                min_record_score=0.5,
                max_recovery_attempts=2,
            )

        mock_selector_memory.force_cleanup_for.assert_any_call("https://example.com/products/42")


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
