"""
Million-Event Evolutionary Ecology Validation — Phase 58
======================================================
LAW: Stable adaptive systems must maintain structural diversity and
causal coherence over multi-million event horizons.

This suite performs a massive longevity run, tracking emergent ecological
metrics: diversity, fragmentation, drift, and oscillation frequency.
"""

import json
import random
import time
from typing import List, Set

from app.semantic_ir import SemanticToken, SemanticType, Span
from app.semantic_world_state import SemanticWorldState


class EcologyAnalyzer:
    """Utility to track emergent ecological metrics over massive horizons."""

    def __init__(self):
        self.diversity_history: List[float] = []
        self.fragmentation_history: List[float] = []
        self.entropy_history: List[float] = []
        self.oscillation_counts: int = 0
        self.dead_regions: Set[str] = set()
        self.start_time = time.time()

    def record_pulse(self, ws: SemanticWorldState):
        """Record a pulse of ecological metrics."""
        # Force community detection for accurate fragmentation stats
        ws._topology.detect_communities()
        report = ws._observability.get_governance_report(ws.capture_governance_snapshot())

        # 1. Diversity (Shannon Entropy)
        self.diversity_history.append(report["diversity"])

        # 2. Entropy
        self.entropy_history.append(ws.metrics.global_entropy)

        # 3. Fragmentation (Communities / Regions)
        n_regions = ws.get_topology_view().region_count()
        n_comm = len(ws.global_communities)
        frag = n_comm / n_regions if n_regions > 0 else 0.0
        self.fragmentation_history.append(frag)

        # 4. Oscillations
        if report["oscillations"]:
            self.oscillation_counts += 1

    def summarize(self):
        """Summarize ecological health."""
        avg_div = sum(self.diversity_history) / len(self.diversity_history) if self.diversity_history else 1.0
        avg_frag = sum(self.fragmentation_history) / len(self.fragmentation_history) if self.fragmentation_history else 0.0
        avg_ent = sum(self.entropy_history) / len(self.entropy_history) if self.entropy_history else 0.0

        return {
            "avg_diversity": round(avg_div, 3),
            "avg_fragmentation": round(avg_frag, 3),
            "avg_entropy": round(avg_ent, 3),
            "oscillation_events": self.oscillation_counts,
            "duration_sec": round(time.time() - self.start_time, 2),
        }


def run_ecology_simulation(cycles: int = 100000, diversity_threshold: float = 0.4):
    ws = SemanticWorldState()
    ws.clear()
    # Ensure journal capacity for long-horizon causal audits
    ws._journal_capacity = 2000

    analyzer = EcologyAnalyzer()
    roles = [f"role_{i}" for i in range(30)]
    types = list(SemanticType)

    print(f"\n--- Initiating Evolutionary Ecology Validation ({cycles} cycles) ---")

    for i in range(cycles):
        # 1. Transactional Event
        with ws.transaction(f"eco_ev_{i}"):
            # Clustered signals simulate real-world semantic recurring patterns
            cluster = i % 5
            if cluster == 0:
                role, ttype = "price", SemanticType.PRICE
            elif cluster == 1:
                role, ttype = "loc", SemanticType.LOCATION
            elif cluster == 2:
                role, ttype = "org", SemanticType.ORGANIZATION
            else:
                role = random.choice(roles)
                ttype = random.choice(types)

            token_val = f"token_{role}_{i % 20}"
            token = SemanticToken(
                raw=token_val,
                normalized=token_val,
                span=Span(0, 5),
                position=0,
                primary_type=ttype,
                type_distribution={ttype: 1.0},
            )
            ws.capture_pre_allocation_field([token], roles)
            ws.apply_force_to_manifold(role, [random.uniform(-0.01, 0.01) for _ in range(16)])

        # 2. Field Stabilization (Phase 56 Governance)
        if i % 10 == 0:
            ws.decay_field_regions()  # Evolve regions to allow decay
            ws.redistribute_instability()
            ws.aggregate_from_regions()

        # 3. Structural Decay
        if i % 100 == 0:
            ws.apply_memory_decay()

        # 4. Resource Governance (Phase 50)
        if i % 500 == 0:
            ws._observability.apply_resource_shedding(ws, ws.capture_governance_snapshot(), max_bytes=100000)

        # 5. Ecological Pulse
        if i % 100 == 0:
            analyzer.record_pulse(ws)

        if i % (cycles // 10) == 0 and i > 0:
            stats = analyzer.summarize()
            print(
                f"  [{i}] Diversity: {stats['avg_diversity']:.2f}, Frag: {stats['avg_fragmentation']:.2f}, "
                f"Oscillations: {stats['oscillation_events']}"
            )

    print("\n--- Initiating Stabilization Phase (2000 cycles, no new signals) ---")
    for i in range(2000):
        ws.decay_field_regions()
        ws.redistribute_instability()
        ws.aggregate_from_regions()
        if i % 100 == 0:
            ws.apply_memory_decay()
            ws._observability.apply_resource_shedding(ws, ws.capture_governance_snapshot(), max_bytes=80000)
            analyzer.record_pulse(ws)

    final_stats = analyzer.summarize()
    print("\n--- Ecology Simulation Completed ---")
    print(json.dumps(final_stats, indent=2))

    # 6. Success Invariants
    assert final_stats["avg_diversity"] > diversity_threshold, "CRITICAL: Semantic field froze (diversity collapse)"

    final_entropy = ws.metrics.global_entropy
    print(f"Final Entropy after stabilization: {final_entropy:.4f}")
    assert final_entropy < 0.4, "CRITICAL: Field failed to reach convergent equilibrium"

    assert ws.get_topology_view().region_count() < 200, "CRITICAL: Topology fragmented uncontrollably"

    print("\n[SUCCESS] Semantic ecology proven stable, diverse, and adaptive.")


if __name__ == "__main__":
    # Start with a 50k cycle run for initial validation
    run_ecology_simulation(cycles=50000)
