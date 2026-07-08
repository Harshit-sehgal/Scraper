from app.semantic_world_state import get_world_state

def test_stability_debt_accumulation():
    ws = get_world_state()
    ws.clear()
    
    # Need at least one region with low integrity and high local energy
    r = ws._topology.add(["role_a"], "test", instability=0.8, integrity=0.2)
    # Ensure local energy is high so it pulls global energy up
    ws._topology.set_region_energy(r.region_id, 9.0)
    
    # Force high energy and low convergence to accumulate debt
    ws._energy.set_energy(9.0)
    ws._energy.set_convergence(0.2)
    
    # Evolve macro state - should increase debt
    ws.evolve_macro_state()
    assert ws.metrics.stability_debt > 0.0

def test_phase_transition_trigger():
    ws = get_world_state()
    ws.clear()
    
    # Need at least one region
    r = ws._topology.add(["role_a"], "test", instability=0.8, integrity=0.2)
    ws._topology.set_region_energy(r.region_id, 9.0)
    
    # Set debt near threshold
    ws._energy.stability_debt = 0.95
    ws._energy.set_energy(9.0)
    ws._energy.set_convergence(0.2)
    
    # 1. Add an exclusion that is NOT anchored
    key = tuple(sorted(["role_a", "role_b"]))
    ws._instability.set_exclusion(key, 0.8)
    
    # 2. Evolve macro state - should trigger phase transition
    ws.evolve_macro_state()
    
    # Debt should be cleared
    assert ws.metrics.stability_debt == 0.0
    # Exclusion should be significantly decayed (melted)
    assert ws.learned_exclusions.get(key, 0.0) < 0.3

def test_anchors_resist_melting():
    ws = get_world_state()
    ws.clear()
    
    # 1. Establish an Anchor
    key = tuple(sorted(["origin", "destination"]))
    ws._topology.record_anchor(key)  # type: ignore[arg-type]
    ws._instability.set_exclusion(key, 1.0)
    
    # 2. Trigger Phase Transition manually
    ws._energy.stability_debt = 2.0
    ws.evolve_macro_state()
    
    # Anchor should still have high exclusion
    assert ws.learned_exclusions.get(key, 0.0) == 1.0

def test_local_reservoir_burst():
    from app.core_types import FieldConflictRegion
    region = FieldConflictRegion(competing_roles=["a", "b"], token="X", instability=0.8)
    region.local_convergence = 0.2
    
    # Evolve multiple times to fill reservoir
    for _ in range(15):
        region.evolve(force=True)
        
    # Should have triggered local restructuring
    assert region.energy_reservoir == 0.0
    assert region.instability < 0.8
