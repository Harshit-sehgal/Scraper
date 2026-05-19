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


async def orchestrate_extraction(
    url: str,
    html: str,
    schema_fields: list[SchemaField],
    min_record_score: float,
    provenance_builder: ProvenanceBuilder | None = None,
    world_state=None,
) -> ExtractionResult:
    """Cascade through extraction methods until high-quality data is found.

    Optionally accepts a ``ProvenanceBuilder`` to track field-level extraction
    provenance for explainability.
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
        # Jump straight to regex if it's historically successful
        if intel.success_count > 3 or intel.anti_bot_risk > 0.7:
            logger.info("[Orchestrator] Selecting proven REGEX strategy for %s", url)
            regex_results = extract_with_regex(html, schema_fields, base_url=url)
            if regex_results:
                _record_field_provenance(regex_results, ExtractionMethod.REGEX)
                return ExtractionResult(regex_results, "regex")
            logger.info("[Orchestrator] Preferred REGEX failed, falling through to cascade")

    # ── Layer 2: Selector Memory ───────────────────────────────────────
    remembered_selectors = memory.get_selectors(url)
    if remembered_selectors:
        logger.info("[Orchestrator] Trying remembered selectors for %s", url)
        raw_results = apply_selectors(html, remembered_selectors, schema_fields, base_url=url)
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
        # Phase 81: Semantic Alignment Pass
        # We run apply_selectors with field quality tracking to see if the LLM
        # swapped fields (common with dynamic grids).
        result = apply_selectors(
            html, discovered_selectors, schema_fields, base_url=url, return_field_quality=True
        )
        
        # Handle tuple return value
        if isinstance(result, tuple):
            raw_results, field_quality = result
        else:
            raw_results = result
            field_quality = {}
        
        # Check for field-swapping
        swapped = _detect_field_swaps(field_quality, schema_fields)
        if swapped:
            logger.warning("[Orchestrator] Detected field swap in discovery: %s. Attempting alignment.", swapped)
            discovered_selectors = _align_selectors(discovered_selectors, swapped)
            if provenance_builder:
                provenance_builder.add_error(f"Field swap detected and aligned: {swapped}")
            # Re-apply with aligned selectors
            raw_results = apply_selectors(html, discovered_selectors, schema_fields, base_url=url)
            # Ensure it's a list
            assert isinstance(raw_results, list)
            
        if raw_results:
            assert isinstance(raw_results, list)
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
    """Identify likely field swaps based on semantic quality scores.
    
    Returns a map of field_name -> correct_field_name if a swap is likely.
    """
    swaps = {}
    
    # 1. Identify "unhappy" fields (low quality) and "potential candidates" (better quality)
    unhappy = [f for f in fields if quality_map.get(f.name, 0.0) < 0.4]
    candidates = [f for f in fields if quality_map.get(f.name, 0.0) > 0.45]
    
    if not unhappy or not candidates:
        return {}

    # 2. Heuristic check: common swap pairs
    for f_unhappy in unhappy:
        for f_candidate in candidates:
            name_u = f_unhappy.name.lower()
            name_c = f_candidate.name.lower()
            
            swap_pairs = [
                ("title", "availability"),
                ("name", "price"),
                ("price", "rating"),
                ("origin", "destination"),
                ("title", "category")
            ]
            
            for p1, p2 in swap_pairs:
                if (p1 in name_u and p2 in name_c) or (p2 in name_u and p1 in name_c):
                    # Check if swapping actually makes sense (heuristic)
                    # For title vs availability: title is usually longer
                    swaps[f_unhappy.name] = f_candidate.name
                    break
                    
    return swaps

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
