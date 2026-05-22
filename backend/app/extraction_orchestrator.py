"""
Extraction Orchestrator — Manages the multi-layered extraction fallback cascade.

Layers:
  1. Selector Profiles (JSON)
  2. Selector Memory (Persistent cache)
  3. LLM Discovery (Generative)
  4. Regex Fallback (Structural pattern matching)
"""

from __future__ import annotations

import logging
from app.config import settings
from app.models import SchemaField
from app.selector_memory import get_selector_memory
from app.selector_discovery import discover_selectors
from app.selector_engine import apply_selectors, extract_with_regex
from app.domain_intelligence import get_domain_intelligence
from app.extraction_provenance import ProvenanceBuilder, ExtractionMethod

logger = logging.getLogger(__name__)


class ExtractionResult:
    def __init__(
        self, 
        records: list[dict], 
        method: str, 
        selector_success: bool = False,
        selectors: dict | None = None
    ):
        self.records = records
        self.method = method
        self.selector_success = selector_success
        self.selectors = selectors or {}


def _merge_composite_records(
    records_list: list[list[dict]],
    schema_fields: list[SchemaField],
) -> list[dict]:
    """Merge records from multiple extraction passes into a composite result.
    
    For complex pages (mixed data, multiple structures), different extraction
    passes may yield different subsets of fields. This merges them intelligently:
    - If two records have the same key field (e.g., name/title), they're merged
    - Records with disjoint field sets are kept separately
    - Higher-confidence values overwrite lower-confidence ones
    """
    if not records_list:
        return []
    
    # If only one pass produced results, return as-is
    if len(records_list) == 1:
        return records_list[0]
    
    # Use the first schema field as the deduplication key 
    # (the user controls field ordering, so the first field is the best candidate)
    id_field = schema_fields[0].name if schema_fields else "name"
    
    from app.data_utils import normalize_scraped_record
    
    merged: dict[str, dict] = {}
    
    for pass_records in records_list:
        for record in pass_records:
            # Try to deduplicate by id_field value
            key_val = str(record.get(id_field, "")).strip()
            norm_key = normalize_scraped_record({id_field: key_val}, schema_fields)[id_field] if key_val else ""
            
            if norm_key and norm_key in merged:
                # Merge — existing takes priority unless new has higher score
                existing = merged[norm_key]
                for field, value in record.items():
                    if field == "record_score":
                        continue
                    existing_val = existing.get(field)
                    if not existing_val or (
                        existing_val in (None, "") and value not in (None, "")
                    ):
                        existing[field] = value
                # Recompute score
                from app.utils.quality import score_record_quality
                existing["record_score"] = score_record_quality(existing, schema_fields)
            else:
                new_record = dict(record)
                # Generate a synthetic key if no id_field value
                if not norm_key:
                    combined = "|".join(str(v) for v in new_record.values() if v not in (None, ""))
                    norm_key = combined if combined else str(len(merged))
                if norm_key not in merged:
                    merged[norm_key] = new_record
    
    result = list(merged.values())
    result.sort(key=lambda r: r.get("record_score", 0.0), reverse=True)
    return result


def _multi_pass_extraction(
    html: str,
    schema_fields: list[SchemaField],
    selectors_map: dict,
    base_url: str = "",
    user_intent: str = "",
) -> list[dict]:
    """Try multiple extraction strategies on the same HTML for complex pages.
    
    Pass 1: Standard extraction using the primary item_container
    Pass 2: If results are sparse, try with alternative container selectors
    Pass 3: Fall back to individual field extraction (no container)
    """
    from app.selector_engine import apply_selectors, extract_raw_from_selectors
    
    # Pass 1: Standard extraction
    pass1 = apply_selectors(
        html, selectors_map, schema_fields,
        base_url=base_url, user_intent=user_intent,
    )
    if not isinstance(pass1, list):
        pass1 = []
    
    # If pass1 is good enough, return it
    if pass1 and len(pass1) >= 3:
        scores = [r.get("record_score", 0.0) for r in pass1]
        avg_score = sum(scores) / len(scores)
        if avg_score > 0.5:
            return pass1
    
    passes = [pass1]
    
    # Pass 2: Try alternative containers (different selectors that might match)
    container = selectors_map.get("item_container", "")
    if container:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        
        # Try parent/ancestor levels
        alt_containers = []
        for el in soup.select(container)[:3]:
            parent = el.parent if hasattr(el, 'parent') and el.parent and el.parent.name != '[document]' else None
            if parent and parent.name not in ('html', 'body'):
                # Build a selector for parent
                parent_sel = parent.name
                if parent.get('class'):
                    classes = parent.get('class')
                    if isinstance(classes, list):
                        parent_sel += '.' + '.'.join(classes[:2])
                if parent_sel != container:
                    alt_containers.append(parent_sel)
        
        for alt_sel in alt_containers[:2]:
            alt_map = dict(selectors_map)
            alt_map["item_container"] = alt_sel
            try:
                alt_result = apply_selectors(
                    html, alt_map, schema_fields,
                    base_url=base_url, user_intent=user_intent,
                )
                if isinstance(alt_result, list) and alt_result:
                    passes.append(alt_result)
            except Exception:
                pass
    
    # Pass 3: Raw extraction without container (extract from full page)
    if not pass1 or (passes and len(passes) == 1):
        try:
            raw = extract_raw_from_selectors(html, selectors_map, base_url=base_url)
            if raw:
                from app.data_utils import align_extracted_keys_to_schema
                from app.utils.quality import score_record_quality
                aligned = align_extracted_keys_to_schema(
                    raw, schema_fields, user_intent=user_intent,
                )
                for rec in aligned:
                    rec["record_score"] = score_record_quality(rec, schema_fields)
                passes.append([r for r in aligned if r.get("record_score", 0) > 0])
        except Exception:
            pass
    
    # Merge all passes
    return _merge_composite_records(passes, schema_fields)


async def orchestrate_extraction(
    url: str,
    html: str,
    schema_fields: list[SchemaField],
    min_record_score: float,
    provenance_builder: ProvenanceBuilder | None = None,
    world_state=None,
    user_intent: str = "",
    provided_selectors: dict | None = None,
) -> ExtractionResult:
    """Cascade through extraction methods until high-quality data is found.

    Optionally accepts a ``ProvenanceBuilder`` to track field-level extraction
    provenance for explainability.
    Uses multi-pass extraction for complex pages.

    If ``provided_selectors`` is given (from URL analysis), it is tried as
    the primary extraction method — replacing memory and LLM discovery.
    The cascade falls back to regex if provided selectors fail.
    """
    memory = get_selector_memory()
    intel = get_domain_intelligence().get_intelligence(url)

    gate_threshold = max(
        min_record_score * settings.SCORE_GATE_THRESHOLD_FACTOR, 
        settings.SCORE_GATE_ABSOLUTE_MIN
    )

    def _record_field_provenance(
        records: list[dict],
        method: str,
        selectors: dict | None = None,
    ):
        """Record provenance for all fields in all extracted records."""
        if not provenance_builder:
            return
        fields_sel = (selectors or {}).get("fields", {})
        for idx, record in enumerate(records):
            for field in schema_fields:
                val = record.get(field.name)
                selector = fields_sel.get(field.name)
                provenance_builder.add_field_provenance(
                    record_idx=idx,
                    field_name=field.name,
                    value=val,
                    method=method,
                    selector=selector,
                    confidence=record.get("record_score", 0.5),
                )
    
    # Phase 79/80: Strategy Self-Selection
    preferred = intel.preferred_strategy

    if preferred == "regex":
        if intel.success_count > 3 or intel.anti_bot_risk > 0.7:
            logger.info("[Orchestrator] Selecting proven REGEX strategy for %s", url)
            regex_results = extract_with_regex(html, schema_fields, base_url=url)
            if regex_results:
                scores = [r.get("record_score", 0.0) for r in regex_results]
                avg = sum(scores) / len(scores) if scores else 0.0
                if avg >= gate_threshold:
                    _record_field_provenance(regex_results, ExtractionMethod.REGEX)
                    return ExtractionResult(regex_results, "regex")
                logger.info("[Orchestrator] Preferred REGEX returned low quality (avg: %.2f), falling through to cascade", avg)
            else:
                logger.info("[Orchestrator] Preferred REGEX failed, falling through to cascade")

    # ── Layer 2: Provided Selectors (from URL Analysis) ───────────────
    # If the user analyzed the URL via the URL Analyzer, we have pre-discovered
    # CSS selectors. Try these first — they skip memory and LLM discovery.
    if provided_selectors and provided_selectors.get("item_container") and provided_selectors.get("fields"):
        logger.info("[Orchestrator] Trying provided selectors from URL analysis for %s", url)
        provided_results = _multi_pass_extraction(
            html, schema_fields, provided_selectors,
            base_url=url, user_intent=user_intent,
        )
        if provided_results:
            scores = [r.get("record_score", 0.0) for r in provided_results]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            if avg_score >= gate_threshold:
                logger.info("[Orchestrator] Provided selectors SUCCESS (avg score: %.2f)", avg_score)
                memory.record_success(url, provided_selectors)
                _record_field_provenance(provided_results, ExtractionMethod.DISCOVERY, provided_selectors)
                return ExtractionResult(provided_results, "discovery", selector_success=True, selectors=provided_selectors)
            else:
                logger.info("[Orchestrator] Provided selectors LOW QUALITY (avg score: %.2f), falling through", avg_score)
                if provenance_builder:
                    provenance_builder.add_fallback_step("provided_selectors_low_quality")
        else:
            logger.info("[Orchestrator] Provided selectors returned no results, falling through")
            if provenance_builder:
                provenance_builder.add_fallback_step("provided_selectors_empty")

    # ── Layer 3: Selector Memory ───────────────────────────────────────
    remembered_selectors = memory.get_selectors(url)
    if remembered_selectors:
        logger.info("[Orchestrator] Trying remembered selectors for %s", url)
        raw_results = apply_selectors(
            html, remembered_selectors, schema_fields, base_url=url, user_intent=user_intent
        )
        if raw_results:
            # Ensure raw_results is a list (apply_selectors returns list when return_field_quality=False)
            assert isinstance(raw_results, list)
            scores = [r.get("record_score", 0.0) for r in raw_results]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            if avg_score >= gate_threshold:
                logger.info("[Orchestrator] Memory SUCCESS (avg score: %.2f)", avg_score)
                memory.record_success(url, remembered_selectors)
                _record_field_provenance(raw_results, ExtractionMethod.MEMORY, remembered_selectors)
                return ExtractionResult(raw_results, "memory", selector_success=True, selectors=remembered_selectors)
            else:
                logger.info("[Orchestrator] Memory FAILURE (avg score: %.2f)", avg_score)
                memory.record_failure(url)
                if provenance_builder:
                    provenance_builder.add_fallback_step("memory_failed")
                
                # Emit SelectorFailureEvent to support event-driven decouple loops (Phase 82)
                try:
                    from app.event_dispatcher import get_dispatcher
                    from app.semantic_events import SemanticEvent, SemanticEventType
                    get_dispatcher().dispatch(SemanticEvent(
                        event_type=SemanticEventType.SELECTOR_FAILURE,
                        source="extraction_orchestrator",
                        payload={"url": url, "avg_score": avg_score}
                    ))
                except Exception as e:
                    logger.warning("[Orchestrator] Failed to dispatch selector failure event: %s", e)

    # ── Layer 3: LLM Discovery ─────────────────────────────────────────
    logger.info("[Orchestrator] Initiating LLM discovery for %s", url)
    
    # Get learned motifs if world_state is available
    solidified_motifs = None
    if world_state:
        solidified_motifs = world_state.solidified_motifs
        if solidified_motifs:
            logger.info("[Orchestrator] Using %d learned motifs for discovery guidance", len(solidified_motifs))
    
    discovered_selectors = await discover_selectors(html, schema_fields, solidified_motifs=solidified_motifs)
    
    if discovered_selectors and discovered_selectors.get("item_container"):
        # Phase 81: Semantic Alignment Pass + Multi-Pass Extraction
        # We run multi-pass extraction to handle complex pages (mixed data types,
        # nested containers, partial field sets).
        
        # First, do a quality check pass with field tracking
        result = apply_selectors(
            html,
            discovered_selectors,
            schema_fields,
            base_url=url,
            return_field_quality=True,
            user_intent=user_intent,
        )
        
        # Handle tuple return value
        if isinstance(result, tuple):
            raw_results, field_quality = result
        else:
            raw_results = result
            field_quality = {}
            
        logger.info("[Orchestrator] FIELD QUALITY MAP: %s", field_quality)
        
        # Check for field-swapping
        swapped = _detect_field_swaps(field_quality, schema_fields)
        if swapped:
            logger.warning("[Orchestrator] Detected field swap in discovery: %s. Attempting alignment.", swapped)
            discovered_selectors = _align_selectors(discovered_selectors, swapped)
            if provenance_builder:
                provenance_builder.add_error(f"Field swap detected and aligned: {swapped}")
        
        # Multi-pass extraction for complex pages
        raw_results = _multi_pass_extraction(
            html, schema_fields, discovered_selectors,
            base_url=url, user_intent=user_intent,
        )
            
        if raw_results:
            scores = [r.get("record_score", 0.0) for r in raw_results]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            if avg_score >= gate_threshold:
                logger.info("[Orchestrator] Discovery SUCCESS (avg score: %.2f)", avg_score)
                memory.record_success(url, discovered_selectors)
                _record_field_provenance(raw_results, ExtractionMethod.DISCOVERY, discovered_selectors)
                return ExtractionResult(raw_results, "discovery", selector_success=True, selectors=discovered_selectors)
            else:
                logger.info("[Orchestrator] Discovery LOW QUALITY (avg score: %.2f)", avg_score)
                if provenance_builder:
                    provenance_builder.add_fallback_step("discovery_low_quality")

    # ── Layer 4: Regex Fallback ────────────────────────────────────────
    logger.info("[Orchestrator] Falling back to regex extraction for %s", url)
    regex_results = extract_with_regex(html, schema_fields, base_url=url)
    _record_field_provenance(regex_results, ExtractionMethod.REGEX)
    if provenance_builder:
        provenance_builder.add_fallback_step("regex_fallback")
    return ExtractionResult(regex_results, "regex")


def _detect_field_swaps(quality_map: dict[str, float], fields: list[SchemaField]) -> dict[str, str]:
    """Identify likely field swaps based on type incompatibility.
    
    Returns a map of field_name -> correct_field_name if a swap is likely.
    Uses only FieldType information — no hardcoded field names.
    
    Logic: if two fields have very low quality AND their types are 
    obviously incompatible (e.g., a BOOLEAN field extracting what looks like
    a long text string, and a STRING field extracting what looks like 
    a boolean), swapping their selectors might help.
    
    Since we lack access to extracted values here, this is a placeholder
    for future value-aware swap detection. Currently returns empty.
    """
    return {}

def _align_selectors(selectors: dict, swaps: dict) -> dict:
    """Re-map selectors based on detected swaps."""
    if not swaps:
        return selectors
        
    field_sels = selectors.get("fields", {})
    new_sels = dict(field_sels)
    
    for current_field, target_field in swaps.items():
        if current_field in field_sels and target_field in field_sels:
            # Swap them
            new_sels[current_field] = field_sels[target_field]
            new_sels[target_field] = field_sels[current_field]
            
    selectors["fields"] = new_sels
    return selectors
