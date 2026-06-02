"""TransitionState — owns all transition probability state.

True ownership boundary: NO external code should mutate transition_probs
or transition_observations directly. All changes go through this state object.

Owns:
- transition_probs: Dict[Tuple[str, str], float] — probability of type transitions
- transition_observations: int — total observations made
"""

from typing import Callable, Dict, Optional, Tuple

from app.transaction_context import active_transaction


class TransitionState:
    """Sole owner of the semantic field's transition probability structures."""

    def __init__(self, delta_callback: Optional[Callable[[str, str, dict], None]] = None):
        self._delta_callback = delta_callback
        self._transition_probs: Dict[Tuple[str, str], float] = {}
        self.transition_observations: int = 0

    @property
    def _staging(self) -> Optional[dict]:
        tx = active_transaction.get()
        if tx is not None:
            return tx.get(f"transition_staging_{id(self)}")
        return None

    @_staging.setter
    def _staging(self, value: Optional[dict]):
        tx = active_transaction.get()
        if tx is not None:
            tx[f"transition_staging_{id(self)}"] = value

    def _record(self, action: str, details: dict):
        if self._delta_callback:
            self._delta_callback("transition", action, details)

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self):
        """Snapshot current state for staging."""
        self._staging = {
            "transition_probs": dict(self._transition_probs),
            "transition_observations": self.transition_observations,
        }

    def commit(self):
        """Apply staged changes."""
        if self._staging is not None:
            self._transition_probs = self._staging["transition_probs"]
            self.transition_observations = self._staging["transition_observations"]
            self._staging = None

    def rollback(self):
        self._staging = None

    def _get_struct(self, key: str):
        if self._staging is not None:
            return self._staging[key]
        attr_map = {
            "transition_probs": "_transition_probs",
            "transition_observations": "transition_observations",
        }
        return getattr(self, attr_map[key])

    def _set_struct(self, key: str, val):
        if self._staging is not None:
            self._staging[key] = val
        else:
            attr_map = {
                "transition_probs": "_transition_probs",
                "transition_observations": "transition_observations",
            }
            setattr(self, attr_map[key], val)

    # ─── Read-Only Accessors ─────────────────────────────────────────────

    @property
    def transition_probs(self) -> Dict[Tuple[str, str], float]:
        return dict(self._get_struct("transition_probs"))

    def get_prob(self, type_a: str, type_b: str) -> float:
        return self._get_struct("transition_probs").get((type_a, type_b), 0.4)

    def get_high_transition_types(self, threshold: float = 0.6) -> list:
        probs = self._get_struct("transition_probs")
        return [(a, b) for (a, b), p in probs.items() if p > threshold]

    # ─── Controlled Mutations ────────────────────────────────────────────

    def set_transition_observations(self, value: int):
        """Set transition observation count through staging-aware API."""
        self._set_struct("transition_observations", max(0, value))
        self._record("set_transition_observations", {"value": value})

    def get_transition_observations(self) -> int:
        """Get transition observation count from staging-aware API."""
        return self._get_struct("transition_observations")

    def set_prob(self, type_a: str, type_b: str, value: float):
        clamped = max(0.0, min(1.0, value))
        probs = self._get_struct("transition_probs")
        if clamped <= 0.0:
            probs.pop((type_a, type_b), None)
        else:
            probs[(type_a, type_b)] = clamped
        self._set_struct("transition_probs", probs)
        self._record("set_prob", {"type_a": type_a, "type_b": type_b, "value": value})

    def adjust_prob(self, type_a: str, type_b: str, delta: float):
        current = self.get_prob(type_a, type_b)
        self.set_prob(type_a, type_b, current + delta)

    def observe(self, type_a: str, type_b: str, is_role_boundary: bool):
        """Observe whether a transition was a role boundary or entity continuation."""
        delta = 0.05 if is_role_boundary else -0.05
        self.adjust_prob(type_a, type_b, delta)
        obs = self._get_struct("transition_observations")
        self._set_struct("transition_observations", obs + 1)
        self._record("observe", {"type_a": type_a, "type_b": type_b, "is_role_boundary": is_role_boundary})

    def update_seed(self, data: dict):
        """Seed bootstrap transitions (overwrites only if empty)."""
        probs = self._get_struct("transition_probs")
        if not probs:
            probs.update(data)
            self._set_struct("transition_probs", probs)
            self._record("update_seed", {"size": len(data)})

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "transition_probs": {f"{k[0]}|{k[1]}": v for k, v in self._transition_probs.items()},
            "transition_observations": self.transition_observations,
        }

    def from_dict(self, data: dict):
        self.clear()
        for k, v in data.get("transition_probs", {}).items():
            if "|" in k:
                parts = k.split("|")
                self._transition_probs[tuple(parts)] = v
        self.transition_observations = data.get("transition_observations", 0)

    def clear(self):
        self._set_struct("transition_probs", {})
        self._set_struct("transition_observations", 0)
