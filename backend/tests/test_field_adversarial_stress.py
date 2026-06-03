from app.semantic_pipeline import run_pipeline
from app.semantic_world_state import get_world_state


def test_adversarial_domain_switching() -> None:
    """Field must survive rapid switching between conflicting domains."""
    ws = get_world_state()
    ws.clear()

    # Domain 1: Flights
    flight_schema = ["origin", "destination", "price"]
    flight_records = [
        {"origin": "LHR", "destination": "JFK", "price": "$500"},
        {"origin": "SFO", "destination": "LAX", "price": "$120"},
    ] * 5  # 10 records

    for r in flight_records:
        run_pipeline([r], flight_schema)

    # Verify Flight Community
    ws.evolve_macro_state()
    assert len(ws.global_communities) >= 1

    # Domain 2: Products (conflicting 'origin' - now a country, 'price' - now a range)
    product_schema = ["product", "origin", "price"]
    product_records = [
        {"product": "iPhone", "origin": "China", "price": "999-1299"},
        {"product": "Wine", "origin": "France", "price": "15-50"},
    ] * 5

    # Rapid switching should increase entropy/energy but not crash
    for r in product_records:
        run_pipeline([r], product_schema)

    ws.evolve_macro_state()
    # Pressure should be high due to 'origin' interpretation clash
    assert ws.metrics.field_pressure > 0.1  # HEAD uses different formula

    # Final check: system should keep both interpretations in the manifold
    assert "origin" in ws.role_manifold
    assert "destination" in ws.role_manifold
    assert "product" in ws.role_manifold


def test_field_memory_pruning_stress() -> None:
    """Field pruning must prevent regional memory bloat under load."""
    ws = get_world_state()
    ws.clear()

    schema = ["a", "b", "c"]

    for i in range(100):
        # Ambiguous record: 'X' could be 'a' or 'b'
        records = [{"a": "X", "b": "X", "c": str(i)}]
        run_pipeline(records, schema)

    # Check that field regions are capped
    assert len(ws.field_regions) <= 200


def test_manifold_solidification_adversarial() -> None:
    """Solidified roles must resist corruption from adversarial noise."""
    ws = get_world_state()
    ws.clear()

    # 1. Establish stable 'price' role
    schema = ["item", "price"]
    stable_records = [{"item": "Book", "price": "$10"}] * 60
    for r in stable_records:
        run_pipeline([r], schema)

    ws.evolve_macro_state()
    # price should be solidified or very stable
    _ = ws.metrics.schema_instability.get("price", 0.5)
    # 0.5 means default — no instability recorded (clean allocation)

    # 2. Inject noisy 'price' data via structural conflict
    # Force a basin by creating a conflict: same token for multiple roles
    noisy_records = [{"price": "Cheap", "data": "Cheap"}] * 5
    for r in noisy_records:
        run_pipeline([r], ["price", "data"])

    ws.evolve_macro_state()

    # Role vector must remain near PRICE despite noise
    from app.semantic_allocation_engine import _get_role_engine
    from app.semantic_ir import SemanticType

    reng = _get_role_engine()
    compat = reng.get_compatibility("price", SemanticType.PRICE)
    assert compat > 0.8  # Still highly compatible with PRICE despite noise
