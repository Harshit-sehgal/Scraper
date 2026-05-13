
"""
Semantic Pipeline Orchestrator
================================
Clean layered pipeline that strictly orchestrates the semantic flow.

Flow:
1. Strip metadata
2. Filter noise
3. Segmentation (expand composite records)
4. Entity grouping (boundary-aware merge)
5. Global allocation (multi-hypothesis role assignment)
6. Continuous Evolution (Inference relaxation)
7. Contradiction Topology (Conflict propagation)
8. Diagnostics (Topological introspection)
"""

import logging
from dataclasses import dataclass, field
from typing import List, Set

from app.semantic_allocation_engine import (
    _get_role_engine,
    allocate_semantic_roles,
    seed_role_engine,
    warm_start_from_values,
)
from app.semantic_boundary_engine import (
    get_boundary_engine,
    group_adjacent_entities,
    record_motif_observation,
)
from app.semantic_ir import (
    SemanticRecord,
    SemanticToken,
    Span,
)
from app.semantic_mapper import detect_semantic_type, is_child_fragment
from app.semantic_segmentation import StructuralMemoryTracker, expand_composite_records
from app.semantic_world_state import get_world_state
from app.event_dispatcher import get_dispatcher
from app.semantic_events import SemanticEvent, SemanticEventType


# Pipeline thresholds — isolated as named constants for observability
_INSTABILITY_SPIKE_THRESHOLD = 0.8
_CONTRADICTION_CONFIDENCE_PENALTY = 0.7
_COHERENCE_SUCCESS_THRESHOLD = 0.6
_DIAGNOSTIC_HISTORY_WINDOW = 20
_UNCERTAINTY_SPIKE_DELTA = 0.3
_CONTRADICTION_DELTA = 0.5
_TOPOLOGY_SHIFT_DELTA = 0.1
_INFERENCE_COHERENCE_FALLBACK = 0.5
_EVOLUTION_REFINE_MIN_TOKENS = 2
_EVOLUTION_REALLOC_MIN_TOKENS = 2


METADATA_FIELDS: Set[str] = {
    "record_score", "_field_confidences",
    "source_url", "source_type", "source_trust_score",
}


@dataclass
class PipelineReport:
    """Report of pipeline operations."""
    input_records: int = 0
    after_metadata_strip: int = 0
    after_noise_filter: int = 0
    after_segmentation: int = 0
    after_allocation: int = 0
    after_validation: int = 0
    noise_removed: int = 0
    metadata_fields_stripped: List[str] = field(default_factory=list)


def strip_metadata(records: list) -> list:
    """Remove all metadata fields from records."""
    if not records:
        return records if records is not None else []

    cleaned = []
    for record in records:
        clean = {k: v for k, v in record.items() if k not in METADATA_FIELDS}
        cleaned.append(clean)

    return cleaned


def filter_noise_records(records: List[dict]) -> List[dict]:
    """Filter out likely noise records using graph-based relational density."""
    if not records:
        return []
    
    filtered = []
    from app.semantic_boundary_engine import (
        _BOOTSTRAP_SUFFIXES,
        _STOP_WORDS,
        get_boundary_engine,
    )
    from app.semantic_ir import SemanticType
    be = get_boundary_engine()
    
    # Entity-relevant types (types that indicate a real data record)
    ENTITY_TYPES = {
        'organization', 'price', 'date', 'code', 'location', 'rating', 'duration', 'name'
    }
    
    for record in records:
        all_text = " ".join(str(v) for v in record.values() if v and isinstance(v, str))
        if not all_text:
            logging.getLogger(__name__).debug("Filtered: empty text")
            continue
        
        # Quick navigation/meta check
        lower = all_text.lower()
        nav_phrases = ["copyright", "all rights reserved", "privacy policy", "terms of service",
                       "terms and conditions", "cookie policy", "powered by", "home about contact"]
        if any(p in lower for p in nav_phrases):
            logging.getLogger(__name__).debug("Filtered: nav phrase in '%s'", lower[:50])
            continue

        from app.semantic_segmentation import extract_candidate_values
        cands = extract_candidate_values(all_text)
        
        if len(cands) == 0:
            logging.getLogger(__name__).debug("Filtered: no candidates in '%s'", all_text[:50])
            continue
            
        # Refine candidates: prefer specific types over generic 'text' or 'number'
        # when specific entity types are present.
        cand_types = [(c.primary_type.value if hasattr(c.primary_type, 'value') else str(c.primary_type)) for c in cands]
        has_specific = any(t in ENTITY_TYPES for t in cand_types)
        
        if has_specific and len(cands) > 1:
            cands = [c for c in cands if (c.primary_type.value if hasattr(c.primary_type, 'value') else str(c.primary_type)) != 'text']
        
        # Deduplicate identical raw strings
        seen_raw = set()
        unique = []
        for c in cands:
            if c.raw not in seen_raw:
                unique.append(c)
                seen_raw.add(c.raw)
        cands = unique
        
        types = [(c.primary_type.value if hasattr(c.primary_type, 'value') else str(c.primary_type)) for c in cands]
        
        # Count core entities
        core_count = sum(1 for t in types if t in ENTITY_TYPES)
        
        if len(cands) == 1:
            if cands[0].primary_type == SemanticType.ORGANIZATION:
                filtered.append(record)
            else:
                logging.getLogger(__name__).debug("Filtered: single non-org cand %s", cands[0].primary_type)
            continue
            
        # Calculate Relational Density Score
        density_score = 0.0
        
        # 1. Edge Density (Transitions)
        for i in range(len(types) - 1):
            t1, t2 = types[i], types[i+1]
            ts = be.transition_detector.score_transition(t1.value if hasattr(t1, 'value') else str(t1), 
                                                        t2.value if hasattr(t2, 'value') else str(t2))
            density_score += ts.probability
            
        # 2. Motif Density
        for size in range(2, min(len(types) + 1, 4)):
            for start in range(len(types) - size + 1):
                motif = tuple(t.value if hasattr(t, 'value') else str(t) for t in types[start:start + size])
                density_score += be.motif_learner.stability(motif) * 0.5
                
        # 3. Core Entity Centrality
        density_score += core_count * 0.5
        
        # Normalize density by max possible edges
        max_edges = len(types) - 1
        normalized_density = density_score / max(1, max_edges)
        
        # Equilibrium reasoning: decision depends on global stability average
        from app.semantic_world_state import get_world_state
        state = get_world_state()
        stability_threshold = max(0.4, min(state.metrics.average_density * 0.9, 0.7))

        if core_count >= 2 or normalized_density > stability_threshold:
            # Propagate to global state for future equilibrium
            state.metrics.cumulative_density += normalized_density
            state.metrics.total_records_processed += 1
            filtered.append(record)
        elif core_count == 1:
            # Multi-word entity check
            has_suffix = any(c.raw.lower() in _BOOTSTRAP_SUFFIXES for c in cands)
            org_cands = [c for c in cands if (c.primary_type.value if hasattr(c.primary_type, 'value') else str(c.primary_type)) in ENTITY_TYPES]
            has_named_entity = len(org_cands) >= 2 and any(c.raw.lower() in _STOP_WORDS for c in org_cands)
            if has_suffix or has_named_entity or normalized_density > (stability_threshold * 0.7):
                 state.metrics.cumulative_density += normalized_density
                 state.metrics.total_records_processed += 1
                 filtered.append(record)
            else:
                 logging.getLogger(__name__).debug("Filtered: core_count=1 but low relative density %f", normalized_density)
        else:
            logging.getLogger(__name__).debug("Filtered: core_count=0, density %f", normalized_density)
                 
    return filtered


def run_pipeline(
    records: list,
    schema_fields: List[str],
) -> list:
    """Run the full semantic pipeline orchestrator."""
    if not records:
        return []
    
    reng = _get_role_engine()
    be = get_boundary_engine()
    dispatcher = get_dispatcher()
    
    # Bootstrap engines
    if schema_fields:
        seed_role_engine(schema_fields)
        warm_start_from_values(records, schema_fields)
    
    report = PipelineReport(input_records=len(records))
    
    # Layer 1: Strip metadata
    records = strip_metadata(records)
    report.after_metadata_strip = len(records)

    # Layer 2: Filter noise
    noise_count = len(records)
    records = filter_noise_records(records)
    report.noise_removed = noise_count - len(records)
    report.after_noise_filter = len(records)
    
    if report.noise_removed > 0:
        dispatcher.dispatch(SemanticEvent(
            event_type=SemanticEventType.TOPOLOGY_SHIFT,
            source="pipeline_filter",
            payload={"removed": report.noise_removed},
            instability_delta=_TOPOLOGY_SHIFT_DELTA
        ))

    if not records:
        return []

    # Layer 3: Semantic segmentation
    mem = StructuralMemoryTracker()
    records = expand_composite_records(records, memory=mem)
    report.after_segmentation = len(records)
    
    # Layer 4: Entity grouping (boundary-aware merge)
    records = group_adjacent_entities(records)
    
    # Layer 5: Global semantic allocation
    allocated_records = []
    for record in records:
        tokens = []
        pos = 0
        seen_values: set[str] = set()
        
        seg_keys = [k for k in record if '_seg_' in k]
        other_keys = [k for k in record if '_seg_' not in k]
        ordered_keys = seg_keys + other_keys
        
        for key in ordered_keys:
            value = record.get(key)
            if value and isinstance(value, str):
                if is_child_fragment(value, seen_values):
                    continue

                st, conf = detect_semantic_type(value, field_name=key)
                tokens.append(SemanticToken(
                    raw=value, normalized=value,
                    span=Span(pos, pos + len(value)), position=pos,
                    primary_type=st,
                    type_distribution={st: conf},
                    source_field=key,
                ))
                seen_values.add(value)
                pos += len(value) + 1

        from app.overlap_resolution import resolve_overlaps
        original_positions = {t.raw: t.position for t in tokens}
        tokens = resolve_overlaps(tokens)
        for t in tokens:
            if t.raw in original_positions:
                t.position = original_positions[t.raw]
        
        if tokens:
            type_sequence = [t.primary_type.value for t in tokens]
            record_motif_observation(type_sequence)

        sem_record = SemanticRecord(tokens=tokens)
        _, alloc_graph = allocate_semantic_roles(sem_record, schema_fields)

        # Refinement pass
        if len(tokens) >= _EVOLUTION_REFINE_MIN_TOKENS:
            sem_record2 = SemanticRecord(tokens=tokens)
            _, alloc_graph2 = allocate_semantic_roles(sem_record2, schema_fields, learn=False)
            if alloc_graph2.coherence_score > alloc_graph.coherence_score:
                alloc_graph = alloc_graph2
                
        output: dict = {}
        for role_name in schema_fields:
            role = alloc_graph.roles.get(role_name)
            if role and role.filled_by:
                output[role_name] = role.filled_by
            else:
                output[role_name] = None

        output["_confidence"] = alloc_graph.coherence_score
        
        # Stage 6: Continuous Semantic Evolution (Inference)
        # Decision is driven by graph energy and instability, not a hard threshold.
        state = get_world_state()
        instability = 1.0 - output["_confidence"]
        relative_instability = instability / max(0.1, state.metrics.average_uncertainty)
        
        if relative_instability > _INSTABILITY_SPIKE_THRESHOLD:
            dispatcher.dispatch(SemanticEvent(
                event_type=SemanticEventType.UNCERTAINTY_SPIKE,
                source="allocation_engine",
                payload={"instability": relative_instability},
                instability_delta=_UNCERTAINTY_SPIKE_DELTA
            ))

        if relative_instability > _INSTABILITY_SPIKE_THRESHOLD and tokens:
            from app.semantic_inference_engine import InferenceEngine
            try:
                # Inference as Iterative Graph Relaxation
                ie = InferenceEngine(max_iterations=5)
                ie_result = ie.infer(tokens, schema_fields)
                if ie_result and ie_result.role_assignments:
                    # Check if inference reduced entropy (improved coherence)
                    ie_coherence = getattr(ie_result, 'coherence_score', _INFERENCE_COHERENCE_FALLBACK)
                    if ie_coherence > output["_confidence"]:
                        for role_name, value in ie_result.role_assignments.items():
                            if value:
                                output[role_name] = value
                        output["_confidence"] = ie_coherence
                        output["_refined_by"] = "evolution_pass"
            except Exception as exc:
                logging.exception(exc)
        
        output["_certainty"] = reng.get_certainty()
        output["_learning_speed"] = reng.get_learning_speed()
        output["_calibrated_confidence"] = reng.get_calibrated_confidence(output["_confidence"])
        
        # Stage 7: Contradiction & Warnings
        from app.semantic_contradiction_engine import (
            apply_contradiction_learning,
            detect_allocation_contradictions,
            detect_role_swap_warnings,
        )
        contradictions = detect_allocation_contradictions(output, schema_fields)
        if contradictions:
            output["_contradictions"] = contradictions
            output["_confidence"] *= _CONTRADICTION_CONFIDENCE_PENALTY
            output["_contradiction_energy"] = len(contradictions)
            dispatcher.dispatch(SemanticEvent(
                event_type=SemanticEventType.CONTRADICTION_DETECTED,
                source="contradiction_engine",
                payload={"conflicts": contradictions},
                instability_delta=_CONTRADICTION_DELTA
            ))

        from app.semantic_allocation_engine import _UNIVERSAL_ROOTS
        warnings = detect_role_swap_warnings(output, schema_fields, detect_semantic_type, _UNIVERSAL_ROOTS)
        if warnings:
            output["_warnings"] = warnings
            
        apply_contradiction_learning(output, schema_fields, reng, detect_semantic_type, contradictions, warnings, _UNIVERSAL_ROOTS)

        # Re-allocation pass: feed contradiction pressure back into the graph
        if contradictions and len(tokens) >= _EVOLUTION_REALLOC_MIN_TOKENS:
            sem_record3 = SemanticRecord(tokens=tokens)
            _, re_alloc_graph = allocate_semantic_roles(sem_record3, schema_fields, learn=False)
            if re_alloc_graph.coherence_score > output["_confidence"]:
                for role_name in schema_fields:
                    role = re_alloc_graph.roles.get(role_name)
                    if role and role.filled_by:
                        output[role_name] = role.filled_by
                output["_confidence"] = re_alloc_graph.coherence_score
                output["_contradiction_resolved"] = True
            
        # Stage 8: Diagnostics
        from app.semantic_diagnostics import generate_allocation_diagnostics
        output["_reasoning"] = generate_allocation_diagnostics(
            output, schema_fields, reng, contradictions, detect_semantic_type, tokens=tokens
        )
        
        coherence = output["_confidence"]
        be = get_boundary_engine()
        for md in be.decision_history[-_DIAGNOSTIC_HISTORY_WINDOW:]:
            md.coherence_after = coherence
            md.success = coherence > _COHERENCE_SUCCESS_THRESHOLD
        
        allocated_records.append(output)

    report.after_allocation = len(allocated_records)
    return allocated_records
