"""ActionState — owns executable cognitive actions and their manifold anchors.

True ownership boundary: NO external code should mutate active_actions directly.
All changes go through this state object, which supports transactions.
"""

import time
from collections.abc import Callable

from app.transaction_context import active_transaction


class ActionState:
    """Sole owner of the semantic field's executable actions and their anchors."""

    def __init__(self, delta_callback: Callable[[str, str, dict], None] | None = None) -> None:
        self._delta_callback = delta_callback
        # Active Actions: action_id -> {target_vec, handler_name, threshold,
        # last_run}
        self._active_actions: dict[str, dict] = {}
        # Action Log: history of triggered actions
        self._action_history: list[dict] = []

    @property
    def _staging(self) -> dict | None:
        tx = active_transaction.get()
        if tx is not None:
            return tx.get(f"action_staging_{id(self)}")
        return None

    @_staging.setter
    def _staging(self, value: dict | None) -> None:
        tx = active_transaction.get()
        if tx is not None:
            tx[f"action_staging_{id(self)}"] = value

    def _record(self, action: str, details: dict) -> None:
        if self._delta_callback:
            self._delta_callback("action", action, details)

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self) -> None:
        """Snapshot current state for staging."""
        self._staging = {
            "active_actions": {k: dict(v) for k, v in self._active_actions.items()},
            "action_history": list(self._action_history),
        }

    def commit(self) -> None:
        """Apply staged changes."""
        if self._staging is not None:
            self._active_actions = self._staging["active_actions"]
            self._action_history = self._staging["action_history"]
            self._staging = None

    def rollback(self) -> None:
        self._staging = None

    def _get_struct(self, key: str):
        if self._staging is not None:
            return self._staging[key]
        attr_map = {"active_actions": "_active_actions", "action_history": "_action_history"}
        return getattr(self, attr_map[key])

    def _set_struct(self, key: str, val) -> None:
        if self._staging is not None:
            self._staging[key] = val
        else:
            attr_map = {"active_actions": "_active_actions", "action_history": "_action_history"}
            setattr(self, attr_map[key], val)

    # ─── Controlled Mutations ────────────────────────────────────────────

    def register_action(self, action_id: str, target_vec: list[float], handler_name: str, threshold: float = 0.3) -> None:
        """Register a new active dispatcher (Phase 37)."""
        actions = self._get_struct("active_actions")
        actions[action_id] = {
            "target_vec": list(target_vec),
            "handler_name": handler_name,
            "threshold": max(0.01, min(1.0, threshold)),
            "last_run": 0.0,
            "success_count": 0,
            "fail_count": 0,
        }
        self._set_struct("active_actions", actions)
        self._record(
            "register_action",
            {
                "action_id": action_id,
                "target_vec": list(target_vec),
                "handler_name": handler_name,
                "threshold": max(0.01, min(1.0, threshold)),
            },
        )

    def log_execution(self, action_id: str, success: bool, details: dict | None = None) -> None:  # noqa: FBT001
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
        history.append({"action_id": action_id, "timestamp": time.time(), "success": success, "details": details or {}})
        if len(history) > 500:
            history = history[-250:]
        self._set_struct("action_history", history)
        self._record("log_execution", {"action_id": action_id, "success": success, "details": details or {}})

    # ─── Read-Only Accessors ─────────────────────────────────────────────

    @property
    def active_actions(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self._get_struct("active_actions").items()}

    @property
    def action_history(self) -> list[dict]:
        return list(self._get_struct("action_history"))

    def get_action(self, action_id: str) -> dict | None:
        return self._get_struct("active_actions").get(action_id)  # type: ignore[no-any-return]

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"active_actions": self.active_actions, "action_history": self.action_history[-100:]}  # Limit history

    def from_dict(self, data: dict) -> None:
        self.clear()
        self._set_struct("active_actions", {k: dict(v) for k, v in data.get("active_actions", {}).items()})
        self._set_struct("action_history", list(data.get("action_history", [])))

    def clear(self) -> None:
        self._set_struct("active_actions", {})
        self._set_struct("action_history", [])
