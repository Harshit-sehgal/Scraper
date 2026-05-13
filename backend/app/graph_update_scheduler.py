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
    def __init__(self):
        self.pending_updates = 0
        self.dispatcher = get_dispatcher()
        self._setup_subscriptions()

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

    def run_relaxation_pass(self):
        """Perform a graph relaxation pass to restore equilibrium."""
        from app.semantic_inference_engine import InferenceEngine
        from app.semantic_ir import SemanticToken, Span, SemanticType
        
        # In a global world state context, we relax the entire topology
        # using the InferenceEngine's energy minimization logic.
        ie = InferenceEngine(max_iterations=5)
        ws = get_world_state()
        
        # Convert world state role compatibilities into a virtual token sequence 
        # for the engine to relax. 
        # (This is a minimal bridge to the iterative energy model)
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
            ie.infer(virtual_tokens, list(ws.role_position_memory.keys()))
            self.dispatcher.dispatch(SemanticEvent(
                event_type=SemanticEventType.EQUILIBRIUM_REACHED,
                source="graph_update_scheduler",
                payload={"energy": ws.metrics.global_energy},
                instability_delta=-0.1
            ))

# Global Scheduler
_scheduler = GraphUpdateScheduler()

def get_scheduler() -> GraphUpdateScheduler:
    return _scheduler
