"""Substrate Policy Engine — governs autonomous field actions.

LAW 12: Cognitive Agency must be bounded by substrate safety policies.
No action may be triggered if it violates system thermodynamic stability.
"""

from weakref import WeakKeyDictionary
from app.semantic_world_state import get_world_state

class SubstratePolicy:
    """Governs when and how autonomous actions and structural changes occur."""

    def __init__(self, ws=None):
        self.ws = ws or get_world_state()
        # Phase 68: Operational Guardrails
        self.max_community_density = 15 # Max roles per cluster
        self.critical_entropy_threshold = 0.8
        self.min_attractor_plasticity = 0.1

    def validate_substrate_health(self) -> dict:
        """Analyze current state against governance policies (Phase 68)."""
        ws = self.ws
        issues = []

        # 1. Density Quotas
        communities = ws.global_communities
        for i, c in enumerate(communities):
            if len(c) > self.max_community_density:
                issues.append({
                    "policy": "community_density",
                    "id": f"C-{i}",
                    "severity": "moderate",
                    "details": f"Density {len(c)} exceeds quota {self.max_community_density}"
                })

        # 2. Thermodynamic Guardrails
        pressure = ws.get_system_pressure()
        if pressure > self.critical_entropy_threshold:
            issues.append({
                "policy": "thermodynamic_guardrail",
                "severity": "critical",
                "details": f"Field pressure {pressure:.3f} exceeds stability threshold"
            })

        # 3. Attractor Plasticity
        health = ws._observability.get_semantic_health_index(ws)
        diversity = health["metrics"]["diversity"]
        if diversity < self.min_attractor_plasticity:
            issues.append({
                "policy": "plasticity_law",
                "severity": "high",
                "details": f"Attractor diversity {diversity:.3f} below plasticity floor"
            })

        return {
            "valid": len([i for i in issues if i["severity"] == "critical"]) == 0,
            "issues": issues
        }

    def enforce_guardrails(self):
        """Automatically trigger stabilization if guardrails are violated (Phase 68)."""
        health = self.validate_substrate_health()
        if not health["valid"]:
            # Trigger emergency stabilization
            self.ws.apply_memory_decay(rate=0.5)
            # Phase 68: Refresh metrics immediately to reflect stabilization
            self.ws._energy.update_from_regions(self.ws._topology._regions)

            self.ws.emit_telemetry("governance_enforcement", {
                "action": "emergency_stabilization",
                "reason": "critical_thermodynamic_violation"
            })

    def can_dispatch_action(self, action_id: str, pressure: float) -> bool:
        """Check if an action is allowed under current field pressure."""
        # ─── Self-Optimization Override (Phase 44) ───
        # Native tools that reduce entropy are allowed up to higher pressure
        if action_id in ["role_merger", "manifold_compressor"]:
            if pressure < 1.8:
                return True

        # Policy 1: Thermodynamics
        # If pressure is extremely high (> 1.5), restrict non-critical actions
        if pressure > 1.5:
            return False

        # Policy 2: Convergence
        # Critical actions require minimum system certainty
        from app.semantic_inference_engine import RoleEmbeddingEngine
        certainty = RoleEmbeddingEngine().get_certainty()
        if certainty < 0.1:
            return False

        return True

def get_policy_engine(ws=None) -> SubstratePolicy:
    target_ws = ws or get_world_state()
    if not hasattr(get_policy_engine, "_instances"):
        get_policy_engine._instances = WeakKeyDictionary()
    instances = get_policy_engine._instances
    if target_ws not in instances:
        instances[target_ws] = SubstratePolicy(ws=target_ws)
    return instances[target_ws]
