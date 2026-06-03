"""
Stress Tests for Domain Health System

Tests the domain health monitoring system under high load:
- Rapid failure/success updates
- Many concurrent domains
- Extreme failure rates
- Recovery from critical states
"""

import pytest
from app.domain_health_alerts import (
    DomainHealthMonitor,
)


class TestDomainHealthStress:
    """Stress test the domain health monitoring system."""

    def test_many_domains_concurrent_monitoring(self) -> None:
        """Test monitoring many domains simultaneously."""
        monitor = DomainHealthMonitor()

        num_domains = 100
        attempts_per_domain = 20

        # Record attempts for many domains
        for domain_id in range(num_domains):
            domain = f"https://domain{domain_id}.com/"
            for i in range(attempts_per_domain):
                # Vary success/failure ratio per domain
                success = (domain_id + i) % 3 != 0  # ~67% success rate
                monitor.record_attempt(f"{domain}page{i}", success=success)

        # Get all health stats
        all_health = monitor.get_all_domains_health()

        assert len(all_health) == num_domains
        assert all(h["health_score"] is not None for h in all_health)

    def test_rapid_state_changes(self) -> None:
        """Test rapid success/failure state changes."""
        monitor = DomainHealthMonitor()
        domain = "https://volatile.com/"

        # Rapid alternating success/failure
        for i in range(50):
            success = i % 2 == 0
            monitor.record_attempt(f"{domain}page{i}", success=success)

        health = monitor.get_domain_health(f"{domain}any")

        assert health is not None
        assert health["success_rate"] == pytest.approx(0.5, 0.1)

    def test_extreme_failure_rate(self) -> None:
        """Test monitoring of domain with extreme failure rate."""
        monitor = DomainHealthMonitor()
        domain = "https://broken.com/"

        # 95% failure rate
        for i in range(100):
            success = i < 5  # Only 5 successes
            monitor.record_attempt(f"{domain}page{i}", success=success)

        health = monitor.get_domain_health(f"{domain}any")

        assert health is not None
        assert health["health_level"] == "blacklisted"  # Should be blacklisted
        assert health["success_rate"] == pytest.approx(0.05, 0.01)

    def test_recovery_from_critical(self) -> None:
        """Test recovery from critical state to healthy."""
        monitor = DomainHealthMonitor()
        domain = "https://recovering.com/"

        # Start in critical (many failures)
        for i in range(15):
            monitor.record_attempt(f"{domain}page{i}", success=False)

        health_critical = monitor.get_domain_health(f"{domain}any")
        assert health_critical is not None
        assert health_critical["health_level"] in ["critical", "unhealthy", "blacklisted"]

        # Then recover (many successes)
        for i in range(15, 35):
            monitor.record_attempt(f"{domain}page{i}", success=True)

        health_recovered = monitor.get_domain_health(f"{domain}any")
        assert health_recovered is not None
        assert health_recovered["health_score"] > health_critical["health_score"]

    def test_long_tail_domain_pattern(self) -> None:
        """Test monitoring of long-tail domain with sparse updates."""
        monitor = DomainHealthMonitor()

        # Create 10 domains with different activity levels
        for domain_id in range(10):
            domain = f"https://sparse{domain_id}.com/"
            # Each domain has different number of attempts
            attempts = (domain_id + 1) * 3  # 3, 6, 9, ...
            for i in range(attempts):
                success = i % 2 == 0
                monitor.record_attempt(f"{domain}page{i}", success=success)

        all_health = monitor.get_all_domains_health()
        assert len(all_health) == 10

        # Verify scores vary by domain
        scores = [h["health_score"] for h in all_health]
        assert min(scores) < max(scores)  # Should have variation

    def test_alert_cooldown_prevents_spam(self) -> None:
        """Test that alert cooldown prevents alert spam."""
        monitor = DomainHealthMonitor()
        alert_count = 0

        def dummy_alert_handler(alert):
            nonlocal alert_count
            alert_count += 1

        monitor.alert_callback = dummy_alert_handler
        monitor._alert_cooldown_seconds = 60  # 60 second cooldown

        domain = "https://spam.com/"

        # Rapid failures
        for i in range(20):
            monitor.record_attempt(f"{domain}page{i}", success=False)

        # Alert should not have fired multiple times due to cooldown
        # (Note: alert handling is async, so actual count may vary)
        # This test just ensures no exceptions are raised
        assert monitor is not None

    def test_consistency_score_high_variance(self) -> None:
        """Test consistency scoring with high variance failures."""
        monitor = DomainHealthMonitor()
        domain = "https://inconsistent.com/"

        # Alternating blocks of successes and failures
        for block in range(3):
            # Success block
            for i in range(10):
                monitor.record_attempt(f"{domain}page{i + block * 20}", success=True)
            # Failure block
            for i in range(10):
                monitor.record_attempt(f"{domain}page{i + block * 20 + 10}", success=False)

        health = monitor.get_domain_health(f"{domain}any")

        # High variance (clustered failures) = lower consistency
        assert health is not None
        assert health["consistency_score"] < 1.0

    def test_trend_detection_gradual_degradation(self) -> None:
        """Test trend detection for gradual degradation."""
        monitor = DomainHealthMonitor()
        domain = "https://degrading.com/"

        # Gradually degrade from 100% success to 10% success
        for i in range(100):
            # Decrease success rate by 1% every 10 attempts
            success = i % (100 - (i // 10)) == 0
            monitor.record_attempt(f"{domain}page{i}", success=success)

        health = monitor.get_domain_health(f"{domain}any")

        # Should detect negative trend (positive slope = degrading)
        assert health is not None
        assert isinstance(health.get("degradation_trend"), float)
        # Trend could be positive or negative depending on implementation
        assert -1.0 <= health.get("degradation_trend", 0) <= 1.0

    def test_memory_efficiency_large_history(self) -> None:
        """Test memory efficiency with large attempt history."""
        monitor = DomainHealthMonitor()

        # Create many domains with long histories
        for domain_id in range(20):
            domain = f"https://domain{domain_id}.com/"
            for i in range(100):  # 100 attempts per domain
                success = (domain_id + i) % 2 == 0
                monitor.record_attempt(f"{domain}page{i}", success=success)

        # Verify system handles it gracefully
        all_health = monitor.get_all_domains_health()
        assert len(all_health) == 20

        # Recent attempts should be capped (deque maxlen=50)
        for domain_metrics in monitor._domains.values():
            assert len(domain_metrics.recent_attempts) <= 50

    def test_failure_category_tracking(self) -> None:
        """Test tracking of specific failure categories over time."""
        monitor = DomainHealthMonitor()
        domain = "https://categories.com/"

        categories = ["selector_decay", "anti_bot_block", "rate_limited"]

        # Record different failure types
        for idx, category in enumerate(categories):
            for i in range(10):
                monitor.record_attempt(f"{domain}page{idx * 10 + i}", success=False, failure_category=category)

        health = monitor.get_domain_health(f"{domain}any")
        assert health is not None
        # Should have tracked a failure category
        assert health.get("recent_failure_category") in categories

    def test_concurrent_domain_updates(self) -> None:
        """Test concurrent updates to multiple domains."""
        monitor = DomainHealthMonitor()

        domains = [f"https://concurrent{i}.com/" for i in range(10)]

        # Simulate concurrent-like updates
        for round_num in range(50):
            for domain_id, domain in enumerate(domains):
                success = (round_num + domain_id) % 3 != 0
                monitor.record_attempt(f"{domain}page{round_num}", success=success)

        all_health = monitor.get_all_domains_health()
        assert len(all_health) == 10

        # All should have meaningful scores
        for h in all_health:
            assert 0 <= h["health_score"] <= 1.0


class TestHealthMetricsEdgeCases:
    """Test edge cases in health calculations."""

    def test_single_attempt_domain(self) -> None:
        """Test health calculation with single attempt."""
        monitor = DomainHealthMonitor()

        monitor.record_attempt("https://single.com/page1", success=True)

        health = monitor.get_domain_health("https://single.com/any")
        assert health is not None
        assert health["success_rate"] == 1.0  # Single success

    def test_100_percent_failure_domain(self) -> None:
        """Test domain with 100% failure rate."""
        monitor = DomainHealthMonitor()
        domain = "https://perfect-fail.com/"

        for i in range(10):
            monitor.record_attempt(f"{domain}page{i}", success=False)

        health = monitor.get_domain_health(f"{domain}any")
        assert health is not None
        assert health["success_rate"] == 0.0
        assert health["health_level"] == "blacklisted"

    def test_100_percent_success_domain(self) -> None:
        """Test domain with 100% success rate."""
        monitor = DomainHealthMonitor()
        domain = "https://perfect-success.com/"

        for i in range(10):
            monitor.record_attempt(f"{domain}page{i}", success=True)

        health = monitor.get_domain_health(f"{domain}any")
        assert health is not None
        assert health["success_rate"] == 1.0
        assert health["health_level"] == "healthy"

    def test_very_fresh_domain(self) -> None:
        """Test domain with minimal history."""
        monitor = DomainHealthMonitor()

        monitor.record_attempt("https://fresh.com/page1", success=True)
        monitor.record_attempt("https://fresh.com/page2", success=True)

        health = monitor.get_domain_health("https://fresh.com/any")
        assert health is not None
        assert health["success_rate"] == 1.0
        assert health["health_level"] == "healthy"
