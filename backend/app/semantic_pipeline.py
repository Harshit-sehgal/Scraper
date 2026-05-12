"""
Semantic Pipeline Orchestrator
================================
Clean layered pipeline that separates:
1. Extraction → raw records
2. Metadata stripping → clean records
3. Noise filtering → entity-only records  
4. Segmentation → semantic candidates
5. Global allocation → role-assigned fields
6. Validation → verified schema output

Metadata must NEVER participate in semantic mapping.
Each layer has ONE responsibility.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set

from app.semantic_ir import (
    SemanticToken, SemanticType, SemanticRecord, DatasetIR, Span,
)
from app.semantic_allocation_engine import allocate_semantic_roles, _get_role_engine
from app.semantic_boundary_engine import score_boundary, record_boundary_feedback, record_motif_observation, get_boundary_engine, _BOOTSTRAP_SUFFIXES, _STOP_WORDS
from app.semantic_segmentation import expand_composite_records, StructuralMemoryTracker, extract_candidate_values


# Seed patterns are now embedded in _seed_role_engine as substring-based
# type hints. This approach generalizes across languages without manual
# translation tables. Seeds are bootstraps — the feedback loop overrides
# them over time.


# Minimal universal semantic roots for bootstrap seeding.
# These are the smallest possible set that covers common semantic categories.
# The cache-derived matching handles everything else.
_UNIVERSAL_ROOTS = [
    (['pric', 'cost', 'prec', 'wert', 'salar'], SemanticType.PRICE),
    (['date', 'zeit'], SemanticType.DATE),
    (['loc', 'city', 'addr', 'ort'], SemanticType.LOCATION),
    (['nam', 'comp', 'firm', 'brand', 'make', 'model', 'builder'], SemanticType.ORGANIZATION),
    (['rat', 'scor', 'bewert'], SemanticType.RATING),
    (['count', 'anzahl', 'experien', 'year', 'mileage', 'age'], SemanticType.NUMBER),
    (['code', 'currenc', 'wahrung', 'ident'], SemanticType.CODE),
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


def _seed_role_engine(schema_fields: list):
    """Seed the RoleEmbeddingEngine with initial role-type compatibilities.

    Combines two strategies:
    1. Universal roots: 5 minimal semantic patterns for common categories.
    2. Cache-derived: nearest-neighbor matching against known role names.

    Both are bootstraps — the feedback loop overrides seeds over time.
    """
    reng = _get_role_engine()
    
    for field in schema_fields:
        field_lower = field.lower()
        
        # Strategy 1: Universal roots
        best_type = SemanticType.TEXT
        for roots, stype in _UNIVERSAL_ROOTS:
            if any(root in field_lower for root in roots):
                best_type = stype
                break
        
        # Strategy 2: Cache-derived nearest neighbor (only if roots gave no answer)
        if best_type == SemanticType.TEXT:
            best_score = 0.0
            for (known_role, type_str), compat in reng.compatibility_cache.items():
                if compat < 0.6:
                    continue
                sim = _name_similarity(field, known_role)
                if sim > best_score:
                    best_score = sim
                    if sim > 0.55:
                        best_type = SemanticType(type_str)
        
        key = (field, best_type.value)
        if key not in reng.compatibility_cache:
            reng.compatibility_cache[key] = 0.7


def _warm_start_from_values(records: list, schema_fields: list):
    """Warm-start the RoleEmbeddingEngine using actual value classifications.

    Classifies the VALUES from the first record and uses those to seed
    the engine. This generalizes to unseen domains without manual hints.
    """
    if not records or not schema_fields:
        return
    
    reng = _get_role_engine()
    first = records[0]
    
    for field in schema_fields:
        val = first.get(field)
        if not isinstance(val, str) or not val.strip():
            continue
        
        st, conf = _detect_semantic_type(val, field)
        key = (field, st.value)
        if key not in reng.compatibility_cache:
            reng.compatibility_cache[key] = 0.7


def _group_adjacent_entities(records: list) -> list:
    """Merge consecutive segmented values that form multi-token entities."""
    if not records:
        return records

    for record in records:
        # First, suppress child fragments
        seen = set()
        keys_to_delete = []
        for k in list(record.keys()):
            v = record.get(k)
            if v and isinstance(v, str):
                if _is_child_fragment(v, seen):
                    keys_to_delete.append(k)
                seen.add(v)
        for k in keys_to_delete:
            if k in record:
                del record[k]

        def _sort_key(k):
            parts = k.rsplit('_', 1)
            return int(parts[-1]) if parts[-1].isdigit() else 0

        seg_keys = sorted([k for k in record if '_seg_' in k], key=_sort_key)
        if len(seg_keys) < 2:
            continue

        merged = set()
        i = 0
        while i < len(seg_keys) - 1:
            k1, k2 = seg_keys[i], seg_keys[i + 1]
            t1 = k1.split('_')[-2] if len(k1.split('_')) >= 3 else ''
            t2 = k2.split('_')[-2] if len(k2.split('_')) >= 3 else ''

            v1, v2 = record.get(k1, ''), record.get(k2, '')
            if v1 and v2:
                should_merge = score_boundary(t1, t2, v1, v2, i, i + 1)
                if should_merge and k1 not in merged and k2 not in merged:
                    record[k1] = f"{v1} {v2}"
                    record[k2] = None
                    merged.add(k2)
                    i += 2
                    continue
            i += 1

        for k in merged:
            if k in record:
                del record[k]

    return records


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
    """Remove all metadata fields from records.

    Only schema-content fields survive.
    record_score, _field_confidences, source_* are removed.
    """
    if not records:
        return records if records is not None else []

    cleaned = []
    for record in records:
        clean = {k: v for k, v in record.items() if k not in METADATA_FIELDS}
        cleaned.append(clean)

    return cleaned


def filter_noise_records(records: List[dict]) -> List[dict]:
    """Filter out likely noise records using graph-based relational density.

    A record is considered meaningful if its tokens form a dense semantic graph
    (e.g., they have valid transitions, form recognizable motifs, or represent
    a core entity with attributes). Contact-only or isolated tokens lack this density.
    """
    if not records:
        return []
    
    filtered = []
    from app.semantic_boundary_engine import get_boundary_engine, _BOOTSTRAP_SUFFIXES, _STOP_WORDS
    be = get_boundary_engine()
    
    # Entity-relevant types (types that indicate a real data record)
    ENTITY_TYPES = {'organization', 'price', 'date', 'code', 'location', 'rating', 'duration', 'name'}
    
    for record in records:
        all_text = " ".join(str(v) for v in record.values() if v and isinstance(v, str))
        if not all_text:
            continue
        
        # Quick navigation/meta check before expensive extraction
        lower = all_text.lower()
        nav_phrases = ["copyright", "all rights reserved", "privacy policy", "terms of service",
                       "terms and conditions", "cookie policy", "powered by", "home about contact"]
        if any(p in lower for p in nav_phrases):
            continue

        from app.semantic_segmentation import extract_candidate_values
        cands = extract_candidate_values(all_text)
        
        if len(cands) == 0:
            continue
            
        types = [c.primary_type for c in cands]
        
        # Count core entities
        core_count = sum(1 for t in types if t in ENTITY_TYPES)
        
        if len(cands) == 1:
            # Single token records are only valid if they are strong entities (Org)
            if cands[0].primary_type == 'organization':
                filtered.append(record)
            continue
            
        # Calculate Relational Density Score
        density_score = 0.0
        
        # 1. Edge Density (Transitions)
        for i in range(len(types) - 1):
            t1, t2 = types[i], types[i+1]
            ts = be.transition_detector.score_transition(t1, t2)
            density_score += ts.probability
            
        # 2. Motif Density
        for size in range(2, min(len(types) + 1, 4)):
            for start in range(len(types) - size + 1):
                motif = tuple(types[start:start + size])
                density_score += be.motif_learner.stability(motif) * 0.5
                
        # 3. Core Entity Centrality
        density_score += core_count * 0.5
        
        # Normalize density by max possible edges
        max_edges = len(types) - 1
        normalized_density = density_score / max(1, max_edges)
        
        # If it's pure contact/noise info, core_count is usually 0 and density is low.
        if core_count >= 2 or normalized_density > 0.8:
            filtered.append(record)
        elif core_count == 1:
            # Multi-word entity check
            has_suffix = any(c.raw.lower() in _BOOTSTRAP_SUFFIXES for c in cands)
            org_cands = [c for c in cands if c.primary_type in ENTITY_TYPES]
            has_named_entity = len(org_cands) >= 2 and any(c.raw.lower() in _STOP_WORDS for c in org_cands)
            if has_suffix or has_named_entity or normalized_density > 0.6:
                 filtered.append(record)
                 
    return filtered


def run_pipeline(
    records: list,
    schema_fields: List[str],
) -> list:
    """Run the full semantic pipeline on extracted records.

    Returns clean, allocated, validated records.
    """
    if not records:
        return []
    
    # Load persisted learning cache (if available)
    reng = _get_role_engine()
    import os
    from app.semantic_boundary_engine import get_boundary_engine
    be = get_boundary_engine()
    
    cache_path = os.environ.get('SEMANTIC_CACHE_PATH', '/tmp/semantic_cache.json')
    boundary_cache_path = os.environ.get('SEMANTIC_BOUNDARY_CACHE_PATH', '/tmp/semantic_boundary_cache.json')
    
    if reng.learning_count == 0:
        reng.load_from_file(cache_path)
    if be.motif_learner.total_records == 0:
        be.load_from_file(boundary_cache_path)
    
    # Bootstrap: seed the RoleEmbeddingEngine using substring hints + value warm-start
    if schema_fields:
        _seed_role_engine(schema_fields)
        _warm_start_from_values(records, schema_fields)
    
    report = PipelineReport(input_records=len(records))
    
    # Layer 1: Strip metadata
    records = strip_metadata(records)
    report.after_metadata_strip = len(records)

    # Layer 2: Filter noise
    noise_count = len(records)
    records = filter_noise_records(records)
    report.noise_removed = noise_count - len(records)
    report.after_noise_filter = len(records)

    if not records:
        return []

    # Layer 3: Semantic segmentation
    mem = StructuralMemoryTracker()
    records = expand_composite_records(records, memory=mem)
    report.after_segmentation = len(records)
    
    # Entity grouping: merge consecutive segments that form multi-token entities
    # (e.g., "Prestige" + "Group" → "Prestige Group", "iPhone" + "16" → "iPhone 16")
    records = _group_adjacent_entities(records)
    
    # Layer 4: Global semantic allocation with overlap suppression
    allocated_records = []
    for record in records:
        # Convert dict to SemanticRecord
        tokens = []
        pos = 0
        seen_values = set()  # Suppress child fragments that duplicate parent values
        # Process segmented values first (composite text), then standalone fields.
        # This preserves positional ordering for text values.
        seg_keys = [k for k in record if '_seg_' in k]
        other_keys = [k for k in record if '_seg_' not in k]
        ordered_keys = seg_keys + other_keys
        
        for key in ordered_keys:
            value = record.get(key)
            if value and isinstance(value, str):
                # Skip child fragments that are parts of larger values
                # (e.g., "22" from "22-05-2026", "238" from "£238")
                if _is_child_fragment(value, seen_values):
                    continue

                st, conf = _detect_semantic_type(value, field_name=key)
                tokens.append(SemanticToken(
                    raw=value, normalized=value,
                    span=Span(pos, pos + len(value)), position=pos,
                    primary_type=st,
                    type_distribution={st: conf},
                    source_field=key,
                ))
                seen_values.add(value)
                pos += len(value) + 1

        # Run overlap resolution to suppress any remaining child fragments
        from app.overlap_resolution import resolve_overlaps
        # Save original positions before overlap resolution (which resets them)
        original_positions = {t.raw: t.position for t in tokens}
        tokens = resolve_overlaps(tokens)
        # Restore original positions so positional ordering works correctly
        for t in tokens:
            if t.raw in original_positions:
                t.position = original_positions[t.raw]
        
        # Record motif observation for structural learning
        if tokens:
            type_sequence = [t.primary_type.value for t in tokens]
            record_motif_observation(type_sequence)

        sem_record = SemanticRecord(tokens=tokens)
        allocated, alloc_graph = allocate_semantic_roles(sem_record, schema_fields)

        # Two-pass refinement: second pass with learning disabled.
        # The first pass already updated the cache via comparative learning.
        # The second pass uses the improved cache without further corruption.
        if len(tokens) >= 2:
            sem_record2 = SemanticRecord(tokens=tokens)
            allocated2, alloc_graph2 = allocate_semantic_roles(sem_record2, schema_fields, learn=False)
            if alloc_graph2.coherence_score > alloc_graph.coherence_score:
                alloc_graph = alloc_graph2
                allocated = allocated2

        # Build output dict from allocation
        output = {}
        for role_name in schema_fields:
            role = alloc_graph.roles.get(role_name)
            if role and role.filled_by:
                output[role_name] = role.filled_by
            else:
                output[role_name] = None  # Empty is better than wrong

        output["_confidence"] = alloc_graph.coherence_score
        
        # Stage 3: Run InferenceEngine only when allocation confidence is low.
        if output["_confidence"] < 0.6 and tokens:
            from app.semantic_inference_engine import InferenceEngine
            try:
                ie = InferenceEngine(max_iterations=3)
                ie_result = ie.infer(tokens, schema_fields)
                if ie_result and ie_result.role_assignments:
                    ie_coherence = ie_result.coherence_score
                    if ie_coherence > output["_confidence"]:
                        for role_name, value in ie_result.role_assignments.items():
                            if value:
                                output[role_name] = value
                        output["_confidence"] = ie_coherence
                        output["_refined_by"] = "inference_engine"
            except Exception:
                pass
        
        # Add calibration from RoleEmbeddingEngine learning state
        output["_certainty"] = reng.get_certainty()
        output["_learning_speed"] = reng.get_learning_speed()
        output["_calibrated_confidence"] = reng.get_calibrated_confidence(output["_confidence"])
        
        # Stage 3: Contradiction detection
        # Check for duplicate values across different schema fields (contradiction)
        filled_vals = {}
        contradictions = []
        for role_name in schema_fields:
            val = output.get(role_name)
            if val:
                if val in filled_vals:
                    contradictions.append(f'{filled_vals[val]}={val} and {role_name}={val}')
                filled_vals[val] = role_name
        if contradictions:
            output["_contradictions"] = contradictions
            output["_confidence"] *= 0.7
            
            # Layer 5: Contradiction-aware learning
            # Penalize both roles' compatibility with this value's type
            for role_name in schema_fields:
                val = output.get(role_name)
                if val:
                    for other_role in schema_fields:
                        if other_role != role_name and output.get(other_role) == val:
                            val_type, _ = _detect_semantic_type(val, "")
                            reng.learn_from_allocation(role_name, val_type, val, success=False, delta=0.15)
                            if hasattr(reng, 'learn_contradiction'):
                                reng.learn_contradiction(role_name, other_role, val_type.value)
        
        # Role swap detection: check if value types match field expectations
        warnings = []
        for role_name in schema_fields:
            val = output.get(role_name)
            if not val:
                continue
            val_type, _ = _detect_semantic_type(val, role_name)
            seed_type = SemanticType.TEXT
            # Determine expected type from universal roots
            for roots, stype in _UNIVERSAL_ROOTS:
                if any(root in role_name.lower() for root in roots):
                    seed_type = stype
                    break
            # Flag type mismatch between expected role type and actual value type
            if seed_type != SemanticType.TEXT and val_type != seed_type:
                warnings.append(f'{role_name}: expected {seed_type.value}, got {val_type.value} ({val})')
                # Layer 5: Contradiction-aware learning
                # Penalize this mismatched type heavily so it learns not to do this again
                reng.learn_from_allocation(role_name, val_type, val, success=False, delta=0.2)
        if warnings:
            output["_warnings"] = warnings
            
        # Layer 8: Meta-cognition diagnostics (Decision Explanation)
        reasoning = []
        for role_name in schema_fields:
            val = output.get(role_name)
            if val:
                val_type, conf = _detect_semantic_type(val, role_name)
                compat = reng.compatibility_cache.get((role_name, val_type.value), 0.5)
                if compat > 0.7:
                    reasoning.append(f"Mapped '{val}' ({val_type.value}) to {role_name} due to high learned compatibility ({compat:.2f}).")
                elif conf > 0.8:
                    reasoning.append(f"Mapped '{val}' to {role_name} based on strong value structure ({val_type.value}).")
                else:
                    reasoning.append(f"Mapped '{val}' to {role_name} via structural best-fit (compatibility: {compat:.2f}).")
        
        if contradictions:
            reasoning.append(f"Penalized confidence due to contradictory claims: {', '.join(contradictions)}.")
        
        output["_reasoning"] = reasoning
        
        # Record merge/split feedback for boundary engine learning
        coherence = output["_confidence"]
        be = get_boundary_engine()
        for md in be.decision_history[-20:]:
            md.coherence_after = coherence
            # Update: success = coherence > 0.6
            md.success = coherence > 0.6
        
        allocated_records.append(output)

    report.after_allocation = len(allocated_records)

    # Persist learned cache for next session
    if reng.learning_count > 0:
        reng.save_to_file(cache_path)
    if be.motif_learner.total_records > 0:
        be.save_to_file(boundary_cache_path)

    return allocated_records


def _detect_semantic_type(value: str, field_name: str = "") -> Tuple[SemanticType, float]:
    import re

    # Field-name hinting (NOT domain-specific - just field role disambiguation)
    name_lower = field_name.lower()

    # Price detection (currency symbol OR numeric in a price-type field)
    if re.search(r"[\$\u20a8\u20ac\u00a3\u00a5\u20b9]", value):
        return SemanticType.PRICE, 0.95
    if any(k in name_lower for k in ["price", "cost", "fare", "amount", "salary"]):
        if re.search(r"\d+", value):
            return SemanticType.PRICE, 0.80

    # Date detection
    if re.search(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", value):
        return SemanticType.DATE, 0.90

    # Code detection (all-uppercase 2-5 chars)
    if re.search(r"^[A-Z]{2,5}$", value):
        return SemanticType.CODE, 0.80

    # Rating detection
    if re.search(r"\d+\.?\d*/\d+", value):
        return SemanticType.RATING, 0.85

    # Duration detection
    if re.search(r"\d+h\s*\d*m|\d+h$", value):
        return SemanticType.DURATION, 0.85

    # Phone detection
    if re.search(r"\+?\d[\d\s\-\(\)]{7,}", value):
        return SemanticType.PHONE, 0.85

    # Stop/quantifier detection - keep as number
    if re.search(r"\d+\s*(stop|direct|non.?stop)", value, re.IGNORECASE):
        return SemanticType.NUMBER, 0.70
    
    # Numeric with suffix (25L, 5+, 10K, 1.2Cr)
    if re.search(r"^\d+\.?\d*[LkKmM]?$", value) and len(value) > 1:
        return SemanticType.NUMBER, 0.60
    if re.search(r"^\d+[+]$", value):
        return SemanticType.NUMBER, 0.60
    # Unit-suffixed numbers: "45000 m", "45000 miles", "1200 sqft"
    if re.search(r"^\d+[\.]?\d*\s+(mi|km|m|ft|sqft|lbs|kg|g|hrs?|hours?|min|sec)", value, re.IGNORECASE):
        return SemanticType.NUMBER, 0.60

    # Generic number
    if re.search(r"^\d+\.?\d*$", value) and len(value) >= 1:
        return SemanticType.NUMBER, 0.60

    # Organization-like (Title Case text)
    if value and value[0].isupper():
        return SemanticType.ORGANIZATION, 0.55
    
    # Product-like (brand naming: starts lowercase, has internal uppercase)
    # Examples: iPhone, iPad, eBay, macOS
    if value and len(value) >= 3 and value[0].islower():
        has_internal_upper = any(c.isupper() for c in value[1:])
        if has_internal_upper:
            return SemanticType.ORGANIZATION, 0.50

    return SemanticType.TEXT, 0.50


def _is_child_fragment(value: str, seen_values: set) -> bool:
    """Check if a value is a child fragment of an already-seen larger value.

    Example: "22" is a child fragment of "22-05-2026"
             "5" is a child fragment of "4.2/5"
             "238" is a child fragment of "£238"
    """
    if not value:
        return False

    for seen in seen_values:
        if len(seen) > len(value) and value in seen:
            import re
            # Only suppress if the child is a prefix or suffix of the parent
            # (prevents suppressing "5" from "25L" where "5" is in the middle)
            # Exception: date children don't need prefix/suffix check
            is_date = re.search(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", seen)
            if not is_date and not (seen.startswith(value) or seen.endswith(value)):
                continue
            if re.search(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", seen):
                if re.match(r"^\d+$", value):
                    return True
            if re.search(r"[\$\u20a8\u20ac\u00a3\u00a5\u20b9]", seen):
                if re.match(r"^\d+$", value):
                    return True
            if "/" in seen and re.search(r"\d+\.?\d*/", seen):
                if re.match(r"^\d+\.?\d*$", value):
                    return True
            if re.search(r"\d+\.?\d*\s*[a-zA-Z]+$", seen):
                if re.match(r"^\d+\.?\d*$", value):
                    return True
                # Also suppress alphabetic fragments that are the unit suffix
                # e.g., "Cr" is a child of "1.2 Cr"
                if re.match(r"^[a-zA-Z]+$", value) and seen.lower().endswith(value.lower()):
                    return True
            # Price parent → number child: "£238" ⊃ "238"
            if re.search(r"[\$\u20a8\u20ac\u00a3\u00a5\u20b9]", seen):
                if re.match(r"^\d+$", value):
                    return True
            # Rating parent → number child: "4.2/5" ⊃ "4.2" or "5"
            if "/" in seen and re.search(r"\d+\.?\d*/", seen):
                if re.match(r"^\d+\.?\d*$", value):
                    return True
    return False
