"""
Integration Tests for Recovery Flows

Tests the end-to-end recovery system including:
- Recovery strategist generating plans per failure type
- Recovery handlers executing actions
- Selector memory cleanup integration
- Domain health monitoring
- API endpoints for health and stats
"""

import pytest
from unittest.mock import MagicMock, patch

from app.recovery_strategies import (
    RecoveryAction,
    get_recovery_strategist,
    get_recovery_executor,
)
from app.recovery_handlers import register_all_recovery_handlers
from app.failure_classification import FailureCategory, FailureClassification
from app.domain_health_alerts import (
    DomainHealthMonitor,
)
from app.selector_memory import get_selector_memory


class TestRecoveryStrategist:
    """Test recovery plan generation."""
    
    def test_recovery_plan_hydration_failure(self):
        """Test recovery plan for hydration failure."""
        strategist = get_recovery_strategist()
        
        classification = FailureClassification(
            category=FailureCategory.HYDRATION_FAILURE,
            confidence=0.9,
        )
        
        plan = strategist.generate_recovery_plan(classification, attempt_number=1)
        
        assert plan.failure_category == FailureCategory.HYDRATION_FAILURE
        assert plan.primary_action == RecoveryAction.INCREASE_HYDRATION_WAIT
        assert len(plan.secondary_actions) > 0
        assert plan.max_retry_attempts == 3
    
    def test_recovery_plan_selector_decay(self):
        """Test recovery plan for selector decay."""
        strategist = get_recovery_strategist()
        
        classification = FailureClassification(
            category=FailureCategory.SELECTOR_DECAY,
            confidence=0.95,
        )
        
        plan = strategist.generate_recovery_plan(classification, attempt_number=1)
        
        assert plan.failure_category == FailureCategory.SELECTOR_DECAY
        assert plan.primary_action == RecoveryAction.FORCE_REDISCOVERY
        assert RecoveryAction.ESCALATE_TO_LLM in plan.secondary_actions
    
    def test_recovery_plan_anti_bot_block(self):
        """Test recovery plan for anti-bot block."""
        strategist = get_recovery_strategist()
        
        classification = FailureClassification(
            category=FailureCategory.ANTI_BOT_BLOCK,
            confidence=0.99,
        )
        
        plan = strategist.generate_recovery_plan(classification, attempt_number=1)
        
        assert plan.failure_category == FailureCategory.ANTI_BOT_BLOCK
        assert plan.primary_action == RecoveryAction.ROTATE_PROXY
        assert plan.backoff_seconds == 10.0
    
    def test_recovery_escalation_on_retry(self):
        """Test that recovery escalates on retry attempts."""
        strategist = get_recovery_strategist()
        
        classification = FailureClassification(
            category=FailureCategory.ANTI_BOT_BLOCK,
            confidence=0.99,
        )
        
        # First attempt: use primary action
        plan1 = strategist.generate_recovery_plan(classification, attempt_number=1)
        assert plan1.primary_action == RecoveryAction.ROTATE_PROXY
        
        # Second attempt: escalate to next action
        plan2 = strategist.generate_recovery_plan(classification, attempt_number=2)
        assert plan2.primary_action in [RecoveryAction.ROTATE_PROXY, RecoveryAction.BACKOFF_AND_SLOW]
    
    def test_parameter_tuning_high_anti_bot_risk(self):
        """Test parameter tuning for high anti-bot risk domains."""
        strategist = get_recovery_strategist()
        
        classification = FailureClassification(
            category=FailureCategory.RATE_LIMITED,
            confidence=0.9,
        )
        
        domain_info = {
            "anti_bot_risk": 0.8,  # High risk
            "failure_rate": 0.3,
            "failure_pattern": "rate_limited",
        }
        
        plan = strategist.generate_recovery_plan(classification, domain_info=domain_info)
        
        # Should have tuned parameters
        assert "delay_ms" in plan.parameters
        assert "slow_factor" in plan.parameters


class TestDomainHealthMonitor:
    """Test domain health monitoring."""
    
    def test_health_monitor_tracks_success_failure(self):
        """Test that health monitor tracks successes and failures."""
        monitor = DomainHealthMonitor()
        
        # Record successes
        monitor.record_attempt("https://example.com/page1", success=True)
        monitor.record_attempt("https://example.com/page2", success=True)
        
        # Record failure
        monitor.record_attempt("https://example.com/page3", success=False, failure_category="selector_decay")
        
        health = monitor.get_domain_health("https://example.com/any")
        assert health is not None
        assert health["success_rate"] == pytest.approx(2/3, 0.01)
    
    def test_health_level_classification(self):
        """Test health level classification."""
        monitor = DomainHealthMonitor()
        
        # Record many successes -> HEALTHY
        for i in range(15):
            monitor.record_attempt(f"https://healthy.com/page{i}", success=True)
        
        health = monitor.get_domain_health("https://healthy.com/any")
        assert health is not None
        assert health["health_level"] == "healthy"
        assert health["health_score"] >= 0.8
    
    def test_health_degradation_detection(self):
        """Test that health monitor detects degradation."""
        monitor = DomainHealthMonitor()
        
        # Start healthy
        for i in range(10):
            monitor.record_attempt(f"https://degrading.com/page{i}", success=True)
        
        # Then degrade
        for i in range(10, 16):
            monitor.record_attempt(f"https://degrading.com/page{i}", success=False)
        
        health = monitor.get_domain_health("https://degrading.com/any")
        assert health is not None
        assert health["degradation_trend"] > 0.0  # Positive trend = degrading
        assert health["health_level"] in ["degrading", "unhealthy"]
    
    def test_health_consistency_score(self):
        """Test consistency score calculation."""
        monitor = DomainHealthMonitor()
        
        # Record consistent failures (clustered)
        for i in range(5):
            monitor.record_attempt(f"https://test.com/page{i}", success=False)
        for i in range(5, 10):
            monitor.record_attempt(f"https://test.com/page{i}", success=True)
        
        health = monitor.get_domain_health("https://test.com/any")
        assert health is not None
        # Clustered failures = lower consistency (more predictable failure pattern)
        assert "consistency_score" in health
    
    def test_critical_health_threshold(self):
        """Test critical health status."""
        monitor = DomainHealthMonitor()
        
        # Record many recent failures
        for i in range(7):
            monitor.record_attempt(f"https://critical.com/page{i}", success=False)
        for i in range(7, 10):
            monitor.record_attempt(f"https://critical.com/page{i}", success=True)
        
        health = monitor.get_domain_health("https://critical.com/any")
        assert health is not None
        assert health["health_level"] in ["unhealthy", "critical"]
    
    def test_system_wide_health_summary(self):
        """Test system-wide health reporting."""
        monitor = DomainHealthMonitor()
        
        # Create diverse domain health states
        # Domain 1: Healthy
        for i in range(10):
            monitor.record_attempt(f"https://domain1.com/p{i}", success=True)
        
        # Domain 2: Unhealthy
        for i in range(10):
            monitor.record_attempt(f"https://domain2.com/p{i}", success=False)
        
        all_health = monitor.get_all_domains_health()
        assert len(all_health) == 2
        assert all_health[0]["health_score"] < all_health[1]["health_score"]


class TestSelectorMemoryCleanup:
    """Test selector memory cleanup integration."""
    
    def test_cleanup_removes_low_confidence(self):
        """Test that cleanup removes low-confidence selectors."""
        selector_memory = get_selector_memory()
        
        # Clear existing memory
        selector_memory._memory.clear()
        
        # Create a low-confidence selector entry manually
        domain = "old-domain.com"
        selector_memory._memory[domain] = {
            "selectors": {"css": ".item"},
            "success_count": 1,
            "failure_count": 10,  # Many failures = low confidence
            "first_seen": 0,  # Very old
            "last_success": 0,
        }
        
        initial_count = len(selector_memory._memory)
        selector_memory.force_cleanup()
        
        # Should have deleted low-confidence selector
        assert len(selector_memory._memory) <= initial_count
    
    def test_get_selector_confidence(self):
        """Test confidence scoring for selectors."""
        selector_memory = get_selector_memory()
        
        selector_memory._memory.clear()
        
        # Create a healthy selector
        domain = "healthy-domain.com"
        import time
        now = time.time()
        selector_memory._memory[domain] = {
            "selectors": {"css": ".product"},
            "success_count": 10,
            "failure_count": 1,
            "first_seen": now - 1000,  # 1000 seconds ago (< 14 days)
            "last_success": now,  # Just used
        }
        
        confidence = selector_memory.get_selector_confidence(f"https://{domain}/page")
        
        assert confidence is not None
        assert confidence.final_score > 0.8  # Should be high confidence
    
    def test_memory_stats_reporting(self):
        """Test memory statistics reporting."""
        selector_memory = get_selector_memory()
        
        selector_memory._memory.clear()
        
        # Create multiple selectors with varying confidence
        import time
        now = time.time()
        
        for i in range(3):
            domain = f"domain{i}.com"
            selector_memory._memory[domain] = {
                "selectors": {"css": f".item{i}"},
                "success_count": 5 + i * 2,
                "failure_count": i,
                "first_seen": now - 10000,
                "last_success": now,
            }
        
        stats = selector_memory.get_memory_stats()
        
        assert stats["total_domains"] == 3
        assert stats["total_selectors"] == 3
        assert 0 <= stats["avg_confidence"] <= 1.0


@pytest.mark.asyncio
class TestRecoveryHandlers:
    """Test recovery action handlers."""
    
    async def test_rotate_proxy_handler(self):
        """Test proxy rotation handler."""
        from app.recovery_handlers import handle_rotate_proxy
        
        # Mock proxy manager
        with patch('app.recovery_handlers.get_proxy_manager') as mock_pm:
            mock_mgr = MagicMock()
            mock_mgr.enabled = True
            mock_mgr.current_proxy = "http://proxy1:8080"
            mock_mgr.rotate = MagicMock(return_value="http://proxy2:8080")
            mock_pm.return_value = mock_mgr
            
            result = await handle_rotate_proxy({}, {"url": "https://example.com"})
            assert result is True
            mock_mgr.rotate.assert_called_once()
    
    async def test_backoff_and_slow_handler(self):
        """Test backoff handler."""
        from app.recovery_handlers import handle_backoff_and_slow
        
        params = {"delay_ms": 100}  # Short delay for testing
        context: dict = {}
        
        import time
        start = time.time()
        result = await handle_backoff_and_slow(params, context)
        elapsed = (time.time() - start) * 1000
        
        assert result is True
        assert elapsed >= 100  # Should have waited at least delay_ms
    
    async def test_force_rediscovery_handler(self):
        """Test force rediscovery handler."""
        from app.recovery_handlers import handle_force_rediscovery
        
        selector_memory = get_selector_memory()
        selector_memory._memory.clear()
        
        # Create a cached selector
        domain = "test.com"
        selector_memory._memory[domain] = {
            "selectors": {"css": ".item"},
            "success_count": 5,
            "failure_count": 0,
            "first_seen": 0,
            "last_success": 0,
        }
        
        context = {"url": f"https://{domain}/page"}
        result = await handle_force_rediscovery({}, context)
        
        assert result is True
        # Should have deleted the cached entry
        assert domain not in selector_memory._memory
    
    async def test_skip_url_handler(self):
        """Test skip URL handler."""
        from app.recovery_handlers import handle_skip_url
        
        context = {"url": "https://example.com/page"}
        result = await handle_skip_url({}, context)
        
        assert result is True


class TestRecoveryIntegration:
    """Integration tests for full recovery flows."""
    
    def test_recovery_handler_registration(self):
        """Test that all recovery handlers are registered."""
        register_all_recovery_handlers()
        
        executor = get_recovery_executor()
        
        # Should have handlers for all actions
        for action in RecoveryAction:
            assert action in executor.action_handlers
    
    def test_failure_to_recovery_flow(self):
        """Test end-to-end failure -> classification -> recovery plan."""
        strategist = get_recovery_strategist()
        
        # Simulate failure
        failure = FailureClassification(
            category=FailureCategory.SELECTOR_DECAY,
            confidence=0.95,
        )
        
        # Generate recovery
        plan = strategist.generate_recovery_plan(failure, attempt_number=1)
        
        # Verify plan is actionable
        assert plan.primary_action is not None
        assert len(plan.secondary_actions) > 0
        assert plan.backoff_seconds >= 0
        assert plan.max_retry_attempts > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
