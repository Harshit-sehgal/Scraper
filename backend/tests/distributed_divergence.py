"""
Distributed Replay Divergence Tester — Phase 55
==============================================
LAW: Distributed semantic systems must reach identical topological states
when replaying identical causal journals.

This test validates that two independent nodes reaching a state via
transactional mutation vs deterministic replay result in 0% divergence.
"""

import random

from app.semantic_world_state import SemanticWorldState


def test_distributed_divergence(event_count: int = 1000) -> bool:
    # Node A: The primary evolver
    ws_a = SemanticWorldState(node_id="node_a")
    ws_a.clear()
    ws_a._journal_capacity = event_count + 100

    # Node B: The replica replayer
    ws_b = SemanticWorldState(node_id="node_b")
    ws_b.clear()

    roles = [f"role_{i}" for i in range(10)]

    print(f"\n--- Starting Divergence Test ({event_count} events) ---")

    # 1. Evolve Node A
    for i in range(event_count):
        with ws_a.transaction(f"tx_{i}"):
            ws_a.set_manifold_vector(random.choice(roles), [random.random() for _ in range(16)])
            if i % 10 == 0:
                ws_a.redistribute_instability()
                ws_a.aggregate_from_regions()

    # 2. Extract causality from A and Replay on B
    journal = ws_a.trace_causality(limit=event_count + 100)

    for tx in journal:
        # Simulate cross-node transfer (JSON serialization)
        import json

        tx_wire = json.loads(json.dumps(tx))
        ws_b.replay_transaction(tx_wire)

    # 3. Measure Divergence
    checksum_a = ws_a.get_manifold_checksum()
    checksum_b = ws_b.get_manifold_checksum()

    energy_a = ws_a.metrics.global_energy
    energy_b = ws_b.metrics.global_energy

    print(f"  Node A Checksum: {checksum_a[:16]}... Energy: {energy_a:.4f}")
    print(f"  Node B Checksum: {checksum_b[:16]}... Energy: {energy_b:.4f}")

    assert checksum_a == checksum_b, "CRITICAL: Manifold checksum mismatch after distributed replay!"
    assert abs(energy_a - energy_b) < 1e-6, "CRITICAL: Thermodynamic divergence detected!"

    print("  Divergence: 0.00% (Perfect Parity confirmed)")
    return True


if __name__ == "__main__":
    test_distributed_divergence(event_count=2000)
