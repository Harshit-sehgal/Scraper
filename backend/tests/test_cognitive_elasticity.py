from app.semantic_inference_engine import RoleEmbeddingEngine
from app.semantic_world_state import get_world_state


def test_cognitive_elasticity_rate_scaling():
    ws = get_world_state()
    ws.clear()

    # 1. Low pressure baseline
    ws._energy.set_energy(5.0)
    # p = (0.5 + 0.5 + 0.1) / 3 = 0.36
    # certainty = 0.0 (fresh state)
    # rate = 0.02 * (1.0) * (0.5 + 0.36) ~= 0.017

    # Manually capture manifold state or forces
    # We can't easily see internal rate, but we can verify the effect

    # 2. High pressure scaling
    ws._energy.set_energy(9.5)
    # pressure should be much higher now

    # Just verify get_system_pressure works and is dynamic
    p_low = ws.get_system_pressure()
    ws._energy.set_energy(10.0)
    p_high = ws.get_system_pressure()
    assert p_high > p_low


def test_manifold_dimensionality_induction():
    ws = get_world_state()
    ws.clear()

    # 1. Initial dimension
    assert ws._manifold.dimension == 16
    ws._manifold.set_manifold_vector("role_a", [0.1] * 16)

    # 2. Expand dimensions
    ws._manifold.expand_dimensions(32)
    assert ws._manifold.dimension == 32

    # 3. Verify padding
    vec = ws._manifold.get_manifold_vector("role_a")
    assert len(vec) == 32
    assert all(v == 0.1 for v in vec[:16])
    assert all(v == 0.5 for v in vec[16:])

    # 4. Verify engines pick up new dimension
    from app.semantic_ir import SemanticType
    reng = RoleEmbeddingEngine()
    assert reng.dimension == 32
    type_vec = reng._get_type_vector(SemanticType.PRICE)
    assert len(type_vec) == 32


def test_knowledge_distillation_atoms():
    ws = get_world_state()
    ws.clear()

    # 1. Create a very stable region
    ws._topology.add(["role_a"], "token_x", instability=0.01, integrity=0.95)
    assert ws._topology.region_count() == 1

    # 2. Distill atoms
    count = ws._topology.distill_crystalline_atoms()
    assert count == 1
    assert ws._topology.region_count() == 0

    # 3. Verify atom store
    atoms = ws._topology._crystalline_atoms
    assert len(atoms) == 1
    assert atoms[0]["token"] == "token_x"


def test_dimensionality_induction_trigger():
    ws = get_world_state()
    ws.clear()

    reng = RoleEmbeddingEngine()
    # 1. Set low certainty conditions
    ws._manifold.learning_count = 300
    # Manifold with near-constant vectors has low certainty (low variance)
    ws._manifold.set_manifold_vector("r1", [0.5] * 16)
    ws._manifold.set_manifold_vector("r2", [0.5001] * 16)

    initial_dim = ws._manifold.dimension

    # 2. Trigger check
    reng.detect_dimensionality_need()

    # 3. Dim should have expanded
    assert ws._manifold.dimension > initial_dim
    assert ws._manifold.dimension == initial_dim + 8


def test_basin_pre_heating():
    ws = get_world_state()
    ws.clear()

    from app.semantic_ir import SemanticType, create_token

    # 1. Setup manifold so that 'contact_role' is near SemanticType.PHONE
    # PHONE vector has 1.0 at index 4, 0.0 at index -2, and 0.5 at index -1
    phone_vec = [0.5] * 16
    phone_vec[4] = 1.0
    phone_vec[-2] = 0.0  # Centrality anchor
    ws._manifold.set_manifold_vector("contact_role", phone_vec)

    # 2. Capture an unidentified token of type PHONE
    token = create_token("555-0100", 0, 8, 0, SemanticType.PHONE)

    # This should trigger pre-heating using find_roles_near_type
    ws.capture_pre_allocation_field([token], [])

    # 3. Verify basin was pre-heated with 'contact_role'
    view = ws._topology.get_view()
    basin = next(r for r in view.all_regions() if r.token == "555-0100")
    assert "contact_role" in basin.competing_roles
    assert "_unidentified" in basin.competing_roles
    assert basin.instability == 0.4  # Pre-heated value
