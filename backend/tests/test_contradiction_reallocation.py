"""Test field-driven exclusion learning — verifies continuous field tension learning."""

from app.semantic_world_state import get_world_state
from app.semantic_ir import SemanticToken, SemanticType, Span


def test_field_conflict_drives_exclusion_learning():
    """When allocation conflicts exist, observe_field_perturbation must reinforce exclusions."""
    ws = get_world_state()
    ws.clear()

    # Record with deliberate conflicts
    output = {
        "origin": "LAX",
        "destination": "LAX",
        "_allocation_conflicts": [
            {"role": "origin", "candidate": "LAX", "reason": "exclusivity", "score": 0.8},
        ],
    }

    tokens = [
        SemanticToken(raw="LAX", normalized="lax", primary_type=SemanticType.LOCATION,
                     span=Span(0, 3), position=0)
    ]

    ws.observe_field_perturbation(output, tokens)

    key = ("destination", "origin")
    learned = ws.learned_exclusions.get(key, 0.0)
    assert learned > 0.0, f"Expected learned exclusion > 0 from field conflicts, got {learned}"


def test_no_field_conflict_does_not_reinforce():
    """Without allocation conflicts, learned_exclusions must decay (not reinforce)."""
    ws = get_world_state()
    ws.clear()

    # Seed an existing exclusion
    key = ("destination", "origin")
    ws._instability.set_exclusion(key, 0.5)

    output = {"origin": "JFK", "destination": "LAX"}
    tokens = [
        SemanticToken(raw="JFK", normalized="jfk", primary_type=SemanticType.LOCATION,
                     span=Span(0, 3), position=0),
        SemanticToken(raw="LAX", normalized="lax", primary_type=SemanticType.LOCATION,
                     span=Span(4, 7), position=1)
    ]
    
    # Observe clean record
    ws.observe_field_perturbation(output, tokens)
    # Trigger decay (Law 3)
    ws.relax_topology()

    learned = ws.learned_exclusions.get(key, 0.0)
    assert learned < 0.5, f"Exclusion should decay without reinforcement, got {learned}"
