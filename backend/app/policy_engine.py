"""Substrate Policy Engine — governs autonomous field actions.

LAW 12: Cognitive Agency must be bounded by substrate safety policies.
No action may be triggered if it violates system thermodynamic stability.
"""

from typing import Optional
from app.semantic_world_state import get_world_state

class SubstratePolicy:
    """Governs when and how autonomous actions can be executed."""

    def __init__(self, ws=None):
        self.ws = ws or get_world_state()

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

_engine: Optional[SubstratePolicy] = None

def get_policy_engine(ws=None) -> SubstratePolicy:
    global _engine
    if _engine is None:
        _engine = SubstratePolicy(ws=ws)
    return _engine
