"""
Semantic Diagnostics Engine (Topological Introspection)
=========================================================
Implements topology replay, graph evolution tracing, and instability zone localization.

Exposes the internal pressure fields and convergence measures of the 
semantic world state.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.semantic_world_state import get_world_state
from app.semantic_ir import SemanticToken, SemanticType


@dataclass
class InstabilityZone:
    zone_type: str
    strength: float
    localization: str
    description: str


class TopologicalDiagnostics:
    """
    Introspects the evolving semantic state and uncertainty propagation.
    Provides zones of instability and graph pressure fields.
    """
    def __init__(self):
        self.state = get_world_state()

    def generate_uncertainty_heatmap(self, tokens: List[SemanticToken]) -> Dict[str, float]:
        """Map uncertainty across specific tokens in a record."""
        heatmap = {}
        for i, token in enumerate(tokens):
            # Entropy calculation for local uncertainty
            dist = token.type_distribution or {token.primary_type: 1.0}
            entropy = sum(-v * math.log2(v) for v in dist.values() if v > 0)
            # Normalize to 0-1
            heatmap[token.raw] = min(entropy / 2.0, 1.0)
        return heatmap

    def trace_uncertainty_propagation(self) -> List[InstabilityZone]:
        """Localize high-entropy zones in the global semantic topology."""
        zones = []
        
        # 1. Role Ambiguity Zones
        for (role, ttype), compat in self.state.role_compatibility.items():
            # Entropy of the compatibility distribution
            # If compat is near 0.5, entropy is high (uncertainty)
            entropy = -compat * math.log2(compat) if 0 < compat < 1 else 0
            if entropy > 0.8:
                zones.append(InstabilityZone(
                    zone_type="ambiguity_node",
                    strength=entropy,
                    localization=f"{role}:{ttype}",
                    description=f"High semantic entropy in role-type mapping ({compat:.2f})"
                ))

        # 2. Transition Instability
        for (t1, t2), prob in self.state.transition_probs.items():
            if 0.4 < prob < 0.6:
                zones.append(InstabilityZone(
                    zone_type="unstable_edge",
                    strength=0.5,
                    localization=f"{t1}->{t2}",
                    description=f"Transition boundary is at probabilistic equilibrium ({prob:.2f})"
                ))

        return sorted(zones, key=lambda z: z.strength, reverse=True)

    def generate_pressure_field_summary(self) -> Dict[str, float]:
        """Quantify topological pressure across the global state."""
        return {
            "global_uncertainty": self.state.metrics.average_uncertainty,
            "motif_entropy": len(self.state.motif_counts) / max(1, self.state.metrics.total_records_processed),
            "convergence_pressure": 1.0 - self.state.metrics.average_density,
            "global_energy": self.state.metrics.global_energy,
            "global_entropy": self.state.metrics.global_entropy
        }


def generate_allocation_diagnostics(
    output: Dict[str, Any],
    schema_fields: List[str],
    reng,
    contradictions: List[str],
    detect_type_fn,
    tokens: List[SemanticToken] = None
) -> Dict[str, Any]:
    """Modern diagnostic orchestrator. Returns structured topological introspection data."""
    td = TopologicalDiagnostics()
    instability_zones = td.trace_uncertainty_propagation()
    pressure_field = td.generate_pressure_field_summary()
    
    heatmap = {}
    if tokens:
        heatmap = td.generate_uncertainty_heatmap(tokens)

    # Narrative reasoning (legacy bridge)
    narrative = []
    ws = get_world_state()
    for role_name in schema_fields:
        val = output.get(role_name)
        if val:
            val_type, _ = detect_type_fn(val, role_name)
            v_type_str = val_type.value if hasattr(val_type, 'value') else str(val_type)
            key = (role_name, v_type_str)
            compat = ws.role_compatibility.get(key, 0.5)
            if compat > 0.7:
                narrative.append(f"STABLE: {role_name}='{val}' (compat {compat:.2f})")
            elif compat < 0.4:
                narrative.append(f"PRESSURE: {role_name}='{val}' deviates from topology (compat {compat:.2f})")

    return {
        "introspection": {
            "instability_zones": [
                {"type": z.zone_type, "loc": z.localization, "strength": round(z.strength, 3)} 
                for z in instability_zones[:5]
            ],
            "uncertainty_heatmap": heatmap,
            "topological_pressure": {k: round(v, 3) for k, v in pressure_field.items()},
        },
        "convergence_narrative": narrative,
        "contradiction_localization": contradictions
    }
