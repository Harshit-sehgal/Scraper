"""Core types — shared dataclasses and constants for the semantic field.

All modules depend on this layer, NOT on each other or on SemanticWorldState.
This prevents reverse dependency entanglement and circular architecture collapse.
"""

import uuid
from typing import List
from dataclasses import dataclass, field

# ─── Field Laws ───────────────────────────────────────────────────────────────

MAX_PROPAGATION_RADIUS = 1
PROPAGATION_DECAY_FLOOR = 0.3
MAX_COUPLING_TRANSFER = 0.3
MAX_ATTRACTOR_PULL = 2.0
MAX_INSTABILITY_FLUX = 0.2

# ─── FieldConflictRegion ──────────────────────────────────────────────────────

@dataclass
class FieldConflictRegion:
    """A persistent, pre-resolution conflict in the semantic field.
    
    Contradictions are NOT immediately resolved. They persist as
    topology structures that propagate, restructure the field,
    and bias equilibrium before interpretation emerges.
    
    Each region is an autonomous basin that self-evolves and propagates
    instability to neighbors via formal locality laws.
    """
    competing_roles: List[str]
    token: str
    instability: float
    region_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    semantic_pressure: float = 0.0
    propagation_radius: int = 1
    recurrence_score: float = 0.0
    topology_neighbors: List[str] = field(default_factory=list)
    source_record: str = ""
    persistence: float = 1.0
    stability_momentum: float = 0.0
    local_convergence: float = 0.3
    local_temperature: float = 0.5
    local_energy: float = 5.0
    integrity: float = 0.5
    domain: str = ""
    local_memory: dict = field(default_factory=dict)
    idle_cycles: int = 0
    energy_reservoir: float = 0.0

    def __post_init__(self):
        if not hasattr(self, '_propagation_count'):
            self._propagation_count = 0

    def evolve(self, force=False):
        """Autonomous basin evolution — self-throttled by field demand.
        
        LAW 5: No fixed evolution cadence. Basins evolve based on field
        demand (tension, pressure, depth), not procedural loops.
        
        - High instability + high recurrence = frequent evolution (hot basin)
        - Low instability + high convergence = rare evolution (settled basin)
        - The force flag overrides throttling (used by explicit evolution passes)
        
        Returns: list of (exclusion_key, delta) tuples for global effects
        that the caller must apply through formal InstabilityState APIs.
        """
        if not force:
            # Field-demand throttle: only evolve if basin has significant tension
            # High instability OR high recurrence indicates a hot basin that needs evolution
            demand = self.instability * 0.6 + self.recurrence_score * 0.4
            # Settled basins (low instability + high convergence) can skip
            if self.local_convergence > 0.7 and self.instability < 0.3:
                demand *= 0.3
            if demand < 0.15:
                self.idle_cycles += 1
                return []
        
        self.idle_cycles = 0
        attractor = min(1.0, self.local_convergence * 1.5)
        plasticity = 1.0 - attractor * 0.8

        self.instability *= 0.95 * plasticity
        effect = 1.0 / (1.0 + 2.718 ** (-10 * (self.recurrence_score - 0.3)))
        self.instability = min(1.0, self.instability + min(0.02 * effect, MAX_INSTABILITY_FLUX))
        self.persistence = min(2.0, self.persistence + 0.05)
        self.local_convergence = min(1.0, self.local_convergence + 0.02 * plasticity)
        decay = 1.0 / (1.0 + 2.718 ** (-10 * (self.instability - 0.3)))
        self.local_convergence *= (1.0 - decay * 0.05)
        self.local_temperature = self.local_temperature * 0.9 + (self.instability * 0.8) * 0.1

        # Accumulate Energy Reservoir if basin is high-instability but not converging
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

        # Compute exclusion effects from local instability — no ws mutation
        effects = []
        distort = 1.0 / (1.0 + 2.718 ** (-10 * (self.instability - 0.3)))
        effect_strength = distort * self.instability * 0.01 * plasticity
        if local_restructure:
            effect_strength *= 5.0 # Burst of exclusion on restructuring
            
        for role in self.competing_roles:
            for peer in self.competing_roles:
                if peer != role:
                    key = tuple(sorted([role, peer]))
                    current = self.local_memory.get(str(key), 0.0)
                    self.local_memory[str(key)] = min(1.0, current + effect_strength)
                    effects.append((key, effect_strength))
        return effects

    def propagate(self) -> list:
        """Autonomous propagation — governed by formal locality laws.
        
        Constraints:
        - Radius: 1 (direct exclusivity neighbors only)
        - Attenuation: at least PROPAGATION_DECAY_FLOOR per hop
        - Transfer cap: MAX_COUPLING_TRANSFER * instability
        
        Returns: list of (exclusion_key, delta) tuples for global effects
        that the caller must apply through formal InstabilityState APIs.
        """
        from app.field_laws import ROLE_EXCLUSIVITY
        effects = []
        for role in self.competing_roles:
            for ra, rb in ROLE_EXCLUSIVITY:
                peer = None
                if role == ra:
                    peer = rb
                elif role == rb:
                    peer = ra
                if peer is not None and peer not in self.competing_roles:
                    local_count = getattr(self, '_propagation_count', 0) + 1
                    self._propagation_count = local_count
                    local_decay = max(PROPAGATION_DECAY_FLOOR, 1.0 / (1.0 + local_count * 0.2))
                    spread = min(self.instability * MAX_COUPLING_TRANSFER * local_decay, self.instability * 0.5)
                    key = tuple(sorted([role, peer]))
                    effects.append((key, spread))
        return effects

    def compute_propagation_effects(self, all_exclusions: set, all_regions: list) -> tuple:
        """Field propagation triggered by reinforcement — returns effect deltas.
        
        Args:
            all_exclusions: set of (role_a, role_b) tuples representing known exclusions
            all_regions: list of FieldConflictRegion for cross-region instability transfers
        
        Returns:
            (exclusion_effects, instability_transfers):
            - exclusion_effects: list of (exclusion_key, delta) tuples
            - instability_transfers: list of (target_region, amount) tuples
        """
        exclusion_effects = []
        instability_transfers = []

        for i in range(len(self.competing_roles)):
            for j in range(i + 1, len(self.competing_roles)):
                pair = tuple(sorted([self.competing_roles[i], self.competing_roles[j]]))
                if pair in all_exclusions:
                    spread = min(self.instability * MAX_COUPLING_TRANSFER, 0.15)
                    exclusion_effects.append((pair, spread))

        for role in self.competing_roles:
            pcount = 0
            for ra, rb in all_exclusions:
                peer = None
                if role == ra:
                    peer = rb
                elif role == rb:
                    peer = ra
                if peer is not None and peer not in self.competing_roles:
                    pcount += 1
                    local_decay = max(PROPAGATION_DECAY_FLOOR, 1.0 / (1.0 + pcount * 0.2))
                    spread = min(self.instability * MAX_COUPLING_TRANSFER * local_decay, 0.1)
                    key = tuple(sorted([role, peer]))
                    exclusion_effects.append((key, spread))
                    for other in all_regions:
                        if other is self:
                            continue
                        if peer in other.competing_roles:
                            transfer = min(spread, self.instability * 0.05)
                            self.instability -= transfer
                            instability_transfers.append((other, transfer))

        return exclusion_effects, instability_transfers

