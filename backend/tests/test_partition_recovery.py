"""
Phase 60: Distributed Partition Recovery & Zombie Data Prevention Tests
======================================================================
LAW: Distributed systems must handle partition recovery deterministically.
Tombstones and Epochs ensure that deleted semantic regions stay deleted.
"""

import pytest
from app.semantic_world_state import SemanticWorldState


@pytest.fixture
def nodes():
    # Node A: The primary evolver
    ws_a = SemanticWorldState(node_id="node_a")
    ws_a.clear()

    # Node B: The replica/partitioned node
    ws_b = SemanticWorldState(node_id="node_b")
    ws_b.clear()

    return ws_a, ws_b


def test_zombie_data_prevention(nodes):
    """Verify that region deletions on one node are respected after merge."""
    ws_a, ws_b = nodes

    # 1. Synchronized state: both have Region 1
    with ws_a.transaction("sync_1"):
        r1 = ws_a._topology.add(["role_1"], "token_1")
        rid1 = r1.region_id

    ws_b.merge_state(ws_a.to_dict())
    assert ws_b.get_topology_view().region_count() == 1

    # 2. Partition: Node A deletes Region 1, Node B is offline
    with ws_a.transaction("delete_1"):
        reg = next(r for r in ws_a._topology._regions if r.region_id == rid1)
        ws_a._topology.remove(reg)

    assert ws_a.get_topology_view().region_count() == 0
    assert rid1 in ws_a._topology._tombstones

    # 3. Reconnection: Node B merges Node A
    # Legacy bug: Node B would re-introduce Region 1 to the cluster (Zombie Data)
    # Phase 60: Node B should prune Region 1 because Node A has a tombstone and newer epoch
    ws_b.merge_state(ws_a.to_dict())

    assert ws_b.get_topology_view().region_count() == 0
    assert rid1 in ws_b._topology._tombstones
    print("\nZombie Data Prevention: Region successfully pruned after partition recovery.")


def test_epoch_divergence_resolution(nodes):
    """Verify that epoch-based reconciliation handles structural divergence."""
    ws_a, ws_b = nodes

    # 1. Setup shared state
    with ws_a.transaction("setup"):
        ws_a._topology.add(["r1"], "t1")
    ws_b.merge_state(ws_a.to_dict())

    e0 = ws_a._topology._topology_epoch

    # 2. Node A performs 5 structural changes
    for i in range(5):
        with ws_a.transaction(f"change_{i}"):
            ws_a._topology.add([f"role_{i}"], f"token_{i}")

    assert ws_a._topology._topology_epoch == e0 + 5

    # 3. Node B merges A
    ws_b.merge_state(ws_a.to_dict())
    assert ws_b._topology._topology_epoch >= ws_a._topology._topology_epoch
    assert ws_b.get_topology_view().region_count() == 6
    print(f"\nEpoch Divergence Resolved: Final Epoch {ws_b._topology._topology_epoch}")
