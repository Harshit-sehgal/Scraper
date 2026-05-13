"""
Semantic Contradiction Engine (Graph-Native)
=============================================
Implements Incompatibility Topology and Conflict Propagation.

Contradictions are no longer just scalar penalties; they are 
EXCLUSION EDGES in the semantic graph that propagate conflict pressure.

Mandatory features:
- Incompatibility Topology
- Exclusion Edges
- Impossible Neighborhood Detection
- Conflict Localization
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional

from app.semantic_ir import (
    SemanticGraph,
    SemanticToken,
    SemanticType,
)
from app.semantic_world_state import get_world_state


@dataclass
class ConflictSource:
    """Localized source of semantic conflict."""
    nodes: List[int]  # node indices
    conflict_type: str
    energy_penalty: float
    description: str


class IncompatibilityTopology:
    """
    Manages exclusion edges and impossible neighborhood structures.
    This topology exerts pressure on the graph to move away from unstable states.
    """
    def __init__(self):
        self.state = get_world_state()

    def detect_impossible_neighborhoods(self, tokens: List[SemanticToken], assignments: Dict[str, str]) -> List[ConflictSource]:
        """Detect subsets of nodes that form an impossible configuration."""
        conflicts = []
        
        # 1. Identity Conflict (Duplicate usage of same token for distinct roles)
        usage_map: dict[str, str] = {}
        for role, val in assignments.items():
            if val:
                if val in usage_map:
                    conflicts.append(ConflictSource(
                        nodes=[], # Tracing nodes is done by value match here
                        conflict_type="identity_clash",
                        energy_penalty=0.8,
                        description=f"Token '{val}' assigned to multiple roles: {usage_map[val]} and {role}"
                    ))
                usage_map[val] = role

        # 2. Structural Incompatibility (Learned Exclusions)
        roles = list(assignments.keys())
        for i in range(len(roles)):
            for j in range(i + 1, len(roles)):
                r1, r2 = roles[i], roles[j]
                v1, v2 = assignments.get(r1), assignments.get(r2)
                if v1 and v2:
                    # Check if r1 and r2 are known to be exclusive
                    exclusion_key = tuple(sorted([r1, r2]))
                    if exclusion_key in self.state.learned_exclusions:
                        strength = self.state.learned_exclusions[exclusion_key]
                        if v1 == v2 and strength > 0.5:
                            conflicts.append(ConflictSource(
                                nodes=[],
                                conflict_type="topological_exclusion",
                                energy_penalty=strength,
                                description=f"Roles {r1} and {r2} are mutually exclusive (learned strength {strength:.2f})"
                            ))

        return conflicts


class ConflictPropagationField:
    """
    Propagates conflict pressure through the graph.
    Localized conflicts create high-energy zones that force interpretation redistribution.
    """
    def __init__(self, conflicts: List[ConflictSource]):
        self.conflicts = conflicts

    def compute_total_pressure(self) -> float:
        """Compute the aggregate conflict energy of the field."""
        if not self.conflicts:
            return 0.0
        
        # Conflict energy adds non-linearly (entropy sum)
        total_energy = sum(c.energy_penalty for c in self.conflicts)
        return min(total_energy, 5.0) # Cap at 5.0 units of conflict energy

    def localize_instability(self) -> List[str]:
        """Identify zones of highest topological pressure."""
        return [c.description for c in self.conflicts if c.energy_penalty > 0.4]


def detect_allocation_contradictions(output: Dict[str, str], schema_fields: List[str]) -> List[str]:
    """Modern bridge to IncompatibilityTopology."""
    it = IncompatibilityTopology()
    conflicts = it.detect_impossible_neighborhoods([], output)
    return [c.description for c in conflicts]

def apply_contradiction_learning(output: Dict[str, str], schema_fields: List[str], reng, detect_type_fn, contradictions: List[str], warnings: List[str], universal_roots):
    """
    Propagates conflict signals into the long-term World State.
    Contradictions create exclusion edges.
    """
    state = get_world_state()
    
    if contradictions:
        # Learn exclusion edges between roles that fought over the same token
        filled_vals: dict[str, str] = {}
        for role, val in output.items():
            if val:
                if val in filled_vals:
                    r1 = filled_vals.get(val, "")
                    r2 = role
                    key = (r1, r2)
                    # Strengthen exclusion edge
                    current = state.learned_exclusions.get(key, 0.0)
                    state.learned_exclusions[key] = min(current + 0.1, 1.0)
                filled_vals[val] = role

    # Original warning learning bridge
    if warnings:
        for role_name in schema_fields:
            _val = output.get(role_name)
            if _val is None:
                continue
            val_type, _ = detect_type_fn(_val, role_name)
            # Find expected type
            seed_type = SemanticType.TEXT
            for roots, stype in universal_roots:
                if any(root in role_name.lower() for root in roots):
                    seed_type = stype
                    break
            if seed_type != SemanticType.TEXT and val_type != seed_type:
                # Penalize compatibility in world state
                key = (role_name, val_type.value if hasattr(val_type, 'value') else str(val_type))
                current = state.role_compatibility.get(key, 0.5)
                state.role_compatibility[key] = max(0.0, current - 0.2)

def detect_role_swap_warnings(output: Dict[str, str], schema_fields: List[str], detect_type_fn, universal_roots) -> List[str]:
    """Identifies role-type mismatches that suggest a potential swap or misallocation."""
    warnings = []
    for role_name in schema_fields:
        val = output.get(role_name)
        if not val:
            continue
        val_type, _ = detect_type_fn(val, role_name)
        v_type_str = val_type.value if hasattr(val_type, 'value') else str(val_type)
        
        expected_type = 'text'
        for roots, stype in universal_roots:
            if any(root in role_name.lower() for root in roots):
                expected_type = stype.value if hasattr(stype, 'value') else str(stype)
                break
        
        if expected_type != 'text' and v_type_str != expected_type:
            warnings.append(f"{role_name}: expected {expected_type}, got {v_type_str} ({val})")
    return warnings
