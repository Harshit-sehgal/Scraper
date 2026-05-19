"""
Tests for Selector Decay Predictor — Predictive selector failure detection.

Tests:
  - Decay prediction for stable vs degrading selectors
  - Confidence trend tracking
  - Risk level classification
  - At-risk domain detection
  - Report generation
"""

import time
from app.selector_decay_predictor import (
    SelectorDecayPredictor,
    get_selector_decay_predictor,
)
from app.selector_memory import get_selector_memory


class TestSelectorDecayPredictor:
    """Test the Selector Decay Predictor."""

    def test_create_predictor(self):
        """Test creating a decay predictor."""
        predictor = SelectorDecayPredictor()
        assert predictor is not None
        assert len(predictor._confidence_snapshots) == 0

    def test_record_observation(self):
        """Test recording a confidence observation."""
        predictor = SelectorDecayPredictor()
        predictor.record_observation("example.com", 0.95)
        assert "example.com" in predictor._confidence_snapshots
        assert len(predictor._confidence_snapshots["example.com"]) == 1

    def test_multiple_observations(self):
        """Test recording multiple observations."""
        predictor = SelectorDecayPredictor()
        for i in range(10):
            predictor.record_observation("example.com", 0.9 - i * 0.05)
        assert len(predictor._confidence_snapshots["example.com"]) == 10

    def test_observation_capped_at_100(self):
        """Test that observations are capped at 100."""
        predictor = SelectorDecayPredictor()
        for i in range(150):
            predictor.record_observation("example.com", 0.5)
        assert len(predictor._confidence_snapshots["example.com"]) == 100

    def test_predict_decay_no_data(self):
        """Test decay prediction with no selector data."""
        predictor = SelectorDecayPredictor()
        prediction = predictor.predict_decay("unknown-domain.com")
        assert prediction.decay_risk == 0.0
        assert prediction.risk_level == "stable"

    def test_predict_decay_with_healthy_selector(self, monkeypatch):
        """Test decay prediction with a healthy selector."""
        memory = get_selector_memory()
        domain = "healthy.example.com"
        
        # Record a healthy entry directly in memory
        memory._memory[domain] = {
            "selectors": {".item": "div.item"},
            "success_count": 50,
            "failure_count": 1,
            "first_seen": time.time() - 86400,  # 1 day ago
            "last_success": time.time() - 3600,  # 1 hour ago
        }
        
        predictor = SelectorDecayPredictor()
        for _ in range(10):
            predictor.record_observation(domain, 0.95)
        
        prediction = predictor.predict_decay(domain)
        assert prediction.decay_risk < 0.3  # Should be stable
        assert prediction.risk_level in ("stable", "watch")
        assert prediction.days_until_failure >= 30.0

    def test_predict_decay_with_degrading_selector(self, monkeypatch):
        """Test decay prediction with a degrading selector."""
        memory = get_selector_memory()
        domain = "degrading.example.com"
        
        # Record a degrading entry - many failures, old age
        memory._memory[domain] = {
            "selectors": {".old-item": "div.old-item"},
            "success_count": 10,
            "failure_count": 20,
            "first_seen": time.time() - (20 * 86400),  # 20 days ago
            "last_success": time.time() - (10 * 86400),  # 10 days ago
        }
        
        predictor = SelectorDecayPredictor()
        # Record declining confidence
        for i in range(10):
            predictor.record_observation(domain, max(0.1, 0.8 - i * 0.07))
        
        prediction = predictor.predict_decay(domain)
        assert prediction.decay_risk > 0.4  # Should be elevated
        assert prediction.risk_level != "stable"

    def test_get_domains_at_risk(self, monkeypatch):
        """Test getting domains at risk above threshold."""
        memory = get_selector_memory()
        
        # Add a healthy domain
        memory._memory["healthy.com"] = {
            "selectors": {".item": "div.item"},
            "success_count": 100,
            "failure_count": 0,
            "first_seen": time.time() - 86400,
            "last_success": time.time(),
        }
        
        # Add a degrading domain
        memory._memory["degrading.com"] = {
            "selectors": {".old-item": "div.old-item"},
            "success_count": 5,
            "failure_count": 15,
            "first_seen": time.time() - (30 * 86400),
            "last_success": time.time() - (20 * 86400),
        }
        
        predictor = SelectorDecayPredictor()
        # Record declining observations for degrading domain
        for i in range(10):
            predictor.record_observation("degrading.com", max(0.1, 0.7 - i * 0.06))
        predictor.record_observation("healthy.com", 0.98)
        
        at_risk = predictor.get_domains_at_risk(threshold=0.5)
        assert len(at_risk) >= 1
        # The degrading domain should be first (highest risk)
        assert at_risk[0].domain == "degrading.com"

    def test_get_decay_report(self, monkeypatch):
        """Test comprehensive decay report."""
        memory = get_selector_memory()
        memory._memory["test.com"] = {
            "selectors": {".item": "div.item"},
            "success_count": 10,
            "failure_count": 2,
            "first_seen": time.time() - 86400,
            "last_success": time.time(),
        }
        
        predictor = SelectorDecayPredictor()
        predictor.record_observation("test.com", 0.85)
        
        report = predictor.get_decay_report()
        assert report["total_domains_tracked"] >= 1
        assert "avg_decay_risk" in report
        assert "predictions" in report
        assert len(report["predictions"]) >= 1

    def test_generate_recommendations_critical(self):
        """Test recommendations for critical risk level."""
        predictor = SelectorDecayPredictor()
        recs = predictor._generate_recommendations(
            "example.com", "critical", 0.85, 0.3,
            type("obj", (object,), {"age_factor": 0.3})()
        )
        assert any("URGENT" in r for r in recs)
        assert any("Re-discover" in r or "re-discover" in r for r in recs)

    def test_generate_recommendations_stable(self):
        """Test recommendations for stable risk level."""
        predictor = SelectorDecayPredictor()
        recs = predictor._generate_recommendations(
            "example.com", "stable", 0.1, 0.0,
            type("obj", (object,), {"age_factor": 0.9})()
        )
        assert any("stable" in r for r in recs)
        assert not any("URGENT" in r for r in recs)


class TestSelectorDecayPredictorGlobal:
    """Test global singleton access."""

    def test_singleton(self):
        """Test singleton access."""
        p1 = get_selector_decay_predictor()
        p2 = get_selector_decay_predictor()
        assert p1 is p2

    def test_snapshot_persistence(self, monkeypatch):
        """Test that confidence snapshots are persisted to JSON and successfully reloaded."""
        import os
        monkeypatch.setenv("TEST_SELECTOR_DECAY_PERSISTENCE", "1")
        predictor = SelectorDecayPredictor()
        predictor._confidence_snapshots.clear()
        predictor.record_observation("persistent.com", 0.88)
        
        predictor2 = SelectorDecayPredictor()
        assert "persistent.com" in predictor2._confidence_snapshots
        assert predictor2._confidence_snapshots["persistent.com"][0][1] == 0.88
        
        try:
            os.remove("backend/data/selector_decay_snapshots.json")
        except Exception:
            pass
