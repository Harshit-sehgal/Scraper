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

Role-type compatibility is derived geometrically from the Role Manifold.
"""

import random
from copy import deepcopy
from typing import List, Set, Tuple

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

def reset_role_engine():
    """Reset the global role engine (for testing)."""
    global _role_engine
    _role_engine = None


# Exclusivity constraints — now defined in field_laws.py to prevent
# upward dependency from core_types.py to this allocation engine.
# Imported here for backward compatibility and local usage.
from app.field_laws import ROLE_EXCLUSIVITY


def _adaptive_exclusion_threshold() -> float:
    """Exclusion threshold with hysteresis + temperature modulation."""
    from app.semantic_world_state import get_world_state
    ws = get_world_state()
    # Read-only access to smoothed metrics updated during evolution
    base = getattr(ws.metrics, "_smoothed_structural", 0.4)
    temp = ws.metrics.semantic_temperature
    conv = ws.metrics.integrity_score
    # Stress (temp) increases threshold; Convergence (trust) decreases it
    result = base + (temp - 0.5) * 0.2 - (conv - 0.5) * 0.15
    return max(0.2, min(0.6, result))


def _adaptive_runtime_exclusion_threshold() -> float:
    """Exclusion threshold with hysteresis + temperature + convergence."""
    from app.semantic_world_state import get_world_state
    ws = get_world_state()
    # Read-only access to smoothed metrics updated during evolution
    base = getattr(ws.metrics, "_smoothed_runtime", 0.3)
    temp = ws.metrics.semantic_temperature
    conv = ws.metrics.integrity_score
    # Stress (temp) increases threshold; Convergence (trust) decreases it
    result = base + (temp - 0.5) * 0.15 - (conv - 0.5) * 0.1
    return max(0.15, min(0.5, result))


# Bootstrap seeds for role-type compatibility.
# These are TEMPORARY priors — learning overrides them over time.
_UNIVERSAL_ROOTS = [
    (['pric', 'cost', 'salar', 'fare', 'preci', 'prix', 'wert'], SemanticType.PRICE),
    (['date', 'time', 'schedule', 'fecha', 'zeit', 'horar'], SemanticType.DATE),
    # Airport / IATA field names (e.g. origin_airport) expect codes, not full locations
    (['airport', 'iata', 'icao'], SemanticType.CODE),
    (['loc', 'city', 'addr', 'place', 'dest', 'orig', 'ubica', 'stadt'], SemanticType.LOCATION),
    (['code', 'currenc', 'ident', 'id', 'codig'], SemanticType.CODE),
    (['nam', 'comp', 'firm', 'brand', 'make', 'model', 'builder', 'nombr', 'hotel', 'resort', 'title'], SemanticType.ORGANIZATION),
    (['rat', 'scor', 'review', 'calif', 'bewert'], SemanticType.RATING),
    (['count', 'number', 'year', 'mileage', 'age', 'experien', 'num', 'jahr'], SemanticType.NUMBER),
    (['avail', 'stock', 'status', 'state'], SemanticType.TEXT),
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
    """Seed the RoleEmbeddingEngine manifold with initial priors and Manifold Transfer."""
    reng = _get_role_engine()
    ws = reng.ws
    
    for f_name in schema_fields:
        if f_name in reng.manifold:
            continue
            
        field_lower = f_name.lower()
        
        # 1. Manifold Transfer: inherit from existing similar stable roles (Phase 23)
        # Search for a stable role with a similar name
        inherited = False
        for existing_role, vec in reng.manifold.items():
            if _name_similarity(field_lower, existing_role.lower()) >= 0.8:
                instability = ws.metrics.get_schema_instability(existing_role)
                if instability < 0.2:
                    # Found a stable similar role; inherit its physical state
                    ws.set_manifold_vector(f_name, list(vec))
                    ws.metrics.set_schema_instability(f_name, instability)
                    inherited = True
                    break
        
        if inherited:
            continue

        # 2. Universal Roots: fallback to symbolic seeds
        best_type = SemanticType.TEXT
        for roots, stype in _UNIVERSAL_ROOTS:
            if any(root in field_lower for root in roots):
                best_type = stype
                break
        
        if best_type == SemanticType.TEXT:
            for st in SemanticType:
                if _name_similarity(field_lower, st.value) > 0.6:
                    best_type = st
                    break
        
        # Initialize manifold vector through controlled method
        ws.set_manifold_vector(f_name, reng._get_type_vector(best_type))
        
        # Initial instability for new roles (Medium) through controlled method
        current_instability = ws.metrics.get_schema_instability(f_name)
        if current_instability == 0.5:
            # Already the default — no mutation needed
            pass
        else:
            ws.metrics.set_schema_instability(f_name, 0.5)


def warm_start_from_values(records: list, schema_fields: list):
    """Warm-start the Role Manifold with observed values."""
    if not records or not schema_fields:
        return
    
    reng = _get_role_engine()
    ws = reng.ws
    first = records[0]
    
    from app.semantic_mapper import detect_semantic_type
    
    for f_name in schema_fields:
        val = first.get(f_name)
        if not isinstance(val, str) or not val.strip():
            continue
        
        st, _ = detect_semantic_type(val, f_name)
        expected_type = _infer_role_type(f_name)
        
        # Grounding check: only seed if types are near
        is_compatible = (st == expected_type) or \
                        (st == SemanticType.TEXT) or \
                        (expected_type == SemanticType.TEXT) or \
                        (st == SemanticType.CODE and expected_type in [SemanticType.LOCATION, SemanticType.PRICE, SemanticType.CODE, SemanticType.IDENTIFIER])
        
        if is_compatible:
            # Move manifold point toward this observed type through controlled blend
            if f_name not in reng.manifold:
                ws.set_manifold_vector(f_name, reng._get_type_vector(expected_type))
            
            target_vec = reng._get_type_vector(st)
            ws.blend_manifold_vector(f_name, target_vec, alpha=0.7, beta=0.3)


def build_allocation_graph(record: SemanticRecord, schema_roles: List[str], abstraction_gradient: float = 0.0) -> AllocationGraph:
    """Build an allocation graph from a record and desired schema roles with Hierarchical Synthesis (Phase 38)."""
    graph = AllocationGraph()
    from app.semantic_world_state import get_world_state
    ws = get_world_state()

    # Expand schema roles to include constituents if gradient allows
    # Preserve order using dict.fromkeys (Phase 38)
    role_list = list(schema_roles)
    if abstraction_gradient > 0.3:
        for role in list(role_list):
            level = ws.get_role_level(role)
            if level > 0:
                env = ws.get_envelope(role)
                if env:
                    # Include constituents in interpretation
                    for c in env["constituents"]:
                        if c not in role_list:
                            role_list.append(c)

    # Register candidates
    seen = set()
    for token in record.tokens:
        if token.raw not in seen:
            seen.add(token.raw)
            graph.candidates[token.raw] = token

    # Register roles in order
    for role_name in role_list:
        expected_type = _infer_role_type(role_name)
        graph.roles[role_name] = SemanticRole(
            role_name=role_name,
            field_type=expected_type,
            required=(role_name in schema_roles), # Only top-level roles are required
        )

    # Topology-driven exclusion edges from field regions
    topo_view = ws.get_topology_view()
    for region in topo_view.all_regions():
        roles = region.competing_roles
        for i in range(len(roles)):
            for j in range(i + 1, len(roles)):
                r1, r2 = roles[i], roles[j]
                if r1 in graph.roles and r2 in graph.roles:
                    pair = (r1, r2)
                    if pair not in graph.exclusivity_edges and (r2, r1) not in graph.exclusivity_edges:
                        graph.exclusivity_edges.append(pair)

    # Compute compatibility scores (Geometric)
    for cand_key, token in graph.candidates.items():
        for role_name, role in graph.roles.items():  # type: ignore[assignment]
            score = _compute_compatibility(token, role_name, role)  # type: ignore[arg-type]
            if score > 0:
                graph.compatibility[(cand_key, role_name)] = score

    # Field instability damping
    # Unstable basins reduce proposal confidence for their roles.
    for region in topo_view.all_regions():
        for role in region.competing_roles:
            if role in graph.roles:
                instability = min(region.instability, 1.0)
                for cand_key in graph.candidates:
                    key = (cand_key, role)
                    if key in graph.compatibility:
                        # Unstable basins reduce proposal confidence
                        graph.compatibility[key] *= (1.0 - instability * 0.3)

    # Topological Inference (Phase 18): Community Pull
    # Roles that are part of a macro-scale community pull each other.
    if ws.global_communities:
        role_comm_map = {}
        for i, comm in enumerate(ws.global_communities):
            for role_name in comm:
                role_comm_map[role_name] = i
        
        # Calculate community "Presence" in this record
        comm_max_scores: dict = {}
        for (cand, role), score in graph.compatibility.items():
            if role in role_comm_map:
                c_idx = role_comm_map[role]
                comm_max_scores[c_idx] = max(comm_max_scores.get(c_idx, 0.0), score)
        
        # Apply pull: roles in an "active" community get a boost
        for (cand, role), score in list(graph.compatibility.items()):
            if role in role_comm_map:
                c_idx = role_comm_map[role]
                pull = comm_max_scores.get(c_idx, 0.0)
                if pull > 0.7:
                    # Community is present; boost other roles in it
                    # (Boost is proportional to community pull and current score)
                    graph.compatibility[(cand, role)] = min(1.0, score + (1.0 - score) * 0.1 * pull)

    # Schema Gravity Pull (Phase 19): Macro-Scale Structural memory
    # If the set of schema roles matches a learned stable pattern, boost compatibility.
    if ws.schema_patterns:
        current_roles = sorted(graph.roles.keys())
        # Check role-pair subsets against stored 2-tuple patterns
        schema_frequency = 0
        for i in range(len(current_roles)):
            for j in range(i + 1, len(current_roles)):
                pair = (current_roles[i], current_roles[j])
                schema_frequency = max(schema_frequency, ws.schema_patterns.get(pair, 0))
        if schema_frequency > 10:
            # Learned stable schema; boost all compatible roles
            boost = min(0.1, schema_frequency / 500.0)
            for key in graph.compatibility:
                graph.compatibility[key] = min(1.0, graph.compatibility[key] + (1.0 - graph.compatibility[key]) * boost)

    # Crystalline Gravity (Phase 22): Predictive Pull from Synthesized Units
    # If a token matches a crystalline record by identity, pull missing fields.
    token_vals = list(graph.candidates.keys())
    attractors = ws.get_crystalline_attractors(token_vals)
    for attractor in attractors:
        # Every field in the attractor exerts a pull on matching candidate tokens
        for role_name, attr_val in attractor.items():
            if role_name in graph.roles:
                for cand_val, token in graph.candidates.items():
                    if cand_val == attr_val:
                        # Direct match found in crystalline unit; boost compatibility
                        key = (cand_val, role_name)
                        current = graph.compatibility.get(key, 0.5)
                        # Strong pull: synthesized knowledge is high-integrity
                        graph.compatibility[key] = min(1.0, current + (1.0 - current) * 0.5)

     # Topological Law Bias (Phase 24): Proximity Laws
    # If roles A and B have a proximity law and are close, boost.
    if ws.topological_laws:
        # Build spatial index: bucket candidates by position (O(n) preprocessing)
        # Bucket size = proximity threshold (50 units)
        position_buckets: dict[int, list] = {}
        for cand_val, token in graph.candidates.items():
            bucket_id = int(token.position // 50)
            if bucket_id not in position_buckets:
                position_buckets[bucket_id] = []
            position_buckets[bucket_id].append((cand_val, token))
        
        for (r1, r2), strength in ws.topological_laws.items():
            if r1 in graph.roles and r2 in graph.roles:
                # For each bucket, check only nearby buckets (spatial locality)
                for bucket_id, candidates_in_bucket in position_buckets.items():
                    # Check current bucket and adjacent buckets only
                    nearby_buckets = [bucket_id - 1, bucket_id, bucket_id + 1]
                    nearby_candidates = []
                    for nearby_id in nearby_buckets:
                        if nearby_id in position_buckets:
                            nearby_candidates.extend(position_buckets[nearby_id])
                    
                    # Now check pairs within nearby candidates (O(k²) where k << n)
                    for i, (c1, t1) in enumerate(candidates_in_bucket):
                        for c2, t2 in nearby_candidates:
                            if c1 == c2:
                                continue
                            dist = abs(t1.position - t2.position)
                            if dist < 50: # Physically close
                                # Boost compatibility for both
                                for role in [r1, r2]:
                                    for cand in [c1, c2]:
                                        key = (cand, role)
                                        if key in graph.compatibility:
                                            # Boost proportional to law strength and physical proximity
                                            proximity_factor = (50 - dist) / 50.0
                                            boost = 0.1 * strength * proximity_factor
                                            graph.compatibility[key] = min(1.0, graph.compatibility[key] + boost)

    # Build exclusivity edges
    reng = _get_role_engine()
    for role_a, role_b in ROLE_EXCLUSIVITY:
        if role_a in graph.roles and role_b in graph.roles:
            graph.exclusivity_edges.append((role_a, role_b))
            
    # Dynamic topological exclusions
    role_names = list(graph.roles.keys())
    for i in range(len(role_names)):
        for j in range(i + 1, len(role_names)):
            r1, r2 = role_names[i], role_names[j]
            if (r1, r2) in graph.exclusivity_edges or (r2, r1) in graph.exclusivity_edges:
                continue
            if reng.get_learned_exclusion(r1, r2) > _adaptive_exclusion_threshold():
                graph.exclusivity_edges.append((r1, r2))

    graph.coherence_score = _compute_allocation_coherence(graph)
    return graph


def _infer_role_type(role_name: str) -> SemanticType:
    """Infer the expected SemanticType for a role name."""
    reng = _get_role_engine()
    
    # 1. Anchor to bootstrap seed
    field_lower = role_name.lower()
    seed_type = SemanticType.TEXT
    for roots, stype in _UNIVERSAL_ROOTS:
        if any(root in field_lower for root in roots):
            seed_type = stype
            break

    # 2. Check manifold geometry
    best_type = SemanticType.TEXT
    best_compat = 0.55
    
    for t in SemanticType:
        compat = reng.get_compatibility(role_name, t)
        if compat > best_compat:
            best_compat = compat
            best_type = t

    # 3. Identity Protection: only switch if overwhelmingly stable
    if seed_type != SemanticType.TEXT:
        return best_type if best_compat > 0.9 else seed_type
    return best_type


def _compute_compatibility(
    token: SemanticToken, role_name: str, role: SemanticRole
) -> float:
    """Geometric compatibility: emergent from Role Manifold similarity."""
    reng = _get_role_engine()
    learned_compat = reng.get_compatibility(role_name, token.primary_type, token=token)

    # Ambiguity penalty (universal entropy constraint)
    dist = token.type_distribution
    if dist and len(dist) > 1:
        primary_conf = dist.get(token.primary_type, 0.5)
        learned_compat *= primary_conf

    return max(0.0, min(1.0, learned_compat))


def optimize_semantic_assignment(graph: AllocationGraph) -> AllocationGraph:
    """Optimize semantic role assignment globally."""
    assigned_candidates: Set[str] = set()
    filled_roles: Set[str] = set()
    field_conflicts: list = []

    assignments = sorted(
        [(score, cand, role) for (cand, role), score in graph.compatibility.items()],
        key=lambda x: -x[0],
    )

    from app.semantic_world_state import get_world_state
    ws = get_world_state()
    topo_view = ws.get_topology_view()
    field_owned_roles: Set[str] = set()
    for region in topo_view.all_regions():
        if region.instability > 0.3:
            for role in region.competing_roles:
                field_owned_roles.add(role)

    for score, cand_key, role_name in assignments:
        if role_name in field_owned_roles:
            conflicts_with_field = any(
                region.token == cand_key
                for region in topo_view.all_regions()
                if role_name in region.competing_roles
            )
            if conflicts_with_field:
                already_assigned_to_peer = False
                for ra, rb in graph.exclusivity_edges:
                    peer = rb if role_name == ra else (ra if role_name == rb else None)
                    if peer and peer in filled_roles and graph.roles[peer].filled_by == cand_key:
                        already_assigned_to_peer = True
                        break
                if already_assigned_to_peer:
                    field_conflicts.append({"role": role_name, "candidate": cand_key, "reason": "exclusivity:self", "score": score})
                    continue

        if cand_key in assigned_candidates or role_name in filled_roles:
            continue

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
            field_conflicts.append({"role": role_name, "candidate": cand_key, "reason": conflict_reason, "score": score})
            continue

        graph.roles[role_name].filled_by = cand_key
        graph.roles[role_name].fill_confidence = score
        assigned_candidates.add(cand_key)
        filled_roles.add(role_name)

    graph.field_conflicts = field_conflicts
    graph.coherence_score = _compute_allocation_coherence(graph)
    return graph


def _compute_allocation_coherence(graph: AllocationGraph) -> float:
    """Compute coherence of the allocation."""
    if not graph.roles:
        return 0.0

    filled = sum(1 for r in graph.roles.values() if r.filled_by is not None)
    fill_ratio = filled / len(graph.roles)

    confidences = [r.fill_confidence for r in graph.roles.values() if r.filled_by is not None]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    exclusivity_violations = 0
    for role_a, role_b in graph.exclusivity_edges:
        if role_a in graph.roles and role_b in graph.roles:
            ra, rb = graph.roles[role_a], graph.roles[role_b]
            if ra.filled_by and rb.filled_by and ra.filled_by == rb.filled_by:
                exclusivity_violations += 1
    exclusivity_score = 1.0 - (exclusivity_violations / max(len(graph.exclusivity_edges), 1))

    coherence = (fill_ratio * 0.3) + (avg_conf * 0.5) + (exclusivity_score * 0.2)
    return min(coherence, 1.0)


def allocate_semantic_roles(
    record: SemanticRecord,
    schema_fields: List[str],
    learn: bool = True,
    abstraction_gradient: float = 0.0,
) -> Tuple[SemanticRecord, AllocationGraph]:
    """Full semantic allocation for a record with Hierarchical support."""
    graph = build_allocation_graph(record, schema_fields, abstraction_gradient=abstraction_gradient)
    graph = optimize_semantic_assignment(graph)

    for role_name, role in graph.roles.items():
        if role.filled_by:
            record.mapped_fields[role_name] = role.filled_by
            record.mapped_confidences[role_name] = role.fill_confidence

    record.overall_confidence = graph.coherence_score

    # Semantic Entropy Filter (Phase 18)
    # High entropy (disorder) in the graph indicates unreliable interpretation.
    ws = _get_role_engine().ws
    # Quality gated by global field pressure and local coherence
    is_unstable = (graph.coherence_score < 0.3) or (ws.metrics.global_entropy > 0.8)
    record.is_unstable = is_unstable
    graph.is_unstable = is_unstable

    if not learn:
        return record, graph

    reng = _get_role_engine()
    candidates = [(cand, role, score) for (cand, role), score in graph.compatibility.items()]
    hypotheses = []
    
    for _strategy, key_fn in [
        ('primary', lambda x: -x[2]),
        ('noisy', lambda x: -x[2] + random.random() * 0.05),
        ('random', lambda x: random.random()),
    ]:
        h = _run_allocation(graph, sorted(candidates, key=key_fn))
        hypotheses.append(h)
    
    hypotheses.sort(key=lambda h: h['coherence'])
    
    if len(hypotheses) >= 2:
        best = hypotheses[-1]
        worst = hypotheses[0]
        if (best['coherence'] - worst['coherence']) > 0.15:
            for role_name in graph.roles:
                best_val = best['roles'].get(role_name)
                worst_val = worst['roles'].get(role_name)
                
                if best_val and worst_val and best_val != worst_val:
                    token = graph.candidates.get(best_val)
                    if token:
                        reng.learn_from_allocation(role_name, token.primary_type, token.raw, success=True, delta=0.05, coherence=best['coherence'])
                    
                    token2 = graph.candidates.get(worst_val)
                    if token2:
                        reng.learn_from_allocation(role_name, token2.primary_type, token2.raw, success=False, delta=0.05, coherence=best['coherence'])
    
    return record, graph


def _run_allocation(graph: AllocationGraph, sorted_assignments: list) -> dict:
    """Run a full allocation given a sorted assignment list."""
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
                
        if not conflicting:
            reng = _get_role_engine()
            for filled_role in filled:
                if g.roles.get(filled_role) and g.roles[filled_role].filled_by == cand_key:
                    if reng.get_learned_exclusion(role_name, filled_role) > _adaptive_runtime_exclusion_threshold():
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

def explain_assignment(role_name: str, candidate_val: str, graph: AllocationGraph) -> dict:
    """Explain why a role was assigned to a candidate using topological evidence."""
    if role_name not in graph.roles:
        return {"error": f"Role {role_name} not found in graph"}
    
    token = graph.candidates.get(candidate_val)
    if not token:
        return {"error": f"Candidate {candidate_val} not found in graph"}
    
    reng = _get_role_engine()
    ws = reng.ws
    
    # 1. Manifold Evidence
    compat = reng.get_compatibility(role_name, token.primary_type, token=token)
    
    # 2. Community Evidence
    community = None
    comm_pull = 0.0
    for comm in ws.global_communities:
        if role_name in comm:
            community = list(comm)
            # Find strongest community presence in this graph
            for peer_role in comm:
                if peer_role != role_name and peer_role in graph.roles:
                    peer_role_obj = graph.roles[peer_role]
                    if peer_role_obj.filled_by:
                        comm_pull = max(comm_pull, peer_role_obj.fill_confidence)
            break
            
    # 3. Schema Evidence
    schema_pattern_match = False
    current_roles = sorted(graph.roles.keys())
    for i in range(len(current_roles)):
        for j in range(i + 1, len(current_roles)):
            pair = (current_roles[i], current_roles[j])
            if pair in ws.schema_patterns:
                schema_pattern_match = True
                break
        if schema_pattern_match:
            break
        
    return {
        "role": role_name,
        "candidate": candidate_val,
        "evidence": {
            "manifold_compatibility": round(compat, 3),
            "community_pull": round(comm_pull, 3),
            "community_context": community,
            "learned_schema_match": schema_pattern_match,
        },
        "coherence_contribution": round(graph.coherence_score, 3)
    }
