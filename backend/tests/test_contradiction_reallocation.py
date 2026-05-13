"""Test contradiction-driven re-allocation — verifies graph-native contradiction pressure."""

from app.semantic_contradiction_engine import (
    detect_allocation_contradictions,
    apply_contradiction_learning,
    IncompatibilityTopology,
)
from app.semantic_world_state import get_world_state


def test_detect_exclusive_role_contradiction():
    """When exclusive roles receive the same value, a contradiction must be detected."""
    ws = get_world_state()
    ws.clear()

    output = {"origin": "LAX", "destination": "LAX"}
    schema = ["origin", "destination"]

    contradictions = detect_allocation_contradictions(output, schema)
    assert len(contradictions) > 0, "Exclusive roles with same value must trigger contradiction"


def test_learned_exclusion_persists():
    """After a contradiction, the learned exclusion must strengthen in world state."""
    ws = get_world_state()
    ws.clear()

    output = {"origin": "LAX", "destination": "LAX"}
    schema = ["origin", "destination"]

    contradictions = detect_allocation_contradictions(output, schema)
    assert len(contradictions) > 0, "Must detect contradiction first"

    # Mock reng + detect_type_fn since apply_contradiction_learning needs them
    from app.semantic_inference_engine import RoleEmbeddingEngine
    reng = RoleEmbeddingEngine()
    from app.semantic_mapper import detect_semantic_type
    from app.semantic_allocation_engine import _UNIVERSAL_ROOTS

    apply_contradiction_learning(output, schema, reng, detect_semantic_type, contradictions, [], _UNIVERSAL_ROOTS)

    key = ("destination", "origin")
    learned = ws.learned_exclusions.get(key, 0.0)
    assert learned > 0.0, f"Expected learned exclusion > 0, got {learned}"


def test_detect_allocation_contradictions_with_schema():
    """detect_allocation_contradictions must work with schema that has no exclusivity rules."""
    ws = get_world_state()
    ws.clear()

    # No exclusivity violation
    output = {"name": "Acme Corp", "price": "100"}
    schema = ["name", "price"]
    contradictions = detect_allocation_contradictions(output, schema)
    assert len(contradictions) == 0, "No contradiction for distinct values on non-exclusive roles"


def test_identity_clash_detection():
    """Same value assigned to multiple roles must trigger identity clash."""
    it = IncompatibilityTopology()
    assignments = {"from": "LAX", "to": "LAX"}
    conflicts = it.detect_impossible_neighborhoods([], assignments)

    identity_clashes = [c for c in conflicts if c.conflict_type == "identity_clash"]
    assert len(identity_clashes) > 0, "Identity clash must be detected for duplicate value"
    assert identity_clashes[0].energy_penalty > 0, "Energy penalty must be positive"
