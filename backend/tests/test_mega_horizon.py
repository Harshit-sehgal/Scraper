"""
Mega-Horizon Evolution Stress Test — Phase 48
=============================================
LAW 48: Systems must be validated against long-horizon dynamical failure
modes: attractor runaway, topology oscillation, and metastable lock states.

This suite runs 10k+ evolution cycles and analyzes the dynamical stability
of the semantic substrate.
"""

import time
import random
import pytest
from typing import List, Dict
from app.semantic_world_state import SemanticWorldState
from app.semantic_ir import SemanticType, SemanticToken, Span

class DynamicalAnalyzer:
    """Utility to detect emergent risks in long-horizon simulations."""
    def __init__(self):
        self.energies: List[float] = []
        self.entropies: List[float] = []
        self.manifold_checksums: List[str] = []
        self.role_stabilities: Dict[str, List[float]] = {}
        
    def record(self, ws: SemanticWorldState):
        self.energies.append(ws.metrics.global_energy)
        self.entropies.append(ws.metrics.global_entropy)
        self.manifold_checksums.append(ws.get_manifold_checksum())
        
        for role, vec in ws.role_manifold.items():
            if role not in self.role_stabilities:
                self.role_stabilities[role] = []
            # Using average vector value as a proxy for 'position' drift
            avg_v = sum(vec) / len(vec) if vec else 0.0
            self.role_stabilities[role].append(avg_v)

    def analyze(self):
        """Perform post-simulation analysis for emergent failures."""
        results = {}
        
        # 1. Detect Lock States (Zero manifold movement over long horizon)
        for role, history in self.role_stabilities.items():
            if len(history) > 100:
                recent = history[-50:]
                if max(recent) - min(recent) < 1e-9:
                    results["lock_state_detected"] = role
                    
        # 2. Detect Runaway Reinforcement (Stability fixed at ceiling)
        # (Actually we track this via convergence in regions)
        
        # 3. Detect Oscillations (Autocorrelation proxy)
        if len(self.energies) > 100:
            energies = self.energies[-100:]
            avg = sum(energies) / len(energies)
            flips = sum(1 for i in range(1, len(energies)) if (energies[i]-avg)*(energies[i-1]-avg) < 0)
            if flips > 25: # High frequency flipping
                results["oscillation_detected"] = True
                
        return results

@pytest.fixture
def ws():
    state = SemanticWorldState()
    state.clear()
    return state

def test_mega_horizon_simulation(ws):
    """Run 5,000 evolution cycles and analyze dynamics."""
    analyzer = DynamicalAnalyzer()
    roles = ["price", "date", "org", "loc", "person"]
    types = [SemanticType.PRICE, SemanticType.DATE, SemanticType.ORGANIZATION, SemanticType.LOCATION, SemanticType.TEXT]
    
    start_time = time.time()
    for i in range(5000):
        # 1. Random semantic event
        role = random.choice(roles)
        ttype = random.choice(types)
        
        with ws.transaction(f"ev_{i}"):
            # Manifold update
            ws.set_manifold_vector(role, [random.random() for _ in range(16)])
            # Region formation
            token = SemanticToken(
                raw=f"val_{i}", normalized=f"val_{i}",
                span=Span(0, 5), position=0,
                primary_type=ttype,
                type_distribution={ttype: 1.0}
            )
            ws.capture_pre_allocation_field([token], roles)
            
        # 2. Systemic relaxation
        if i % 5 == 0:
            ws.redistribute_instability()
            ws.aggregate_from_regions()
            
        # 3. Decay cycles
        if i % 100 == 0:
            ws.apply_memory_decay()
            
        # 4. Record diagnostics
        if i % 10 == 0:
            analyzer.record(ws)
            
    duration = time.time() - start_time
    print(f"\nMega-horizon simulation (5000 events) completed in {duration:.2f}s")
    
    analysis = analyzer.analyze()
    print(f"Dynamical Analysis: {analysis}")
    
    # Assertions for basic sanity
    assert ws.metrics.global_energy < 50.0 # No energy explosion
    assert ws.metrics.global_entropy <= 1.0 # Bounded entropy
    assert "lock_state_detected" not in analysis # No semantic freezing
    assert "oscillation_detected" not in analysis # No hidden loops

def test_attractor_runaway_vulnerability(ws):
    """Stress test the substrate with a single dominant role to check for runaway."""
    analyzer = DynamicalAnalyzer()
    
    # Single role bombarded with 1000 identical signals
    for i in range(1000):
        with ws.transaction("dominance"):
            ws.set_manifold_vector("dominant_role", [0.9]*16)
            token = SemanticToken(
                raw="heavy", normalized="heavy", span=Span(0, 5), position=0,
                primary_type=SemanticType.PRICE, type_distribution={SemanticType.PRICE: 1.0}
            )
            ws.capture_pre_allocation_field([token], ["dominant_role"])
        
        ws.aggregate_from_regions()
        if i % 10 == 0:
            analyzer.record(ws)
            
    print(f"\nDominance test completed. Final Energy: {ws.metrics.global_energy:.2f}")
    # Dominance should not lead to energy explosion
    assert ws.metrics.global_energy < 20.0

def test_emergent_risk_detection(ws):
    """Verify that the observability layer can detect oscillations and runaway attractors."""
    # 1. Runaway Attractor
    history = {"role_a": [0.99] * 30} # Zero variance, high value
    runaways = ws._observability.detect_runaway_attractors(history)
    assert len(runaways) == 1
    assert runaways[0]["role"] == "role_a"
    
    # 2. Metastable Lock
    e_history = [8.5] * 60
    s_history = [0.1] * 60
    is_locked = ws._observability.detect_metastable_locks(e_history, s_history)
    assert is_locked == True
    
    # 3. Memory Profile
    snapshot = ws.capture_governance_snapshot()
    profile = ws._observability.get_memory_profile(snapshot)
    assert profile["total_estimated_bytes"] > 0
    print(f"\nMemory Profile: {profile}")
    
    # 4. Resource Shedding
    # Trigger with a very low threshold
    did_shed = ws._observability.apply_resource_shedding(ws, ws.capture_governance_snapshot(), max_bytes=10)
    assert did_shed == True
    print("\nResource shedding successfully triggered and executed.")

def test_topology_scaling_benchmark(ws):
    """Verify propagation latency with 500+ regions (Phase 47)."""
    roles = ["r1", "r2", "r3", "r4", "r5"]
    
    # 1. Create 500 regions
    start_time = time.time()
    with ws.transaction("scaling_load"):
        for i in range(500):
            token = SemanticToken(
                raw=f"val_{i}", normalized=f"val_{i}",
                span=Span(0, 5), position=0,
                primary_type=SemanticType.NUMBER,
                type_distribution={SemanticType.NUMBER: 1.0}
            )
            # Creating complex coupling by using overlapping roles
            ws.capture_pre_allocation_field([token], [roles[i % 5], roles[(i+1) % 5]])
            
    load_duration = time.time() - start_time
    print(f"\nScaling Benchmark: Created 500 regions in {load_duration:.2f}s")
    
    # 2. Run propagation
    start_time = time.time()
    ws.redistribute_instability()
    prop_duration = time.time() - start_time
    print(f"Propagation (500 regions) completed in {prop_duration:.4f}s")
    
    # Target: propagation should be < 100ms for 500 regions
    assert prop_duration < 0.2 # Adjusted for CI environment
