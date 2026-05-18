"""
Semantic Stress Testing — Adversarial Substrate Validation
=========================================================
LAW 46: Systemic survivability requires resilience against adversarial
semantic streams (noise, contradictions, and recursive hallucinations).
"""

import pytest
from app.semantic_pipeline import run_pipeline
from app.semantic_world_state import get_world_state
from app.semantic_ir import SemanticType

@pytest.fixture
def ws():
    state = get_world_state()
    state.clear()
    return state

def test_contradictory_bombardment(ws):
    """Feed two batches of data that directly contradict each other's schema
    patterns and verify thermodynamic containment."""
    
    # Use roles that are in ROLE_EXCLUSIVITY to ensure regions are created
    schema = ["price", "cost"]
    
    batch1 = [
        {"price": "$100", "cost": "$80", "other": "Product A"},
        {"price": "$200", "cost": "$150", "other": "Product B"}
    ]
    
    # Contradiction: Swap them or use values that create tension
    batch2 = [
        {"price": "2026-05-17", "cost": "2026-05-18", "other": "Contradictory C"},
        {"price": "Chennai", "cost": "Bangalore", "other": "Contradictory D"}
    ]
    
    print("\n--- Phase 1: Stable Knowledge Acquisition ---")
    run_pipeline(batch1, schema)
    # Ensure some regions were created
    assert ws.get_topology_view().region_count() > 0
    
    print("\n--- Phase 2: Contradictory Bombardment ---")
    run_pipeline(batch2, schema)
    
    # Entropy and Energy should reflect the tension (Adjusted for Phase 56 smoothing)
    print(f"Entropy after bombardment: {ws.metrics.global_entropy:.2f}")
    assert ws.metrics.global_entropy > 0.05
    
    print("\n--- Phase 3: Stabilization Pass ---")
    for _ in range(5):
        run_pipeline(batch1, schema)
        ws.apply_memory_decay()
        ws.aggregate_from_regions()
        
    print(f"Entropy after stabilization: {ws.metrics.global_entropy:.2f}")
    assert ws.metrics.global_entropy < 0.7

def test_recursive_hallucination_chain(ws):
    """Simulate a loop where the system's own outputs are fed back."""
    
    schema = ["entity_name", "price"]
    # Meaty data to pass filters
    data = [{"entity_name": "Product Alpha", "price": "$100"}]
    
    for i in range(10):
        results = run_pipeline(data, schema)
        if not results:
            break
        # Create a new record from the result
        data = [{"entity_name": results[0].get("entity_name", "Alpha"), 
                 "price": results[0].get("price", "$10")}]
        
    # Should not crash and should remain stable
    assert ws.metrics.global_entropy < 1.0

def test_oscillation_detection(ws):
    """Artificially create an energy oscillation and verify detection."""
    snapshots = []
    # Create 20 snapshots with oscillating energy
    for i in range(20):
        # Sine-wave energy oscillation
        energy = 5.0 + 2.0 * (i % 2) # Toggle between 5 and 7
        snapshots.append({"energy": energy, "label": f"snap_{i}"})
        
    oscillations = ws._observability.detect_oscillations(snapshots, window=20)
    assert len(oscillations) > 0
    assert oscillations[0]["type"] == "global_energy"
    print(f"\nOscillation detected: {oscillations[0]}")

def test_massive_topology_scaling(ws):
    """Verify performance with 100 regions."""
    import time
    from app.semantic_ir import SemanticToken, Span
    
    start_time = time.time()
    
    with ws.transaction("scaling_test"):
        for i in range(100):
            token = SemanticToken(
                raw=f"val_{i}", normalized=f"val_{i}",
                span=Span(0, 5), position=0,
                primary_type=SemanticType.NUMBER,
                type_distribution={SemanticType.NUMBER: 1.0}
            )
            # Use 'price' and 'cost' to trigger ROLE_EXCLUSIVITY regions
            ws.capture_pre_allocation_field([token], ["price", "cost"])
            
    capture_duration = time.time() - start_time
    print(f"\nCaptured {ws.get_topology_view().region_count()} regions in {capture_duration:.2f}s")
    
    start_time = time.time()
    ws.redistribute_instability()
    prop_duration = time.time() - start_time
    print(f"Propagation completed in {prop_duration:.2f}s")
    
    assert prop_duration < 0.2
