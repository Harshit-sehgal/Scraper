from app.semantic_world_state import get_world_state
from app.semantic_os import get_semantic_os
from app.semantic_inference_engine import RoleEmbeddingEngine

def test_intent_biasing_manifold():
    ws = get_world_state()
    ws.clear()
    sos = get_semantic_os()
    
    # 1. Setup a role at neutral position
    role = "steerable_role"
    ws._manifold.set_manifold_vector(role, [0.5]*16)
    
    # 2. Set an intent to pull toward 1.0 (extreme high)
    target = [1.0]*16
    sos.set_cognitive_intent("push_high", target, strength=1.0)
    
    # 3. Perform relaxation
    reng = RoleEmbeddingEngine()
    # Mock multiple cycles to see movement
    for _ in range(50):
        reng.relax_manifold()
        
    # 4. Verify vector moved toward target
    vec = ws._manifold.get_manifold_vector(role)
    assert vec[0] > 0.5
    assert vec[0] < 1.0 # Should be moving toward it
    
def test_targeted_intent_isolation():
    ws = get_world_state()
    ws.clear()
    sos = get_semantic_os()
    
    # r1 is targeted, r2 is NOT
    ws._manifold.set_manifold_vector("r1", [0.5]*16)
    ws._manifold.set_manifold_vector("r2", [0.5]*16)
    
    target = [0.0]*16
    sos.set_cognitive_intent("pull_r1_low", target, strength=1.0, target_roles=["r1"])
    
    # Relaxation
    reng = RoleEmbeddingEngine()
    for _ in range(20):
        reng.relax_manifold()
        
    v1 = ws._manifold.get_manifold_vector("r1")
    v2 = ws._manifold.get_manifold_vector("r2")
    
    assert v1[0] < 0.5
    # v2 should be relatively unchanged (only tiny restoral force)
    assert abs(v2[0] - 0.5) < 0.01

def test_intent_persistence_checkpoint():
    ws = get_world_state()
    ws.clear()
    sos = get_semantic_os()
    
    sos.set_cognitive_intent("p1", [0.9]*16)
    
    # Save/Load
    state = ws.to_dict()
    ws.clear()
    assert len(ws._intent.active_intents) == 0
    
    ws.from_dict(state)
    assert "p1" in ws._intent.active_intents
    assert ws._intent.active_intents["p1"]["target_vec"][0] == 0.9
