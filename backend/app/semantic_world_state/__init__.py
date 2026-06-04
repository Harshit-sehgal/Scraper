from app.core_types import FieldConflictRegion
from app.semantic_world_state.core import SemanticWorldState

__all__ = ["FieldConflictRegion", "SemanticWorldState", "get_world_state", "reset_world_state"]

# Global Singleton
_world_state: SemanticWorldState | None = None


def get_world_state() -> SemanticWorldState:
    global _world_state
    if _world_state is None:
        _world_state = SemanticWorldState()
    return _world_state


def reset_world_state() -> None:
    """Reset the global world state singleton (for testing)."""
    global _world_state
    if _world_state is not None:
        _world_state.close()
    _world_state = None

    # Also reset dependent singletons to avoid stale subscriptions / state
    from app.event_dispatcher import reset_dispatcher
    from app.graph_update_scheduler import reset_scheduler
    from app.instability_api import reset_immune_system
    from app.llm_bridge import reset_plugin_manager
    from app.semantic_allocation_engine import reset_role_engine
    from app.semantic_boundary_engine import reset_boundary_engine
    from app.semantic_os import reset_semantic_os

    reset_dispatcher()
    reset_scheduler()
    reset_semantic_os()
    reset_immune_system()
    reset_role_engine()
    reset_boundary_engine()
    reset_plugin_manager()
