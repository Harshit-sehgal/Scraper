"""Topology Region Ops — controlled attribute mutations on FieldConflictRegions.

Extracted from topology_state.py for modularity.  Every function takes
the ``TopologyState`` as the first argument so the caller can still use
``self.set_region_instability(...)`` style via thin delegation.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.topology_state import TopologyState


def set_region_instability(state: "TopologyState", region_id: Any, value: float) -> None:
    r = state.get_region(region_id)
    if r:
        old_val = r.instability
        r.instability = max(0.01, min(1.0, value))
        state._record("set_region_instability", {"region_id": r.region_id, "value": value})

        # Phase 71: Emit wave on significant instability spike
        delta = value - old_val
        if delta > 0.15:
            state.emit_field_wave(r.region_id, delta)


def adjust_region_instability(state: "TopologyState", region_id: Any, delta: float) -> None:
    r = state.get_region(region_id)
    if r:
        set_region_instability(state, r.region_id, r.instability + delta)


def set_region_energy(state: "TopologyState", region_id: Any, value: float) -> None:
    r = state.get_region(region_id)
    if r:
        r.local_energy = max(0.0, min(10.0, value))
        state._record("set_region_energy", {"region_id": r.region_id, "value": value})


def adjust_region_energy(state: "TopologyState", region_id: Any, delta: float) -> None:
    r = state.get_region(region_id)
    if r:
        set_region_energy(state, r.region_id, r.local_energy + delta)


def set_region_integrity(state: "TopologyState", region_id: Any, value: float) -> None:
    r = state.get_region(region_id)
    if r:
        r.integrity = max(0.1, min(1.0, value))
        state._record("set_region_integrity", {"region_id": r.region_id, "value": value})


def set_region_recurrence(state: "TopologyState", region_id: Any, value: float) -> None:
    r = state.get_region(region_id)
    if r:
        r.recurrence_score = max(0.0, min(1.0, value))
        state._record("set_region_recurrence", {"region_id": r.region_id, "value": value})


def adjust_region_recurrence(state: "TopologyState", region_id: str, delta: float) -> None:
    r = state.get_region(region_id)
    if r:
        set_region_recurrence(state, region_id, r.recurrence_score + delta)


def set_region_momentum(state: "TopologyState", region_id: str, value: float) -> None:
    r = state.get_region(region_id)
    if r:
        r.stability_momentum = max(0.0, min(1.0, value))
        state._record("set_region_momentum", {"region_id": r.region_id, "value": value})


def set_region_persistence(state: "TopologyState", region_id: str, value: float) -> None:
    r = state.get_region(region_id)
    if r:
        r.persistence = max(0.0, min(2.0, value))
        state._record("set_region_persistence", {"region_id": r.region_id, "value": value})


def set_region_pressure(state: "TopologyState", region_id: str, value: float) -> None:
    r = state.get_region(region_id)
    if r:
        r.semantic_pressure = value
        state._record("set_region_pressure", {"region_id": r.region_id, "value": value})


def set_region_temperature(state: "TopologyState", region_id: str, value: float) -> None:
    r = state.get_region(region_id)
    if r:
        r.local_temperature = max(0.0, min(1.0, value))
        state._record("set_region_temperature", {"region_id": r.region_id, "value": value})


def set_region_convergence(state: "TopologyState", region_id: str, value: float) -> None:
    r = state.get_region(region_id)
    if r:
        r.local_convergence = max(0.0, min(1.0, value))
        state._record("set_region_convergence", {"region_id": r.region_id, "value": value})


def update_region_after_recurrence(state: "TopologyState", region_id: str, field_pressure: float) -> None:
    r = state.get_region(region_id)
    if not r:
        return
    target_instability = min(1.0, r.instability + 0.15)
    r.stability_momentum = r.stability_momentum * 0.7 + 0.3 * target_instability
    r.instability = r.stability_momentum
    r.recurrence_score = min(1.0, r.recurrence_score + 0.1)
    r.semantic_pressure = field_pressure
    r.persistence = max(0.5, r.persistence - 0.1)


def update_local_memory_from_instability(state: "TopologyState") -> None:
    for r in state._get_regions():
        for role in r.competing_roles:
            r.local_memory[str(role)] = r.instability
