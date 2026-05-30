"""Field Laws — formal locality, conservation, and coupling constraints.

These constants define the physical behavior of the semantic field.
They are separated from the world state to make them independently
auditable and to prevent accidental modification during refactors.

This is the foundational constants layer — zero upward dependencies.
"""

from typing import List, Tuple

# Propagation radius: basins propagate only to direct neighbors
PROPAGATION_DECAY_FLOOR = 0.3

# Coupling transfer: max instability flow per interaction
MAX_COUPLING_TRANSFER = 0.3

# Instability flux: max per-step instability change per basin
MAX_INSTABILITY_FLUX = 0.2

# Attractor pull: max convergence-driven energy reduction
MAX_ATTRACTOR_PULL = 2.0

# ─── Thermodynamic Constants ─────────────────────────────────────────────

# Coupling coefficient for free-energy-gradient-driven redistribution.
# Scales the flow = conductance * free_energy_gradient * COUPLING_COEFFICIENT.
# Higher values = faster equilibration; lower = more conservative.
COUPLING_COEFFICIENT = 0.05

# Maximum free energy gradient per redistribution step (clamp to prevent
# chaotic oscillations from extreme gradient differentials).
FREE_ENERGY_CLAMP = 2.0

# Exclusivity constraints (bootstrap seeds, others learned dynamically)
# Moved here from semantic_allocation_engine.py to prevent upward dependency
# from core_types.py (the foundational type layer) to the allocation engine.
ROLE_EXCLUSIVITY: List[Tuple[str, str]] = [
    # Domain-agnostic role pairs (not transportation-specific)
    ("start", "end"),
    ("price", "cost"),
    ("source", "target"),
    ("input", "output"),
]

# Semantic needs that must not align to the same schema slot
SEMANTIC_NEED_EXCLUSIVITY: List[Tuple[str, str]] = [
    ("status", "date"),
    ("seller", "location"),
]
