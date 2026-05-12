"""
Semantic Persistence
====================
Manages the loading and saving of the learned state for all semantic engines.
"""

import os

from app.semantic_allocation_engine import _get_role_engine
from app.semantic_boundary_engine import get_boundary_engine


def get_cache_paths():
    cache_path = os.environ.get('SEMANTIC_CACHE_PATH', '/tmp/semantic_cache.json')
    boundary_cache_path = os.environ.get('SEMANTIC_BOUNDARY_CACHE_PATH', '/tmp/semantic_boundary_cache.json')
    return cache_path, boundary_cache_path

def load_semantic_state():
    """Load persisted learning cache into the engines if available."""
    reng = _get_role_engine()
    be = get_boundary_engine()
    cache_path, boundary_cache_path = get_cache_paths()
    
    if reng.learning_count == 0:
        reng.load_from_file(cache_path)
    if be.motif_learner.total_records == 0:
        be.load_from_file(boundary_cache_path)

def save_semantic_state():
    """Persist learned cache for next session."""
    reng = _get_role_engine()
    be = get_boundary_engine()
    cache_path, boundary_cache_path = get_cache_paths()
    
    if reng.learning_count > 0:
        reng.save_to_file(cache_path)
    if be.motif_learner.total_records > 0:
        be.save_to_file(boundary_cache_path)
