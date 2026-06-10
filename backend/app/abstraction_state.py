from typing import Any

"""AbstractionState — owns hierarchical concept mappings and role envelopes.

True ownership boundary: NO external code should mutate envelopes directly.
All changes go through this state object, which supports transactions.
"""

import time
from collections.abc import Callable

from app.transaction_context import active_transaction


class AbstractionState:
    """Sole owner of the semantic field's hierarchical abstractions."""

    def __init__(self, delta_callback: Callable[[str, str, dict], None] | None = None) -> None:
        self._delta_callback = delta_callback
        # Envelopes: envelope_id -> {constituents: Set[str], manifold_vec:
        # list, level: int}
        self._envelopes: dict[str, dict] = {}
        # Abstraction Levels: role -> level (0 = base, 1 = higher-order)
        self._role_levels: dict[str, int] = {}

    @property
    def _staging(self) -> dict | None:
        tx = active_transaction.get()
        if tx is not None:
            return tx.get(f"abstraction_staging_{id(self)}")
        return None

    @_staging.setter
    def _staging(self, value: dict | None) -> None:
        tx = active_transaction.get()
        if tx is not None:
            tx[f"abstraction_staging_{id(self)}"] = value

    def _record(self, action: str, details: dict[str, Any]) -> None:
        if self._delta_callback:
            self._delta_callback("abstraction", action, details)

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self) -> None:
        """Snapshot current state for staging."""
        self._staging = {
            "envelopes": {k: dict(v) for k, v in self._envelopes.items()},
            "role_levels": dict(self._role_levels),
        }

    def commit(self) -> None:
        """Apply staged changes."""
        if self._staging is not None:
            self._envelopes = self._staging["envelopes"]
            self._role_levels = self._staging["role_levels"]
            self._staging = None

    def rollback(self) -> None:
        self._staging = None

    def _get_struct(self, key: str):
        if self._staging is not None:
            return self._staging[key]
        attr_map = {"envelopes": "_envelopes", "role_levels": "_role_levels"}
        return getattr(self, attr_map[key])

    def _set_struct(self, key: str, val) -> None:
        if self._staging is not None:
            self._staging[key] = val
        else:
            attr_map = {"envelopes": "_envelopes", "role_levels": "_role_levels"}
            setattr(self, attr_map[key], val)

    # ─── Controlled Mutations ────────────────────────────────────────────

    def create_envelope(self, envelope_id: str, constituents: list[str], manifold_vec: list[float], level: int = 1) -> None:
        """Distill a set of roles into a singular higher-order envelope (Phase 38)."""
        envelopes = self._get_struct("envelopes")
        levels = self._get_struct("role_levels")

        envelopes[envelope_id] = {
            "constituents": set(constituents),
            "manifold_vec": list(manifold_vec),
            "level": level,
            "created_at": time.time(),
        }
        levels[envelope_id] = level

        self._set_struct("envelopes", envelopes)
        self._set_struct("role_levels", levels)
        self._record(
            "create_envelope",
            {
                "envelope_id": envelope_id,
                "constituents": list(constituents),
                "manifold_vec": list(manifold_vec),
                "level": level,
            },
        )

    def dissolve_envelope(self, envelope_id: str) -> None:
        """Dissolve a higher-order concept back into its constituents."""
        envelopes = self._get_struct("envelopes")
        levels = self._get_struct("role_levels")

        if envelope_id in envelopes:
            del envelopes[envelope_id]
            levels.pop(envelope_id, None)
            self._set_struct("envelopes", envelopes)
            self._set_struct("role_levels", levels)
            self._record("dissolve_envelope", {"envelope_id": envelope_id})

    # ─── Read-Only Accessors ─────────────────────────────────────────────

    @property
    def envelopes(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self._get_struct("envelopes").items()}

    def get_envelope(self, envelope_id: str) -> dict | None:
        env = self._get_struct("envelopes").get(envelope_id)
        return dict(env) if env else None

    def get_role_level(self, role: str) -> int:
        return self._get_struct("role_levels").get(role, 0)  # type: ignore[no-any-return]

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "abstraction": {
                "envelopes": {
                    k: {
                        "constituents": list(v["constituents"]),
                        "manifold_vec": list(v["manifold_vec"]),
                        "level": v["level"],
                    }
                    for k, v in self.envelopes.items()
                },
                "role_levels": dict(self._role_levels),
            },
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        self.clear()
        abs_data = data.get("abstraction", {})
        raw_envelopes = abs_data.get("envelopes", {})
        self._envelopes = {
            k: {"constituents": set(v["constituents"]), "manifold_vec": list(v["manifold_vec"]), "level": v["level"]}
            for k, v in raw_envelopes.items()
        }
        self._role_levels = dict(abs_data.get("role_levels", {}))

    def clear(self) -> None:
        self._set_struct("envelopes", {})
        self._set_struct("role_levels", {})
