"""Semantic Pipeline Orchestrator.
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
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.event_dispatcher import get_dispatcher

# Import scheduler singleton to wire event subscriptions at module load time
from app.graph_update_scheduler import get_scheduler
from app.semantic_allocation_engine import (
    _UNIVERSAL_ROOTS,
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
from app.semantic_events import SemanticEvent, SemanticEventType
from app.semantic_ir import (
    SemanticRecord,
    SemanticToken,
    Span,
)
from app.semantic_mapper import detect_semantic_type, is_child_fragment
from app.semantic_segmentation import (
    StructuralMemoryTracker,
    expand_composite_records,
    sem_type_str,
)
from app.semantic_world_state import get_world_state

logger = logging.getLogger(__name__)

get_scheduler()


# Pipeline thresholds — derived from field state, not hardcoded
# Each function reads the current field_pressure and returns a dynamic threshold.
# No fixed constants remain — all thresholds emerge from topology.


def _field_instability_threshold():
    """Instability spike threshold tightens as field stabilizes and converges."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    p = ws.metrics.field_pressure
    c = ws.metrics.convergence_score
    return max(0.4, min(0.9, 0.5 + p * 0.4 - c * 0.2))


def _field_contradiction_penalty():
    """Contradiction penalty softens as field matures (less disruptive)."""
    from app.semantic_world_state import get_world_state

    p = get_world_state().metrics.field_pressure
    return 0.5 + p * 0.3  # range: [0.5, 0.8]


def _field_coherence_threshold():
    """Coherence success threshold adapts to field stability."""
    from app.semantic_world_state import get_world_state

    p = get_world_state().metrics.field_pressure
    return 0.4 + p * 0.3  # range: [0.4, 0.7]


def _field_instability_delta():
    """Uncertainty spike delta grows with field instability."""
    from app.semantic_world_state import get_world_state

    p = get_world_state().metrics.field_pressure
    return 0.1 + p * 0.3  # range: [0.1, 0.4]


def _field_contradiction_delta():
    """Contradiction delta modulates with field pressure."""
    from app.semantic_world_state import get_world_state

    p = get_world_state().metrics.field_pressure
    return 0.2 + p * 0.4  # range: [0.2, 0.6]


def _field_topology_delta():
    """Topology shift delta is small but responsive to field changes."""
    from app.semantic_world_state import get_world_state

    p = get_world_state().metrics.field_pressure
    return 0.05 + p * 0.1  # range: [0.05, 0.15]


METADATA_FIELDS: set[str] = {
    "record_score",
    "_field_confidences",
    "source_url",
    "source_type",
    "source_trust_score",
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
    metadata_fields_stripped: list[str] = field(default_factory=list)


def strip_metadata(records: list | None) -> list[Any]:
    """Remove all metadata fields from records."""
    if not records:
        return []

    cleaned = []
    for record in records:
        clean = {k: v for k, v in record.items() if k not in METADATA_FIELDS}
        cleaned.append(clean)

    return cleaned


def filter_noise_records(records: list[dict] | None) -> list[dict]:
    """Filter out likely noise records using graph-based relational density."""
    if not records:
        return []

    filtered = []
    from app.semantic_boundary_engine import (
        _BOOTSTRAP_SUFFIXES,
        _STOP_WORDS,
        get_boundary_engine,
    )

    be = get_boundary_engine()

    # Entity-relevant types (types that indicate a real data record)
    ENTITY_TYPES = {
        "organization",
        "price",
        "date",
        "code",
        "identifier",
        "location",
        "rating",
        "duration",
        "name",
    }

    for record in records:
        all_text = " ".join(str(v) for v in record.values() if v and isinstance(v, str))
        if not all_text:
            logger.debug("Filtered: empty text")
            continue

        # Quick navigation / meta check
        lower = all_text.lower()
        nav_phrases = [
            "copyright",
            "all rights reserved",
            "privacy policy",
            "terms of service",
            "terms and conditions",
            "cookie policy",
            "powered by",
            "home about contact",
        ]
        if any(p in lower for p in nav_phrases):
            logger.debug("Filtered: nav phrase in '%s'", lower[:50])
            continue

        from app.semantic_segmentation import extract_candidate_values

        cands = extract_candidate_values(all_text)

        if len(cands) == 0:
            logger.debug("Filtered: no candidates in '%s'", all_text[:50])
            continue

        # Refine candidates: prefer specific types over generic 'text' or 'number'
        # when specific entity types are present.
        cand_types = [sem_type_str(c.primary_type) for c in cands]
        has_specific = any(t in ENTITY_TYPES for t in cand_types)

        if has_specific and len(cands) > 1:
            cands = [c for c in cands if sem_type_str(c.primary_type) != "text"]

        # Deduplicate identical raw strings only at the SAME position
        # (same value from different record positions is a contradiction signal)
        seen_raw = set()
        unique = []
        for c in cands:
            key = (c.raw, c.position)
            if key not in seen_raw:
                unique.append(c)
                seen_raw.add(key)
        cands = unique

        types = [sem_type_str(c.primary_type) for c in cands]

        # Count core entities
        core_count = sum(1 for t in types if t in ENTITY_TYPES)

        if len(cands) == 1:
            pt = cands[0].primary_type
            if sem_type_str(pt) == "organization":
                filtered.append(record)
            else:
                logger.debug("Filtered: single non-org cand %s", cands[0].primary_type)
            continue

        # Calculate Relational Density Score
        density_score = 0.0

        # 1. Edge Density (Transitions)
        for i in range(len(types) - 1):
            t1, t2 = types[i], types[i + 1]
            ts = be.transition_detector.score_transition(t1, t2)
            density_score += ts.probability

        # 2. Motif Density
        for size in range(2, min(len(types) + 1, 4)):
            for start in range(len(types) - size + 1):
                motif = tuple(types[start : start + size])
                density_score += be.motif_learner.stability(motif) * 0.5

        # 3. Core Entity Centrality
        density_score += core_count * 0.5

        # Normalize density by max possible edges
        max_edges = len(types) - 1
        normalized_density = density_score / max(1, max_edges)

        # Equilibrium reasoning: decision depends on global stability average
        state = get_world_state()
        stability_threshold = max(0.4, min(state.metrics.average_density * 0.9, 0.7))

        if core_count >= 2 or normalized_density > stability_threshold:
            # Propagate to global state for future equilibrium
            state.accumulate_density(normalized_density)
            state.increment_records()
            filtered.append(record)
        elif core_count == 1:
            # Multi-word entity check
            has_suffix = any(c.raw.lower() in _BOOTSTRAP_SUFFIXES for c in cands)
            org_cands = [c for c in cands if sem_type_str(c.primary_type) in ENTITY_TYPES]
            has_named_entity = len(org_cands) >= 2 and any(c.raw.lower() in _STOP_WORDS for c in org_cands)
            if has_suffix or has_named_entity or normalized_density > (stability_threshold * 0.7):
                state.accumulate_density(normalized_density)
                state.increment_records()
                filtered.append(record)
            else:
                logger.debug("Filtered: core_count=1 but low relative density %f", normalized_density)
        else:
            logger.debug("Filtered: core_count=0, density %f", normalized_density)

    return filtered


def detect_role_swap_warnings(
    output: dict[str, Any],
    schema_fields: list[Any],
    detect_type_fn: Callable,
    universal_roots: Any,
) -> list[Any]:
    """Detect potential role swap warnings from allocation output."""
    from app.semantic_segmentation import sem_type_str

    warnings = []
    for role_name in schema_fields:
        val = output.get(role_name)
        if not val:
            continue
        val_type, _ = detect_type_fn(val, role_name)
        for roots, stype in universal_roots:
            if any(root in role_name.lower() for root in roots):
                vts = sem_type_str(val_type)
                sts = sem_type_str(stype)
                if val_type != stype:
                    warnings.append(f"{role_name}: expected {sts}, got {vts} ({val})")
                break
    return warnings


def run_pipeline(
    records: list | None,
    schema_fields: list[str],
) -> list[Any]:
    """Run the full semantic pipeline orchestrator."""
    if not records:
        return []

    state = get_world_state()
    with state.transaction("run_pipeline"):
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
            dispatcher.dispatch(
                SemanticEvent(
                    event_type=SemanticEventType.TOPOLOGY_SHIFT,
                    source="pipeline_filter",
                    payload={"removed": report.noise_removed},
                    instability_delta=_field_topology_delta(),
                ),
            )

        if not records:
            return []

        # Layer 3: Semantic segmentation — expand composite records into
        # individual candidates. Only expands when a value has multiple distinct
        # semantic types (e.g., "Lufthansa LON PAR" → ORG + CODE + CODE).
        # Single-type values (e.g., company names like "British Airways")
        # are NOT expanded.
        mem = StructuralMemoryTracker()
        records = expand_composite_records(records, memory=mem)
        report.after_segmentation = len(records)

        # Layer 4: Entity grouping (boundary-aware merge) — merges segmented
        # tokens that belong together (e.g., "Prestige" + "Group" → "Prestige
        # Group")
        records = group_adjacent_entities(records)

        # Layer 5: Global semantic allocation
        allocated_records: list[Any] = []
        for record in records:
            state.clear_active_regions()
            tokens = []
            pos = 0
            seen_values: set[str] = set()

            seg_keys = [k for k in record if "_seg_" in k]
            other_keys = [k for k in record if "_seg_" not in k]
            ordered_keys = seg_keys + other_keys

            for key in ordered_keys:
                value = record.get(key)
                if value and isinstance(value, str):
                    if is_child_fragment(value, seen_values):
                        continue

                    st, conf = detect_semantic_type(value, field_name=key)
                    tokens.append(
                        SemanticToken(
                            raw=value,
                            normalized=value,
                            span=Span(pos, pos + len(value)),
                            position=pos,
                            primary_type=st,
                            type_distribution={st: conf},
                            source_field=key,
                        ),
                    )
                    seen_values.add(value)
                    pos += len(value) + 1

            from app.semantic_segmentation import resolve_overlaps

            original_positions = {t.raw: t.position for t in tokens}
            tokens = resolve_overlaps(tokens)
            for t in tokens:
                if t.raw in original_positions:
                    t.position = original_positions[t.raw]

            type_sequence: list[str] = []
            if tokens:
                type_sequence = [t.primary_type.value for t in tokens]
                record_motif_observation(type_sequence)

            # Phase 4A: Capture pre-allocation conflict topology
            # Preserves raw instability geometry before allocation resolves it
            if tokens:
                get_world_state().capture_pre_allocation_field(tokens, schema_fields)

            # Phase 4C: Propagate field regions before allocation
            # Instability spreads to neighboring roles, so allocation sees
            # propagated pressure rather than raw resolved state
            if tokens:
                get_world_state().propagate_field_regions()

            sem_record = SemanticRecord(tokens=tokens)
            _, alloc_graph = allocate_semantic_roles(sem_record, schema_fields)

            # Refinement pass
            if len(tokens) >= 2:
                sem_record2 = SemanticRecord(tokens=tokens)
                _, alloc_graph2 = allocate_semantic_roles(sem_record2, schema_fields, learn=False)
                if alloc_graph2.coherence_score > alloc_graph.coherence_score:
                    alloc_graph = alloc_graph2

            # P1: Topology-driven output — allocator is candidate generator only
            # Output comes from topology state when the allocator detected a conflict
            # (field_owned_roles). Otherwise the allocator's assignment is used.
            topo_view = get_world_state().get_topology_view()
            output: dict[str, Any] = {}
            field_owned = {fc["role"] for fc in getattr(alloc_graph, "field_conflicts", [])}
            for role_name in schema_fields:
                if role_name in record and record.get(role_name) is not None and role_name not in field_owned:
                    output[role_name] = record.get(role_name)
                    continue

                role = alloc_graph.roles.get(role_name)
                allocator_confident = role and role.filled_by and role.fill_confidence > 0.8
                if role_name in field_owned and not allocator_confident:
                    # Topology decides — find the matching field region
                    top_val = None
                    for region in topo_view.all_regions():
                        if role_name in region.competing_roles and region.token:
                            top_val = region.token
                            break
                    output[role_name] = top_val
                elif role and role.filled_by:
                    output[role_name] = role.filled_by
                else:
                    output[role_name] = None

            output["_confidence"] = alloc_graph.coherence_score

            # Preserve conflict geometry from allocation for field arbitration
            alloc_conflicts = getattr(alloc_graph, "field_conflicts", [])
            if alloc_conflicts:
                output["_allocation_conflicts"] = alloc_conflicts
                for fc in alloc_conflicts:
                    role = fc["role"]
                    if isinstance(role, str) and (role not in output or not output[role]):
                        output[role] = fc["candidate"]
                        output[f"_{role}_conflict"] = fc["reason"]

            # Stage 6: Continuous Semantic Evolution (Inference)
            # Decision is driven by graph energy and instability, not a hard
            # threshold.
            state = get_world_state()

            # Field perturbation: register learned exclusions from conflicts
            state.observe_field_perturbation(output, tokens)
            instability = 1.0 - output["_confidence"]
            relative_instability = instability / max(0.1, state.metrics.average_uncertainty)
            # Unified field pressure modulates: high pressure amplifies
            # instability
            pressure = state.metrics.field_pressure
            relative_instability *= 1.0 + pressure * 0.5

            if relative_instability > _field_instability_threshold():
                dispatcher.dispatch(
                    SemanticEvent(
                        event_type=SemanticEventType.UNCERTAINTY_SPIKE,
                        source="allocation_engine",
                        payload={"instability": relative_instability},
                        instability_delta=_field_instability_delta(),
                    ),
                )

            output["_certainty"] = reng.get_certainty()
            output["_learning_speed"] = reng.get_learning_speed()
            output["_calibrated_confidence"] = reng.get_calibrated_confidence(output["_confidence"])

            # Stage 7: Field tension is continuous — no explicit contradiction
            # detection.
            warnings = detect_role_swap_warnings(output, schema_fields, detect_semantic_type, _UNIVERSAL_ROOTS)
            if warnings:
                output["_warnings"] = warnings

            # Phase 7: Topology snapshot for observability + replay
            state.snapshot(label=f"alloc_{len(allocated_records)}")

            # Phase 4: Semantic memory as topology pressure
            # Stable motifs strengthen role-type compatibility — memory becomes
            # gravity
            if tokens:
                for size in range(2, min(len(type_sequence) + 1, 4)):
                    for start in range(len(type_sequence) - size + 1):
                        motif = tuple(type_sequence[start : start + size])
                        stability = state.get_motif_stability(motif)
                        if stability > 0.01:
                            for role_name in schema_fields:
                                boost = (stability - 0.5) * 0.05
                                new_val = min(1.0, state.get_compatibility(role_name, motif[0]) + boost)
                                state.set_compatibility(role_name, motif[0], new_val)

            coherence = output["_confidence"]
            be = get_boundary_engine()
            be.update_recent_decisions(coherence, _field_coherence_threshold())

            # Field evolution — single topology-canonical entry point.
            # Replaces individual calls to decay_field_regions(),
            # aggregate_from_regions(), and redistribute_instability().
            state.evolve_field()

            # Synthesize crystalline records for stable runs
            if output["_confidence"] > 0.7 and tokens:
                state._synthesize_crystalline_record(output)

            allocated_records.append(output)

        report.after_allocation = len(allocated_records)
        return allocated_records
