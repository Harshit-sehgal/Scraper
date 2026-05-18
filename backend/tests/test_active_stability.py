"""
Active Stability Control & Value-Aware Pruning Tests
===================================================
LAW 49/50: Adaptive systems must govern their own dynamics via active
damping and protect high-value semantic nodes during resource shedding.
"""

import pytest
from app.semantic_world_state import SemanticWorldState
from app.semantic_ir import SemanticType

@pytest.fixture
def ws():
    state = SemanticWorldState()
    state.clear()
    return state

def test_active_damping_calculation(ws):
    """Verify that damping factor decreases as oscillations are detected."""
    # 1. No oscillations
    snapshots = [{"energy": 5.0}] * 10
    damping = ws._observability.calculate_damping_factor(snapshots)
    assert damping == 1.0
    
    # 2. Strong oscillations (autocorrelation flips)
    oscillating_snapshots = []
    for i in range(20):
        val = 5.0 + 2.0 * (i % 2)
        oscillating_snapshots.append({"energy": val})
        
    damping = ws._observability.calculate_damping_factor(oscillating_snapshots)
    assert damping < 1.0
    print(f"\nDamping factor for oscillation: {damping:.2f}")

def test_value_aware_pruning_priority(ws):
    """Verify that high-importance regions are preserved during shedding."""
    # 1. Create 60 regions
    # Region 1: High Centrality, High Stability (Should be kept)
    r_high = ws._topology.add(["role_a"], "IMPORTANT", instability=0.01)
    ws._topology._centrality[r_high.region_id] = 1.0
    
    # Fill up to 60 with garbage
    for i in range(59):
        ws._topology.add(["junk"], f"JUNK_{i}", instability=0.9)
        
    assert ws._topology.region_count() == 60
    
    # 2. Trigger Shedding (max_bytes=1 to force it)
    ws._observability.apply_resource_shedding(ws, max_bytes=1)
    
    # 3. Verify top regions (kept top 50)
    current_regions = ws._topology._get_regions()
    assert len(current_regions) == 50
    
    # The high-importance region should be in the kept set
    kept_ids = [r.region_id for r in current_regions]
    assert r_high.region_id in kept_ids
    print("\nValue-Aware Pruning: High-importance region successfully preserved.")

def test_stability_policy_generation(ws):
    """Verify that the engine generates a valid stabilization policy."""
    policy = ws._observability.get_stability_policy(ws)
    assert "propagation_damping" in policy
    assert "attractor_scaling" in policy
    assert "force_decay" in policy
    print(f"\nStabilization Policy: {policy}")
