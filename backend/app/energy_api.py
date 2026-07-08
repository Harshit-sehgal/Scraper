"""EnergyAPI — controlled mutations for energy state.

Encapsulates all energy mutations behind EnergyState ownership.
No subsystem should call ws.metrics.global_energy = x directly — use EnergyAPI instead.
"""

import logging

logger = logging.getLogger(__name__)


class EnergyAPI:
    """Controlled interface for energy mutations.
    
    Delegates all state mutations to EnergyState.
    NEVER accesses ws.metrics directly.
    """

    def __init__(self, ws):
        from app.energy_state import EnergyState
        if isinstance(ws, EnergyState):
            self._energy = ws
        else:
            self._energy = ws.energy_state

    # ─── Query Operations (read-only) ────────────────────────────────────

    def get_global_energy(self) -> float:
        return self._energy.global_energy

    # ─── Mutation Operations (state-changing) ────────────────────────────

    def set_global_energy(self, value: float):
        self._energy.set_energy(value)

    # Region energy mutations belong to TopologyState — use TopologyAPI instead.
    # These were bypassing the topology ownership boundary. Removed in Phase 1.
