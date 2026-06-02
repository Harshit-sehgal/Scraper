from app.semantic_world_state import get_world_state


def test_relational_recall_stabilizes_new_basins():
    ws = get_world_state()
    ws.clear()

    # 1. Manually synthesize a crystalline record containing a token
    # This represents 'known' high-integrity knowledge
    token_val = "LAX"
    ws._synthesize_crystalline_record({"origin": token_val, "dest": "JFK"})

    # 2. Capture tokens including the known one
    from app.semantic_ir import SemanticType, create_token

    tokens = [create_token(token_val, 0, 3, 0, SemanticType.LOCATION)]
    schema = ["origin", "destination"]

    ws.capture_pre_allocation_field(tokens, schema)

    # 3. Verify the region has reduced initial instability (knowledge boost)
    # Default instability for un-matched tokens is 0.5 or 0.2 depending on context
    # Our recall boost should reduce it below 0.2 for schema pairs or 0.5 for others.
    view = ws._topology.get_view()
    region = next(r for r in view.all_regions() if r.token == token_val)
    # initial_u = 0.2 - boost (which is 0.1 for 1 match) = 0.1
    assert region.instability < 0.2


def test_temporal_manifold_weighting():
    ws = get_world_state()
    ws.clear()

    token_val = "JFK"

    # 1. Synthesize an OLD crystalline record
    # Manually adjust record index to simulation 'old' knowledge
    ws._synthesize_crystalline_record({"origin": token_val}, 0)
    ws.metrics.increment_records(1000)  # Fast forward 1000 records

    # 2. Check boost for old knowledge
    # current_idx = 1000, record_idx = 0 -> age = 1000
    # weight = e^(-1000/500) = e^-2 ~= 0.13
    boost_old = ws._history.find_crystalline_matches(token_val, current_record=1000)

    # 3. Synthesize a NEW crystalline record
    ws._synthesize_crystalline_record({"dest": token_val}, 1000)

    # 4. Check boost for new knowledge (should be higher)
    boost_new = ws._history.find_crystalline_matches(token_val, current_record=1000)

    assert boost_new > boost_old
    assert boost_new > 0.5  # 1.0 (new) + 0.13 (old) = 1.13 -> clamped to 1.0


def test_substrate_checksum_deterministic():
    ws = get_world_state()
    ws.clear()

    ws._manifold.set_manifold_vector("role_a", [0.5] * 16)
    c1 = ws._manifold.get_manifold_checksum()

    ws._manifold.set_manifold_vector("role_a", [0.5] * 16)
    c2 = ws._manifold.get_manifold_checksum()

    assert c1 == c2

    ws._manifold.set_manifold_vector("role_b", [0.1] * 16)
    c3 = ws._manifold.get_manifold_checksum()
    assert c1 != c3
