"""TopologyAPI — controlled mutations for the field region graph.

Encapsulates all field_regions access behind TopologyState ownership.
No subsystem should call topology_state.add() directly — use TopologyAPI instead.
"""

import logging
from typing import List, Set, Optional
from app.core_types import FieldConflictRegion
from app.topology_state import RegionSnapshot

logger = logging.getLogger(__name__)


class TopologyAPI:
    """Controlled interface for topology mutations.
    
    Delegates all state mutations to TopologyState.
    NEVER accesses ws.field_regions directly.
    """

    def __init__(self, ws):
        from app.topology_state import TopologyState
        if isinstance(ws, TopologyState):
            self._topology = ws
        else:
            self._topology = ws.topology_state

    # ─── Query Operations (read-only) ────────────────────────────────────

    def find_region(self, token: str, roles: Set[str], domain: str = "") -> Optional[RegionSnapshot]:
        return self._topology.find(token, roles, domain)

    def region_count(self) -> int:
        return self._topology.region_count()

    # ─── Mutation Operations (state-changing) ────────────────────────────

    def add_region(self, competing_roles: List[str], token: str, instability: float = 0.5,
                   integrity: float = 0.5, domain: str = "") -> FieldConflictRegion:
        return self._topology.add(competing_roles, token, instability, integrity, domain)

    def remove_region(self, region) -> bool:
        return self._topology.remove(region)

    def prune_weak_regions(self, min_instability: float = 0.02, min_energy: float = 0.5) -> int:
        return self._topology.prune(min_instability, min_energy)
