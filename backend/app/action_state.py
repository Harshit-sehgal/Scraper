"""ActionState — owns executable cognitive actions and their manifold anchors.

True ownership boundary: NO external code should mutate active_actions directly.
All changes go through this state object, which supports transactions.
"""

from typing import Dict, List, Optional, Callable

import time

class ActionState:
    """Sole owner of the semantic field's executable actions and their anchors."""

    def __init__(self, delta_callback: Optional[Callable[[str, str, dict], None]] = None):
        self._delta_callback = delta_callback
        # Active Actions: action_id -> {target_vec, handler_name, threshold, last_run}
        self._active_actions: Dict[str, dict] = {}
        # Action Log: history of triggered actions
        self._action_history: List[dict] = []
        
        # ─── Transaction Staging ──────────────────────────────────────
        self._staging: Optional[dict] = None

    def _record(self, action: str, details: dict):
        if self._delta_callback:
            self._delta_callback("action", action, details)

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self):
        """Snapshot current state for staging."""
        self._staging = {
            "active_actions": {k: dict(v) for k, v in self._active_actions.items()},
            "action_history": list(self._action_history)
        }

    def commit(self):
        """Apply staged changes."""
        if self._staging is not None:
            self._active_actions = self._staging["active_actions"]
            self._action_history = self._staging["action_history"]
            self._staging = None

    def rollback(self):
        self._staging = None

    def _get_struct(self, key: str):
        if self._staging is not None:
            return self._staging[key]
        attr_map = {
            "active_actions": "_active_actions",
            "action_history": "_action_history"
        }
        return getattr(self, attr_map[key])

    def _set_struct(self, key: str, val):
        if self._staging is not None:
            self._staging[key] = val
        else:
            attr_map = {
                "active_actions": "_active_actions",
                "action_history": "_action_history"
            }
            setattr(self, attr_map[key], val)

    # ─── Controlled Mutations ────────────────────────────────────────────

    def register_action(self, action_id: str, target_vec: List[float], 
                        handler_name: str, threshold: float = 0.3):
        """Register a new active dispatcher (Phase 37)."""
        actions = self._get_struct("active_actions")
        actions[action_id] = {
            "target_vec": list(target_vec),
            "handler_name": handler_name,
            "threshold": max(0.01, min(1.0, threshold)),
            "last_run": 0.0,
            "success_count": 0,
            "fail_count": 0
        }
        self._set_struct("active_actions", actions)
        self._record("register_action", {"action_id": action_id, "handler": handler_name})

    def log_execution(self, action_id: str, success: bool, details: Optional[dict] = None):
        """Record the outcome of an action execution."""
        actions = self._get_struct("active_actions")
        if action_id in actions:
            actions[action_id]["last_run"] = time.time()
            if success:
                actions[action_id]["success_count"] += 1
            else:
                actions[action_id]["fail_count"] += 1
            self._set_struct("active_actions", actions)
            
        history = self._get_struct("action_history")
        history.append({
            "action_id": action_id,
            "timestamp": time.time(),
            "success": success,
            "details": details or {}
        })
        if len(history) > 500:
            history = history[-250:]
        self._set_struct("action_history", history)
        self._record("log_execution", {"action_id": action_id, "success": success})

    # ─── Read-Only Accessors ─────────────────────────────────────────────

    @property
    def active_actions(self) -> Dict[str, dict]:
        return {k: dict(v) for k, v in self._get_struct("active_actions").items()}

    @property
    def action_history(self) -> List[dict]:
        return list(self._get_struct("action_history"))

    def get_action(self, action_id: str) -> Optional[dict]:
        return self._get_struct("active_actions").get(action_id)

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "active_actions": self.active_actions,
            "action_history": self.action_history[-100:] # Limit history
        }

    def from_dict(self, data: dict):
        self.clear()
        self._set_struct("active_actions", {k: dict(v) for k, v in data.get("active_actions", {}).items()})
        self._set_struct("action_history", list(data.get("action_history", [])))

    def clear(self):
        self._set_struct("active_actions", {})
        self._set_struct("action_history", [])
