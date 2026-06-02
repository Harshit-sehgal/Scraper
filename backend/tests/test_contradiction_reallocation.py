"""Test field-driven exclusion learning — verifies continuous field tension learning."""

from app.semantic_ir import SemanticToken, SemanticType, Span
from app.semantic_world_state import get_world_state


def test_field_conflict_drives_exclusion_learning():
    """When allocation conflicts exist, observe_field_perturbation must reinforce exclusions."""
    ws = get_world_state()
    ws.clear()

    # Record with deliberate conflicts
    output = {
        "source": "LAX",
        "target": "LAX",
        "_allocation_conflicts": [
            {"role": "source", "candidate": "LAX", "reason": "exclusivity", "score": 0.8},
        ],
    }

    tokens = [SemanticToken(raw="LAX", normalized="lax", primary_type=SemanticType.LOCATION, span=Span(0, 3), position=0)]

    ws.observe_field_perturbation(output, tokens)

    key = ("source", "target")
    learned = ws.learned_exclusions.get(key, 0.0)
    assert learned > 0.0, f"Expected learned exclusion > 0 from field conflicts, got {learned}"


def test_no_field_conflict_does_not_reinforce():
    """Without allocation conflicts, learned_exclusions must decay (not reinforce)."""
    ws = get_world_state()
    ws.clear()

    # Seed an existing exclusion
    key = ("source", "target")
    ws._instability.set_exclusion(key, 0.5)

    output = {"source": "JFK", "target": "LAX"}
    tokens = [
        SemanticToken(raw="JFK", normalized="jfk", primary_type=SemanticType.LOCATION, span=Span(0, 3), position=0),
        SemanticToken(raw="LAX", normalized="lax", primary_type=SemanticType.LOCATION, span=Span(4, 7), position=1),
    ]

    # Observe clean record
    ws.observe_field_perturbation(output, tokens)
    # Trigger decay (Law 3)
    ws.relax_topology()

    learned = ws.learned_exclusions.get(key, 0.0)
    assert learned < 0.5, f"Exclusion should decay without reinforcement, got {learned}"


def test_exclusion_to_topology_law_bridge():
    """High learned exclusion must create repulsive topological law."""
    ws = get_world_state()
    ws.clear()

    key = ("source", "target")
    # Set exclusion above threshold — should trigger topology law bridge
    ws.set_exclusion_by_key(key, 0.5)

    # Check that topology law was updated (should become more repulsive)
    law = ws.topological_laws.get(key, 0.0)
    assert law < 0.0, f"Expected repulsive topological law from high exclusion, got {law}"


def test_topology_law_to_exclusion_bridge():
    """Strong repulsive topological law must sync back to learned_exclusions."""
    ws = get_world_state()
    ws.clear()

    key = ("source", "target")
    # Set a strongly repulsive topological law
    ws._topology.set_topological_law(key, -0.6)

    # Run evolve_macro_state which triggers the laws → exclusions bridge
    ws.evolve_macro_state()

    # Check that learned_exclusions reflects the repulsive law
    exclusion = ws.learned_exclusions.get(key, 0.0)
    # Note: evolve_macro_state calls decay_topological_laws() (5% decay) before the bridge,
    # so law_val = -0.6 * 0.95 = -0.57, expected_excl = min(1.0, abs(-0.57) * 0.5) = 0.285
    assert exclusion > 0.28, f"Expected exclusion > 0.28 from repulsive law (after decay), got {exclusion}"


def test_contradiction_pressure_triggers_restructuring():
    """High contradiction pressure triggers topology restructuring."""
    ws = get_world_state()
    ws.clear()

    # Seed high field_pressure by setting its underlying components
    # field_pressure = (norm_energy + entropy + exclusion_norm) / 3
    # For 0.6: (0.6 + 0.6 + 0.6) / 3
    ws._energy.set_energy(6.0)
    ws._energy.set_entropy(0.6)
    ws._energy.set_exclusion_count(6)
    assert abs(ws._energy.field_pressure - 0.6) < 0.01

    # Monkey-patch restructure_topology to detect if it was called
    was_restructured = [False]
    original = ws._topology.restructure_topology

    def tracked_restructure(*args, **kwargs):
        was_restructured[0] = True
        return original(*args, **kwargs)

    # Create many allocation conflicts to drive contradiction_pressure > 0.3
    output = {
        "source": "LAX",
        "target": "LAX",
        "price": "100",
        "cost": "200",
        "_allocation_conflicts": [
            {"role": "source", "candidate": "LAX", "reason": "exclusivity", "score": 0.8},
            {"role": "target", "candidate": "LAX", "reason": "exclusivity", "score": 0.7},
            {"role": "price", "candidate": "100", "reason": "duplicate", "score": 0.6},
            {"role": "cost", "candidate": "200", "reason": "duplicate", "score": 0.5},
        ],
    }

    tokens = [
        SemanticToken(raw="LAX", normalized="lax", primary_type=SemanticType.LOCATION, span=Span(0, 3), position=0),
        SemanticToken(raw="100", normalized="100", primary_type=SemanticType.NUMBER, span=Span(4, 7), position=1),
    ]

    try:
        ws._topology.restructure_topology = tracked_restructure  # type: ignore[method-assign]
        ws.observe_field_perturbation(output, tokens)
        # Contradiction pressure should have triggered restructuring
        assert was_restructured[0], "restructure_topology should have been called under high contradiction pressure"
    finally:
        ws._topology.restructure_topology = original  # type: ignore[method-assign]


def test_contradiction_pressure_low_does_not_restructure():
    """Low contradiction pressure does not unnecessarily restructure topology."""
    ws = get_world_state()
    ws.clear()

    # Low field_pressure (< 0.5): set underlying components to yield ~0.3
    ws._energy.set_energy(3.0)
    ws._energy.set_entropy(0.3)
    ws._energy.set_exclusion_count(3)
    assert abs(ws._energy.field_pressure - 0.3) < 0.01

    # Monkey-patch to detect if restructure_topology was called
    was_restructured = [False]
    original = ws._topology.restructure_topology

    def tracked_restructure(*args, **kwargs):
        was_restructured[0] = True
        return original(*args, **kwargs)

    output = {
        "source": "JFK",
        "target": "LAX",
        "_allocation_conflicts": [
            {"role": "source", "candidate": "JFK", "reason": "exclusivity", "score": 0.8},
        ],
    }

    tokens = [
        SemanticToken(raw="JFK", normalized="jfk", primary_type=SemanticType.LOCATION, span=Span(0, 3), position=0),
    ]

    try:
        ws._topology.restructure_topology = tracked_restructure  # type: ignore[method-assign]
        # contradiction_pressure = (1 + 1) / 4 = 0.5, but field_pressure 0.3 < 0.5
        # So threshold (contradiction_pressure > 0.3 AND field_pressure > 0.5) is NOT met
        ws.observe_field_perturbation(output, tokens)
        # Verify restructuring was NOT triggered
        assert not was_restructured[0], "restructure_topology should NOT have been called under low pressure"
    finally:
        ws._topology.restructure_topology = original  # type: ignore[method-assign]

    # Verify observable outcome — exclusion was still learned
    key = ("source", "target")
    learned = ws.learned_exclusions.get(key, 0.0)
    assert learned > 0.0, f"Expected exclusion learning even without restructuring, got {learned}"
