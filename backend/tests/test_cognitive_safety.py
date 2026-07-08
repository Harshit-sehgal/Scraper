from app.semantic_world_state import get_world_state
from app.semantic_inference_engine import RoleEmbeddingEngine

def test_invariant_anchoring():
    ws = get_world_state()
    ws.clear()
    
    # 1. Anchor a role
    ws._manifold.set_manifold_vector("core_role", [1.0]*16)
    ws._manifold.anchor_role("core_role")
    
    # 2. Try to relax it
    reng = RoleEmbeddingEngine()
    # Mock some force in buffer
    reng.force_buffer["core_role"] = [-0.5]*16
    reng.relax_manifold()
    
    # 3. Verify vector unchanged
    vec = ws._manifold.get_manifold_vector("core_role")
    assert all(v == 1.0 for v in vec)

def test_ontological_firewall_high_entropy():
    ws = get_world_state()
    ws.clear()
    
    # High entropy remote vector (all 0.5)
    data = {
        "manifold": {"uncertain_role": [0.5]*16},
        "version": "1.1"
    }
    
    # 2. Import
    ws.import_federated_manifold(data)
    
    # 3. Verify filtered
    assert not ws._manifold.has_manifold_role("uncertain_role")

def test_ontological_firewall_contradiction():
    ws = get_world_state()
    ws.clear()
    
    # Local stable role
    ws._manifold.set_manifold_vector("stable_role", [1.0]*16)
    ws._energy.set_schema_instability("stable_role", 0.1)
    
    # Remote contradictory role (all 0.0)
    data = {
        "manifold": {"stable_role": [0.0]*16},
        "version": "1.1"
    }
    
    # 2. Import
    ws.import_federated_manifold(data)
    
    # 3. Verify no change (blending skipped due to distance)
    vec = ws._manifold.get_manifold_vector("stable_role")
    assert vec[0] == 1.0

def test_cognitive_health_summary():
    ws = get_world_state()
    ws.clear()
    
    # Add some roles
    ws._manifold.set_manifold_vector("price", [1.0]*16)
    ws._manifold.anchor_role("price")
    
    health = ws.get_cognitive_health()
    assert "overall_health" in health
    assert health["role_stats"]["anchored"] == 1
