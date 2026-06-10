"""Topology Forces — edge field force calculations and redirection.

Extracted from topology_state.py for modularity.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.topology_state import TopologyState


def compute_edge_field_forces(state: "TopologyState") -> dict[tuple[str, str], dict[str, Any]]:
    """Compute force vectors from the unified edge field for each role pair."""
    view = state.get_view()
    forces: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in view.get_edge_fields():
        pair = (edge.source, edge.target) if edge.source < edge.target else (edge.target, edge.source)
        forces[pair] = {
            "affinity": edge.affinity,
            "repulsion": edge.repulsion,
            "pressure": edge.pressure,
            "route_strength": edge.route_strength,
            "semantics": edge.semantics,
        }
    return forces


def redirect_repulsive_pressure(
    state: "TopologyState",
    source_region: Any,
    pressure_amount: float,
    forces: dict[tuple[str, str], dict[str, Any]],
) -> None:
    """Redirect repulsive pressure through alternative high-affinity edge field routes."""
    # 1. Find high-affinity routes from the source region's roles
    route_targets: dict[str, float] = {}  # target_role -> weight
    for role in source_region.competing_roles:
        for pair, force in forces.items():
            if role not in pair:
                continue
            peer = pair[0] if pair[1] == role else pair[1]
            if peer in source_region.competing_roles:
                continue
            # High-affinity edges with decent route_strength are good targets
            if force["affinity"] > 0.3 and force["route_strength"] > 0.2:
                weight = force["affinity"] * force["route_strength"]
                if peer not in route_targets or weight > route_targets[peer]:
                    route_targets[peer] = weight

    if not route_targets:
        # No alternative routes: dissipate trapped pressure as heat
        source_region.local_temperature = min(1.0, source_region.local_temperature + pressure_amount * 0.1)
        state.record(
            "redirect_repulsive_pressure_dissipate",
            {
                "region_id": source_region.region_id,
                "pressure_amount": round(pressure_amount, 4),
            },
        )
        return

    # 2. Normalize weights and redirect pressure
    total_weight = sum(route_targets.values())
    regs = state.get_regions()
    redirected = 0.0
    affected_targets = []

    for target_role, weight in route_targets.items():
        redirect_amount = (weight / total_weight) * pressure_amount * 0.5
        # Find target regions containing this role
        for target_r in regs:
            if target_role in target_r.competing_roles and target_r.region_id != source_region.region_id:
                # Apply edge-field-modulated pressure to target region state
                target_r.instability = min(1.0, target_r.instability + redirect_amount * 0.05)
                target_r.semantic_pressure = max(0.0, target_r.semantic_pressure + redirect_amount * 0.03)
                redirected += redirect_amount
                affected_targets.append(target_r.region_id)
                # Record each target mutation for MVCC tracking
                state.record(
                    "redirect_pressure_to_target",
                    {
                        "region_id": target_r.region_id,
                        "source": source_region.region_id,
                        "target_role": target_role,
                        "redirect_amount": round(redirect_amount, 4),
                        "new_instability": round(target_r.instability, 4),
                        "new_pressure": round(target_r.semantic_pressure, 4),
                    },
                )
                break

    # 3. Any unredirected pressure heats the source (thermodynamic dissipation)
    remaining = pressure_amount - redirected
    if remaining > 0.01:
        source_region.local_temperature = min(1.0, source_region.local_temperature + remaining * 0.05)
        state.record(
            "redirect_repulsive_pressure_remainder",
            {
                "region_id": source_region.region_id,
                "remaining_heat": round(remaining, 4),
            },
        )


def route_contradiction(state: "TopologyState", role_a: str, role_b: str, strength: float = 0.1) -> dict[str, Any]:
    """Route a contradiction event through the unified edge field."""
    forces = state.compute_edge_field_forces()
    pair: tuple[str, str] = (role_a, role_b) if role_a <= role_b else (role_b, role_a)
    force = forces.get(pair, {})  # type: ignore[arg-type]

    if not force:
        # No edge field data for this pair: establish a basic repulsive topological law
        current = state._topological_laws.get(pair, 0.0)
        state.set_topological_law(pair, min(current - strength * 0.3, -0.01))
        return {"redirected": 0.0, "excluded": strength, "through_edge_field": False}

    is_repulsive = force.get("semantics") == "repulsive" or force.get("repulsion", 0) > 0.3

    if is_repulsive:
        # Repulsive edge: redirect pressure via the topology
        for r in state.get_regions():
            if role_a in r.competing_roles or role_b in r.competing_roles:
                state.redirect_repulsive_pressure(r, strength * 0.5, forces)

        # Strengthen the repulsive topological law
        current_law = state._topological_laws.get(pair, 0.0)
        state.set_topological_law(pair, min(current_law - strength * 0.1, -0.01))

        return {
            "redirected": round(strength * 0.5, 4),
            "excluded": round(strength * 0.1, 4),
            "through_edge_field": True,
        }
    # Non-repulsive pair contradicting: establish / strengthen a repulsive law
    current_law = state._topological_laws.get(pair, 0.0)
    state.set_topological_law(pair, min(current_law - strength * 0.2, -0.01))

    return {
        "redirected": 0.0,
        "excluded": round(strength * 0.8, 4),
        "through_edge_field": True,
    }
