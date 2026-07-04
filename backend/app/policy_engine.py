"""Substrate Policy Engine — governs automated field actions.

LAW 12: Cognitive Agency must be bounded by substrate safety policies.
No action may be triggered if it violates system thermodynamic stability.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any
from weakref import WeakKeyDictionary


def get_world_state() -> SemanticWorldState:
    import app.semantic_world_state

    return app.semantic_world_state.get_world_state()


if TYPE_CHECKING:
    from app.semantic_world_state import SemanticWorldState


class SubstratePolicy:
    """Governs when and how automated actions and structural changes occur."""

    def __init__(self, ws: SemanticWorldState | None = None) -> None:
        self.ws: SemanticWorldState = ws or get_world_state()
        # Phase 68: Operational Guardrails
        self.max_community_density = 15  # Max roles per cluster
        self.critical_entropy_threshold = 0.8
        self.min_attractor_plasticity = 0.1

    def validate_substrate_health(self) -> dict[str, Any]:
        """Analyze current state against governance policies (Phase 68)."""
        ws = self.ws
        issues = []

        # 1. Density Quotas
        communities = ws.global_communities
        for i, c in enumerate(communities):
            if len(c) > self.max_community_density:
                issues.append(
                    {
                        "policy": "community_density",
                        "id": f"C-{i}",
                        "severity": "moderate",
                        "details": f"Density {len(c)} exceeds quota {self.max_community_density}",
                    },
                )

        # 2. Thermodynamic Guardrails
        pressure = ws.get_system_pressure()
        if pressure > self.critical_entropy_threshold:
            issues.append(
                {
                    "policy": "thermodynamic_guardrail",
                    "severity": "critical",
                    "details": f"Field pressure {pressure:.3f} exceeds stability threshold",
                },
            )

        # 3. Attractor Plasticity — capture snapshot for governance reads
        snapshot = ws.capture_governance_snapshot()
        health = ws._observability.get_semantic_health_index(snapshot)
        diversity = health["metrics"]["diversity"]
        if diversity < self.min_attractor_plasticity:
            issues.append(
                {
                    "policy": "plasticity_law",
                    "severity": "high",
                    "details": f"Attractor diversity {diversity:.3f} below plasticity floor",
                },
            )

        return {"valid": len([i for i in issues if i["severity"] == "critical"]) == 0, "issues": issues}

    def enforce_guardrails(self) -> None:
        """Automatically trigger stabilization if guardrails are violated (Phase 68)."""
        health = self.validate_substrate_health()
        if not health["valid"]:
            # Trigger emergency stabilization
            self.ws.apply_memory_decay(rate=0.5)
            # Phase 68: Refresh metrics immediately to reflect stabilization
            self.ws._energy.update_from_regions(self.ws._topology._regions)

            self.ws.emit_telemetry(
                "governance_enforcement",
                {"action": "emergency_stabilization", "reason": "critical_thermodynamic_violation"},
            )

    def can_dispatch_action(self, action_id: str, pressure: float) -> bool:
        """Check if an action is allowed under current field pressure."""
        # ─── Self-Optimization Override (Phase 44) ───
        # Native tools that reduce entropy are allowed up to higher pressure
        if action_id in ["role_merger", "manifold_compressor"] and pressure < 1.8:
            return True

        # Policy 1: Thermodynamics
        # If pressure is extremely high (> 1.5), restrict non-critical actions
        if pressure > 1.5:
            return False

        # Policy 2: Convergence
        # Critical actions require minimum system certainty

        certainty = _get_role_embedding_engine().get_certainty()
        return not certainty < 0.1


_policy_instances: WeakKeyDictionary | None = None
_policy_instances_lock = threading.Lock()

# Module-level singleton for RoleEmbeddingEngine so we don't re-seed
# the baseline manifold on every can_dispatch_action() call.
_role_embedding_engine = None
_role_embedding_engine_lock = threading.Lock()


def _get_role_embedding_engine():
    """Return the module-level RoleEmbeddingEngine singleton."""
    global _role_embedding_engine
    if _role_embedding_engine is not None:
        return _role_embedding_engine
    with _role_embedding_engine_lock:
        if _role_embedding_engine is None:
            from app.semantic_inference_engine import RoleEmbeddingEngine

            _role_embedding_engine = RoleEmbeddingEngine()
    return _role_embedding_engine


def get_policy_engine(ws: SemanticWorldState | None = None) -> SubstratePolicy:
    target_ws = ws or get_world_state()
    global _policy_instances
    if _policy_instances is None:
        with _policy_instances_lock:
            if _policy_instances is None:
                _policy_instances = WeakKeyDictionary()
    # Hold the lock across the check+assign so concurrent callers sharing
    # the same ``target_ws`` cannot both pass the ``not in`` test and
    # create duplicate SubstratePolicy instances (WeakKeyDictionary
    # mutation is not thread-safe).
    with _policy_instances_lock:
        if target_ws not in _policy_instances:
            _policy_instances[target_ws] = SubstratePolicy(ws=target_ws)
        return _policy_instances[target_ws]  # type: ignore[no-any-return]
