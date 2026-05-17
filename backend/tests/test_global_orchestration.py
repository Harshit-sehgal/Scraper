from app.semantic_world_state import get_world_state, SemanticWorldState

def test_cross_node_causality_trace():
    # 1. Node A creates a transaction
    ws_a = SemanticWorldState(node_id="node_a")
    ws_a.clear()
    
    with ws_a.transaction("original_source"):
        ws_a._energy.set_energy(2.0)
        
    # Journal updated AFTER context manager exits
    trace_id = ws_a._global_journal[-1]["trace_id"]
    state_a = ws_a.to_dict()
    assert state_a["last_trace_id"] == trace_id
    
    # 2. Node B merges state A
    ws_b = SemanticWorldState(node_id="node_b")
    ws_b.clear()
    
    ws_b.merge_state(state_a)
    
    # 3. Verify B's journal shows the remote trace ID
    journal = ws_b.trace_causality()
    merge_tx = next(t for t in journal if t["label"] == "merge:node_a")
    assert merge_tx["trace_id"] == trace_id
    
    # Find the merge entry
    merge_entry = next(e for e in merge_tx["entries"] if e["action"] == "merge_state")
    assert merge_entry["details"]["remote_trace"] == trace_id

def test_substrate_heartbeat_alignment():
    from app.heartbeat_manager import get_heartbeat_manager
    hm = get_heartbeat_manager()
    hm.node_registry.clear()
    
    # 1. Two aligned nodes
    hm.record_heartbeat("n1", {}, "hash_abc", 5.0)
    hm.record_heartbeat("n2", {}, "hash_abc", 5.0)
    
    health = hm.get_global_health()
    assert health["status"] == "synchronized"
    assert health["alignment_score"] == 1.0
    
    # 2. Divergent node joins
    hm.record_heartbeat("n3", {}, "hash_xyz", 5.0)
    health = hm.get_global_health()
    assert health["status"] == "divergent"
    assert health["alignment_score"] < 1.0

def test_adaptive_pressure_throttling():
    ws = get_world_state()
    ws.clear()
    
    # 1. Low pressure
    ws._energy.set_energy(5.0)
    p_low = ws.get_system_pressure()
    
    # 2. High pressure (high energy, high fragmentation)
    ws._energy.set_energy(9.5)
    # Manually mock fragmentation
    ws._topology._communities = [{"a"}, {"b"}, {"c"}, {"d"}, {"e"}]
    
    p_high = ws.get_system_pressure()
    assert p_high > p_low
    
    # 3. Verify dream cycle uses budget correctly (indirectly via journal)
    ws.dream(cycles=1)
    # Find the dream entry in the last transaction
    dream_tx = ws._global_journal[-1]
    dream_entry = next(e for e in dream_tx["entries"] if e["action"] == "dream")
    assert "budget" in dream_entry["details"]
