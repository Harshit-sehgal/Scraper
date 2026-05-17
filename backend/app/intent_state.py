"""IntentState — owns user-defined cognitive goals and field biasing vectors.

True ownership boundary: NO external code should mutate active_intents directly.
All changes go through this state object, which supports transactions.
"""

from typing import Callable, Dict, List, Optional

class IntentState:
    """Sole owner of the semantic field's cognitive intents and goal attractors."""

    def __init__(self, delta_callback: Optional[Callable[[str, str, dict], None]] = None):
        self._delta_callback = delta_callback
        # Active Intents: intent_id -> details {target_vec, strength, target_roles}
        self._active_intents: Dict[str, dict] = {}
        
        # ─── Transaction Staging ──────────────────────────────────────
        self._staging: Optional[dict] = None

    def _record(self, action: str, details: dict):
        if self._delta_callback:
            self._delta_callback("intent", action, details)

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self):
        """Snapshot current state for staging."""
        self._staging = {
            "active_intents": {k: dict(v) for k, v in self._active_intents.items()}
        }

    def commit(self):
        """Apply staged changes."""
        if self._staging is not None:
            self._active_intents = self._staging["active_intents"]
            self._staging = None

    def rollback(self):
        self._staging = None

    def _get_struct(self, key: str):
        if self._staging is not None:
            return self._staging[key]
        attr_map = {
            "active_intents": "_active_intents"
        }
        return getattr(self, attr_map[key])

    def _set_struct(self, key: str, val):
        if self._staging is not None:
            self._staging[key] = val
        else:
            attr_map = {
                "active_intents": "_active_intents"
            }
            setattr(self, attr_map[key], val)

    # ─── Controlled Mutations ────────────────────────────────────────────

    def set_intent(self, intent_id: str, target_vec: List[float], strength: float = 0.5, target_roles: Optional[List[str]] = None):
        """Define a new cognitive intent (Phase 36)."""
        intents = self._get_struct("active_intents")
        intents[intent_id] = {
            "target_vec": list(target_vec),
            "strength": max(0.0, min(1.0, strength)),
            "target_roles": list(target_roles) if target_roles else []
        }
        self._set_struct("active_intents", intents)
        self._record("set_intent", {"intent_id": intent_id, "strength": strength, "roles_count": len(target_roles) if target_roles else 0})

    def remove_intent(self, intent_id: str):
        intents = self._get_struct("active_intents")
        if intent_id in intents:
            del intents[intent_id]
            self._set_struct("active_intents", intents)
            self._record("remove_intent", {"intent_id": intent_id})

    # ─── Read-Only Accessors ─────────────────────────────────────────────

    @property
    def active_intents(self) -> Dict[str, dict]:
        return {k: dict(v) for k, v in self._get_struct("active_intents").items()}

    def get_intent(self, intent_id: str) -> Optional[dict]:
        intent = self._get_struct("active_intents").get(intent_id)
        return dict(intent) if intent else None

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "active_intents": self.active_intents
        }

    def from_dict(self, data: dict):
        self.clear()
        self._set_struct("active_intents", {k: dict(v) for k, v in data.get("active_intents", {}).items()})

    def clear(self):
        self._set_struct("active_intents", {})
