"""
Active Stabilization & Substrate Sharding Verification — Phase 52/53
==================================================================
LAW: Adaptive systems must actively dampen pathological loops and scale
via topological partitioning.
"""

import pytest
from app.semantic_world_state import SemanticWorldState


@pytest.fixture
def ws():
    state = SemanticWorldState()
    state.clear()
    return state


def test_attractor_rebalancing(ws) -> None:
    """Verify that monopolistic basin dominance triggers energy dissipation."""
    # 1. Setup a dominant role
    ws.set_manifold_vector("role_a", [0.9] * 16)
    ws._energy.set_energy(10.0)
    ws._energy.set_entropy(0.1)

    # 2. Trigger rebalancing
    # (In redistribute_instability)
    ws.redistribute_instability()

    # 3. Verify energy drop and entropy spike
    assert ws.metrics.global_energy < 10.0
    assert ws.metrics.global_entropy > 0.1
    print(f"\nAttractor Rebalanced: Energy={ws.metrics.global_energy:.2f}, Entropy={ws.metrics.global_entropy:.2f}")


def test_topology_restructuring_lock_escape(ws) -> None:
    """Verify that metastable locks trigger structural rewiring."""
    # 1. Setup a lock state
    with ws.transaction("lock_setup"):
        r = ws._topology.add(["r1"], "lock", instability=0.01)
        ws._topology.set_region_temperature(r.region_id, 0.1)

    # Energy should be high enough to warrant escape if stable
    ws._energy.set_energy(9.0)
    # Trigger redistribution multiple times to simulate history
    for _ in range(50):
        ws.snapshot()

    # 2. Trigger redistribution (where lock escape is checked)
    ws.redistribute_instability()

    # 3. Verify restructuring (neighbor cleared, temperature spike)
    r_live = ws.get_topology_view().find_by_token_and_roles("lock", ("r1",))
    assert r_live.local_temperature > 0.5
    print("\nMetastable Lock Escaped via structural rewiring.")


def test_substrate_sharding_assignment(ws) -> None:
    """Verify that the partitioner correctly assigns regions to shards."""
    # 1. Setup disconnected communities
    with ws.transaction("shard_setup"):
        # Community A
        ws._topology.add(["price", "cost"], "t1")
        # Community B
        ws._topology.add(["loc", "org"], "t2")

    # 2. Partition
    shards = ws.shard_substrate()

    # 3. Verify
    assert len(shards) >= 2
    # Ensure Community A roles are in the same shard
    role_shards = ws._manifold._role_shards
    assert role_shards["price"] == role_shards["cost"]
    assert role_shards["loc"] == role_shards["org"]
    assert role_shards["price"] != role_shards["loc"]

    print(f"\nSubstrate Sharded into {len(shards)} independent logical partitions.")
