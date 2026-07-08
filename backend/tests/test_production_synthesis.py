import os
from app.semantic_world_state import get_world_state
from app.checkpoint_manager import get_checkpoint_manager

def test_exhaustive_replay_manifold():
    ws = get_world_state()
    ws.clear()
    
    # 1. Record a manifold mutation
    with ws.transaction("manifold_test"):
        ws._manifold.set_manifold_vector("role_x", [0.1]*16)
        
    journal = ws.trace_causality()
    tx = journal[-1]
    
    # 2. Replay
    ws.clear()
    assert not ws._manifold.has_manifold_role("role_x")
    
    ws.replay_transaction(tx)
    
    # 3. Verify
    assert ws._manifold.has_manifold_role("role_x")
    assert ws._manifold.get_manifold_vector("role_x")[0] == 0.1

def test_checkpoint_round_trip():
    ws = get_world_state()
    ws.clear()
    mgr = get_checkpoint_manager()
    
    # 1. Set some complex state
    ws._energy.set_energy(3.3)
    ws._topology.add(["a", "b"], "token_z", instability=0.7)
    ws._instability.set_exclusion(("a", "b"), 0.9)
    
    # 2. Create checkpoint
    path = mgr.create_checkpoint(label="test_suite")
    assert os.path.exists(path)
    
    # 3. Clear and restore
    ws.clear()
    assert ws.metrics.global_energy == 5.0
    assert ws._topology.region_count() == 0
    
    mgr.load_checkpoint(path)
    
    # 4. Verify full restoration
    assert ws.metrics.global_energy == 3.3
    assert ws._topology.region_count() == 1
    assert ws.learned_exclusions.get(("a", "b")) == 0.9
    
    # Cleanup
    os.remove(path)

def test_nested_transaction_causality():
    ws = get_world_state()
    ws.clear()
    
    with ws.transaction("outer"):
        ws._energy.set_energy(1.0)
        with ws.transaction("inner"):
            ws._energy.set_entropy(0.1)
            
    journal = ws.trace_causality()
    # Should be one transaction with multiple entries
    assert len(journal) == 1
    tx = journal[0]
    assert len(tx["entries"]) >= 2
    # Verify entries are recorded from sub-states
    assert any(e["subsystem"] == "energy" and e["action"] == "set_energy" for e in tx["entries"])
    assert any(e["subsystem"] == "energy" and e["action"] == "set_entropy" for e in tx["entries"])

def test_semantic_os_gateway():
    from app.semantic_os import get_semantic_os
    sos = get_semantic_os()
    sos.reset_engine()
    
    # 1. Ingest via OS
    schema = ["item", "cost"]
    sos.ingest_records([{"item": "Phone", "cost": "00"}], schema)
    
    # 2. Query via OS
    res = sos.query("STABLE 0.6")
    assert res["type"] == "roles"
    
    # 3. Snapshot via OS
    path = sos.save_snapshot(label="os_test")
    assert os.path.exists(path)
    
    # 4. Restore via OS
    sos.reset_engine()
    sos.restore_snapshot(path)
    assert get_world_state().metrics.total_records_processed > 0
    
    os.remove(path)
