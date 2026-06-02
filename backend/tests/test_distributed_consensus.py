from app.semantic_os import SemanticOS
from app.semantic_world_state import SemanticWorldState


def test_causal_sync():
    # Node A starts
    ws_a = SemanticWorldState(node_id="node_a")
    ws_a.clear()

    with ws_a.transaction("t1"):
        ws_a._energy.set_energy(2.0)

    state_a_v1 = ws_a.to_dict()

    # Node B starts with A's state
    ws_b = SemanticWorldState(node_id="node_b")
    ws_b.from_dict(state_a_v1)
    ws_b.node_id = "node_b"  # from_dict overwrites node_id

    # Node B evolves further
    with ws_b.transaction("t2"):
        ws_b._energy.set_energy(1.0)

    state_b_v2 = ws_b.to_dict()

    # Node A syncs with B
    # B is descendant of A (A is ancestor)
    ws_a.merge_state(state_b_v2)

    # Verify A caught up to B (Alpha was 0.7)
    # local(2.0) * 0.3 + remote(1.0) * 0.7 = 0.6 + 0.7 = 1.3
    # Wait, EnergyState.merge uses alpha for avg.
    assert abs(ws_a.metrics.global_energy - 1.3) < 0.01


def test_concurrent_conflict_resolution():
    ws_base = SemanticWorldState(node_id="base")
    ws_base.clear()
    base_state = ws_base.to_dict()

    # Node A evolves from base
    ws_a = SemanticWorldState(node_id="node_a")
    ws_a.from_dict(base_state)
    ws_a.node_id = "node_a"
    with ws_a.transaction("t_a"):
        ws_a._energy.set_energy(1.0)

    # Node B evolves from base (concurrently)
    ws_b = SemanticWorldState(node_id="node_b")
    ws_b.from_dict(base_state)
    ws_b.node_id = "node_b"
    with ws_b.transaction("t_b"):
        ws_b._energy.set_energy(9.0)

    # Node A syncs with B (Concurrent relation)
    # alpha should be 0.3 (conservative)
    # local(1.0) * 0.7 + remote(9.0) * 0.3 = 0.7 + 2.7 = 3.4
    ws_a.merge_state(ws_b.to_dict())

    assert abs(ws_a.metrics.global_energy - 3.4) < 0.01

    # Vector clock should be merged AND incremented for node_a (the merger)
    clock = ws_a._vector_clock.get_clock()
    assert clock["node_a"] == 2
    assert clock["node_b"] == 1


def test_gossip_substrate_propagation():
    # 1. Setup three nodes
    os_a = SemanticOS(SemanticWorldState(node_id="node_a"))
    os_b = SemanticOS(SemanticWorldState(node_id="node_b"))
    os_c = SemanticOS(SemanticWorldState(node_id="node_c"))

    os_a.register_with_network()
    os_b.register_with_network()
    os_c.register_with_network()

    # 2. Node A learns something
    with os_a.ws.transaction("a_learns"):
        os_a.ws._energy.set_energy(8.0)

    # 3. Perform multiple gossip cycles
    # A should propagate to B or C, and then to the third one
    for _ in range(10):
        os_a.perform_gossip()
        os_b.perform_gossip()
        os_c.perform_gossip()

    # 4. Verify all nodes converged toward the new energy
    # (Since alpha is 0.7 for descendants, they should be very close to 8.0)
    assert os_b.ws.metrics.global_energy > 5.0
    assert os_c.ws.metrics.global_energy > 5.0
