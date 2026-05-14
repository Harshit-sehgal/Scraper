"""
Graph Update Scheduler
========================
Coordinates background graph relaxation and stabilization passes.
"""

from app.semantic_events import SemanticEvent, SemanticEventType
from app.event_dispatcher import get_dispatcher
from app.semantic_world_state import get_world_state

class GraphUpdateScheduler:
    """
    Schedules topological updates based on incoming semantic events.
    Prevents update storms by batching and prioritizing convergence.
    """
    def _setup_subscriptions(self):
        """Subscribe to events that require graph recalculation."""
        self.dispatcher.subscribe(SemanticEventType.CONTRADICTION_DETECTED, self.on_instability)
        self.dispatcher.subscribe(SemanticEventType.UNCERTAINTY_SPIKE, self.on_instability)
        self.dispatcher.subscribe(SemanticEventType.TOPOLOGY_SHIFT, self.on_instability)

    def on_instability(self, event: SemanticEvent):
        """React to destabilizing signals — record to history + relax topology."""
        ws = get_world_state()
        ws.decision_history.append({
            "type": event.event_type.value,
            "source": event.source,
            "delta": event.instability_delta,
            "timestamp": event.timestamp or 0,
        })
        # Keep history bounded
        if len(ws.decision_history) > 1000:
            ws.decision_history = ws.decision_history[-500:]
        self.run_relaxation_pass()

    def __init__(self):
        self.pending_updates = 0
        self._wave_count = 0
        self.dispatcher = get_dispatcher()
        self._setup_subscriptions()

    def run_relaxation_pass(self):
        """Perform a graph relaxation pass to restore equilibrium.

        Implements PROPAGATION WAVES: if pressure doesn't drop enough,
        a secondary event fires to trigger another relaxation iteration.
        This creates cascading topology activation until equilibrium.
        """
        from app.semantic_inference_engine import InferenceEngine
        from app.semantic_ir import SemanticToken, Span, SemanticType
        
        # Limit propagation waves to prevent infinite cascading
        if self._wave_count >= 3:
            self._wave_count = 0
            return
        self._wave_count += 1
        
        ie = InferenceEngine(max_iterations=5)
        ws = get_world_state()
        pressure_before = ws.metrics.field_pressure
        
        virtual_tokens = []
        for (role, ttype), compat in list(ws.role_compatibility.items()):
            if compat > 0.0:
                stype = SemanticType(ttype) if isinstance(ttype, str) else ttype
                virtual_tokens.append(SemanticToken(
                    raw=role, normalized=role, span=Span(0,0), position=0,
                    primary_type=stype,
                    type_distribution={stype: compat}
                ))
        
        if virtual_tokens:
            result = ie.infer(virtual_tokens, list(ws.role_position_memory.keys()))
            if ws.field_regions:
                ws.field_regions[-1].local_energy = result.energy
            if result.belief_field:
                ws.metrics.average_entropy = result.belief_field.field_entropy
            
            # Continuous basin evolution — not pipeline-phase-driven
            ws.decay_field_regions()
            ws.aggregate_from_regions()
            ws.redistribute_instability()

            pressure_after = ws.metrics.field_pressure
            drop = pressure_before - pressure_after
            ws.snapshot(label=f"relax_wave_{self._wave_count}")
            
            self.dispatcher.dispatch(SemanticEvent(
                event_type=SemanticEventType.EQUILIBRIUM_REACHED,
                source="graph_update_scheduler",
                payload={"energy": result.energy, "wave": self._wave_count, "pressure_drop": drop},
                instability_delta=-0.1
            ))
            
            # Propagation wave: if pressure didn't drop enough AND field isn't converged, cascade
            convergence = ws.metrics.convergence_score
            if drop < 0.02 and pressure_before > 0.3 and self._wave_count < 3 and convergence < 0.8:
                self.dispatcher.dispatch(SemanticEvent(
                    event_type=SemanticEventType.TOPOLOGY_SHIFT,
                    source=f"propagation_wave_{self._wave_count}",
                    payload={"wave": self._wave_count, "pressure": pressure_after},
                    instability_delta=0.05
                ))

# Global Scheduler (lazy — created on first access to avoid circular imports)
_scheduler = None

def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = object()  # placeholder to prevent re-entrant creation
        _scheduler = GraphUpdateScheduler()
    return _scheduler
