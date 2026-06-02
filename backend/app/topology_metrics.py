"""Topology metrics — pure computation functions extracted from TopologyState.

These functions operate on a TopologyState instance and return computed
metrics. They do not mutate state directly — mutation is done by the
caller through TopologyState APIs.

Extracted from topology_state.py for modularity (see REFACTOR_PLAN.md).
"""

from typing import Dict, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from app.topology_state import TopologyState


def compute_aggregate_metrics(state: "TopologyState") -> Tuple[Dict, Dict, Dict]:
    """Aggregate region metrics into summary dicts."""
    regs = state._get_regions()
    if not regs:
        return {}, {}, {}
    n = len(regs)
    avg_convergence = sum(r.local_convergence for r in regs) / n
    avg_temp = sum(r.local_temperature for r in regs) / n
    avg_energy = sum(r.local_energy for r in regs) / n
    return {"convergence": avg_convergence, "temperature": avg_temp, "energy": avg_energy, "count": n}


def compute_topology_entropy(state: "TopologyState") -> float:
    """Compute global topology entropy as mean region instability."""
    regs = state._get_regions()
    if not regs:
        return 0.0
    return sum(r.instability for r in regs) / len(regs)


def compute_macro_energy(state: "TopologyState", convergence: float) -> float:
    """Compute target macro energy from region averages and attractor strength."""
    regs = state._get_regions()
    if not regs:
        return 5.0
    avg_energy = sum(r.local_energy for r in regs) / len(regs)
    attractor_strength = 1.0 / (1.0 + 2.718 ** (-15 * (convergence - 0.6)))
    attractor_pull = min(attractor_strength * convergence * 2.0, 2.0)
    target_energy = max(0.0, avg_energy - attractor_pull)
    return target_energy


def distill_crystalline_atoms(
    state: "TopologyState",
    integrity_threshold: float = 0.9,
    instability_threshold: float = 0.1,
) -> int:
    """Move extremely stable regions into the permanent atom store (Phase 34).

    Returns the number of newly distilled atoms.
    """
    import time

    regs = state._get_regions()
    atoms = state._get_struct("crystalline_atoms")

    remaining = []
    new_atoms_count = 0

    for r in regs:
        if r.integrity >= integrity_threshold and r.instability <= instability_threshold:
            atom = {
                "token": r.token,
                "roles": list(r.competing_roles),
                "domain": r.domain,
                "timestamp": time.time(),
            }
            atoms.append(atom)
            new_atoms_count += 1
        else:
            remaining.append(r)

    if new_atoms_count > 0:
        state._set_regions(remaining)
        state._set_struct("crystalline_atoms", atoms)
        state._record("distill_crystalline_atoms", {"count": new_atoms_count})

    return new_atoms_count
