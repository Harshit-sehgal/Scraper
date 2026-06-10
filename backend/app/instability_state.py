from typing import Any

"""InstabilityState — owns learned exclusions and controls all tension mutations.

True ownership boundary: NO external code should mutate learned_exclusions directly.
All tension changes go through this state object, which validates invariants.
"""

import logging
from collections.abc import Callable

from app.transaction_context import active_transaction

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────
EXCLUSION_EPSILON: float = 0.01
"""Threshold below which exclusion values are considered negligible and pruned."""
EXPECTED_KEY_PARTS: int = 2
"""Expected number of parts for pipe-separated or tuple keys."""


class InstabilityState:
    """Sole owner of the semantic field's tension / exclusion structure."""

    def __init__(self, delta_callback: Callable[[str, str, dict], None] | None = None) -> None:
        self._delta_callback = delta_callback
        self._exclusions: dict[tuple, float] = {}

    @property
    def _staging(self) -> dict[tuple, float] | None:
        tx = active_transaction.get()
        if tx is not None:
            return tx.get(f"instability_staging_{id(self)}")
        return None

    @_staging.setter
    def _staging(self, value: dict[tuple, float] | None) -> None:
        tx = active_transaction.get()
        if tx is not None:
            tx[f"instability_staging_{id(self)}"] = value

    def _record(self, action: str, details: dict[str, Any]) -> None:
        if self._delta_callback:
            self._delta_callback("instability", action, details)

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self) -> None:
        """Start a new transaction by initializing the staging area."""
        self._staging = dict(self._exclusions)

    def commit(self) -> None:
        """Apply staged changes to the active state."""
        if self._staging is not None:
            self._exclusions = self._staging
            self._staging = None

    def rollback(self) -> None:
        """Discard staged changes."""
        self._staging = None

    @property
    def in_transaction(self) -> bool:
        return self._staging is not None

    # ─── Read-Only Accessors ─────────────────────────────────────────────

    @property
    def exclusions(self) -> dict[tuple, float]:
        """Return a copy of the exclusions dict to prevent reference aliasing."""
        source = self._staging if self._staging is not None else self._exclusions
        return dict(source)

    def get_exclusion(self, role_a: str, role_b: str) -> float:
        key = tuple(sorted([role_a, role_b]))
        source = self._staging if self._staging is not None else self._exclusions
        return source.get(key, 0.0)

    def get_exclusion_by_key(self, key: tuple[str, str]) -> float:
        source = self._staging if self._staging is not None else self._exclusions
        return source.get(tuple(sorted(key)), 0.0)

    def exclusion_count(self) -> int:
        source = self._staging if self._staging is not None else self._exclusions
        return len(source)

    def items(self):
        source = self._staging if self._staging is not None else self._exclusions
        return source.items()

    # ─── Controlled Mutations ────────────────────────────────────────────

    def set_exclusion(self, key: tuple[str, str], value: float) -> None:
        sk = tuple(sorted(key))
        clamped = max(0.0, min(1.0, value))
        target = self._staging if self._staging is not None else self._exclusions

        if clamped <= EXCLUSION_EPSILON:
            target.pop(sk, None)
        else:
            target[sk] = clamped
        self._record("set_exclusion", {"key": sk, "value": value})

    def add_exclusion(self, role_a: str, role_b: str, strength: float) -> None:
        key = tuple(sorted([role_a, role_b]))
        target = self._staging if self._staging is not None else self._exclusions
        current = target.get(key, 0.0)
        target[key] = min(1.0, max(0.0, current + strength))
        self._record("add_exclusion", {"role_a": role_a, "role_b": role_b, "strength": strength})

    def decay(self, rate: float = 0.05) -> None:
        target = self._staging if self._staging is not None else self._exclusions
        for key in list(target.keys()):
            target[key] = max(0.0, target[key] - target[key] * rate)
            if target[key] <= EXCLUSION_EPSILON:
                del target[key]
        self._record("decay", {"rate": rate})

    def decay_exclusion(self, role_a: str, role_b: str, rate: float = 0.05) -> None:
        key = tuple(sorted([role_a, role_b]))
        target = self._staging if self._staging is not None else self._exclusions
        if key in target:
            new_val = target[key] - target[key] * rate
            if new_val <= EXCLUSION_EPSILON:
                del target[key]
            else:
                target[key] = new_val

    def delete_exclusion(self, key: tuple[str, str]) -> None:
        target = self._staging if self._staging is not None else self._exclusions
        target.pop(tuple(sorted(key)), None)
        self._record("delete_exclusion", {"key": key})

    def prune_exclusions_weak(self, threshold: float = 0.01) -> int:
        """Remove all exclusions below threshold. Returns count removed."""
        target = self._staging if self._staging is not None else self._exclusions
        before = len(target)
        for key in list(target.keys()):
            if target[key] < threshold:
                del target[key]
        removed = before - len(target)
        if removed:
            self._record("prune_exclusions_weak", {"threshold": threshold, "removed": removed})
        return removed

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {"learned_exclusions": {f"{k[0]}|{k[1]}": v for k, v in self._exclusions.items()}}

    # Maximum length for a string key before trying ast.literal_eval  # nosec
    MAX_KEY_LENGTH = 1_000_000

    def from_dict(self, data: dict[str, Any]) -> None:
        self.clear()
        target = self._staging if self._staging is not None else self._exclusions

        # Phase 47: Symmetry fix - extract nested dictionary if present
        source = data.get("learned_exclusions", data)

        for k, v in source.items():
            if isinstance(k, str):
                if "|" in k:
                    parts = k.split("|")
                    if len(parts) == EXPECTED_KEY_PARTS:
                        sk = tuple(sorted(parts))
                        target[sk] = max(0.0, min(1.0, v))
                    continue

                if len(k) > self.MAX_KEY_LENGTH:
                    logger.warning("Skipping overly long key (%d chars)", len(k))
                    continue

                import ast

                try:
                    k = ast.literal_eval(k)  # nosec  # noqa: PLW2901, RUF100
                except (ValueError, SyntaxError):
                    continue
            if isinstance(k, (list, tuple)) and len(k) == EXPECTED_KEY_PARTS:
                sk = tuple(sorted(k))
                target[sk] = max(0.0, min(1.0, v))

    def clear(self) -> None:
        target = self._staging if self._staging is not None else self._exclusions
        target.clear()

    def merge(self, other_data: dict[str, Any]) -> None:
        """Merge remote instability state into local (Phase 32)."""
        # data format uses pipe-separated keys
        remote_excl = other_data.get("learned_exclusions", {})
        for key_str, r_val in remote_excl.items():
            parts = key_str.split("|")
            if len(parts) == EXPECTED_KEY_PARTS:
                key = tuple(parts)
                l_val = self.get_exclusion_by_key(key)
                # CRDT-lite: pick the strongest exclusion signal
                if r_val > l_val:
                    self.set_exclusion(key, r_val)

        self._record("merge", {"remote_exclusions": len(remote_excl)})
