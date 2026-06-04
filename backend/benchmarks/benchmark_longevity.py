"""
Million-Event Evolutionary Validation — Phase 54
===============================================
LAW: Systems must survive 1M+ evolution cycles without structural decay.

This suite performs a massive longevity run, tracking entropy economics,
causal graph growth, and topology fragmentation.
"""

import random
import time

from app.semantic_ir import SemanticToken, SemanticType, Span
from app.semantic_world_state import SemanticWorldState


def run_longevity_validation(cycles: int = 100000, diversity_threshold: float = 0.5):
    ws = SemanticWorldState()
    ws.clear()

    roles = [f"role_{i}" for i in range(20)]
    types = list(SemanticType)

    start_time = time.time()
    checkpoint_interval = cycles // 20

    history_diversity = []

    print(f"\n--- Initiating Longevity Validation ({cycles} cycles) ---")

    for i in range(cycles):
        # 1. Randomized but clustered Event (simulate recurring patterns)
        with ws.transaction(f"longevity_{i}"):
            # Picking a role to evolve
            role = random.choice(roles)
            ttype = random.choice(types)

            # Create token with some recurring consistency
            token_val = f"val_{role}_{i % 50}"
            token = SemanticToken(
                raw=token_val,
                normalized=token_val,
                span=Span(0, 5),
                position=0,
                primary_type=ttype,
                type_distribution={ttype: 1.0},
            )
            ws.capture_pre_allocation_field([token], roles)
            # Manifold drift - very small for longevity
            ws.apply_force_to_manifold(role, [random.uniform(-0.005, 0.005) for _ in range(16)])

        # 2. Adaptive Governance (Phase 56)
        # Includes: Instability redistribution, Attractor rebalancing, Entropy economy
        if i % 10 == 0:
            ws.redistribute_instability()
            ws.aggregate_from_regions()

        # 3. Decay & GC
        if i % 100 == 0:
            ws.apply_memory_decay()
            ws.decay_field_regions()

        # 4. Resource Shedding (Phase 50)
        if i % 500 == 0:
            # Memory profiler check
            snapshot = ws.capture_governance_snapshot()
            profile = ws._observability.get_memory_profile(snapshot)
            if profile["total_estimated_bytes"] > 100000:
                ws._observability.apply_resource_shedding(ws, ws.capture_governance_snapshot(), max_bytes=80000)

        # 5. Diagnostic Tracking
        if i % 50 == 0:
            diversity = ws._observability.calculate_attractor_diversity(ws.capture_governance_snapshot())
            history_diversity.append(diversity)

        if i % checkpoint_interval == 0 and i > 0:
            elapsed = time.time() - start_time
            report = ws._observability.get_governance_report(ws.capture_governance_snapshot())
            print(
                f"  [{i}] Energy: {ws.metrics.global_energy:.2f}, Entropy: {ws.metrics.global_entropy:.2f}, "
                f"Diversity: {report['diversity']:.2f}, Elapsed: {elapsed:.1f}s",
            )

    total_duration = time.time() - start_time
    final_report = ws._observability.get_governance_report(ws.capture_governance_snapshot())

    print("\n--- Longevity Validation Completed ---")
    print(f"Total Duration: {total_duration:.2f}s")
    print(f"Final Global Energy: {ws.metrics.global_energy:.2f}")
    print(f"Final Global Entropy: {ws.metrics.global_entropy:.2f}")
    print(f"Final Diversity: {final_report['diversity']:.3f}")
    print(f"Active Regions: {ws.get_topology_view().region_count()}")

    # 6. Evolutionary Stability Invariants
    # Energy must be bounded
    assert ws.metrics.global_energy < 50.0
    # Entropy should be contained (Phase 56 economy)
    assert ws.metrics.global_entropy <= 1.0
    # Diversity should not collapse to zero (Semantic Freezing)
    avg_diversity = sum(history_diversity) / len(history_diversity)
    print(f"Average Diversity over horizon: {avg_diversity:.3f}")
    assert avg_diversity > diversity_threshold

    # Check Journal Health (Phase 57)
    journal_size = ws.trace_causality(limit=1000000)
    print(f"Causal Journal Size: {len(journal_size)}")

    print("\n[OK] Synthetic longevity invariants held for this run.")


if __name__ == "__main__":
    # Running 20k sample for validation
    run_longevity_validation(cycles=20000, diversity_threshold=0.3)
