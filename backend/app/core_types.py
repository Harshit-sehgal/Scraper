"""Foundational Types for the Semantic Substrate.

LAW: Physical truth is a topological property of the field.
Meaning is a geometric distance in the Role Manifold.
"""

import uuid
from dataclasses import dataclass, field

from app.field_laws import (
    MAX_COUPLING_TRANSFER,
    MAX_INSTABILITY_FLUX,
    PROPAGATION_DECAY_FLOOR,
    ROLE_EXCLUSIVITY,
)


@dataclass
class FieldConflictRegion:
    """A metastable region in the semantic field where multiple roles compete."""

    competing_roles: list[str]
    token: str
    instability: float = 1.0  # [0, 1] entropy / tension level
    region_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Dynamics (Internal)  # noqa: ERA001, RUF100
    recurrence_score: float = 0.0
    persistence: float = 1.0
    stability_momentum: float = 0.0
    local_convergence: float = 0.3
    local_temperature: float = 0.5
    local_energy: float = 5.0
    integrity: float = 0.5
    domain: str = ""
    source_record: str = ""
    local_memory: dict = field(default_factory=dict)
    idle_cycles: int = 0
    energy_reservoir: float = 0.0
    version: int = 1  # MVCC monotonic version counter
    semantic_pressure: float = 0.5
    topology_neighbors: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not hasattr(self, "_propagation_count"):
            self._propagation_count = 0
        if not self.region_id:
            self.region_id = str(uuid.uuid4())[:8]

    def evolve(self, force: bool = False):
        """Evolve basin state (Instability, Convergence, Persistence).

        LAW 5: No fixed evolution cadence. Basins evolve based on field
        demand (tension, pressure, depth), not procedural loops.
        """
        # Phase 58: Always apply state decay to ensure convergence
        attractor = min(1.0, self.local_convergence * 1.5)
        plasticity = 1.0 - attractor * 0.8
        self.instability *= 0.95 * plasticity
        self.recurrence_score *= 0.9

        if not force:
            # Field-demand throttle: skip expensive updates if basin is settled
            demand = self.instability * 0.6 + self.recurrence_score * 0.4
            if self.local_convergence > 0.7 and self.instability < 0.3:
                demand *= 0.3
            if demand < 0.15:
                self.idle_cycles += 1
                # Still update energy to reflect decay
                self.local_energy = max(0.0, self.instability * 5.0 + self.semantic_pressure * 5.0)
                return []

        self.idle_cycles = 0
        effect = 1.0 / (1.0 + 2.718 ** (-10 * (self.recurrence_score - 0.3)))
        self.instability = min(1.0, self.instability + min(0.02 * effect, MAX_INSTABILITY_FLUX))
        self.persistence = min(2.0, self.persistence + 0.05)
        self.local_convergence = min(1.0, self.local_convergence + 0.02 * plasticity)
        decay = 1.0 / (1.0 + 2.718 ** (-10 * (self.instability - 0.3)))
        self.local_convergence *= 1.0 - decay * 0.05
        self.local_temperature = self.local_temperature * 0.9 + (self.instability * 0.8) * 0.1

        # Accumulate Energy Reservoir if basin is high-instability but not
        # converging
        if self.instability > 0.6 and plasticity > 0.5:
            self.energy_reservoir += 0.1
        else:
            self.energy_reservoir *= 0.9  # Dissipate if not trapped

        local_restructure = False
        if self.energy_reservoir > 1.0:
            # Phase Transition: Reset local state to allow escaping minima
            self.instability *= 0.5
            self.local_convergence = 0.3
            self.energy_reservoir = 0.0
            local_restructure = True

        # Phase 47: Grounding Energy Update
        # LAW 2: Energy = instability (potential) + pressure (external tension)
        self.local_energy = max(0.0, self.instability * 5.0 + self.semantic_pressure * 5.0)

        # Compute exclusion effects from local instability — no ws mutation
        effects = []
        distort = 1.0 / (1.0 + 2.718 ** (-10 * (self.instability - 0.3)))
        effect_strength = distort * self.instability * 0.01 * plasticity
        if local_restructure:
            effect_strength *= 5.0  # Burst of exclusion on restructuring

        for role in self.competing_roles:
            for peer in self.competing_roles:
                if peer != role:
                    key = tuple(sorted([role, peer]))
                    current = self.local_memory.get(str(key), 0.0)
                    self.local_memory[str(key)] = min(1.0, current + effect_strength)
                    effects.append((key, effect_strength))
        return effects

    def propagate(self) -> list:
        """Autonomous propagation — governed by formal locality laws."""
        effects = []
        for role in self.competing_roles:
            for ra, rb in ROLE_EXCLUSIVITY:
                peer = None
                if role == ra:
                    peer = rb
                elif role == rb:
                    peer = ra
                if peer is not None and peer not in self.competing_roles:
                    local_count = getattr(self, "_propagation_count", 0) + 1
                    self._propagation_count = local_count
                    local_decay = max(PROPAGATION_DECAY_FLOOR, 1.0 / (1.0 + local_count * 0.2))
                    spread = min(self.instability * MAX_COUPLING_TRANSFER * local_decay, self.instability * 0.5)
                    key = tuple(sorted([role, peer]))
                    effects.append((key, spread))
        return effects
