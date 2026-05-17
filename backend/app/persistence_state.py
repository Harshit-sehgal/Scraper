"""Persistence state — serialization and deserialization of the semantic field.

Extracted from SemanticWorldState to separate persistence concerns from
runtime field dynamics.

ALL mutations go through the owning state objects. No direct ws.* dict/list
mutations are performed here.
"""


def world_state_to_dict(ws) -> dict:
    """Serialize the world state to a dict for JSON-compatible storage."""
    return ws.to_dict()


def world_state_from_dict(ws, data: dict):
    """Restore the world state from a serialized dict.

    Delegates to SemanticWorldState.from_dict() which correctly dispatches
    to each owned state object's from_dict/load_from_dict method.
    """
    ws.from_dict(data)


def clear_world_state(ws):
    ws.clear()
