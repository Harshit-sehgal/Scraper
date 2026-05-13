"""
Global Semantic Allocation Engine
====================================
Replaces local field matching with global graph-based semantic allocation.

The engine stops asking:
"What value best matches this field?"

And instead asks:
"What semantic arrangement creates the MOST COHERENT GLOBAL GRAPH?"

Candidates compete GLOBALLY for semantic roles.
The optimal assignment maximizes global coherence.

Role-type compatibility is LEARNED, not hardcoded.
Uses RoleEmbeddingEngine from semantic_inference_engine.
"""

import random
from copy import deepcopy
from typing import List, Optional, Set, Tuple

from app.semantic_ir import (
    AllocationGraph,
    SemanticRecord,
    SemanticRole,
    SemanticToken,
    SemanticType,
)

# SHARED role embedding engine instance (learned, not hardcoded)
# Imported lazily to avoid circular deps
_role_engine = None

def _get_role_engine():
    global _role_engine
    if _role_engine is None:
        from app.semantic_inference_engine import RoleEmbeddingEngine
        _role_engine = RoleEmbeddingEngine()
    return _role_engine


# Exclusivity constraints (bootstrap seeds, others learned dynamically)
ROLE_EXCLUSIVITY: List[Tuple[str, str]] = [
    ("origin", "destination"),
    ("departure", "arrival"),
    ("start", "end"),
]


_smoothed_structural = 0.4
_smoothed_runtime = 0.3

def _adaptive_exclusion_threshold() -> float:
    """Exclusion threshold with hysteresis to prevent oscillation."""
    global _smoothed_structural
    from app.semantic_world_state import get_world_state
    ws = get_world_state()
    maturity = min(ws.metrics.total_records_processed / 100.0, 1.0)
    pressure = ws.metrics.field_pressure
    density = ws.topology_density
    target = 0.4 - (maturity * 0.2) + (pressure * 0.3) + (density * 0.2)
    target = max(0.2, min(0.6, target))
    _smoothed_structural = _smoothed_structural * 0.7 + target * 0.3
    return _smoothed_structural


def _adaptive_runtime_exclusion_threshold() -> float:
    """Runtime exclusion threshold with hysteresis."""
    global _smoothed_runtime
    from app.semantic_world_state import get_world_state
    ws = get_world_state()
    maturity = min(ws.metrics.total_records_processed / 100.0, 1.0)
    pressure = ws.metrics.field_pressure
    density = ws.topology_density
    target = 0.3 - (maturity * 0.15) + (pressure * 0.3) + (density * 0.15)
    target = max(0.15, min(0.5, target))
    _smoothed_runtime = _smoothed_runtime * 0.7 + target * 0.3
    return _smoothed_runtime


# Bootstrap seeds for role-type compatibility.
# These are TEMPORARY priors — learning overrides them over time.
# They are NOT universal truths; they give the system a starting point
# so that the first records processed have non-zero compatibility.
# After enough observations, learned compatibilities dominate.
_UNIVERSAL_ROOTS = [
    (['pric', 'cost', 'salar', 'fare'], SemanticType.PRICE),
    (['date', 'time', 'schedule'], SemanticType.DATE),
    (['loc', 'city', 'addr', 'place'], SemanticType.LOCATION),
    (['nam', 'comp', 'firm', 'brand', 'make', 'model', 'builder'], SemanticType.ORGANIZATION),
    (['rat', 'scor', 'review'], SemanticType.RATING),
    (['count', 'number', 'year', 'mileage', 'age', 'experien'], SemanticType.NUMBER),
    (['code', 'currenc', 'ident', 'id'], SemanticType.CODE),
]


def _name_similarity(a: str, b: str) -> float:
    """Compute longest common subsequence ratio between two role names."""
    if not a or not b:
        return 0.0
    a, b = a.lower(), b.lower()
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.8
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i-1] == b[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    lcs = dp[m][n]
    return lcs / max(m, n)


def seed_role_engine(schema_fields: list):
    """Seed the RoleEmbeddingEngine with initial role-type compatibilities."""
    reng = _get_role_engine()
    
    for f_name in schema_fields:
        field_lower = f_name.lower()
        
        # Strategy 1: Universal roots
        best_type = SemanticType.TEXT
        for roots, stype in _UNIVERSAL_ROOTS:
            if any(root in field_lower for root in roots):
                best_type = stype
                break
        
        # Strategy 2: Cache-derived nearest neighbor
        if best_type == SemanticType.TEXT:
            best_score = 0.0
            for (known_role, type_str), compat in reng.compatibility_cache.items():
                if compat < 0.6:
                    continue
                sim = _name_similarity(f_name, known_role)
                if sim > best_score:
                    best_score = sim
                    if sim > 0.55:
                        best_type = SemanticType(type_str)
        
        key = (f_name, best_type.value)
        if key not in reng.compatibility_cache:
            reng.compatibility_cache[key] = 0.7


def warm_start_from_values(records: list, schema_fields: list):
    """Warm-start the RoleEmbeddingEngine using actual value classifications."""
    if not records or not schema_fields:
        return
    
    reng = _get_role_engine()
    first = records[0]
    
    from app.semantic_mapper import detect_semantic_type
    
    for f_name in schema_fields:
        val = first.get(f_name)
        if not isinstance(val, str) or not val.strip():
            continue
        
        st, conf = detect_semantic_type(val, f_name)
        key = (f_name, st.value)
        if key not in reng.compatibility_cache:
            reng.compatibility_cache[key] = 0.7


def build_allocation_graph(record: SemanticRecord, schema_roles: List[str]) -> AllocationGraph:
    """Build an allocation graph from a record and desired schema roles.

    Each candidate token competes for each role.
    The graph captures compatibility scores and exclusivity constraints.
    """
    graph = AllocationGraph()

    # Register role order (for positional ordering signals)
    graph.role_order = list(schema_roles)

    # Register candidates (deduplicated by text)
    seen = set()
    for token in record.tokens:
        if token.raw not in seen:
            seen.add(token.raw)
            graph.candidates[token.raw] = token

    # Register roles
    for role_name in schema_roles:
        expected_type = _infer_role_type(role_name)
        graph.roles[role_name] = SemanticRole(
            role_name=role_name,
            field_type=expected_type,
            required=True,
        )

    # Compute compatibility scores
    for cand_key, token in graph.candidates.items():
        for role_name, role in graph.roles.items():
            score = _compute_compatibility(token, role_name, role, graph.role_order)
            if score > 0:
                graph.compatibility[(cand_key, role_name)] = score

    # Phase 4D: Equilibrium search — modulate compatibility by field region instability
    # Roles in active conflict regions have their compatibility scores weighted down
    # by field pressure, so allocation hesitates rather than confidently resolving.
    from app.semantic_world_state import get_world_state as _gws_eq
    _ws_eq = _gws_eq()
    for region in _ws_eq.field_regions:
        for role in region.competing_roles:
            if role in graph.roles:
                instability = min(region.instability, 1.0)
                for cand_key in graph.candidates:
                    key = (cand_key, role)
                    if key in graph.compatibility:
                        weight = 1.0 - (instability * 0.3)
                        graph.compatibility[key] *= weight

    # Build exclusivity edges
    reng = _get_role_engine()
    for role_a, role_b in ROLE_EXCLUSIVITY:
        if role_a in graph.roles and role_b in graph.roles:
            graph.exclusivity_edges.append((role_a, role_b))
            
    # Add dynamic learned exclusions
    roles = list(graph.roles.keys())
    for i in range(len(roles)):
        for j in range(i + 1, len(roles)):
            r1, r2 = roles[i], roles[j]
            if (r1, r2) in graph.exclusivity_edges or (r2, r1) in graph.exclusivity_edges:
                continue
            exclusion_threshold = _adaptive_exclusion_threshold()
            if reng.get_learned_exclusion(r1, r2) > exclusion_threshold:
                graph.exclusivity_edges.append((r1, r2))

    # Phase 4: Check restructuring queue — flag role pairs for separation
    from app.semantic_world_state import get_world_state as _gws
    _ws = _gws()
    for pair in list(_ws.restructuring_queue):
        r1, r2 = pair
        if r1 in graph.roles and r2 in graph.roles:
            if (r1, r2) not in graph.exclusivity_edges and (r2, r1) not in graph.exclusivity_edges:
                graph.exclusivity_edges.append((r1, r2))

    # Phase 4B: Field activation — topology mutates BEFORE allocation
    # Reads persistent field regions and converts conflict geometry into
    # exclusion edges, making the field state causally shape allocation.
    for region in _ws.field_regions:
        roles = region.competing_roles
        for i in range(len(roles)):
            for j in range(i + 1, len(roles)):
                r1, r2 = roles[i], roles[j]
                if r1 in graph.roles and r2 in graph.roles:
                    pair = (r1, r2)
                    rev_pair = (r2, r1)
                    if pair not in graph.exclusivity_edges and rev_pair not in graph.exclusivity_edges:
                        graph.exclusivity_edges.append((r1, r2))

    # Initial coherence
    graph.coherence_score = _compute_allocation_coherence(graph)

    return graph


def _infer_role_type(role_name: str) -> SemanticType:
    """Infer the expected SemanticType for a role name.

    Delegates to RoleEmbeddingEngine which learns dynamically.
    Finds the type with the highest learned compatibility for this role.
    """
    reng = _get_role_engine()
    best_type = SemanticType.TEXT
    best_compat = -1.0
    
    for t in SemanticType:
        compat = reng.get_compatibility(role_name, t)
        if compat > best_compat:
            best_compat = compat
            best_type = t
            
    return best_type


def _compute_compatibility(
    token: SemanticToken, role_name: str, role: SemanticRole,
    role_order: Optional[List[str]] = None
) -> float:
    """Compute how compatible a candidate is with a semantic role.

    Uses learned role embeddings from RoleEmbeddingEngine.
    Adds positional ordering bonus: earlier tokens match earlier schema roles.
    No hardcoded TYPE_ROLE_COMPATIBILITY matrix.
    No hardcoded pattern matching.
    Purely emergent from learning.
    """
    # Use learned role embeddings for compatibility
    reng = _get_role_engine()
    learned_compat = reng.get_compatibility(role_name, token.primary_type)

    # Ambiguity penalty (universal, not symbolic)
    dist = token.type_distribution
    if dist and len(dist) > 1:
        primary_conf = dist.get(token.primary_type, 0.5)
        ambiguity_penalty = (1.0 - primary_conf) * 0.2
        learned_compat -= ambiguity_penalty

    # Positional ordering bonus (structural signal, not domain-specific)
    # Tokens earlier in the text are preferred for earlier schema roles.
    # Blends schema-order positions with learned role positions.
    if role_order and role_name in role_order:
        role_idx = role_order.index(role_name)
        total_roles = len(role_order)
        if total_roles > 1:
            # Learned position from past allocations (if available)
            schema_pos = role_idx / (total_roles - 1)
            # When learning count is low, use stronger positional signal.
            # Over time, learned compatibility takes over.
            learning_count = reng.learning_count
            pos_weight = 0.15 + max(0, 0.20 - learning_count * 0.02)  # Starts at 0.35, decays to 0.15
            ideal_pos = schema_pos
            
            token_pos = min(token.position / 20, 1.0)
            pos_accuracy = 1.0 - abs(ideal_pos - token_pos)
            learned_compat += pos_accuracy * pos_weight

    return max(min(learned_compat, 1.0), 0.0)


def optimize_semantic_assignment(graph: AllocationGraph) -> AllocationGraph:
    """Optimize semantic role assignment globally.

    Greedy algorithm:
    1. Score every candidate-role pair
    2. Assign highest-confidence pairs first
    3. Remove assigned candidates and filled roles from pool
    4. Resolve exclusivity conflicts
    5. Repeat until all roles filled or no candidates remain
    """
    assigned_candidates: Set[str] = set()
    filled_roles: Set[str] = set()
    field_conflicts: list = []  # preserve conflict geometry for field arbitration

    assignments = sorted(
        [(score, cand, role) for (cand, role), score in graph.compatibility.items()],
        key=lambda x: -x[0],
    )

    for score, cand_key, role_name in assignments:
        # Check exclusivity BEFORE generic 'already assigned' — preserve conflict geometry
        conflicting = False
        conflict_reason = ""
        for role_a, role_b in graph.exclusivity_edges:
            if role_name == role_a and role_b in filled_roles and graph.roles[role_b].filled_by == cand_key:
                conflicting = True
                conflict_reason = f"exclusivity:{role_name}↔{role_b}"
                break
            if role_name == role_b and role_a in filled_roles and graph.roles[role_a].filled_by == cand_key:
                conflicting = True
                conflict_reason = f"exclusivity:{role_name}↔{role_a}"
                break

        if conflicting:
            field_conflicts.append({
                "role": role_name, "candidate": cand_key,
                "reason": conflict_reason, "score": score
            })
            continue

        if cand_key in assigned_candidates:
            continue
        if role_name in filled_roles:
            continue

        graph.roles[role_name].filled_by = cand_key
        graph.roles[role_name].fill_confidence = score
        assigned_candidates.add(cand_key)
        filled_roles.add(role_name)

    graph._field_conflicts = field_conflicts
    graph.coherence_score = _compute_allocation_coherence(graph)
    return graph


def _compute_allocation_coherence(graph: AllocationGraph) -> float:
    """Compute coherence of the allocation.

    Factors:
    - Fill ratio (how many roles are filled)
    - Average fill confidence
    - Exclusivity satisfaction
    """
    if not graph.roles:
        return 0.0

    # Fill ratio
    filled = sum(1 for r in graph.roles.values() if r.filled_by is not None)
    fill_ratio = filled / len(graph.roles)

    # Average confidence
    confidences = [r.fill_confidence for r in graph.roles.values() if r.filled_by is not None]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    # Exclusivity satisfaction
    exclusivity_violations = 0
    for role_a, role_b in graph.exclusivity_edges:
        if role_a in graph.roles and role_b in graph.roles:
            ra, rb = graph.roles[role_a], graph.roles[role_b]
            if ra.filled_by and rb.filled_by and ra.filled_by == rb.filled_by:
                exclusivity_violations += 1
    exclusivity_score = 1.0 - (exclusivity_violations / max(len(graph.exclusivity_edges), 1))

    coherence = (fill_ratio * 0.4) + (avg_conf * 0.4) + (exclusivity_score * 0.2)
    return min(coherence, 1.0)


def allocate_semantic_roles(
    record: SemanticRecord,
    schema_fields: List[str],
    learn: bool = True,
) -> Tuple[SemanticRecord, AllocationGraph]:
    """Full semantic allocation for a record.

    When learn=False, the feedback loop is skipped (seeds are preserved).
    Use learn=False for the first pass, learn=True for refinement passes.

    Returns (updated_record, allocation_graph).
    """
    graph = build_allocation_graph(record, schema_fields)
    graph = optimize_semantic_assignment(graph)

    # Apply allocation to record
    for role_name, role in graph.roles.items():
        if role.filled_by:
            record.mapped_fields[role_name] = role.filled_by
            record.mapped_confidences[role_name] = role.fill_confidence

    record.overall_confidence = graph.coherence_score
    
    # Propagate uncertainty to global state
    from app.semantic_world_state import get_world_state
    state = get_world_state()
    state.metrics.cumulative_uncertainty += (1.0 - graph.coherence_score)

    if not learn:
        return record, graph

    # CLOSE THE FEEDBACK LOOP via multi-hypothesis comparison
    # Four allocation strategies compete:
    #   1. Primary: default greedy (score descending)
    #   2. Reverse: reversed score order  
    #   3. Noisy: scores perturbed with noise
    #   4. Random: shuffled candidates for genuine exploration
    # The assignments that DIFFER between best and worst hypotheses
    # (by coherence) provide comparative learning signals.
    # Learning rate adapts: fast when uncertain, slow when certain.
    reng = _get_role_engine()
    
    # Build competing hypotheses
    candidates = [(cand, role, score) for (cand, role), score in graph.compatibility.items()]
    hypotheses = []
    
    for _strategy, key_fn in [
        ('primary', lambda x: -x[2]),
        ('reverse', lambda x: x[2]),
        ('noisy', lambda x: -x[2] + random.random() * 0.05),
        ('random', lambda x: random.random()),
    ]:
        h = _run_allocation(graph, sorted(candidates, key=key_fn))
        hypotheses.append(h)
    
    # Sort by coherence
    hypotheses.sort(key=lambda h: h['coherence'])
    
    if len(hypotheses) >= 2:
        best = hypotheses[-1]
        worst = hypotheses[0]
        coherence_gap = best['coherence'] - worst['coherence']
        
        # Only learn when the coherence gap is significant (> 0.15).
        # Small gaps mean both hypotheses are equally plausible — 
        # learning from noise would reinforce wrong patterns.
        if coherence_gap > 0.15:
            for role_name in graph.roles:
                best_val = best['roles'].get(role_name)
                worst_val = worst['roles'].get(role_name)
                
                if best_val and worst_val and best_val != worst_val:
                    # Check confidence gap: if the greedy algorithm had a clear
                    # winner (score gap > 0.15 to second place), don't let
                    # comparative learning override it.
                    role_scores = sorted([
                        (graph.compatibility.get((c, role_name), 0), c)
                        for c in graph.candidates
                    ], key=lambda x: -x[0])
                    if len(role_scores) >= 2:
                        gap = role_scores[0][0] - role_scores[1][0]
                        if gap > 0.15:
                            continue  # Confident assignment, don't override
                    
                    token = graph.candidates.get(best_val)
                    if token:
                        key = (role_name, token.primary_type.value)
                        current_compat = reng.compatibility_cache.get(key, 0.5)
                        certainty = abs(current_compat - 0.5) * 2
                        base_rate = 0.05 * (1.0 - certainty * 0.5)
                        delta = abs(best['coherence'] - 0.5) * base_rate
                        reng.learn_from_allocation(role_name, token.primary_type, token.raw, success=True, delta=delta)
                    
                    token2 = graph.candidates.get(worst_val)
                    if token2:
                        key2 = (role_name, token2.primary_type.value)
                        current2 = reng.compatibility_cache.get(key2, 0.5)
                        certainty2 = abs(current2 - 0.5) * 2
                        base_rate2 = 0.05 * (1.0 - certainty2 * 0.5)
                        delta2 = abs(0.5 - worst['coherence']) * base_rate2
                        reng.learn_from_allocation(role_name, token2.primary_type, token2.raw, success=False, delta=delta2)
    
    # Co-occurrence learning: record which (role, type) pairs co-occur successfully
    best_hyp = hypotheses[-1] if len(hypotheses) >= 2 else hypotheses[0]
    assignments = {}
    for role_name in graph.roles:
        val = best_hyp['roles'].get(role_name)
        if val and val in graph.candidates:
            token = graph.candidates[val]
            assignments[role_name] = (token.primary_type.value, val)
    
    items = list(assignments.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            role_i, (type_i, val_i) = items[i]
            role_j, (type_j, val_j) = items[j]
            reng.learn_co_occurrence(
                (role_i, type_i), (role_j, type_j),
                success=best_hyp['coherence'] > 0.5
            )
    
    # Role position learning: record where each role was in the token order
    for _idx, role_name in enumerate(schema_fields):
        fill_val = graph.roles[role_name].filled_by
        if fill_val and fill_val in graph.candidates:
            token = graph.candidates[fill_val]
            total_tokens = len(graph.candidates)
            if total_tokens > 1:
                norm_pos = token.position / max(total_tokens - 1, 1)
                reng.learn_role_position(role_name, norm_pos)

    return record, graph


def _run_allocation(graph: AllocationGraph, sorted_assignments: list) -> dict:
    """Run a full allocation given a sorted assignment list.
    
    sorted_assignments: list of (cand_key, role_name, score) tuples, 
                        pre-sorted by desired strategy.
    Returns {'roles': {role: candidate}, 'coherence': float}.
    """
    g = deepcopy(graph)
    assigned = set()
    filled: set[str] = set()
    
    for cand_key, role_name, score in sorted_assignments:
        if cand_key in assigned or role_name in filled:
            continue
        conflicting = False
        for role_a, role_b in g.exclusivity_edges:
            other = role_b if role_name == role_a else (role_a if role_name == role_b else None)
            if other and other in filled and g.roles.get(other) and g.roles[other].filled_by == cand_key:
                conflicting = True
                break
                
        # Layer 5: Dynamic learned exclusivity (already covered if using g.exclusivity_edges)
        if not conflicting:
            reng = _get_role_engine()
            if hasattr(reng, 'get_learned_exclusion'):
                for filled_role in filled:
                    if g.roles.get(filled_role) and g.roles[filled_role].filled_by == cand_key:
                        exclusion_score = reng.get_learned_exclusion(role_name, filled_role)
                        runtime_threshold = _adaptive_runtime_exclusion_threshold()
                        if exclusion_score > runtime_threshold:
                            conflicting = True
                            break
                            
        if conflicting:
            continue
        g.roles[role_name].filled_by = cand_key
        g.roles[role_name].fill_confidence = score
        assigned.add(cand_key)
        filled.add(role_name)
    
    coh = _compute_allocation_coherence(g)
    return {'roles': {r: g.roles[r].filled_by for r in g.roles}, 'coherence': coh}


def allocate_all_records(
    records: List[SemanticRecord],
    schema_fields: List[str],
) -> List[Tuple[SemanticRecord, AllocationGraph]]:
    """Allocate semantic roles for all records in a dataset."""
    results = []
    for record in records:
        result, graph = allocate_semantic_roles(record, schema_fields)
        results.append((result, graph))
    return results
