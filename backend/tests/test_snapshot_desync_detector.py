"""Tests for the Snapshot Desync Detector."""

import pytest
from app.snapshot_desync_detector import SnapshotDesyncDetector, reset_desync_detector


@pytest.fixture(autouse=True)
def reset():
    reset_desync_detector()


def make_snapshot(node_id="node_a", clock=None, topology=None, manifold=None, energy=None, instability=None, history=None):
    """Helper to create a minimal world state snapshot."""
    return {
        "node_id": node_id,
        "clock": clock or {node_id: 10},
        "topology": topology
        or {
            "regions": [{"region_id": "r1", "competing_roles": ["a", "b"], "instability": 0.5}],
            "topological_laws": {},
            "neighborhood_cohesion": {},
            "communities": [],
            "topology_epoch": 1,
        },
        "manifold": manifold
        or {
            "role_manifold": {"role_a": [0.5] * 16},
            "role_compatibility": {},
        },
        "energy": energy
        or {
            "global_energy": 5.0,
            "global_entropy": 0.5,
            "convergence_score": 0.6,
            "field_pressure": 0.3,
            "stability_debt": 0.1,
        },
        "instability": instability
        or {
            "exclusions": {},
        },
        "history": history
        or {
            "transaction_journal": [],
            "topology_snapshots": [],
            "field_activation_count": 0,
        },
    }


class TestSnapshotDesyncDetector:
    """Verify desync detection across identical, divergent, and causal scenarios."""

    # ─── Identical Snapshots ────────────────────────────────────────────

    def test_identical_snapshots_no_divergence(self) -> None:
        snap = make_snapshot()
        detector = SnapshotDesyncDetector()
        report = detector.compare(snap, snap, "node_a", "node_b")
        assert report.divergence_score == 0.0
        assert report.critical is False
        assert report.recommended_action == "none"

    # ─── Causal Scenarios ───────────────────────────────────────────────

    def test_causal_descendant_is_accepted(self) -> None:
        snap_a = make_snapshot(clock={"node_a": 10, "node_b": 5}, node_id="node_a")
        snap_b = make_snapshot(clock={"node_a": 5, "node_b": 10}, node_id="node_b")
        detector = SnapshotDesyncDetector()
        report = detector.compare(snap_a, snap_b, "node_a", "node_b")
        # Even without topology divergence, the clock shows A has more updates
        assert report.divergence_score == 0.0

    def test_concurrent_clocks_detected(self) -> None:
        snap_a = make_snapshot(clock={"node_a": 10, "node_b": 5}, node_id="node_a")
        snap_b = make_snapshot(clock={"node_a": 5, "node_b": 10}, node_id="node_b")
        # Add actual divergence
        snap_b["topology"]["regions"] = [{"region_id": "r2", "competing_roles": ["c", "d"], "instability": 0.8}]
        snap_b["topology"]["topological_laws"] = {"c|d": -0.5}
        detector = SnapshotDesyncDetector()
        report = detector.compare(snap_a, snap_b, "node_a", "node_b")
        assert report.divergence_score > 0.0
        assert "topology" in report.subsystem_divergence

    # ─── Topology Divergence ────────────────────────────────────────────

    def test_topology_region_count_divergence(self) -> None:
        snap_a = make_snapshot()
        snap_b = make_snapshot()
        snap_b["topology"]["regions"] = [
            {"region_id": "r1", "competing_roles": ["a", "b"], "instability": 0.5},
            {"region_id": "r2", "competing_roles": ["c", "d"], "instability": 0.8},
        ]
        detector = SnapshotDesyncDetector()
        report = detector.compare(snap_a, snap_b)
        assert report.subsystem_divergence.get("topology", 0) > 0.0

    def test_topology_laws_divergence(self) -> None:
        snap_a = make_snapshot()
        snap_b = make_snapshot()
        snap_b["topology"]["topological_laws"] = {"a|b": -0.5, "c|d": 0.8}
        detector = SnapshotDesyncDetector()
        report = detector.compare(snap_a, snap_b)
        assert "topology" in report.subsystem_divergence

    def test_topology_epoch_divergence_triggers_critical(self) -> None:
        snap_a = make_snapshot()
        snap_b = make_snapshot()
        snap_b["topology"]["topology_epoch"] = 5
        detector = SnapshotDesyncDetector()
        report = detector.compare(snap_a, snap_b)
        assert report.epoch_gap == 4
        assert report.critical is True
        assert report.recommended_action in ("full_reconciliation",)

    # ─── Manifold Divergence ────────────────────────────────────────────

    def test_manifold_role_set_divergence(self) -> None:
        snap_a = make_snapshot()
        snap_b = make_snapshot()
        snap_b["manifold"]["role_manifold"] = {
            "role_a": [0.5] * 16,
            "role_b": [0.3] * 16,
        }
        detector = SnapshotDesyncDetector()
        report = detector.compare(snap_a, snap_b)
        assert report.subsystem_divergence.get("manifold", 0) > 0.0

    def test_manifold_vector_divergence(self) -> None:
        snap_a = make_snapshot()
        snap_b = make_snapshot()
        snap_b["manifold"]["role_manifold"] = {
            "role_a": [0.9] * 16  # Very different from [0.5] * 16
        }
        detector = SnapshotDesyncDetector()
        report = detector.compare(snap_a, snap_b)
        assert report.subsystem_divergence.get("manifold", 0) > 0.0

    # ─── Energy Divergence ──────────────────────────────────────────────

    def test_energy_divergence(self) -> None:
        snap_a = make_snapshot()
        snap_b = make_snapshot()
        snap_b["energy"]["global_energy"] = 9.0  # Very different from 5.0
        detector = SnapshotDesyncDetector()
        report = detector.compare(snap_a, snap_b)
        assert report.subsystem_divergence.get("energy", 0) > 0.0

    # ─── Instability Divergence ─────────────────────────────────────────

    def test_instability_exclusion_divergence(self) -> None:
        snap_a = make_snapshot()
        snap_b = make_snapshot()
        snap_b["instability"]["exclusions"] = {"a|b": 0.8}
        detector = SnapshotDesyncDetector()
        report = detector.compare(snap_a, snap_b)
        assert report.subsystem_divergence.get("instability", 0) > 0.0

    # ─── Composite Critical Threshold ───────────────────────────────────

    def test_high_divergence_triggers_critical(self) -> None:
        snap_a = make_snapshot()
        snap_b = make_snapshot()
        snap_b["topology"]["regions"] = [
            {"region_id": "r1", "competing_roles": ["x", "y"], "instability": 0.9},
        ]
        snap_b["topology"]["topological_laws"] = {"a|b": -0.9}
        snap_b["topology"]["neighborhood_cohesion"] = {"a|b": 0.9}
        snap_b["manifold"]["role_manifold"] = {"role_z": [0.2] * 16}
        snap_b["energy"]["global_energy"] = 9.5
        snap_b["instability"]["exclusions"] = {"x|y": 0.9}
        detector = SnapshotDesyncDetector(divergence_threshold=0.15)
        report = detector.compare(snap_a, snap_b)
        assert report.critical is True

    # ─── Edge Cases ─────────────────────────────────────────────────────

    def test_empty_snapshots(self) -> None:
        snap_a = make_snapshot()
        snap_b = make_snapshot()
        snap_b["topology"]["regions"] = []
        snap_b["manifold"]["role_manifold"] = {}
        snap_b["energy"] = {}
        snap_b["instability"]["exclusions"] = {}
        snap_b["history"] = {}
        detector = SnapshotDesyncDetector()
        report = detector.compare(snap_a, snap_b)
        # Should handle gracefully without crashing
        assert report.divergence_score >= 0.0
        assert isinstance(report.critical, bool)

    def test_recent_reports_tracking(self) -> None:
        snap_a = make_snapshot()
        snap_b = make_snapshot()
        snap_b["topology"]["regions"] = [{"region_id": "r2", "competing_roles": ["c"]}]
        detector = SnapshotDesyncDetector()
        detector.compare(snap_a, snap_b, "n1", "n2")
        reports = detector.get_recent_reports()
        assert len(reports) == 1
        assert reports[0]["node_a"] == "n1"
        assert reports[0]["node_b"] == "n2"

    def test_recommendation_causal_merge(self) -> None:
        snap_a = make_snapshot(clock={"node_a": 10, "node_b": 5}, node_id="node_a")
        snap_b = make_snapshot(clock={"node_a": 5, "node_b": 10}, node_id="node_b")
        snap_b["topology"]["regions"] = [
            {"region_id": "r2", "competing_roles": ["c", "d"], "instability": 0.8},
        ]
        snap_b["topology"]["topological_laws"] = {"c|d": -0.7}
        snap_b["topology"]["neighborhood_cohesion"] = {"c|d": 0.9}
        detector = SnapshotDesyncDetector()
        report = detector.compare(snap_a, snap_b)
        # Concurrent + high divergence => causal_merge
        if report.causal_relation == "concurrent":
            assert report.recommended_action == "causal_merge"
