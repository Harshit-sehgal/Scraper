import pytest


@pytest.fixture(autouse=True)
def reset_sovereignty_state():
    import app.semantic_allocation_engine
    import app.semantic_world_state

    app.semantic_world_state.reset_world_state()
    app.semantic_allocation_engine.reset_role_engine()
    yield
    app.semantic_world_state.reset_world_state()
    app.semantic_allocation_engine.reset_role_engine()


def _get_role_engine(*args, **kwargs):
    import app.semantic_allocation_engine

    return app.semantic_allocation_engine._get_role_engine(*args, **kwargs)


def seed_role_engine(*args, **kwargs):
    import app.semantic_allocation_engine

    return app.semantic_allocation_engine.seed_role_engine(*args, **kwargs)


class LazyEnumMeta(type):
    def __getattr__(cls, name):
        import app.semantic_ir

        return getattr(app.semantic_ir.SemanticType, name)


class SemanticType(metaclass=LazyEnumMeta):
    pass


def create_token(*args, **kwargs):
    import app.semantic_ir

    return app.semantic_ir.create_token(*args, **kwargs)


def get_world_state(*args, **kwargs):
    import app.semantic_world_state

    return app.semantic_world_state.get_world_state(*args, **kwargs)


def test_manifold_transfer():
    """New roles should inherit interpretations from stable similar roles."""
    ws = get_world_state()
    ws.clear()

    # 1. Establish stable 'price' role
    reng = _get_role_engine()
    price_vec = reng._get_type_vector(SemanticType.PRICE)
    ws._manifold.set_manifold_vector("price", price_vec)
    ws._energy.set_schema_instability("price", 0.05)
    # 2. Seed 'price_val' role - should inherit from 'price'
    # 'price' vs 'price_val' has high similarity
    seed_role_engine(["price_val"])

    fare_vec = reng.manifold.get("price_val")

    assert fare_vec == price_vec
    assert ws._energy.get_schema_instability("price_val") == 0.05


def test_topological_dreaming():
    """Dreaming should reduce field entropy and energy."""
    ws = get_world_state()
    ws.clear()

    # Create some tension: high instability basin
    ws.capture_pre_allocation_field([create_token("X", 0, 1, 0, SemanticType.PRICE)], ["name", "price"])

    # Set initial high instability manually for testing
    r = next(ws._topology.iterate_regions())
    ws._topology.set_region_instability(r, 0.8)
    ws._topology.set_region_integrity(r, 0.5)

    ws.evolve_macro_state()
    initial_entropy = ws.metrics.global_entropy

    # Dreaming for 10 cycles
    ws.dream(cycles=10)

    # Entropy should drop as the lone basin relaxes toward equilibrium
    assert ws.metrics.global_entropy < initial_entropy


def test_re_align_communities():
    """Roles in a community should pull each other toward a manifold consensus."""
    ws = get_world_state()
    ws.clear()

    reng = _get_role_engine()

    # 1. Establish a community: [role_a, role_b]
    ws._topology._neighborhood_cohesion[("role_a", "role_b")] = 0.9
    ws.detect_communities()
    assert any({"role_a", "role_b"} <= set(c) for c in ws.global_communities)

    # 2. Set conflicting manifold positions
    vec_a = [0.5] * 16
    vec_a[0] = 1.0
    vec_b = [0.5] * 16
    vec_b[1] = 1.0
    ws._manifold.set_manifold_vector("role_a", list(vec_a))
    ws._manifold.set_manifold_vector("role_b", list(vec_b))

    # role_a is unstable (will move more)
    ws._energy.set_schema_instability("role_a", 0.8)
    # role_b is stable (will move less)
    ws._energy.set_schema_instability("role_b", 0.1)
    # 3. Dream
    ws.dream(cycles=10)

    new_a = reng.manifold["role_a"]

    # role_a should have moved toward the consensus (centroid)
    # Centroid index 1 was 0.75; vec_a[1] started at 0.5
    assert new_a[1] > 0.5
    assert new_a[0] < 1.0


def test_induce_constraints():
    """System should learn exclusions from persistent conflict basins."""
    ws = get_world_state()
    ws.clear()

    # 1. Create a persistent conflict basin
    ws.capture_pre_allocation_field([create_token("X", 0, 1, 0, SemanticType.PRICE)], ["role_a", "role_b"])

    assert len(ws.field_regions) > 0
    r = next(ws._topology.iterate_regions())
    ws._topology.set_region_recurrence(r.region_id, 0.8)
    ws._topology.set_region_instability(r.region_id, 1.0)

    # 2. Dream
    ws.dream(cycles=1)

    # 3. Verify exclusion learned
    key = tuple(sorted(["role_a", "role_b"]))
    assert ws.learned_exclusions.get(key, 0.0) > 0.0


def test_autonomous_role_spawning():
    """System should hypothesize new roles from recurring unidentified basins."""
    ws = get_world_state()
    ws.clear()

    # 1. Create a recurring unidentified basin
    # Empty schema ensures token won't match anything and will become _unidentified
    token = create_token("UID999", 0, 6, 0, SemanticType.IDENTIFIER)

    # Simulate recurring observation
    for _ in range(10):
        ws.capture_pre_allocation_field([token], [])

    # Ensure it's in an _unidentified basin
    assert any("_unidentified" in r.competing_roles for r in ws.field_regions)

    # Manually promote to 'promising' state for spawning
    for r in ws._topology.iterate_regions():
        if "_unidentified" in r.competing_roles:
            ws._topology.set_region_integrity(r.region_id, 0.8)
            ws._topology.set_region_recurrence(r.region_id, 0.5)

    # 2. Evolve macro state - should trigger spawning
    ws.evolve_macro_state()

    # 3. Verify new role exists
    has_hypo = any(r.startswith("hypo_") for r in ws.role_manifold)
    assert has_hypo


def test_manifold_merge_sovereignty():
    """System should be able to merge knowledge from external sources."""
    ws = get_world_state()
    ws.clear()

    # 1. Local state: empty
    # 2. Remote state: learned 'price' manifold
    remote_data = {"role_manifold": {"price": [0.9] * 16}, "learned_exclusions": {"origin|destination": 0.8}}

    # Call the merge logic from the experimental router
    import asyncio
    from unittest.mock import MagicMock

    from app.routers.experimental import merge_knowledge

    mock_req = MagicMock()
    mock_req.headers = {}

    asyncio.run(merge_knowledge(mock_req, remote_data))

    assert max(ws.role_manifold.get("price", [0])) > 0.5
    assert ws.learned_exclusions[("destination", "origin")] == 0.8


def test_exclusion_pruning_via_cohesion():
    """Exclusions should decay faster if roles have high mutual cohesion."""
    ws = get_world_state()
    ws.clear()

    # 1. Set an exclusion between role_a and role_b
    key = ("role_a", "role_b")
    ws._instability.set_exclusion(key, 0.8)

    # 2. Set high mutual cohesion
    ws._topology._neighborhood_cohesion[key] = 0.9

    # 3. Relax topology
    # (High cohesion should trigger fast decay)
    ws.relax_topology()

    # 4. Verify decay
    assert ws.learned_exclusions[key] < 0.8


def test_manifold_re_seeding():
    """Highly unstable roles should be re-seeded from community stable members."""
    ws = get_world_state()
    ws.clear()
    reng = _get_role_engine()

    # 1. Establish community with one stable member and one unstable
    ws._topology._neighborhood_cohesion[("role_a", "role_b")] = 0.9
    ws.detect_communities()

    # role_a is stable
    vec_a = [0.1] * 16
    reng.manifold["role_a"] = list(vec_a)
    ws._energy.set_schema_instability("role_a", 0.05)

    # role_b is unstable
    vec_b = [0.9] * 16
    reng.manifold["role_b"] = list(vec_b)
    ws._energy.set_schema_instability("role_b", 0.8)

    # 2. Evolve macro state - should trigger re-seeding
    ws.evolve_macro_state()

    # role_b manifold should have moved toward vec_a
    new_b = reng.manifold["role_b"]
    assert new_b[0] < 0.9
    # instability should be reset to 0.4
    assert ws._energy.get_schema_instability("role_b") == 0.4


def test_topology_self_healing():
    """Contradictory laws and exclusions should be thermodynamicly resolved."""
    ws = get_world_state()
    ws.clear()

    # 1. Establish contradictory signals: Exclusion (0.8) vs Proximity Law (0.2)
    key = tuple(sorted(["role_a", "role_b"]))
    ws._instability.set_exclusion(key, 0.8)
    ws._topology._topological_laws[key] = 0.2

    # 2. Evolve macro state - should trigger self-healing
    ws.evolve_macro_state()

    # Exclusion (0.8) is stronger, so Law (0.2) should be weakened
    assert ws.topological_laws.get(key, 0.0) <= 0.2
    # Stronger signal preserved (read from InstabilityState directly)
    assert ws._instability.get_exclusion_by_key(key) == 0.8
