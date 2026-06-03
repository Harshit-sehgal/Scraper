from app.semantic_world_state import SemanticWorldState, get_world_state


def test_dynamic_schema_expansion() -> None:
    ws = get_world_state()
    ws.clear()

    # 1. Create a hypo role and make it stable
    ws._manifold.set_manifold_vector("hypo_discount", [0.8] * 16)
    ws._energy.set_schema_instability("hypo_discount", 0.1)  # Very stable

    # 2. Trigger macro evolution
    ws._topology.add(["role_a"], "test")  # Need one region to run loop
    ws.evolve_macro_state()

    # 3. Verify promotion
    assert "discount" in ws.evolved_schema
    assert ws._manifold.has_manifold_role("discount")
    assert not ws._manifold.has_manifold_role("hypo_discount")


def test_manifold_federation_blending() -> None:
    ws_local = get_world_state()
    ws_local.clear()

    # Local knowledge
    ws_local._manifold.set_manifold_vector("role_a", [1.0] * 16)

    # Remote knowledge - must pass Ontological Firewall (dist < 1.5, entropy < 0.9)
    ws_remote = SemanticWorldState()
    ws_remote._manifold.set_manifold_vector("role_a", [0.8] * 16)
    federation_data = ws_remote.export_manifold()

    # 2. Absorb knowledge
    ws_local.import_federated_manifold(federation_data)

    # 3. Verify blending (0.8 * local + 0.2 * remote)
    # 0.8 * 1.0 + 0.2 * 0.8 = 0.8 + 0.16 = 0.96
    vec = ws_local._manifold.get_manifold_vector("role_a")
    assert abs(vec[0] - 0.96) < 0.01


def test_manifold_federation_acquisition() -> None:
    ws_local = get_world_state()
    ws_local.clear()

    # Remote has unique role - must pass entropy filter (dist doesn't apply)
    ws_remote = SemanticWorldState()
    ws_remote._manifold.set_manifold_vector("unique_role", [0.8] * 16)
    data = ws_remote.export_manifold()

    # 2. Absorb
    ws_local.import_federated_manifold(data)

    # 3. Verify acquisition
    assert ws_local._manifold.has_manifold_role("unique_role")
    assert ws_local.metrics.get_schema_instability("unique_role") == 0.3
