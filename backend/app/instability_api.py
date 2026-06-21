"""Instability API — Hardened interface for tension-aware field dynamics.

LAW 14: All field perturbations must pass through the Immunity Layer.
High-entropy data sources are quarantined before they can affect stable basins.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)


def get_world_state() -> SemanticWorldState:
    import app.semantic_world_state

    return app.semantic_world_state.get_world_state()


if TYPE_CHECKING:
    from app.semantic_world_state import SemanticWorldState


class InstabilityAPI:
    """Hardened interface for controlled exclusion and tension mutations."""

    def __init__(self, ws: SemanticWorldState | None = None) -> None:
        self.ws: SemanticWorldState = ws or get_world_state()

    # ─── Query Operations ────────────────────────────────────────────────

    def get_learned_exclusion(self, r1: str, r2: str) -> float:
        return self.ws.get_exclusion(r1, r2)

    def get_exclusion(self, r1: str, r2: str) -> float:
        """Alias for get_learned_exclusion (legacy support)."""
        return self.get_learned_exclusion(r1, r2)

    # ─── Mutation Operations ─────────────────────────────────────────────

    def set_exclusion(self, r1: str, r2: str, value: float) -> None:
        with self.ws.transaction(f"api_exclusion:{r1}"):
            self.ws.set_exclusion_by_key((r1, r2), value)

    def add_exclusion(self, r1: str, r2: str, delta: float) -> None:
        """Add to an existing exclusion (legacy support)."""
        current = self.get_learned_exclusion(r1, r2)
        self.set_exclusion(r1, r2, current + delta)

    def decay_exclusion(self, r1: str, r2: str, rate: float = 0.9) -> None:
        """Decay an existing exclusion."""
        current = self.get_learned_exclusion(r1, r2)
        self.set_exclusion(r1, r2, current * rate)


class ImmunityLayer:
    """Governs semantic data ingestion and protects against adversarial perturbations."""

    def __init__(self, ws: SemanticWorldState | None = None) -> None:
        self.ws = ws or get_world_state()
        # Quarantine Registry: domain / source -> trust_score
        self._quarantined_sources: dict[str, float] = {}

    # ─── Query Operations ────────────────────────────────────────────────

    def get_trust(self, source: str) -> float:
        return self._quarantined_sources.get(source, 1.0)

    # ─── Mutation Operations ─────────────────────────────────────────────

    def validate_perturbation(self, source: str, token: str, roles: list[str]) -> bool:  # noqa: ARG002, RUF100
        """Evaluate if a data source is safe to perturb the field (Phase 42)."""
        trust = self._quarantined_sources.get(source, 1.0)

        # 1. Source Trust
        if trust < 0.2:
            logger.warning("IMMUNITY: Blocked perturbation from untrusted source [%s]", source)
            return False

        # 2. Regional Integrity
        # If any target roles are "Crystalline", check system energy
        for role in roles:
            level = self.ws.get_role_level(role)
            if (level > 0 or self.ws.is_role_anchored(role)) and self.ws.metrics.global_energy > 7.0:
                # System is too hot to allow mutation of high-level
                # concepts
                logger.info(
                    "IMMUNITY: Shielded high-integrity role [%s] from mutation (Energy too high)",
                    role,
                )
                return False

        # 3. Adversarial Pressure Detection (Phase 42)
        # Check if this source is repeatedly causing high energy spikes
        if self.ws.metrics.global_energy > 5.0 and trust < 0.6:
            logger.warning("IMMUNITY: Quarantining source [%s] for contributing to field fever.", source)
            self.quarantine_source(source, penalty=0.2)
            return False

        return True

    def quarantine_source(self, source: str, penalty: float = 0.5) -> None:
        """Lower trust score for a specific data source."""
        current = self._quarantined_sources.get(source, 1.0)
        self._quarantined_sources[source] = max(0.0, current - penalty)
        # Evict sources with zero trust when registry grows too large
        if len(self._quarantined_sources) > 500:
            expired = [k for k, v in self._quarantined_sources.items() if v <= 0.0]
            for k in expired:
                self._quarantined_sources.pop(k, None)


_immune_system: Any = None


def get_immune_system(ws: SemanticWorldState | None = None) -> ImmunityLayer:
    global _immune_system
    if _immune_system is None:
        _immune_system = ImmunityLayer(ws=ws)
    return _immune_system


def reset_immune_system() -> None:
    """Reset the global immune system (for testing)."""
    global _immune_system
    _immune_system = None
