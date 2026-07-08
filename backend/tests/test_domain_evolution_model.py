"""
Tests for Domain Evolution Model — Behavioral domain tracking.

Tests:
  - Mutation tracking
  - Anti-bot escalation detection
  - Volatility index computation
  - Selector lifespan tracking
  - Report generation
"""

import time
from app.domain_evolution_model import (
    DomainEvolutionModel,
    get_domain_evolution_model,
)
from app.selector_memory import get_selector_memory


class TestDomainEvolutionModel:
    """Test the Domain Evolution Model."""

    def test_create_model(self):
        """Test creating an evolution model."""
        model = DomainEvolutionModel()
        assert model is not None
        assert len(model._domains) == 0

    def test_record_mutation(self):
        """Test recording a structural mutation."""
        model = DomainEvolutionModel()
        model.record_mutation("example.com")
        
        metrics = model._domains["example.com"]
        assert metrics.mutation_count == 1
        assert metrics.layout_drift_events == 1
        assert metrics.last_mutation > 0

    def test_multiple_mutations(self):
        """Test recording multiple mutations."""
        model = DomainEvolutionModel()
        for _ in range(5):
            model.record_mutation("example.com")
        
        metrics = model._domains["example.com"]
        assert metrics.mutation_count == 5

    def test_record_anti_bot_escalation(self):
        """Test recording anti-bot escalation."""
        model = DomainEvolutionModel()
        model.record_anti_bot_escalation("example.com", 0.7)
        
        metrics = model._domains["example.com"]
        assert metrics.anti_bot_escalations >= 1
        assert metrics.current_anti_bot_level in ("moderate", "aggressive")

    def test_anti_bot_levels(self):
        """Test anti-bot level computation."""
        model = DomainEvolutionModel()
        
        model.record_anti_bot_escalation("example.com", 0.35)
        assert model._domains["example.com"].current_anti_bot_level == "basic"
        
        model.record_anti_bot_escalation("example.com", 0.65)
        assert model._domains["example.com"].current_anti_bot_level == "moderate"
        
        model.record_anti_bot_escalation("example.com", 0.9)
        assert model._domains["example.com"].current_anti_bot_level == "aggressive"

    def test_volatility_increases_with_mutations(self):
        """Test that volatility increases with more mutations."""
        model = DomainEvolutionModel()
        
        # Low volatility domain
        model.record_mutation("stable.com")
        
        # High volatility domain
        for _ in range(20):
            model.record_mutation("volatile.com")
        
        stable_metrics = model._domains["stable.com"]
        volatile_metrics = model._domains["volatile.com"]
        
        assert volatile_metrics.volatility_index >= stable_metrics.volatility_index

    def test_volatility_increases_with_anti_bot(self):
        """Test that anti-bot escalations increase volatility."""
        model = DomainEvolutionModel()
        
        model.record_mutation("test.com")
        base_volatility = model._domains["test.com"].volatility_index
        
        # Add anti-bot escalation
        model.record_anti_bot_escalation("test.com", 0.8)
        post_escalation_volatility = model._domains["test.com"].volatility_index
        
        assert post_escalation_volatility >= base_volatility

    def test_selector_replacement_tracking(self):
        """Test tracking selector replacements."""
        model = DomainEvolutionModel()
        model.record_selector_replaced("example.com", 168.0)  # 7 days
        
        metrics = model._domains["example.com"]
        assert metrics.mutation_count == 1
        assert metrics.selector_lifespan_avg_hours == 168.0

    def test_selector_lifespan_moving_average(self):
        """Test selector lifespan uses exponential moving average."""
        model = DomainEvolutionModel()
        model.record_selector_replaced("example.com", 100.0)
        model.record_selector_replaced("example.com", 200.0)
        
        metrics = model._domains["example.com"]
        # After first: 100, after second: (1-0.3)*100 + 0.3*200 = 70 + 60 = 130
        assert abs(metrics.selector_lifespan_avg_hours - 130.0) < 0.1

    def test_get_volatile_domains(self):
        """Test getting volatile domains."""
        model = DomainEvolutionModel()
        
        for _ in range(20):
            model.record_mutation("volatile.com")
        
        volatile = model.get_volatile_domains(threshold=0.1)
        assert len(volatile) >= 1
        assert volatile[0].domain == "volatile.com"

    def test_get_evolution_report_empty(self):
        """Test evolution report with no data."""
        model = DomainEvolutionModel()
        report = model.get_evolution_report()
        assert report["total_domains"] == 0

    def test_get_evolution_report_with_data(self):
        """Test evolution report with data."""
        model = DomainEvolutionModel()
        model.record_mutation("example.com")
        model.record_anti_bot_escalation("example.com", 0.8)
        
        report = model.get_evolution_report()
        assert report["total_domains"] >= 1
        assert "avg_volatility" in report
        assert "volatile_domains" in report
        assert "domain_map" in report

    def test_analyze_from_memory(self, monkeypatch):
        """Test analyzing from selector memory."""
        memory = get_selector_memory()
        memory._memory["test.com"] = {
            "selectors": {".item": "div.item"},
            "success_count": 5,
            "failure_count": 5,
            "first_seen": time.time() - 86400,
            "last_success": time.time(),
        }
        
        model = DomainEvolutionModel()
        model.analyze_from_memory()
        
        # Should have at least analyzed the domain
        # Failure count > 3 without lineage triggers drift event
        assert "test.com" in model._domains


class TestDomainEvolutionModelGlobal:
    """Test global singleton access."""

    def test_singleton(self):
        """Test singleton access."""
        m1 = get_domain_evolution_model()
        m2 = get_domain_evolution_model()
        assert m1 is m2
