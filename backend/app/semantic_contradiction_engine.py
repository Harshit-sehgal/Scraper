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

import logging
from dataclasses import dataclass, field
from typing import Dict, List

from app.semantic_ir import (
    SemanticGraph,
    SemanticToken,
    SemanticType,
)
from app.semantic_world_state import get_world_state
from app.event_dispatcher import get_dispatcher
from app.semantic_events import SemanticEvent, SemanticEventType


@dataclass
class Contradiction:
    """A detected contradiction in the semantic graph."""
    description: str
    confidence_damage: float
    nodes: list = field(default_factory=list)
    contradiction_type: str = "generic"


@dataclass
class ConflictSource:
    """Localized source of semantic conflict."""
    nodes: List[int]  # node indices
    conflict_type: str
    energy_penalty: float
    description: str


# Learning and propagation constants — isolated for observability
_EXCLUSION_LEARN_RATE = 0.1
_COMPATIBILITY_DECAY_RATE = 0.2
_EXCLUSION_CONTRADICTION_DELTA = 0.2
_COMPATIBILITY_CONTRADICTION_DELTA = 0.1
_CONTRADICTION_ENERGY_CAP = 0.8
_EXCLUSION_STRENGTH_THRESHOLD = 0.5
_INSTABILITY_PRESSURE_THRESHOLD = 0.4


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
        usage_map = {}
        for role, val in assignments.items():
            if not val or role.startswith('_'):
                continue
            if val in usage_map:
                conflicts.append(ConflictSource(
                    nodes=[],
                    conflict_type="identity_clash",
                    energy_penalty=_CONTRADICTION_ENERGY_CAP,
                    description=f"Token '{val}' assigned to multiple roles: {usage_map[val]} and {role}"
                ))
            usage_map[val] = role

        # 2. Structural Incompatibility (Learned Exclusions + Bootstrap ROLE_EXCLUSIVITY)
        from app.semantic_allocation_engine import ROLE_EXCLUSIVITY
        roles = list(assignments.keys())
        for i in range(len(roles)):
            for j in range(i + 1, len(roles)):
                r1, r2 = roles[i], roles[j]
                v1, v2 = assignments.get(r1), assignments.get(r2)
                if v1 and v2:
                    # Check bootstrap exclusivity seeds (sorted to match ROLE_EXCLUSIVITY storage)
                    sorted_pair = tuple(sorted([r1, r2]))
                    if sorted_pair in ROLE_EXCLUSIVITY:
                        if v1 == v2:
                            conflicts.append(ConflictSource(
                                nodes=[],
                                conflict_type="topological_exclusion",
                                energy_penalty=_CONTRADICTION_ENERGY_CAP,
                                description=f"Roles {r1} and {r2} are mutually exclusive (seed rule)"
                            ))
                    # Check learned exclusions
                    exclusion_key = sorted_pair
                    if exclusion_key in self.state.learned_exclusions:
                        strength = self.state.learned_exclusions[exclusion_key]
                        if v1 == v2 and strength > _EXCLUSION_STRENGTH_THRESHOLD:
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
        return [c.description for c in self.conflicts if c.energy_penalty > _INSTABILITY_PRESSURE_THRESHOLD]


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
    dispatcher = get_dispatcher()
    
    # Global topology decay: weaken all learned exclusions slightly each cycle.
    # Only strong, consistently-reinforced exclusions survive over time.
    for key in list(state.learned_exclusions.keys()):
        decay = state.learned_exclusions[key] * 0.05
        state.learned_exclusions[key] = max(0.0, state.learned_exclusions[key] - decay)
        if state.learned_exclusions[key] <= 0.01:
            del state.learned_exclusions[key]
    
    if contradictions:
        # Learn exclusion edges between roles that fought over the same token
        filled_vals = {}
        for role, val in output.items():
            if role.startswith('_') or not val:
                continue
            if val in filled_vals:
                r1, r2 = filled_vals[val], role
                key = tuple(sorted([r1, r2]))
                current = state.learned_exclusions.get(key, 0.0)
                state.learned_exclusions[key] = min(current + _EXCLUSION_LEARN_RATE, 1.0)
                dispatcher.dispatch(SemanticEvent(
                    event_type=SemanticEventType.CONTRADICTION_DETECTED,
                    source="contradiction_engine",
                    payload={"role_pair": key, "conflict_type": "identity_clash"},
                    instability_delta=_EXCLUSION_CONTRADICTION_DELTA
                ))
            filled_vals[val] = role

        # Phase 4: Neighborhood cohesion tracking
        # Decrement cohesion for role pairs in contradiction descriptions
        for c in contradictions:
            c_str = str(c)
            for role in schema_fields:
                if role in c_str:
                    for other_role in schema_fields:
                        if other_role != role and other_role in c_str:
                            key = tuple(sorted([role, other_role]))
                            current = state.neighborhood_cohesion.get(key, 0.5)
                            state.neighborhood_cohesion[key] = max(0.0, current - 0.1)
                            if state.neighborhood_cohesion[key] < 0.3:
                                state.restructuring_queue.add(key)

    # Increment cohesion for non-conflicting co-occurrences
    if not contradictions:
        for role in output:
            if role.startswith('_') or not output[role]:
                continue
            for other_role in output:
                if other_role.startswith('_') or not output[other_role] or other_role == role:
                    continue
                key = tuple(sorted([role, other_role]))
                current = state.neighborhood_cohesion.get(key, 0.5)
                state.neighborhood_cohesion[key] = min(1.0, current + 0.02)

    # Original warning learning bridge
    if warnings:
        for role_name in schema_fields:
            val = output.get(role_name)
            if not val:
                continue
            val_type, _ = detect_type_fn(val, role_name)
            # Find expected type
            seed_type = SemanticType.TEXT
            for roots, stype in universal_roots:
                if any(root in role_name.lower() for root in roots):
                    seed_type = stype
                    break
            
            v_type_str = val_type.value if hasattr(val_type, 'value') else str(val_type)
            if seed_type != SemanticType.TEXT and v_type_str != (seed_type.value if hasattr(seed_type, 'value') else str(seed_type)):
                # Penalize compatibility in world state
                key = (role_name, v_type_str)
                current = state.role_compatibility.get(key, 0.5)
                state.role_compatibility[key] = max(0.0, current - _COMPATIBILITY_DECAY_RATE)
                logger = logging.getLogger(__name__)
                logger.debug("Decayed compatibility for %s: %.3f -> %.3f", key, current, current - _COMPATIBILITY_DECAY_RATE)
                dispatcher.dispatch(SemanticEvent(
                    event_type=SemanticEventType.UNCERTAINTY_SPIKE,
                    source="contradiction_engine",
                    payload={"role_pair": key, "decay": _COMPATIBILITY_DECAY_RATE},
                    instability_delta=_COMPATIBILITY_CONTRADICTION_DELTA
                ))

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


def detect_contradictions(graph: SemanticGraph) -> List[Contradiction]:
    """Detect contradictions in a semantic graph."""
    contradictions: List[Contradiction] = []

    # 1. Identity contradictions (same value in multiple roles)
    value_to_roles: Dict[str, List[str]] = {}
    for region in graph.regions:
        for token in region.tokens:
            if token.raw:
                if token.raw not in value_to_roles:
                    value_to_roles[token.raw] = []
                value_to_roles[token.raw].append(f"region_{region.region_id}")

    for value, roles in value_to_roles.items():
        if len(roles) > 1:
            contradictions.append(Contradiction(
                description=f"Token '{value}' appears in multiple regions: {roles}",
                confidence_damage=0.3 * len(roles),
                contradiction_type="identity_clash",
            ))

    # 2. Structural incompatibilities in ownership
    for edge in graph.ownership_edges:
        if edge.owner_region_id == edge.owned_region_id:
            contradictions.append(Contradiction(
                description=f"Circular ownership edge: region {edge.owner_region_id} owns itself",
                confidence_damage=0.5,
                nodes=[edge.owner_region_id],
                contradiction_type="circular_ownership",
            ))

    return contradictions
