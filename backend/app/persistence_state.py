"""Persistence state — serialization and deserialization of the semantic field.

Extracted from SemanticWorldState to separate persistence concerns from
runtime field dynamics.

ALL mutations go through the owning state objects. No direct ws.* dict / list
mutations are performed here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.semantic_world_state import SemanticWorldState


def world_state_to_dict(ws: SemanticWorldState) -> dict:
    """Serialize the world state to a dict for JSON-compatible storage."""
    return ws.to_dict()  # type: ignore[no-any-return]


def world_state_from_dict(ws: SemanticWorldState, data: dict):
    """Restore the world state from a serialized dict.

    Delegates to SemanticWorldState.from_dict() which correctly dispatches
    to each owned state object's from_dict / load_from_dict method.
    """
    ws.from_dict(data)


def clear_world_state(ws: SemanticWorldState):
    ws.clear()
