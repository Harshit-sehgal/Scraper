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
    gate_threshold = max(
        min_record_score * settings.SCORE_GATE_THRESHOLD_FACTOR, 
        settings.SCORE_GATE_ABSOLUTE_MIN
    )

    # ── Layer 1: Selector Profiles ─────────────────────────────────────
    # (Note: Profile extraction usually happens before fetch in the main loop
    # but we handle the case where it might be called here or if it returned 0)
    # Actually, Step 1 is already in scraper.py's main loop to avoid double-fetch.
    # We focus on Layers 2-4 here.

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
