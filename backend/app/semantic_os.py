"""
Semantic OS — Official Engine Interface
======================================
The production-hardened API for interacting with the Semantic Field Dynamics.
Provides high-level orchestration, state governance, and topological search.
"""

import logging
from typing import Callable, List, Dict, Optional
from app.semantic_world_state import get_world_state
from app.checkpoint_manager import get_checkpoint_manager
class SemanticOS:
    """The official gateway to the semantic cognitive substrate."""
    
    def __init__(self, ws=None):
        self.ws = ws or get_world_state()
        self.checkpoints = get_checkpoint_manager()

    def ingest_records(self, records: List[dict], schema: List[str]):
        """Standard entry point for new semantic data. Automatically handles schema expansion."""
        effective_schema = self.get_effective_schema(schema)
        from app.semantic_pipeline import run_pipeline
        return run_pipeline(records, effective_schema)

    def get_effective_schema(self, base_schema: List[str]) -> List[str]:
        """Combine the base schema with any field-evolved roles (Phase 29)."""
        evolved = self.ws.evolved_schema
        # Return merged set as a sorted list for predictability
        return sorted(list(set(base_schema) | set(evolved)))

    def evolve_field(self, cycles: int = 1):
        """Standard entry point for cognitive evolution."""
        return self.ws.dream(cycles=cycles)

    def query(self, tql_string: str) -> dict:
        """Execute a topological query."""
        return self.ws.execute_tql(tql_string)

    def save_snapshot(self, label: str = "manual") -> str:
        """Create a versioned persistent checkpoint."""
        return self.checkpoints.create_checkpoint(label=label)

    def restore_snapshot(self, filepath: str):
        """Restore engine state from a checkpoint."""
        self.checkpoints.load_checkpoint(filepath)

    def get_causality_trace(self, limit: int = 50) -> List[dict]:
        """Return recent transactional history."""
        return self.ws.trace_causality(limit=limit)

    def get_substrate_checksum(self) -> str:
        """Return a cryptographic checksum of the current manifold geometry (Phase 31)."""
        return self.ws.get_manifold_checksum()

    def reset_engine(self):
        """Clear the entire semantic world state."""
        self.ws.clear()

    # ─── Multi-Node Consensus (Phase 32) ─────────────────────────────────

    def sync_node(self, remote_state: dict, trace_id: Optional[str] = None):
        """Synchronize with another Semantic OS node."""
        self.ws.merge_state(remote_state, trace_id=trace_id)

    def get_substrate_clock(self) -> dict:
        """Return the current vector clock."""
        return self.ws.get_vector_clock()

    def register_with_network(self):
        """Register this OS node with the virtual gossip network."""
        from app.gossip_substrate import get_gossip_substrate
        get_gossip_substrate().register_node(self.ws.node_id, self.ws)

    def perform_gossip(self):
        """Perform a gossip cycle with a random peer and send heartbeat."""
        from app.gossip_substrate import get_gossip_substrate
        from app.heartbeat_manager import get_heartbeat_manager
        
        get_gossip_substrate().gossip(self.ws.node_id)
        
        # Send heartbeat to the substrate
        get_heartbeat_manager().record_heartbeat(
            node_id=self.ws.node_id,
            clock=self.ws.get_vector_clock(),
            checksum=self.ws.get_manifold_checksum(),
            energy=self.ws.metrics.global_energy
        )

    def get_network_health(self) -> dict:
        """Return the global health of the distributed network (Phase 33)."""
        from app.heartbeat_manager import get_heartbeat_manager
        return get_heartbeat_manager().get_global_health()

    # ─── Knowledge Federation (Phase 29) ─────────────────────────────────

    def share_knowledge(self) -> dict:
        """Export learned role meanings for other instances."""
        return self.ws.export_manifold()

    def absorb_knowledge(self, federation_data: dict):
        """Import role meanings from another instance."""
        self.ws.import_federated_manifold(federation_data)

    # ─── Semantic Steering (Phase 36) ────────────────────────────────────

    def set_cognitive_intent(self, intent_id: str, target_vec: List[float], 
                             strength: float = 0.5, target_roles: Optional[List[str]] = None):
        """Inject a high-level goal to bias the semantic field (Phase 36)."""
        with self.ws.transaction(f"set_intent:{intent_id}"):
            self.ws.set_intent(intent_id, target_vec, strength, target_roles)

    def remove_cognitive_intent(self, intent_id: str):
        """Remove a specific cognitive goal."""
        with self.ws.transaction(f"remove_intent:{intent_id}"):
            self.ws.remove_intent(intent_id)

    def clear_all_intents(self):
        """Clear all active cognitive steering."""
        with self.ws.transaction("clear_intents"):
            self.ws.clear_intents()

    # ─── Cognitive Agency (Phase 37) ─────────────────────────────────────

    def register_action(self, action_id: str, target_vec: List[float], 
                        handler_name: str, threshold: float = 0.3):
        """Map executable logic into the semantic field (Phase 37)."""
        with self.ws.transaction(f"register_action:{action_id}"):
            self.ws.register_action(action_id, target_vec, handler_name, threshold)

    def trigger_actions(self) -> int:
        """Manually trigger autonomous dispatchers."""
        return self.ws.dispatch_actions()

    def report_outcome(self, action_id: str, success: bool, details: Optional[dict] = None):
        """Feed action outcomes back into the manifold (Feedback Loop)."""
        with self.ws.transaction(f"action_outcome:{action_id}"):
            self.ws.log_action_execution(action_id, success, details)
            if success and details and "role" in details:
                role = details["role"]
                action = self.ws.get_action(action_id)
                if action:
                    target_vec = action["target_vec"]
                    # Reward successful interpretation by pulling role toward action anchor
                    self.ws.blend_manifold_vector(role, target_vec, alpha=0.9, beta=0.1)
                    logging.getLogger(__name__).info(
                        f"FEEDBACK REINFORCED: Role [{role}] rewarded by Action [{action_id}]"
                    )

    # ─── Hierarchical Synthesis (Phase 38) ───────────────────────────────

    def perform_hierarchical_synthesis(self):
        """Manually trigger distillation of higher-order role envelopes."""
        self.ws.synthesize_hierarchical_envelopes()

    def get_role_abstraction_level(self, role: str) -> int:
        """Query the hierarchy level of a semantic role (0=base, 1=envelope)."""
        return self.ws.get_role_level(role)

    # ─── Substrate Branching (Phase 39) ──────────────────────────────────

    def branch_substrate(self, label: str) -> "SemanticOS":
        """Spawn an isolated experiment branch of the OS."""
        child_ws = self.ws.branch(label)
        return SemanticOS(ws=child_ws)

    def merge_substrate(self, branch_os: "SemanticOS", alpha: float = 0.5):
        """Merge an experimental branch back into the main OS consensus."""
        self.ws.merge_branch(branch_os.ws, alpha=alpha)

    def diff_substrate(self, other_os: "SemanticOS") -> dict:
        """Quantify divergence between this OS and another."""
        return self.ws.semantic_diff(other_os.ws)

    # ─── Cognitive Scheduling (Phase 40) ─────────────────────────────────

    def schedule_task(self, task_id: str, priority_level: str, handler: Callable, *args, **kwargs):
        """Register an autonomous cognitive task (Phase 40)."""
        from app.graph_update_scheduler import TaskPriority
        p_map = {
            "critical": TaskPriority.CRITICAL,
            "urgent": TaskPriority.URGENT,
            "normal": TaskPriority.NORMAL,
            "background": TaskPriority.BACKGROUND
        }
        priority = p_map.get(priority_level.lower(), TaskPriority.NORMAL)
        self.ws.schedule_cognitive_task(task_id, priority, handler, *args, **kwargs)

    def process_queue(self, budget_ms: float = 100.0) -> int:
        """Execute scheduled tasks within the time budget."""
        return self.ws.process_cognitive_queue(budget_ms=budget_ms)

    # ─── Cognitive Observability (Phase 41) ──────────────────────────────

    def get_telemetry(self) -> List[dict]:
        """Query the recent stream of cognitive events."""
        return self.ws.observability_telemetry

    def get_activity_heatmap(self) -> Dict[str, float]:
        """Query the regional activity heatmap scores."""
        return self.ws.observability_heatmap

    def get_manifold_drift_log(self, role: str) -> List[float]:
        """Query historical manifold drift for a specific role."""
        return self.ws.get_role_drift(role)

    def log_manual_telemetry(self, event_type: str, details: dict):
        """Inject a manual telemetry event into the stream."""
        with self.ws.transaction("manual_telemetry"):
            self.ws.emit_telemetry(event_type, details)

    def record_degradation(self, subsystem: str, severity: str, cause: str,
                           topology_state: Optional[str] = None,
                           semantic_entropy: Optional[float] = None):
        """Record a structured degradation event with causality tracking."""
        self.ws.record_degradation(
            subsystem=subsystem,
            severity=severity,
            cause=cause,
            topology_state=topology_state,
            semantic_entropy=semantic_entropy,
        )

_os_instance: Optional[SemanticOS] = None

def get_semantic_os() -> SemanticOS:
    global _os_instance
    if _os_instance is None:
        _os_instance = SemanticOS()
    return _os_instance

def reset_semantic_os():
    """Reset the global Semantic OS instance (for testing)."""
    global _os_instance
    _os_instance = None
