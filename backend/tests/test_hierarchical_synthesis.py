from app.semantic_world_state import get_world_state
from app.semantic_os import get_semantic_os


def test_envelope_creation_and_persistence():
    ws = get_world_state()
    ws.clear()
    
    # 1. Create an envelope
    envelope_id = "complex_concept"
    constituents = ["role_a", "role_b"]
    vec = [0.1]*16
    
    with ws.transaction("distillation"):
        ws._abstraction.create_envelope(envelope_id, constituents, vec, level=1)
        
    # 2. Verify
    assert ws._abstraction.get_role_level(envelope_id) == 1
    env = ws._abstraction.get_envelope(envelope_id)
    assert env["constituents"] == {"role_a", "role_b"}
    
    # 3. Checkpoint round-trip
    state = ws.to_dict()
    ws.clear()
    assert ws._abstraction.get_role_level(envelope_id) == 0
    
    ws.from_dict(state)
    assert ws._abstraction.get_role_level(envelope_id) == 1
    assert ws._abstraction.get_envelope(envelope_id)["constituents"] == {"role_a", "role_b"}

def test_causal_replay_abstraction():
    ws = get_world_state()
    ws.clear()
    
    # 1. Record a transaction
    with ws.transaction("abstraction_op"):
        ws._abstraction.create_envelope("env1", ["r1"], [0.5]*16)
        
    journal = ws.trace_causality()
    tx = journal[-1]
    
    # 2. Replay
    ws.clear()
    ws.replay_transaction(tx)
    
    # 3. Verify
    assert ws._abstraction.get_role_level("env1") == 1

def test_autonomous_hierarchical_synthesis():
    ws = get_world_state()
    ws.clear()
    sos = get_semantic_os()
    
    # 1. Setup a stable community
    # Roles r1 and r2 are in same community and stable
    ws._manifold.set_manifold_vector("r1", [1.0, 0.0]*8)
    ws._manifold.set_manifold_vector("r2", [0.9, 0.1]*8)
    ws._energy.set_schema_instability("r1", 0.05)
    ws._energy.set_schema_instability("r2", 0.05)
    
    # Mock topology communities
    ws._topology._communities = [{"r1", "r2"}]
    
    # 2. Trigger synthesis
    sos.perform_hierarchical_synthesis()
    
    # 3. Verify envelope created
    envs = ws._abstraction.envelopes
    assert len(envs) == 1
    env_id = list(envs.keys())[0]
    assert envs[env_id]["constituents"] == {"r1", "r2"}
    
    # 4. Verify envelope registered in manifold and anchored
    assert ws._manifold.has_manifold_role(env_id)
    assert ws._manifold.is_role_anchored(env_id)
    
    # Level should be 1
    assert sos.get_role_abstraction_level(env_id) == 1

def test_hierarchical_interpretation():
    from app.semantic_ir import SemanticToken, SemanticRecord, SemanticType, Span
    from app.semantic_allocation_engine import allocate_semantic_roles
    
    ws = get_world_state()
    ws.clear()
    
    # 1. Setup an envelope role 'contact_group' wrapping 'phone' and 'email'
    ws._manifold.set_manifold_vector("phone", [1,0,0,0]*4)
    ws._manifold.set_manifold_vector("email", [0,1,0,0]*4)
    
    # Envelope centroid
    centroid = [0.5, 0.5, 0, 0]*4
    ws._manifold.set_manifold_vector("contact_group", centroid)
    ws._abstraction.create_envelope("contact_group", ["phone", "email"], centroid)
    
    # 2. Interpreting with abstraction_gradient=0 (passive abstraction)
    record = SemanticRecord(tokens=[
        SemanticToken("555-0100", "5550100", Span(0, 8), 0, [0.5]*16, SemanticType.PHONE),
        SemanticToken("test@example.com", "test@example.com", Span(10, 25), 1, [0.5]*16, SemanticType.TEXT)
    ])
    
    # Interpret only the envelope
    rec, graph = allocate_semantic_roles(record, ["contact_group"], abstraction_gradient=0.0)
    
    # Should only have the envelope role in graph
    assert "contact_group" in graph.roles
    assert "phone" not in graph.roles
    
    # 3. Interpreting with abstraction_gradient=1.0 (deep interpretation)
    rec, graph = allocate_semantic_roles(record, ["contact_group"], abstraction_gradient=1.0)
    
    # Should have both envelope AND constituents
    assert "contact_group" in graph.roles
    assert "phone" in graph.roles
    assert "email" in graph.roles

def test_topological_meta_reasoning():
    ws = get_world_state()
    ws.clear()
    
    # 1. Setup an envelope with contradictory constituents
    ws._abstraction.create_envelope("bad_env", ["r1", "r2"], [0.5]*16)
    
    # Force high repulsion between r1 and r2
    ws._instability.set_exclusion(("r1", "r2"), 0.9)
    
    # 2. Evaluate consistency
    report = ws.evaluate_topological_consistency()
    
    # 3. Verify contradiction detected
    assert report["score"] < 1.0
    assert len(report["contradictions"]) == 1
    assert report["contradictions"][0]["envelope"] == "bad_env"
    assert report["contradictions"][0]["type"] == "internal_repulsion"

def test_cross_domain_knowledge_synthesis():
    ws = get_world_state()
    ws.clear()
    
    # 1. Local envelope
    ws._abstraction.create_envelope("local_env", ["r1"], [0.5]*16)
    
    # 2. Remote knowledge (similar vector but different constituents)
    remote_data = {
        "envelopes": {
            "remote_env": {
                "constituents": ["r2"],
                "manifold_vec": [0.51]*16, # very close
                "level": 1
            }
        }
    }
    
    # 3. Merge
    ws.merge_hierarchical_knowledge(remote_data)
    
    # 4. Verify local_env was updated with r2
    env = ws._abstraction.get_envelope("local_env")
    assert "r2" in env["constituents"]
    assert "r1" in env["constituents"]
