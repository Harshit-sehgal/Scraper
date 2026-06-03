# mypy: ignore-errors
# type: ignore
import logging

logger = logging.getLogger(__name__)


class MetricsMixin:
    def get_derived_exclusion(self, role_a: str, role_b: str) -> float:
        """Compute exclusion strength from topology metrics — the dict is secondary.

        Exclusion emerges from topology itself:
        1. Motif instability: if motifs containing these roles are unstable, exclude more
        2. Compatibility divergence: roles with divergent type preferences exclude more
        3. Neighborhood instability: if roles are in different neighborhoods, exclude more
        4. Learned exclusion history (symbolic bridge, secondary)

        The topology baseline produces non-zero exclusion even when the dict is empty.
        The dict only amplifies patterns already visible in the topology.
        """
        baseline = 0.0

        # 1. Motif pressure (topology-native): unstable motifs → exclusion
        # Stable motifs REPEL exclusion (they indicate compatible
        # neighborhoods)
        ra_types = {t for r, t in self.role_compatibility if r == role_a}
        rb_types = {t for r, t in self.role_compatibility if r == role_b}
        for motif in self.motif_counts:
            if any(t in motif for t in ra_types) and any(t in motif for t in rb_types):
                stability = self.get_motif_stability(motif)
                if stability < 0.5:
                    baseline += 0.18 * (0.5 - stability)
                else:
                    baseline -= 0.03 * (stability - 0.5)

        # 2. Compatibility pressure (topology-native): divergent type
        # preferences → exclusion
        observed_types = set()
        for r, t in self.role_compatibility:
            observed_types.add(t)
        for ttype in observed_types:
            ca = self.role_compatibility.get((role_a, ttype), 0.5)
            cb = self.role_compatibility.get((role_b, ttype), 0.5)
            if abs(ca - cb) > 0.2:
                baseline += 0.06

        # 3. Topology persistence: stable field regions reduce exclusion
        view = self._topology.get_view()
        for region in view.all_regions():
            if role_a in region.competing_roles and role_b in region.competing_roles:
                if region.instability < 0.3:
                    baseline -= 0.05

        # 4. Learned exclusion (symbolic bridge, secondary cache — 0.1x weight)
        key = tuple(sorted([role_a, role_b]))
        learned = self.learned_exclusions.get(key, 0.0) * 0.1
        total = baseline + learned

        return max(0.0, min(1.0, total))

    @property
    def topology_density(self) -> float:
        """Graph interconnectedness — edges per possible role pair.

        Dense topology = many exclusivity relationships = conflicts
        propagate easily. Used to tighten exclusion thresholds so the
        graph geometry itself governs cognition.
        """
        from app.field_laws import ROLE_EXCLUSIVITY

        possible = len(ROLE_EXCLUSIVITY) + max(len(self.learned_exclusions), 1)
        actual = len(self.learned_exclusions)
        return min(actual / possible, 1.0) if possible > 0 else 0.0

    def get_system_pressure(self) -> float:
        """Composite pressure metric for adaptive throttling (Phase 33)."""
        health = self.get_cognitive_health()
        # High fragmentation, energy, or topology-native entropy increases pressure.
        # High certainty decreases pressure
        entropy_pressure = self.metrics.global_entropy * 0.15
        pressure = (health["system_energy"] / 10.0 + health["fragmentation"] + entropy_pressure) - health["certainty"] * 0.5
        return max(0.1, min(2.0, pressure))

    def evaluate_topological_consistency(self) -> dict:
        """Evaluate the manifold's logical consistency (Meta-Reasoning - Phase 38)."""
        envelopes = self._abstraction.envelopes
        contradictions = []

        for eid, details in envelopes.items():
            constituents = list(details["constituents"])
            if len(constituents) < 2:
                continue

            # Check for mutual repulsion within the envelope
            for i in range(len(constituents)):
                for j in range(i + 1, len(constituents)):
                    r1, r2 = constituents[i], constituents[j]
                    exclusion = self._instability.get_exclusion(r1, r2)

                    # If constituents strongly repel each other, the envelope
                    # is contradictory
                    if exclusion > 0.7:
                        contradictions.append(
                            {"envelope": eid, "pair": (r1, r2), "exclusion": exclusion, "type": "internal_repulsion"}
                        )

        consistency_score = 1.0 - (len(contradictions) / max(len(envelopes), 1))

        if contradictions:
            self.record_delta(
                "global",
                "meta_reasoning",
                {"consistency_score": consistency_score, "contradiction_count": len(contradictions)},
            )

        return {"score": consistency_score, "contradictions": contradictions}

    # ─── Garbage Collection Gateway APIs ────────────────────────────────
    # These encapsulate all GC operations so topology_gc.py never needs
    # to access sub-states directly — strengthening the ownership boundary.

    def gc_collect_stale_regions(self, min_instability: float = 0.02, min_energy: float = 0.5) -> int:
        """Remove field regions below thresholds. Returns count removed."""
        before = self._topology.region_count()
        self._topology.filter_regions(lambda r: r.instability > min_instability or r.local_energy > min_energy)
        return before - self._topology.region_count()

    def gc_collect_stale_motifs(self, threshold: float = 0.05) -> int:
        """Remove motifs that have decayed below usefulness threshold. Returns count removed."""
        before = self._motif.count()
        self._motif.prune_weak(threshold=threshold)
        return before - self._motif.count()

    def gc_collect_stale_exclusions(self, threshold: float = 0.01) -> int:
        """Remove very weak exclusions. Returns count removed."""
        return self._instability.prune_exclusions_weak(threshold=threshold)

    def gc_trim_snapshots(self, max_size: int = 500, keep: int = 250) -> int:
        """Trim excess topology snapshots. Returns count removed."""
        before = len(self._history.get_snapshots())
        self._history.trim_snapshots(max_size=max_size, keep=keep)
        return before - len(self._history.get_snapshots())

    def gc_collect(self) -> dict:
        """Run full garbage collection cycle. Returns dict with counts per category."""
        return {
            "regions": self.gc_collect_stale_regions(),
            "motifs": self.gc_collect_stale_motifs(),
            "exclusions": self.gc_collect_stale_exclusions(),
            "snapshots": self.gc_trim_snapshots(),
        }
