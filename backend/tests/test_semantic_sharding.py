import pytest
from app.semantic_world_state import get_world_state
from app.semantic_inference_engine import RoleEmbeddingEngine

def test_manifold_sharding():
    ws = get_world_state()
    ws.clear()
    
    # 1. Setup roles and communities
    ws._manifold.set_manifold_vector("r1", [0.5]*16)
    ws._manifold.set_manifold_vector("r2", [0.5]*16)
    ws._manifold.set_manifold_vector("r3", [0.1]*16)
    ws._manifold.set_manifold_vector("r4", [0.1]*16)
    
    # Communities: {r1, r2} and {r3, r4}
    communities = [{"r1", "r2"}, {"r3", "r4"}]
    ws._manifold.shard_manifold(communities)
    
    # 2. Verify shards
    shards = ws._manifold.get_shards()
    assert len(shards) == 2
    assert ws._manifold.get_role_shard("r1") != ws._manifold.get_role_shard("r3")
    
    # 3. Perform sharded relaxation
    reng = RoleEmbeddingEngine()
    # Mock some forces
    reng.force_buffer["r1"] = [0.1]*16
    reng.force_buffer["r3"] = [0.05]*16
    
    reng.relax_manifold()
    
    # 4. Verify relaxation occurred in both shards
    v1 = ws._manifold.get_manifold_vector("r1")
    v3 = ws._manifold.get_manifold_vector("r3")
    assert v1[0] > 0.5
    assert v3[0] > 0.1
    assert len(reng.force_buffer) == 0

def test_cross_shard_repulsion_isolation():
    """Roles in different shards should not repel each other (Phase 35 isolation)."""
    ws = get_world_state()
    ws.clear()
    
    # Setup r1 and r2 with high exclusion but in different shards
    ws._manifold.set_manifold_vector("r1", [0.5]*16)
    ws._manifold.set_manifold_vector("r2", [0.5]*16)
    ws._instability.set_exclusion(("r1", "r2"), 1.0)
    
    # Force different shards
    ws._manifold.shard_manifold([{"r1"}, {"r2"}])
    
    v1_before = ws._manifold.get_manifold_vector("r1")
    
    reng = RoleEmbeddingEngine()
    reng.relax_manifold()
    
    v1_after = ws._manifold.get_manifold_vector("r1")
    
    # In monolithic relaxation, they would push each other apart.
    # In sharded relaxation, they are isolated. 
    # Small changes may occur due to restoral force (re-alignment) but not repulsion.
    assert v1_after == pytest.approx(v1_before, abs=1e-4)

def test_shard_rebalancing():
    ws = get_world_state()
    ws.clear()
    
    # 1. Create many roles in one community
    roles = [f"r{i}" for i in range(25)]
    ws._manifold.shard_manifold([set(roles)])
    
    # 2. Rebalance with small max size
    ws._manifold.rebalance_shards(max_shard_size=10)
    
    # 3. Verify multiple shards created
    shards = ws._manifold.get_shards()
    # 25 roles / 10 = 3 shards (0-9, 10-19, 20-24)
    assert len(shards) == 3
    assert any(s.endswith("_sub1") for s in shards)
    assert any(s.endswith("_sub2") for s in shards)
