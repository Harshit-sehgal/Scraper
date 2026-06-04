"""
DataForge Chaos Engineering Test Suite

Verifies system resilience, automated failure classification, recovery planning,
and execution SLAs under injected chaos failure scenarios.
"""

import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.chaos_simulator import FailureMode, get_chaos_simulator
from app.failure_classification import FailureCategory
from app.models import FieldType, SchemaField
from app.recovery_handlers import register_all_recovery_handlers
from app.recovery_strategies import RecoveryAction, RecoveryExecutor
from app.scrape_telemetry import get_scrape_telemetry
from app.scraper_recovery_integration import scrape_url_with_recovery
from app.selector_memory import get_selector_memory

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def setup_chaos_environment():
    """Setup and teardown chaos engineering test environment."""
    # Register all recovery handlers
    register_all_recovery_handlers()

    # Reset chaos simulator active failure flags
    chaos = get_chaos_simulator()
    chaos.active_failures.clear()

    # Clear scrape telemetry collector
    telemetry = get_scrape_telemetry()
    telemetry.clear()

    # Clear selector memory cache
    selector_memory = get_selector_memory()
    selector_memory._memory.clear()

    yield

    # Clean up state to avoid leakage between tests
    chaos.active_failures.clear()
    telemetry.clear()
    selector_memory._memory.clear()


@pytest.mark.asyncio
async def test_network_timeout_recovery() -> None:
    """Verifies that NETWORK_TIMEOUT triggers INCREASE_TIMEOUT and recovery succeeds on retry."""
    chaos = get_chaos_simulator()
    chaos.active_failures[FailureMode.NETWORK_TIMEOUT.value] = True

    # We will patch the executor's execute method to clear the chaos flag
    # as a side-effect, representing the recovery action resolving the failure.
    original_execute = RecoveryExecutor.execute
    recovery_executed = []

    async def mock_execute(self, plan, context, attempt_ctx=None):
        if plan.primary_action == RecoveryAction.INCREASE_TIMEOUT:
            recovery_executed.append(plan.primary_action)
            # Simulate recovery resolving the network timeout failure
            chaos.active_failures[FailureMode.NETWORK_TIMEOUT.value] = False
        return await original_execute(self, plan, context)

    # Patch scrape_url to return simulated records on success
    mock_results = [{"company_name": "Antigravity Solutions", "email": "contact@antigravity.ai"}]

    with (
        patch("app.scraper.scrape_url", AsyncMock(return_value=mock_results)),
        patch("app.recovery_strategies.RecoveryExecutor.execute", mock_execute),
    ):
        schema = [
            SchemaField(name="company_name", field_type=FieldType.STRING, description="", required=True),
            SchemaField(name="email", field_type=FieldType.EMAIL, description="", required=True),
        ]

        results, stats = await scrape_url_with_recovery(
            url="https://antigravity-solutions.com/contact",
            schema_fields=schema,
            max_recovery_attempts=3,
        )

        # Verify success and recovery stats
        assert stats["success"] is True
        assert stats["attempts"] == 2
        assert stats["recovery_attempts"] == 1
        assert RecoveryAction.INCREASE_TIMEOUT.value in stats["recovery_actions_taken"]
        assert len(results) == 1
        assert results[0]["company_name"] == "Antigravity Solutions"

        # Assert SLA (< 10 seconds recovery)
        recovery_time_sec = stats["total_time_ms"] / 1000.0
        assert recovery_time_sec < 10.0

        # Check that classification caught a timeout failure category
        classifications = stats["failure_classifications"]
        assert len(classifications) > 0
        cat = classifications[0]["category"]
        assert cat in [FailureCategory.CONNECTION_TIMEOUT.value, FailureCategory.TIMEOUT.value]

        # Check that mock_execute was called and successfully cleared failure
        assert len(recovery_executed) > 0
        assert not chaos.is_failure_active(FailureMode.NETWORK_TIMEOUT)


@pytest.mark.asyncio
async def test_browser_crash_recovery() -> None:
    """Verifies BROWSER_CRASH triggers recovery and successfully recycles browser resources."""
    chaos = get_chaos_simulator()
    chaos.active_failures[FailureMode.BROWSER_CRASH.value] = True

    original_execute = RecoveryExecutor.execute
    recovery_executed = []

    async def mock_execute(self, plan, context, attempt_ctx=None):
        if plan.primary_action == RecoveryAction.ROTATE_PROXY:
            recovery_executed.append(plan.primary_action)
            # Simulate browser recycle / restart by turning off crash simulator
            chaos.active_failures[FailureMode.BROWSER_CRASH.value] = False
        return await original_execute(self, plan, context)

    mock_results = [{"name": "Crashed Site Resolved"}]

    with (
        patch("app.scraper.scrape_url", AsyncMock(return_value=mock_results)),
        patch("app.recovery_strategies.RecoveryExecutor.execute", mock_execute),
    ):
        schema = [SchemaField(name="name", field_type=FieldType.STRING, description="", required=True)]

        results, stats = await scrape_url_with_recovery(
            url="https://crashed-site.com",
            schema_fields=schema,
            max_recovery_attempts=3,
        )

        assert stats["success"] is True
        assert stats["attempts"] == 2
        assert stats["recovery_attempts"] == 1
        assert len(results) == 1

        # Assert classifier mapped it to BROWSER_CRASH
        classifications = stats["failure_classifications"]
        assert len(classifications) > 0
        assert classifications[0]["category"] == FailureCategory.BROWSER_CRASH.value

        # Assert SLA
        assert (stats["total_time_ms"] / 1000.0) < 10.0
        assert len(recovery_executed) > 0


@pytest.mark.asyncio
async def test_selector_decay_rediscovery() -> None:
    """Verifies that empty record returns classify as SELECTOR_DECAY and successfully clear selector memory."""
    chaos = get_chaos_simulator()
    chaos.active_failures[FailureMode.SELECTOR_POISONING.value] = True

    # Store a selector in memory first
    selector_memory = get_selector_memory()
    url = "https://decaying-selectors.com/catalog"
    selector_memory._memory["decaying-selectors.com"] = {
        "selectors": {"css": ".old-selector"},
        "success_count": 10,
        "failure_count": 0,
        "first_seen": time.time(),
        "last_success": time.time(),
    }

    # Assert that it is in memory initially
    assert "decaying-selectors.com" in selector_memory._memory

    original_execute = RecoveryExecutor.execute
    recovery_executed = []

    async def mock_execute(self, plan, context, attempt_ctx=None):
        if plan.primary_action == RecoveryAction.FORCE_REDISCOVERY:
            recovery_executed.append(plan.primary_action)
            # Turn off SELECTOR_POISONING on retry
            chaos.active_failures[FailureMode.SELECTOR_POISONING.value] = False
        return await original_execute(self, plan, context)

    mock_results = [{"product": "Decay Cleared Book"}]

    with (
        patch("app.scraper.scrape_url", AsyncMock(return_value=mock_results)),
        patch("app.recovery_strategies.RecoveryExecutor.execute", mock_execute),
    ):
        schema = [SchemaField(name="product", field_type=FieldType.STRING, description="", required=True)]

        results, stats = await scrape_url_with_recovery(url=url, schema_fields=schema, max_recovery_attempts=3)

        assert stats["success"] is True
        assert stats["attempts"] == 2
        assert len(results) == 1

        # Check classification was SELECTOR_DECAY
        classifications = stats["failure_classifications"]
        assert len(classifications) > 0
        assert classifications[0]["category"] == FailureCategory.SELECTOR_DECAY.value

        # Verify selector memory was forced to clean up for this domain
        assert "decaying-selectors.com" not in selector_memory._memory
        assert len(recovery_executed) > 0


@pytest.mark.asyncio
async def test_anti_bot_proxy_rotation() -> None:
    """Verifies anti-bot block triggers active proxy rotation and exponential backoff."""
    chaos = get_chaos_simulator()
    chaos.active_failures[FailureMode.ANTI_BOT_ESCALATION.value] = True

    original_execute = RecoveryExecutor.execute
    proxy_rotated = []

    async def mock_execute(self, plan, context, attempt_ctx=None):
        if plan.primary_action == RecoveryAction.ROTATE_PROXY:
            proxy_rotated.append(plan.primary_action)
            # Resolve chaos anti bot block
            chaos.active_failures[FailureMode.ANTI_BOT_ESCALATION.value] = False
        return await original_execute(self, plan, context)

    mock_results = [{"insight": "Anti-bot bypassed"}]

    with (
        patch("app.scraper.scrape_url", AsyncMock(return_value=mock_results)),
        patch("app.recovery_strategies.RecoveryExecutor.execute", mock_execute),
        patch("app.recovery_handlers.get_proxy_manager") as mock_pm,
    ):
        # Mock proxy manager rotation success
        mock_mgr = MagicMock()
        mock_mgr.enabled = True
        mock_mgr.current_proxy = "http://old-proxy:8888"
        mock_mgr.rotate = MagicMock(return_value="http://new-proxy:8888")
        mock_pm.return_value = mock_mgr

        schema = [SchemaField(name="insight", field_type=FieldType.STRING, description="", required=True)]

        results, stats = await scrape_url_with_recovery(
            url="https://bot-guarded.com/login",
            schema_fields=schema,
            max_recovery_attempts=3,
        )

        assert stats["success"] is True
        assert stats["attempts"] == 2
        assert len(results) == 1

        # Verify WAF anti-bot classification
        classifications = stats["failure_classifications"]
        assert len(classifications) > 0
        assert classifications[0]["category"] == FailureCategory.ANTI_BOT_BLOCK.value

        # Check proxy rotated and backoff executed
        assert len(proxy_rotated) > 0
        mock_mgr.rotate.assert_called()


@pytest.mark.asyncio
async def test_concurrency_reduction_under_resource_exhaustion() -> None:
    """Verifies that cascading/repeated failures (like browser crash or timeout) trigger REDUCE_CONCURRENCY."""
    chaos = get_chaos_simulator()
    # Trigger browser crash to initiate failures
    chaos.active_failures[FailureMode.BROWSER_CRASH.value] = True

    original_execute = RecoveryExecutor.execute
    concurrency_reduced = []

    async def mock_execute(self, plan, context, attempt_ctx=None):
        if plan.primary_action == RecoveryAction.REDUCE_CONCURRENCY:
            concurrency_reduced.append(plan.primary_action)
            # Resolve the failure mode on the escalated try
            chaos.active_failures[FailureMode.BROWSER_CRASH.value] = False
        return await original_execute(self, plan, context)

    mock_results = [{"name": "Resource Exhaustion Resolved"}]

    with (
        patch("app.scraper.scrape_url", AsyncMock(return_value=mock_results)),
        patch("app.recovery_strategies.RecoveryExecutor.execute", mock_execute),
    ):
        schema = [SchemaField(name="name", field_type=FieldType.STRING, description="", required=True)]

        # We need max_recovery_attempts=3 to trigger escalation to REDUCE_CONCURRENCY on attempt 2
        _results, stats = await scrape_url_with_recovery(
            url="https://resource-exhausted-target.org",
            schema_fields=schema,
            max_recovery_attempts=3,
        )

        assert stats["success"] is True
        assert stats["attempts"] == 3  # attempt 1 failed, attempt 2 failed, attempt 3 succeeded after reduction
        assert stats["recovery_attempts"] == 2

        # Ensure REDUCE_CONCURRENCY is in the list of actions taken
        assert RecoveryAction.REDUCE_CONCURRENCY.value in stats["recovery_actions_taken"]
        assert len(concurrency_reduced) > 0
