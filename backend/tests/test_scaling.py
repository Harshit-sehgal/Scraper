"""
Phase 66: Long-Horizon Scaling & Causal Pruning Tests
=====================================================
LAW: Substrate must maintain causal integrity while skeletonizing history.
"""

from app.semantic_world_state import SemanticWorldState
from app.event_journal import get_journal


def test_hierarchical_causal_pruning():
    """Verify that trivial manifold updates are pruned from the journal."""
    ws = SemanticWorldState(node_id="scale_test")
    ws.clear()
    journal = get_journal()
    journal.clear()

    # 1. High-displacement update (should be recorded)
    with ws.transaction("big_shift"):
        ws.set_manifold_vector("role_a", [1.0] * 16)

    # 2. Trivial-displacement update (should be PRUNED by Phase 66 logic)
    # The displacement must be < 1e-3 to be pruned
    with ws.transaction("small_shift"):
        ws.apply_force_to_manifold("role_a", [0.0001] * 16)  # Total displacement ~0.0004

    # 3. Structural update (should ALWAYS be recorded)
    with ws.transaction("structural"):
        ws._topology.add(["role_b"], "token_b")

    entries = journal._entries
    types = [e["type"] for e in entries]

    assert "set_manifold_vector" in types  # Big shift kept
    assert "apply_force_to_manifold" not in types  # Trivial shift pruned
    assert "add" in types  # Structural change kept

    print("\nHierarchical Causal Pruning: Trivial noise successfully filtered.")


def test_attractor_skeletonization():
    """Verify that extremely stable attractors skip redundant learning."""
    ws = SemanticWorldState(node_id="skeleton_test")
    ws.clear()

    # 1. Establish high-certainty role
    with ws.transaction("stabilize"):
        ws.set_manifold_vector("role_a", [1.0] * 16)
        # Force high certainty (variance = 0)

    from app.semantic_inference_engine import RoleEmbeddingEngine
    engine = RoleEmbeddingEngine()
    engine.ws = ws  # Force the test world state

    # Check certainty
    assert ws._manifold.get_role_certainty("role_a") > 0.98

    # 2. Attempt low-strength learning (should be skipped by Phase 66)
    c0 = ws.learning_count
    from app.semantic_ir import SemanticType
    engine.learn_from_allocation("role_a", SemanticType.TEXT, "data", success=True, delta=0.01)

    assert ws.learning_count == c0  # Learning skipped due to saturation

    # 3. Attempt breakthrough learning (should be processed)
    engine.learn_from_allocation("role_a", SemanticType.TEXT, "breakthrough", success=True, delta=0.2)
    assert ws.learning_count == c0 + 1  # Learning allowed

    print("\nAttractor Skeletonization: Semantic Saturation successfully applied.")


def test_journal_skeletonization_fidelity():
    """Verify that historical structural events are preserved during trimming."""
    ws = SemanticWorldState(node_id="journal_test")
    journal = get_journal()
    journal.clear()
    journal._max = 20  # Small limit for testing

    # 1. Create structural event (Early)
    with ws.transaction("early_structural"):
        ws._topology.add(["role_early"], "t_early")

    # 2. Flood with 30 trivial events (will trigger trimming)
    for i in range(30):
        with ws.transaction(f"noise_{i}"):
            ws.set_manifold_vector(f"role_{i}", [0.5] * 16)

    # Phase 66 should have kept the 'add' event from 'early_structural'
    # even though it's far beyond the keep_count (10)
    types = [e["type"] for e in journal._entries]
    assert "add" in types
    assert len(journal._entries) <= 15  # 10 (recent) + historical structural (1)

    print("\nJournal Skeletonization: Critical historical events preserved.")
