"""Snapshot Desync Detector — identifies divergent state across instances.

Compares serialized world state snapshots from different nodes to detect
causal divergence. Uses vector clocks for causality ordering and structural
hash comparisons per subsystem to pinpoint exactly where state diverged.

Phase 47: Distributed Resilience — detecting divergent state in multi-node clusters.
"""

import logging

logger = logging.getLogger(__name__)


class DesyncReport:
    """Frozen report of a desync detection result."""

    __slots__ = (
        "causal_relation",
        "critical",
        "divergence_score",
        "epoch_gap",
        "node_a",
        "node_b",
        "recommended_action",
        "subsystem_divergence",
    )

    def __init__(
        self,
        node_a: str,
        node_b: str,
        causal_relation: str,
        divergence_score: float,
        subsystem_divergence: dict[str, float],
        critical: bool,
        epoch_gap: int = 0,
        recommended_action: str = "none",
    ) -> None:
        self.node_a = node_a
        self.node_b = node_b
        self.causal_relation = causal_relation
        self.divergence_score = divergence_score
        self.subsystem_divergence = subsystem_divergence
        self.critical = critical
        self.epoch_gap = epoch_gap
        self.recommended_action = recommended_action

    def to_dict(self) -> dict:
        return {
            "node_a": self.node_a,
            "node_b": self.node_b,
            "causal_relation": self.causal_relation,
            "divergence_score": round(self.divergence_score, 4),
            "subsystem_divergence": {k: round(v, 4) for k, v in self.subsystem_divergence.items()},
            "critical": self.critical,
            "epoch_gap": self.epoch_gap,
            "recommended_action": self.recommended_action,
        }


class SnapshotDesyncDetector:
    """Detects divergent state between two serialized world state snapshots.

    Detection strategy:
    1. Vector clock comparison to determine causal ordering
    2. Per-subsystem structural hash comparison to pinpoint divergence
    3. Per-subsystem numerical divergence measurement (mean absolute difference)
    4. Composite divergence score with critical threshold alerting
    5. Recommended action based on divergence severity and causality
    """

    def __init__(self, divergence_threshold: float = 0.15) -> None:
        self._threshold = divergence_threshold
        self._history: list[DesyncReport] = []

    def compare(
        self,
        snapshot_a: dict,
        snapshot_b: dict,
        node_a: str = "node_a",
        node_b: str = "node_b",
    ) -> DesyncReport:
        """Compare two serialized world state snapshots and return a desync report.

        Args:
            snapshot_a: Serialized world state from node A (from SemanticWorldState.to_dict())
            snapshot_b: Serialized world state from node B
            node_a: Identifier for node A
            node_b: Identifier for node B

        Returns:
            DesyncReport with divergence metrics and recommended action.

        """
        # 1. Causal relation via vector clocks
        clock_a = snapshot_a.get("clock", {})
        clock_b = snapshot_b.get("clock", {})
        causal_relation = self._compare_clocks(clock_a, clock_b, node_a, node_b)

        # 2. Epoch gap from topology
        topo_a = snapshot_a.get("topology", {})
        topo_b = snapshot_b.get("topology", {})
        epoch_a = topo_a.get("topology_epoch", 0)
        epoch_b = topo_b.get("topology_epoch", 0)
        epoch_gap = abs(epoch_a - epoch_b)

        # 3. Per-subsystem divergence
        subsystems = [
            ("topology", self._compare_topology),
            ("manifold", self._compare_manifold),
            ("energy", self._compare_energy),
            ("instability", self._compare_instability),
            ("history", self._compare_history),
        ]

        subsystem_divergence: dict[str, float] = {}
        for name, fn in subsystems:
            try:
                score = fn(snapshot_a, snapshot_b)
            except Exception as e:
                logger.warning("Desync compare failed for subsystem %s: %s", name, e)
                score = 1.0  # Cannot compare = fully divergent
            if score > 0.0:
                subsystem_divergence[name] = score

        # 4. Composite divergence score (weighted mean)
        weights = {
            "topology": 0.35,
            "manifold": 0.30,
            "energy": 0.15,
            "instability": 0.10,
            "history": 0.10,
        }
        composite = 0.0
        total_weight = 0.0
        for name, score in subsystem_divergence.items():
            w = weights.get(name, 0.1)
            composite += score * w
            total_weight += w
        divergence_score = composite / total_weight if total_weight > 0 else 0.0

        # 5. Critical threshold detection
        critical = divergence_score > self._threshold or epoch_gap > 2

        # 6. Recommended action
        recommended_action = self._recommend_action(causal_relation, divergence_score, epoch_gap, critical)

        report = DesyncReport(
            node_a=node_a,
            node_b=node_b,
            causal_relation=causal_relation,
            divergence_score=divergence_score,
            subsystem_divergence=subsystem_divergence,
            critical=critical,
            epoch_gap=epoch_gap,
            recommended_action=recommended_action,
        )

        self._history.append(report)
        if len(self._history) > 100:
            self._history = self._history[-50:]

        if critical:
            logger.warning(
                "DESYNC DETECTED: %s ↔ %s divergence=%.4f epoch_gap=%d action=%s",
                node_a,
                node_b,
                divergence_score,
                epoch_gap,
                recommended_action,
            )

        return report

    def get_recent_reports(self, n: int = 10) -> list[dict]:
        """Return the most recent desync reports."""
        return [r.to_dict() for r in self._history[-n:]]

    # ─── Clock Comparison ────────────────────────────────────────────

    def _compare_clocks(self, clock_a: dict, clock_b: dict, node_a: str, node_b: str) -> str:
        """Determine causal relation between two vector clocks."""
        self_newer = False
        other_newer = False

        if not clock_a:
            return "no_clock_a"
        if not clock_b:
            return "no_clock_b"

        all_nodes = set(clock_a.keys()) | set(clock_b.keys())
        for node in all_nodes:
            va = clock_a.get(node, 0)
            vb = clock_b.get(node, 0)
            if va > vb:
                self_newer = True
            elif vb > va:
                other_newer = True

        if self_newer and other_newer:
            return "concurrent"
        if self_newer:
            return "descendant"  # A is newer than B
        if other_newer:
            return "ancestor"  # A is older than B
        return "equal"

    # ─── Subsystem Comparators ───────────────────────────────────────

    def _compare_topology(self, a: dict, b: dict) -> float:
        """Compare topology regions and laws. Returns divergence 0 - 1."""
        topo_a = a.get("topology", {})
        topo_b = b.get("topology", {})

        # Compare regions (count + structural hash)
        regions_a = topo_a.get("regions", [])
        regions_b = topo_b.get("regions", [])
        region_count_div = self._relative_diff(len(regions_a), len(regions_b))

        # Compare topological laws
        laws_a = topo_a.get("topological_laws", {})
        laws_b = topo_b.get("topological_laws", {})
        laws_div = self._dict_divergence(laws_a, laws_b)

        # Compare cohesion
        cohesion_a = topo_a.get("neighborhood_cohesion", {})
        cohesion_b = topo_b.get("neighborhood_cohesion", {})
        cohesion_div = self._dict_divergence(cohesion_a, cohesion_b)

        # Compare communities (multi-set structural hash)
        comm_a = {tuple(c) for c in topo_a.get("communities", [])}
        comm_b = {tuple(c) for c in topo_b.get("communities", [])}
        comm_div = 0.0
        if comm_a or comm_b:
            intersection = comm_a & comm_b
            union = comm_a | comm_b
            comm_div = 1.0 - (len(intersection) / len(union)) if union else 0.0

        # Compare epoch
        epoch_a = topo_a.get("topology_epoch", 0)
        epoch_b = topo_b.get("topology_epoch", 0)
        epoch_div = 1.0 if epoch_a != epoch_b else 0.0

        return region_count_div * 0.25 + laws_div * 0.25 + cohesion_div * 0.20 + comm_div * 0.20 + epoch_div * 0.10

    def _compare_manifold(self, a: dict, b: dict) -> float:
        """Compare manifold role embeddings. Returns divergence 0 - 1."""
        man_a = a.get("manifold", {})
        man_b = b.get("manifold", {})

        roles_a = set(man_a.get("role_manifold", {}).keys())
        roles_b = set(man_b.get("role_manifold", {}).keys())

        # Role set divergence
        if not roles_a and not roles_b:
            return 0.0
        role_jaccard = 1.0
        if roles_a or roles_b:
            intersection = roles_a & roles_b
            union = roles_a | roles_b
            role_jaccard = len(intersection) / len(union) if union else 1.0

        # Vector divergence for shared roles
        vec_a = man_a.get("role_manifold", {})
        vec_b = man_b.get("role_manifold", {})
        total_dist = 0.0
        shared_count = 0
        for role in roles_a & roles_b:
            va = vec_a.get(role, [0.0] * 16)
            vb = vec_b.get(role, [0.0] * 16)
            if va and vb:
                dist = sum(abs(x - y) for x, y in zip(va, vb[: len(va)], strict=False)) / len(va)
                total_dist += dist
                shared_count += 1

        avg_vec_dist = total_dist / shared_count if shared_count > 0 else 0.0

        # Compatibility divergence
        compat_a = {tuple(k.split("|")) if isinstance(k, str) else k for k in man_a.get("role_compatibility", {})}
        compat_b = {tuple(k.split("|")) if isinstance(k, str) else k for k in man_b.get("role_compatibility", {})}
        compat_div = 0.0
        if compat_a or compat_b:
            compat_intersection = compat_a & compat_b
            compat_union = compat_a | compat_b
            compat_div = 1.0 - (len(compat_intersection) / len(compat_union)) if compat_union else 0.0

        return (1.0 - role_jaccard) * 0.35 + avg_vec_dist * 0.35 + compat_div * 0.30

    def _compare_energy(self, a: dict, b: dict) -> float:
        """Compare energy state metrics. Returns divergence 0 - 1."""
        energy_a = a.get("energy", {})
        energy_b = b.get("energy", {})

        if not energy_a and not energy_b:
            return 0.0

        # Compare key scalar metrics
        keys = ["global_energy", "global_entropy", "convergence_score", "field_pressure", "stability_debt"]
        total_div = 0.0
        count = 0
        for key in keys:
            va = energy_a.get(key, 0.0)
            vb = energy_b.get(key, 0.0)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                total_div += self._relative_diff(va, vb)
                count += 1

        return total_div / count if count > 0 else 0.0

    def _compare_instability(self, a: dict, b: dict) -> float:
        """Compare learned exclusions. Returns divergence 0 - 1."""
        inst_a = a.get("instability", {})
        inst_b = b.get("instability", {})

        excl_a = inst_a.get("exclusions", {})
        excl_b = inst_b.get("exclusions", {})

        return self._dict_divergence(excl_a, excl_b)

    def _compare_history(self, a: dict, b: dict) -> float:
        """Compare history states. Returns divergence 0 - 1."""
        hist_a = a.get("history", {})
        hist_b = b.get("history", {})

        # Compare transaction count
        ta_count = len(hist_a.get("transaction_journal", []))
        tb_count = len(hist_b.get("transaction_journal", []))
        count_div = self._relative_diff(ta_count, tb_count)

        # Compare topology snapshot count
        sa_count = len(hist_a.get("topology_snapshots", []))
        sb_count = len(hist_b.get("topology_snapshots", []))
        snap_div = self._relative_diff(sa_count, sb_count)

        # Compare field activation count
        fa = hist_a.get("field_activation_count", 0)
        fb = hist_b.get("field_activation_count", 0)
        act_div = self._relative_diff(fa, fb)

        return count_div * 0.5 + snap_div * 0.25 + act_div * 0.25

    # ─── Utilities ──────────────────────────────────────────────────

    def _relative_diff(self, a: float, b: float) -> float:
        """Compute relative difference between two values: 0 (same) to 1 (max divergent)."""
        if a == b:
            return 0.0
        if a == 0 or b == 0:
            return 1.0 if abs(a - b) > 0.001 else 0.0
        diff = abs(a - b) / max(abs(a), abs(b))
        return min(1.0, diff)

    def _dict_divergence(self, d1: dict, d2: dict, value_threshold: float = 0.01) -> float:
        """Compute divergence between two dicts with numeric values."""
        keys_all = set(d1.keys()) | set(d2.keys())
        if not keys_all:
            return 0.0

        diff_sum = 0.0
        diff_count = 0
        for key in keys_all:
            v1 = d1.get(key, 0.0)
            v2 = d2.get(key, 0.0)
            if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                if abs(v1 - v2) > value_threshold:
                    diff_sum += 1.0
                diff_count += 1
            else:
                if v1 != v2:
                    diff_sum += 1.0
                diff_count += 1

        return diff_sum / diff_count if diff_count > 0 else 0.0

    def _recommend_action(self, causal_relation: str, divergence: float, epoch_gap: int, critical: bool) -> str:
        """Recommend an action based on divergence analysis."""
        if not critical:
            return "none"

        if epoch_gap > 2:
            return "full_reconciliation"  # Epoch divergence requires topology reconciliation

        if causal_relation == "concurrent" and divergence > 0.3:
            return "causal_merge"  # Concurrent branches need merge

        if causal_relation == "ancestor" and divergence > 0.2:
            return "fast_forward"  # One node is behind, catch up

        if causal_relation == "descendant" and divergence > 0.2:
            return "accept_newer"  # Other node is ahead, adopt

        return "investigate"


# Global singleton
_detector: SnapshotDesyncDetector | None = None


def get_desync_detector() -> SnapshotDesyncDetector:
    """Get or create the global SnapshotDesyncDetector instance."""
    global _detector
    if _detector is None:
        _detector = SnapshotDesyncDetector()
    return _detector


def reset_desync_detector() -> None:
    """Reset the global detector (for testing)."""
    global _detector
    _detector = None
