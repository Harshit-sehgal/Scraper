
"""
Semantic Persistence Hub
=========================
Single orchestrator for all semantic memory and learned state.
Unifies:
1. Role compatibility (RoleEmbeddingEngine)
2. Boundary decisions (SemanticBoundaryEngine)
3. Successful motifs (SemanticMemory)
"""

import json
import logging
import os
from typing import Dict, Optional

from app.semantic_allocation_engine import _get_role_engine
from app.semantic_boundary_engine import get_boundary_engine


def get_canonical_cache_path() -> str:
    """Get the path to the canonical semantic state file."""
    path = os.environ.get('SEMANTIC_STATE_PATH', '/tmp/semantic_state_v2.json')
    # print(f"DEBUG: Canonical path resolved to: {path}")
    return path


def load_semantic_state():
    """Load unified semantic state from the filesystem."""
    path = get_canonical_cache_path()
    if not os.path.exists(path):
        return

    try:
        with open(path, 'r') as f:
            full_state = json.load(f)

        reng = _get_role_engine()

        # 1. Load Role Engine State
        if "role_engine" in full_state:
            reng.load_cache(full_state["role_engine"])

        # 2. Load Boundary Engine State
        if "boundary_engine" in full_state:
            get_boundary_engine().load_state(full_state["boundary_engine"])

        # 3. Load Motif Memory (Inference Engine)
        if "motif_memory" in full_state:
            from app.semantic_inference_engine import SemanticMemory
            # We don't have a singleton for SemanticMemory yet, but we can 
            # store it in the boundary engine's motif_learner for now 
            # as they represent the same facts.
            pass

        logging.getLogger(__name__).info("Loaded unified semantic state from %s", path)
    except Exception as e:
        print(f"ERROR: Failed to load semantic state: {e}")
        import traceback
        traceback.print_exc()
        logging.getLogger(__name__).error("Failed to load semantic state: %s", e)


def save_semantic_state():
    """Save unified semantic state to the filesystem."""
    path = get_canonical_cache_path()
    
    try:
        reng = _get_role_engine()
        be = get_boundary_engine()

        full_state = {
            "version": "2.0",
            "role_engine": reng.save_cache(),
            "boundary_engine": be.save_state(),
        }
        
        print(f"DEBUG: full_state keys: {list(full_state.keys())}")

        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w') as f:
            json.dump(full_state, f, indent=2)
            
        print(f"DEBUG: Saved state to {path}")
    except Exception as e:
        print(f"ERROR: Failed to save semantic state: {e}")
        import traceback
        traceback.print_exc()
        logging.getLogger(__name__).error("Failed to save semantic state: %s", e)


def clear_semantic_state(clear_file: bool = True):
    """Reset all learned semantic state."""
    if clear_file:
        path = get_canonical_cache_path()
        if os.path.exists(path):
            os.remove(path)
    
    # Reset in-memory singletons
    reng = _get_role_engine()
    reng.compatibility_cache.clear()
    reng.learning_count = 0
    reng.co_occurrence.clear()
    reng.total_co_occurrences = 0
    reng.role_position_memory.clear()
    if hasattr(reng, '_learned_exclusions'):
        reng._learned_exclusions.clear()
    
    be = get_boundary_engine()
    be.motif_learner.motif_counts.clear()
    be.motif_learner.total_records = 0
    be.transition_detector.observation_count = 0
    be.transition_detector.transition_probs.clear()
    from app.semantic_boundary_engine import _BOOTSTRAP_TRANSITIONS
    be.transition_detector.transition_probs.update(_BOOTSTRAP_TRANSITIONS)
    be.decision_history.clear()
    be.cohesion_model.merge_success.clear()
    be.cohesion_model.merge_attempts.clear()
    be.cohesion_model.split_success.clear()
    be.cohesion_model.split_attempts.clear()
