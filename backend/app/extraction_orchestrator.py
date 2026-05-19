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
from typing import List, Optional, Tuple

from app.config import settings
from app.models import SchemaField
from app.selector_profiles.loader import try_profile_extraction
from app.selector_memory import get_selector_memory
from app.selector_discovery import discover_selectors
from app.selector_engine import apply_selectors, extract_with_regex
from app.data_utils import process_raw_records
from app.domain_intelligence import get_domain_intelligence

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
) -> ExtractionResult:
    """Cascade through extraction methods until high-quality data is found."""
    memory = get_selector_memory()
    intel = get_domain_intelligence().get_intelligence(url)

    gate_threshold = max(
        min_record_score * settings.SCORE_GATE_THRESHOLD_FACTOR, 
        settings.SCORE_GATE_ABSOLUTE_MIN
    )
    
    # Phase 79/80: Strategy Self-Selection
    preferred = intel.preferred_strategy

    if preferred == "regex":
        # Jump straight to regex if it's historically successful
        if intel.success_count > 3 or intel.anti_bot_risk > 0.7:
            logger.info("[Orchestrator] Selecting proven REGEX strategy for %s", url)
            regex_results = extract_with_regex(html, schema_fields, base_url=url)
            if regex_results:
                return ExtractionResult(regex_results, "regex")
            logger.info("[Orchestrator] Preferred REGEX failed, falling through to cascade")

    # ── Layer 2: Selector Memory ───────────────────────────────────────
    remembered_selectors = memory.get_selectors(url)
    if remembered_selectors:
        logger.info("[Orchestrator] Trying remembered selectors for %s", url)
        raw_results = apply_selectors(html, remembered_selectors, schema_fields, base_url=url)
        if raw_results:
            scores = [r.get("record_score", 0.0) for r in raw_results]
            avg_score = sum(scores) / len(scores)
            if avg_score >= gate_threshold:
                logger.info("[Orchestrator] Memory SUCCESS (avg score: %.2f)", avg_score)
                memory.record_success(url, remembered_selectors)
                return ExtractionResult(raw_results, "memory", selector_success=True, selectors=remembered_selectors)
            else:
                logger.info("[Orchestrator] Memory FAILURE (avg score: %.2f)", avg_score)
                memory.record_failure(url)

    # ── Layer 3: LLM Discovery ─────────────────────────────────────────
    logger.info("[Orchestrator] Initiating LLM discovery for %s", url)
    discovered_selectors = await discover_selectors(html, schema_fields)
    
    if discovered_selectors and discovered_selectors.get("item_container"):
        # Phase 81: Semantic Alignment Pass
        # We run apply_selectors with field quality tracking to see if the LLM
        # swapped fields (common with dynamic grids).
        raw_results, field_quality = apply_selectors(
            html, discovered_selectors, schema_fields, base_url=url, return_field_quality=True
        )
        
        # Check for field-swapping
        swapped = _detect_field_swaps(field_quality, schema_fields)
        if swapped:
            logger.warning("[Orchestrator] Detected field swap in discovery: %s. Attempting alignment.", swapped)
            discovered_selectors = _align_selectors(discovered_selectors, swapped)
            # Re-apply with aligned selectors
            raw_results = apply_selectors(html, discovered_selectors, schema_fields, base_url=url)
            
        if raw_results:
            scores = [r.get("record_score", 0.0) for r in raw_results]
            avg_score = sum(scores) / len(scores)
            if avg_score >= gate_threshold:
                logger.info("[Orchestrator] Discovery SUCCESS (avg score: %.2f)", avg_score)
                memory.record_success(url, discovered_selectors)
                return ExtractionResult(raw_results, "discovery", selector_success=True, selectors=discovered_selectors)
            else:
                logger.info("[Orchestrator] Discovery LOW QUALITY (avg score: %.2f)", avg_score)

    # ── Layer 4: Regex Fallback ────────────────────────────────────────
    logger.info("[Orchestrator] Falling back to regex extraction for %s", url)
    regex_results = extract_with_regex(html, schema_fields, base_url=url)
    return ExtractionResult(regex_results, "regex")


def _detect_field_swaps(quality_map: dict[str, float], fields: list[SchemaField]) -> dict[str, str]:
    """Identify likely field swaps based on semantic quality scores.
    
    Returns a map of field_name -> correct_field_name if a swap is likely.
    """
    swaps = {}
    # If we had access to the manifold here, we would use it to find which role
    # best fits the actual extracted values. 
    # For now, we use a simple heuristic: if a required field has 0.0 quality
    # and an optional field has 1.0, they MIGHT be swapped.
    # This is placeholder logic for the real 'Semantic Alignment' pass.
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
