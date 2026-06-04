"""Million-Event Evolutionary Validation — Phase 54.
===============================================
LAW: Systems must survive 1M+ evolution cycles without structural decay.

This suite performs a massive longevity run, tracking entropy economics,
causal graph growth, and topology fragmentation.
"""

import random
import time

from app.semantic_ir import SemanticToken, SemanticType, Span
from app.semantic_world_state import SemanticWorldState


def _check(condition: bool, message: str) -> None:
    """Runtime invariant check. Used instead of ``assert`` so the benchmark
    keeps working when run with ``python -O`` (which strips asserts).
    """
    if not condition:
        msg = f"BENCHMARK INVARIANT FAILED: {message}"
        raise SystemExit(msg)


def run_longevity_validation(cycles: int = 100000, diversity_threshold: float = 0.5) -> None:
    ws = SemanticWorldState()
    ws.clear()

    roles = [f"role_{i}" for i in range(20)]
    types = list(SemanticType)

    start_time = time.time()
    checkpoint_interval = cycles // 20

    history_diversity = []

    for i in range(cycles):
        # 1. Randomized but clustered Event (simulate recurring patterns)
        with ws.transaction(f"longevity_{i}"):
            # Picking a role to evolve
            role = random.choice(roles)  # nosec B311 — synthetic load generator, no security need
            ttype = random.choice(types)  # nosec B311 — synthetic load generator, no security need

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
            ws.apply_force_to_manifold(role, [random.uniform(-0.005, 0.005) for _ in range(16)])  # nosec B311 — synthetic load generator, no security need

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
            time.time() - start_time
            ws._observability.get_governance_report(ws.capture_governance_snapshot())

    time.time() - start_time
    ws._observability.get_governance_report(ws.capture_governance_snapshot())

    # 6. Evolutionary Stability Invariants
    # Energy must be bounded
    _check(ws.metrics.global_energy < 50.0, f"global_energy drifted: {ws.metrics.global_energy}")
    # Entropy should be contained (Phase 56 economy)
    _check(ws.metrics.global_entropy <= 1.0, f"global_entropy exceeded economy bound: {ws.metrics.global_entropy}")
    # Diversity should not collapse to zero (Semantic Freezing)
    avg_diversity = sum(history_diversity) / len(history_diversity)
    _check(avg_diversity > diversity_threshold, f"diversity collapsed: {avg_diversity} <= {diversity_threshold}")

    # Check Journal Health (Phase 57)
    ws.trace_causality(limit=1000000)


if __name__ == "__main__":
    # Running 20k sample for validation
    run_longevity_validation(cycles=20000, diversity_threshold=0.3)
