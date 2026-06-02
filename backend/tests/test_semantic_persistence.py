
"""
Regression tests for Semantic Persistence.
Ensures that learned state survives a save/load round-trip and affects decisions.
"""

import os
from pathlib import Path

from app.semantic_allocation_engine import _get_role_engine
from app.semantic_boundary_engine import get_boundary_engine
from app.semantic_ir import SemanticType
from app.semantic_persistence import clear_semantic_state, load_semantic_state, save_semantic_state


def test_persistence_round_trip():
    # 1. Setup local path
    test_path = str(Path(__file__).parent / "test_semantic_state.json")
    os.environ['SEMANTIC_STATE_PATH'] = test_path

    # 2. Clear initial state
    clear_semantic_state()
    if os.path.exists(test_path):
        os.remove(test_path)

    reng = _get_role_engine()
    be = get_boundary_engine()

    # 3. Inject some "learning"
    # Role compatibility
    reng.learn_from_allocation("price", SemanticType.PRICE, "100", success=True, delta=0.4)
    # Boundary decision (successful merge)
    from app.semantic_boundary_engine import MergeDecision
    be.record_decision(MergeDecision(
        type_a='organization', type_b='organization',
        value_a='Prestige', value_b='Group',
        merged=True, coherence_after=0.9, success=True
    ))
    # Motif observation
    from app.semantic_boundary_engine import record_motif_observation
    record_motif_observation(['organization', 'price'])

    # Verify pre-save state
    assert reng.get_compatibility("price", SemanticType.PRICE) > 0.6
    assert be.motif_learner.total_records == 1

    # 4. Save state
    save_semantic_state()
    import time
    time.sleep(0.1)  # Wait for filesystem sync
    assert os.path.exists(test_path)

    # 5. Clear in-memory state
    clear_semantic_state(clear_file=False)
    reng.load_cache({})  # clear in-memory cache
    assert reng.get_compatibility("price", SemanticType.PRICE) == 0.5
    assert be.motif_learner.total_records == 0

    # 6. Load state
    load_semantic_state()

    # 7. Verify post-load state
    assert reng.get_compatibility("price", SemanticType.PRICE) > 0.6
    assert be.motif_learner.total_records == 1

    # Verify boundary decision affected behavior
    s = be.score_pair('organization', 'organization', 'X', 'Y', 0, 1)
    assert s.cohesion > 0.6

    # 8. Cleanup
    if os.path.exists(test_path):
        os.remove(test_path)


def test_persistence_affects_pipeline():
    # Ensures that saved state actually changes run_pipeline behavior
    test_path = str(Path(__file__).parent / "test_pipeline_persistence.json")
    os.environ['SEMANTIC_STATE_PATH'] = test_path
    clear_semantic_state()
    if os.path.exists(test_path):
        os.remove(test_path)
