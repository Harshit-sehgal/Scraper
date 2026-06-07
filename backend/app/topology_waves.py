"""Topology Waves — active field wave emission and absorption.

Extracted from topology_state.py for modularity.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.topology_state import TopologyState


def emit_field_wave(state: "TopologyState", source_region_id: str, intensity: float) -> None:  # noqa: ARG001, RUF100
    """Emit a semantic wave from a region into the field.

    Instead of a global scheduler calling propagate(), individual regions
    now emit "waves" that ripple through the topology.
    """
    if intensity < 0.01:
        return

    from app.event_dispatcher import get_dispatcher
    from app.semantic_events import SemanticEvent, SemanticEventType

    get_dispatcher().dispatch(
        SemanticEvent(
            event_type=SemanticEventType.FIELD_WAVE,
            source=f"region:{source_region_id}",
            payload={"intensity": intensity, "source_id": source_region_id},
            instability_delta=intensity * 0.1,
        ),
    )


def process_field_wave(state: "TopologyState", source_region_id: str, intensity: float) -> None:
    """Reactive handling of a field wave by neighboring regions."""
    source = state.get_region(source_region_id)
    if not source:
        return

    forces = state._compute_edge_field_forces()
    regs = state._get_regions()

    # 1. Propagate along edge field forces
    for target in regs:
        if target.region_id == source_region_id:
            continue

        # Find max route strength between any shared role pairs
        max_route = 0.0
        for ra in source.competing_roles:
            for rb in target.competing_roles:
                pair = (ra, rb) if ra < rb else (rb, ra)
                f = forces.get(pair)
                if f:
                    max_route = max(max_route, f["route_strength"])

        if max_route > 0.1:
            # Wave intensity decays as it spreads
            absorption = getattr(target, "persistence", 0.5) * 0.2
            received_intensity = intensity * max_route * (1.0 - absorption)

            if received_intensity > 0.01:
                # Update target region
                # Phase 71: Intensity now has a stronger impact to overcome
                # natural decay
                target.instability = min(1.0, target.instability + received_intensity * 0.3)
                target.semantic_pressure = max(0.0, target.semantic_pressure + received_intensity * 0.1)

                # High intensity waves trigger immediate evolution pass
                if received_intensity > 0.4:
                    target.evolve(force=True)

                state._record(
                    "wave_absorption",
                    {
                        "region_id": target.region_id,
                        "source_id": source_region_id,
                        "intensity": round(received_intensity, 4),
                    },
                )

                # Phase 71: Causal telemetry for field waves
                from app.semantic_world_state import get_world_state

                ws = get_world_state()
                ws.emit_telemetry(
                    "wave_absorption",
                    {
                        "region_id": target.region_id,
                        "source_id": source_region_id,
                        "intensity": round(received_intensity, 4),
                    },
                )

                # Causal chaining: target may emit its own (weaker) wave
                # (modulated to prevent infinite feedback loops)
                if received_intensity > 0.2:
                    # Schedule next wave hop via dispatcher to avoid deep
                    # recursion
                    from app.graph_update_scheduler import TaskPriority, get_scheduler

                    scheduler = get_scheduler()
                    if scheduler is not None:
                        scheduler.schedule(
                            f"wave_hop:{target.region_id}",
                            TaskPriority.NORMAL,
                            state.emit_field_wave,
                            target.region_id,
                            received_intensity * 0.5,
                        )
