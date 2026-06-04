"""Phase 67: Distributed Partition Healing & History Re-alignment Tests.
=====================================================================
LAW: Substrate must reconcile divergent causal journals after partitions.
"""

import pytest
from app.semantic_world_state import SemanticWorldState


@pytest.fixture
def partitioned_nodes():
    ws_a = SemanticWorldState(node_id="node_a")
    ws_a.clear()
    ws_b = SemanticWorldState(node_id="node_b")
    ws_b.clear()
    return ws_a, ws_b


def test_causal_stitching(partitioned_nodes) -> None:
    """Verify that divergent transaction journals are stitched together."""
    ws_a, ws_b = partitioned_nodes

    # 1. Shared history
    with ws_a.transaction("shared"):
        ws_a.set_manifold_vector("common", [0.5] * 16)

    ws_b.merge_state(ws_a.to_dict())

    # 2. Partition: A does work, B does different work
    with ws_a.transaction("a_only"):
        ws_a.set_manifold_vector("a_role", [1.0] * 16)

    with ws_b.transaction("b_only"):
        ws_b.set_manifold_vector("b_role", [0.0] * 16)

    # 3. Merge: B merges A
    ws_b.merge_state(ws_a.to_dict())

    # Verify B's journal has ALL transactions
    journal = ws_b._history.transaction_journal
    labels = [tx.get("label") for tx in journal]

    assert "shared" in labels
    assert "a_only" in labels
    assert "b_only" in labels

    # Check temporal order (by timestamp)
    timestamps = [tx.get("timestamp", 0) for tx in journal]
    assert timestamps == sorted(timestamps)


def test_divergence_analyzer(partitioned_nodes) -> None:
    """Verify that causal divergence is correctly quantified."""
    ws_a, _ws_b = partitioned_nodes

    # Simulate skew
    clock_a = {"node_a": 100, "node_b": 5}
    clock_b = {"node_a": 10, "node_b": 50}

    analysis = ws_a._observability.analyze_causal_divergence(clock_a, clock_b)

    assert analysis["total_divergence"] == (100 - 10) + (50 - 5)
    assert analysis["max_causal_skew"] == 90
    assert analysis["drift_risk"] == "high"
    assert analysis["action_recommendation"] == "merge"  # Still merge since 90 < 100
