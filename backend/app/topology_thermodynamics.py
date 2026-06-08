"""Topology Thermodynamics — thermodynamic evolution and free energy flow dynamics.

Extracted from topology_state.py for modularity.
"""

from typing import TYPE_CHECKING

from app.core_types import MAX_COUPLING_TRANSFER
from app.field_laws import COUPLING_COEFFICIENT, FREE_ENERGY_CLAMP

if TYPE_CHECKING:
    from app.topology_state import TopologyState


def evolve_all(state: "TopologyState", force: bool = False) -> list:
    """Evolve all basins modulated by edge field forces and multi-scale feedback."""
    forces = state._compute_edge_field_forces()

    # 1. Compute meso clusters and macro continents BEFORE evolving
    state.compute_meso_clusters()
    state.compute_macro_continents()

    survivors = []
    all_effects = []
    for r in state._get_regions():
        # Compute edge field force on this region
        region_pressure = 0.0
        region_affinity = 0.0
        roles = r.competing_roles
        for i in range(len(roles)):
            for j in range(i + 1, len(roles)):
                pair = (roles[i], roles[j]) if roles[i] < roles[j] else (roles[j], roles[i])
                f = forces.get(pair)
                if f:
                    region_pressure = max(region_pressure, f["pressure"])
                    region_affinity = max(region_affinity, f["affinity"])

        # Edge field modulates evolution
        local_force = force or region_pressure > 0.3
        if region_pressure > 0.3:
            r.semantic_pressure = region_pressure

        effects = r.evolve(force=local_force)
        all_effects.extend(effects)

        # Survival: high affinity keeps regions alive even at low instability
        if r.instability > 0.001 or r.idle_cycles < 20 or region_affinity > 0.4:
            survivors.append(r)

    state._set_regions(survivors)

    # 2. Apply full cross-scale pressure flow
    state.cross_scale_pressure_flow()

    return all_effects


def propagate_all(state: "TopologyState") -> list:
    """Propagate instability through the unified edge field."""
    forces = state._compute_edge_field_forces()
    all_effects = []
    for r in state._get_regions():
        effects = []
        repulsive_pressure = 0.0

        for role in r.competing_roles:
            # Find all edges from this role in the edge field
            for pair, force in forces.items():
                if role not in pair:
                    continue
                peer = pair[0] if pair[1] == role else pair[1]
                if peer in r.competing_roles:
                    continue  # Don't propagate within the same region

                # Edge-field-modulated propagation
                spread_potential = r.instability * force["pressure"]

                if force["semantics"] == "repulsive":
                    # ─── Repulsive Edge: Redirect Through Edge Field ───
                    repulsive_pressure += spread_potential * MAX_COUPLING_TRANSFER
                    # Still emit a minimal exclusion signal for learning continuity
                    spread = spread_potential * MAX_COUPLING_TRANSFER * 0.1
                    if spread > 0.001:
                        effects.append((pair, spread))
                elif force["semantics"] == "attractive":
                    # Attractive edges propagate but dampened by containment
                    spread = spread_potential * MAX_COUPLING_TRANSFER * 0.3
                    if spread > 0.001:
                        effects.append((pair, spread))
                        # Also propagate instability directly through attractive edges
                        for target_r in state._get_regions():
                            if peer in target_r.competing_roles and target_r.region_id != r.region_id:
                                target_r.instability = min(1.0, target_r.instability + spread * 0.005)
                                break
                else:
                    spread = spread_potential * MAX_COUPLING_TRANSFER * 0.5
                    if spread > 0.001:
                        effects.append((pair, spread))

        # Redirect accumulated repulsive pressure through edge field routes
        if repulsive_pressure > 0.01:
            state._redirect_repulsive_pressure(r, repulsive_pressure, forces)
            state._record(
                "redirect_repulsive_pressure",
                {
                    "region_id": r.region_id,
                    "pressure_redirected": round(repulsive_pressure, 4),
                },
            )

        if not effects:
            # Fallback: use legacy propagation when no edge field exists
            effects = r.propagate()
        all_effects.extend(effects)
    return all_effects


def redistribute_instability(state: "TopologyState", damping: float = 1.0) -> dict:
    """Redistribute instability across regions using thermodynamic free energy gradients."""
    regs = state._get_regions()
    if len(regs) < 2:
        return {"total_flow": 0.0, "source_flow": 0.0, "sink_flow": 0.0, "pairs_coupled": 0}

    forces = state._compute_edge_field_forces()

    # Compute free energy for each region
    free_energies = {}
    for r in regs:
        fe = r.local_energy - r.local_temperature * r.instability
        free_energies[r.region_id] = fe

    # 1. Compute flows using thermodynamic free energy gradient
    deltas = {r.region_id: 0.0 for r in regs}
    source_flow = 0.0  # Flow OUT of source regions
    sink_flow = 0.0  # Flow INTO sink regions
    pairs_coupled = 0

    for i in range(len(regs)):
        for j in range(i + 1, len(regs)):
            ri = regs[i]
            rj = regs[j]

            # Compute edge field conductance between these regions
            edge_conductance = 0.0
            for ra in ri.competing_roles:
                for rb in rj.competing_roles:
                    pair = (ra, rb) if ra < rb else (rb, ra)
                    force = forces.get(pair)
                    if force:
                        # Edge conductance = route_strength (how well signals flow)
                        edge_conductance = max(edge_conductance, force["route_strength"])

            if edge_conductance < 0.01:
                continue  # No field connection: no thermodynamic coupling

            pairs_coupled += 1

            # Thermodynamic free energy gradient
            fe_ri = free_energies[ri.region_id]
            fe_rj = free_energies[rj.region_id]
            fe_gradient = fe_ri - fe_rj

            # Clamp gradient to prevent extreme oscillations
            fe_gradient = max(-FREE_ENERGY_CLAMP, min(FREE_ENERGY_CLAMP, fe_gradient))

            # Flow = conductance * gradient * damping * COUPLING_COEFFICIENT  # noqa: ERA001, RUF100
            flow = edge_conductance * fe_gradient * damping * COUPLING_COEFFICIENT
            flow = max(-0.1, min(0.1, flow))

            deltas[ri.region_id] -= flow
            deltas[rj.region_id] += flow

            if flow > 0:
                source_flow += flow
                sink_flow += flow
            else:
                source_flow += abs(flow)
                sink_flow += abs(flow)

    # 2. Apply deltas
    for rid, delta in deltas.items():
        if abs(delta) > 1e-6:
            region_to_update = state.get_region(rid)
            if region_to_update is not None:
                state.set_region_instability(rid, region_to_update.instability + delta)

    total_flow = round(sum(abs(d) for d in deltas.values()), 4)
    state._record(
        "redistribute_instability",
        {
            "count": len(regs),
            "total_flow": total_flow,
            "pairs_coupled": pairs_coupled,
        },
    )

    return {
        "total_flow": total_flow,
        "source_flow": round(source_flow, 4),
        "sink_flow": round(sink_flow, 4),
        "pairs_coupled": pairs_coupled,
    }
