from app.semantic_world_state import get_world_state


def test_topological_search() -> None:
    """System should find relevant records based on manifold proximity."""
    ws = get_world_state()
    ws.clear()

    # 1. Add crystalline records
    records = [
        {"name": "Alpha-Hotel", "location": "Paris", "price": "$100", "_confidence": 0.9},
        {"name": "Beta-Resort", "location": "Dubai", "price": "$500", "_confidence": 0.9},
    ]
    # Manually synthesize to ensure they exist
    for r in records:
        ws._synthesize_crystalline_record(r)

    assert len(ws.crystalline_records) == 2

    # 2. Search by value
    results = ws.topological_search("Alpha")
    assert len(results) >= 1
    assert "Alpha-Hotel" in results[0]["name"]

    # 3. Search by 'Intent' (Dubai)
    results = ws.topological_search("Dubai")
    assert len(results) >= 1
    assert "Beta-Resort" in results[0]["name"]


def test_manifold_sharding() -> None:
    """Basins in different domains should not couple."""
    ws = get_world_state()
    ws.clear()

    # 1. Seed roles that both match PRICE type
    from app.semantic_allocation_engine import seed_role_engine
    from app.semantic_ir import SemanticType, create_token

    seed_role_engine(["price", "cost"])

    # Domain A: Hotel
    ws.capture_pre_allocation_field([create_token("$100", 0, 4, 0, SemanticType.PRICE)], ["price", "cost"], domain="hotels")

    # Domain B: Product
    ws.capture_pre_allocation_field([create_token("$200", 0, 4, 0, SemanticType.PRICE)], ["price", "cost"], domain="products")

    # Ensure they are in basins
    assert len(ws.field_regions) == 2

    # 2. Update coupling
    # (Coupling discovery should not find peers across domains)
    hot = ws.update_scale_coupling()

    # Each basin has 0 peers because they are in different domains
    # So hot_neighborhoods should be 0
    assert hot == 0


def test_autonomous_law_induction() -> None:
    """System should learn proximity laws from cohesion."""
    ws = get_world_state()
    ws.clear()

    # 1. Establish high cohesion between role_a and role_b
    key = ("role_a", "role_b")
    for _ in range(10):
        ws._topology.record_cohesion_merge_attempt(key)
        ws._topology.record_cohesion_merge_success(key)

    # 2. Induce laws
    ws.induce_topological_laws(min_attempts=5)

    # 3. Verify law learned
    assert ws.topological_laws.get(key, 0.0) > 0.0


def test_topological_law_bias() -> None:
    """Learned proximity laws should bias future allocations."""
    ws = get_world_state()
    ws.clear()

    # 1. Establish a proximity law between 'name' and 'price'
    key = ("name", "price")
    ws._topology._topological_laws[key] = 1.0

    # 2. Allocate a record where name and price are physically close
    # Text: "ITEM_X is $100"
    from app.semantic_ir import SemanticType, create_token

    tokens = [create_token("ITEM_X", 0, 6, 0, SemanticType.TEXT), create_token("$100", 10, 14, 10, SemanticType.PRICE)]

    # Seed roles
    from app.semantic_allocation_engine import (
        SemanticRecord,
        allocate_semantic_roles,
        seed_role_engine,
    )

    seed_role_engine(["name", "price"])

    record = SemanticRecord(tokens=tokens)
    _, graph = allocate_semantic_roles(record, ["name", "price"])

    # Verify that compatibility was boosted (High confidence due to law)
    assert graph.coherence_score > 0.6
    assert graph.roles["name"].filled_by == "ITEM_X"
    assert graph.roles["price"].filled_by == "$100"
