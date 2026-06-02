"""
Test Decentralized Field Waves — Phase 71 Verification.
"""

import asyncio

import pytest
from app.event_dispatcher import get_dispatcher
from app.semantic_events import SemanticEventType
from app.semantic_world_state import get_world_state, reset_world_state


@pytest.fixture(autouse=True)
def clean_state():
    reset_world_state()
    # Ensure dispatcher starts clean but allow new world state to subscribe
    dispatcher = get_dispatcher()
    dispatcher.subscribers[SemanticEventType.FIELD_WAVE] = []

    # Trigger creation of new world state which will subscribe itself
    get_world_state()

    # Re-setup scheduler subscription
    from app.graph_update_scheduler import get_scheduler

    get_scheduler()._setup_subscriptions()


@pytest.mark.asyncio
async def test_field_wave_propagation():
    ws = get_world_state()
    ws.clear()

    # 1. Create two regions with shared roles to create a topological route
    # Region A: [role1, role2]
    # Region B: [role2, role3]
    # Shared role2 creates the route.

    with ws.transaction("setup"):
        ra = ws._topology.add(["role1", "role2"], token="tokenA", instability=0.1)
        rb = ws._topology.add(["role2", "role3"], token="tokenB", instability=0.1)

        # Establish strong affinity between role1 and role2 to ensure route strength
        ws._topology.set_neighborhood_cohesion(("role1", "role2"), 0.9)
        ws._topology.set_neighborhood_cohesion(("role2", "role3"), 0.9)

    rid_a = ra.region_id
    rid_b = rb.region_id

    # 2. Emit a wave from Region A
    # A significant instability spike in A should ripple to B
    region_b = ws._topology.get_region(rid_b)
    assert region_b is not None
    initial_instability_b = region_b.instability

    with ws.transaction("trigger_wave"):
        # We manually trigger a wave to ensure it's not decayed by evolve during setup
        ws._topology.emit_field_wave(rid_a, 0.7)

    # Give some time for background tasks/dispatcher if any (though currently sync)
    await asyncio.sleep(0.1)

    # 3. Verify Region B absorbed the wave
    region_b_final = ws._topology.get_region(rid_b)
    assert region_b_final is not None
    final_instability_b = region_b_final.instability
    assert final_instability_b > initial_instability_b

    # 4. Check causal telemetry
    causal = ws.get_causal_telemetry()
    wave_events = [e for e in causal if e.get("type") == "wave_absorption"]
    assert len(wave_events) > 0
    assert wave_events[0]["details"]["region_id"] == rid_b
    assert wave_events[0]["details"]["source_id"] == rid_a


@pytest.mark.asyncio
async def test_wave_causal_chain():
    ws = get_world_state()
    ws.clear()

    # Region A -> B -> C
    with ws.transaction("setup"):
        ra = ws._topology.add(["role1", "role2"], token="A", instability=0.1)
        rb = ws._topology.add(["role2", "role3"], token="B", instability=0.1)
        rc = ws._topology.add(["role3", "role4"], token="C", instability=0.1)

        ws._topology.set_neighborhood_cohesion(("role1", "role2"), 0.9)
        ws._topology.set_neighborhood_cohesion(("role2", "role3"), 0.9)
        ws._topology.set_neighborhood_cohesion(("role3", "role4"), 0.9)

    # Trigger strong wave in A
    with ws.transaction("trigger"):
        ws._topology.emit_field_wave(ra.region_id, 1.0)

    # Wait for dispatcher (some wave hops are scheduled via scheduler)
    # The first hop (A->B) is synchronous in _on_field_wave.
    # If intensity > 0.2, it schedules a second hop (B->C).

    # We need to run the scheduler step to process the second hop
    ws.process_cognitive_queue(budget_ms=100)
    await asyncio.sleep(0.1)

    # Verify C absorbed a wave
    region_c = ws._topology.get_region(rc.region_id)
    assert region_c is not None
    inst_c = region_c.instability
    assert inst_c > 0.1

    # Verify causality chain
    causal = ws.get_causal_telemetry()
    absorptions = [e for e in causal if e.get("type") == "wave_absorption"]

    # Should see A->B and B->C
    targets = [a["details"]["region_id"] for a in absorptions]
    assert rb.region_id in targets
    assert rc.region_id in targets
