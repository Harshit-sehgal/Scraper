"""
Unit Tests for Phase 86 Adaptive DOM Quietness.
"""

from __future__ import annotations

import pytest
from app.telemetry_state import get_telemetry_state


def test_default_stabilization_threshold():
    telemetry = get_telemetry_state()
    telemetry.clear()
    
    # Defaults to 1500ms for unknown domains
    val = telemetry.get_avg_stabilization("unknown-domain.com")
    assert val == 1500.0


def test_adaptive_stabilization_learning():
    telemetry = get_telemetry_state()
    telemetry.clear()
    
    # Record quick renders: 800ms
    for _ in range(5):
        telemetry.record_stabilization("fast-site.com", 800.0)

    # Average should adapt close to 800ms
    val = telemetry.get_avg_stabilization("fast-site.com")
    assert val == pytest.approx(800.0)

    # Record slow renders: 4000ms
    for _ in range(5):
        telemetry.record_stabilization("slow-site.com", 4000.0)

    val_slow = telemetry.get_avg_stabilization("slow-site.com")
    assert val_slow == pytest.approx(4000.0)


def test_bounding_rules():
    telemetry = get_telemetry_state()
    telemetry.clear()

    # Sub-500ms records should clamp to 500ms to allow minimal page paints
    telemetry.record_stabilization("lightning.com", 100.0)
    assert telemetry.get_avg_stabilization("lightning.com") == 500.0

    # Hyper-slow renders (> 5000ms) should clamp to 5000ms to avoid infinite crawl stalls
    telemetry.record_stabilization("stall.com", 9999.0)
    assert telemetry.get_avg_stabilization("stall.com") == 5000.0
