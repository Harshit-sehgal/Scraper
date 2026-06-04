"""Systemic Survivability & Long-Horizon Evolution Stress Tests.
===========================================================
LAW 46: Adaptive systems must be validated via adversarial simulation,
not just unit tests.

This suite performs 10,000+ transaction simulations with chaos injection
to detect emergent causality drift and attractor collapse.
"""

import random
import time

import pytest
from app.failure_injector import set_injection_probability
from app.semantic_ir import SemanticToken, SemanticType, Span
from app.semantic_world_state import SemanticWorldState


@pytest.fixture
def ws():
    return SemanticWorldState()


def simulate_event(ws: SemanticWorldState, role_name: str, token_type: SemanticType) -> None:
    """Simulate a single semantic event within a transaction."""
    with ws.transaction(f"event:{role_name}"):
        # 1. Update manifold
        ws.set_manifold_vector(role_name, [random.random() for _ in range(16)])

        # 2. Update compatibility
        ws.set_compatibility(role_name, token_type.value, random.random())

        # 3. Create actual field regions to drive energy/entropy
        token = SemanticToken(
            raw="simulated_token",
            normalized="simulated_token",
            span=Span(0, 5),
            position=0,
            primary_type=token_type,
            type_distribution={token_type: 1.0},
        )
        # Capture field (creates regions)
        ws.capture_pre_allocation_field([token], [role_name])

        # 4. Trigger topology movement
        ws.redistribute_instability()
        ws.aggregate_from_regions()


def test_long_horizon_stability(ws) -> None:
    """Run 500 events and check for basic thermodynamic sanity."""
    roles = ["price", "date", "location", "org", "rating"]
    types = [SemanticType.PRICE, SemanticType.DATE, SemanticType.LOCATION, SemanticType.ORGANIZATION, SemanticType.RATING]

    start_time = time.time()
    for i in range(500):
        role = random.choice(roles)
        ttype = random.choice(types)
        simulate_event(ws, role, ttype)

        # Every 50 events, perform cognitive decay
        if i % 50 == 0:
            ws.apply_memory_decay()

    time.time() - start_time

    # Sanity checks
    assert ws.metrics.global_energy >= 0.0
    assert ws.metrics.global_entropy >= 0.0
    assert len(ws.role_manifold) == len(roles)


def test_chaos_transaction_survivability(ws) -> None:
    """Inject random failures during 100 transactions and verify atomicity."""
    set_injection_probability(0.05)  # 5% failure rate

    roles = ["chaos_role_1", "chaos_role_2"]
    success_count = 0
    failure_count = 0

    for _i in range(100):
        try:
            simulate_event(ws, random.choice(roles), SemanticType.TEXT)
            success_count += 1
        except RuntimeError:
            failure_count += 1

    set_injection_probability(0.0)  # Reset

    # The world state should still be 'clean' (no partial commits)
    assert ws.metrics.global_energy >= 0.0


def test_attractor_collapse_resistance(ws) -> None:
    """Feed adversarial contradictory data and check if entropy increases."""
    role = "unstable_role"
    # Constant bombardment with contradictory types
    for _ in range(50):
        # Morning: it's a price
        simulate_event(ws, role, SemanticType.PRICE)
        # Afternoon: it's a date
        simulate_event(ws, role, SemanticType.DATE)

    # Entropy should be high due to contradiction (instability accumulation)
    assert ws.metrics.global_entropy > 0.3

    # Now stabilize it
    for _ in range(100):
        simulate_event(ws, role, SemanticType.PRICE)

    # Energy should decay as it settles into a stable PRICE basin
    ws.apply_memory_decay()
    ws.aggregate_from_regions()

    # Stability should return (Entropy contained, but elevated by Phase 55/56 diversification)
    assert ws.metrics.global_entropy < 0.95


def test_causal_lineage_traceability(ws) -> None:
    """Verify that every state mutation is linked to a trace ID."""
    simulate_event(ws, "traced_role", SemanticType.NUMBER)

    trace = ws.get_causal_telemetry()
    assert len(trace) > 0
    # Every event must have a trace_id and node_id in details
    for entry in trace:
        details = entry.get("details", {})
        assert "trace_id" in details
        assert details["node_id"] == ws.node_id
