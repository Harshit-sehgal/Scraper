"""Extraction Orchestrator — Manages the multi-layered extraction fallback cascade.

Layers:
  0. Network / JSON (Hydration, JSON-LD, Next.js state, Apollo cache)
  1. Provided Selectors (URL Analysis)
  2. Selector Memory (Persistent cache)
  3. LLM Discovery (Generative)
  4. Container Discovery (Universal evidence-based)
  5. Rendered Visible-Text Extraction (Spatial card grouping)
  6. Regex Fallback (Structural pattern matching)
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.container_discovery import (
    classify_container_failure,
    multi_pass_container_extraction,
)
from app.extraction_provenance import ExtractionMethod, ProvenanceBuilder
from app.models import FieldType, SchemaField
from app.network_extractor import extract_from_network
from app.page_evidence_collector import collect_page_evidence
from app.rendered_visible_text_extractor import extract_from_visible_blocks
from app.selector_discovery import discover_selectors
from app.selector_engine import apply_selectors, extract_with_regex
from app.selector_memory import get_selector_memory

logger = logging.getLogger(__name__)


class ExtractionResult:
    def __init__(
        self,
        records: list[dict],
        method: str,
        selector_success: bool = False,
        selectors: dict | None = None,
        page_closed: bool = False,
        network_diagnostics: list[str] | None = None,
    ) -> None:
        self.records = records
        self.method = method
        self.selector_success = selector_success
        self.selectors = selectors or {}
        self.network_diagnostics = network_diagnostics or []


def _average_record_score(records: list[dict]) -> float:
    if not records:
        return 0.0
    return sum(r.get("record_score", 0.0) for r in records) / len(records)


def _unique_record_value_count(records: list[dict]) -> int:
    unique_values = {
        tuple(
            sorted(
                (key, str(value).strip())
                for key, value in record.items()
                if value not in (None, "") and key != "record_score" and not key.startswith("_")
            ),
        )
        for record in records
    }
    return len(unique_values)


def _should_prefer_structural_candidate(
    current_records: list[dict],
    candidate_records: list[dict],
    min_candidate_avg: float = 0.50,
) -> bool:
    """Prefer structural extraction when it is at least as complete and credible."""
    if not candidate_records:
        return False
    if not current_records:
        return True

    current_avg = _average_record_score(current_records)
    candidate_avg = _average_record_score(candidate_records)
    if (
        _unique_record_value_count(candidate_records) > _unique_record_value_count(current_records)
        and candidate_avg >= min_candidate_avg
    ):
        return True
    if len(candidate_records) > len(current_records) and candidate_avg >= min_candidate_avg:
        return True
    return len(candidate_records) >= len(current_records) and candidate_avg >= current_avg + 0.05


def _merge_composite_records(
    records_list: list[list[dict]],
    schema_fields: list[SchemaField],
) -> list[dict]:
    """Merge records from multiple extraction passes into a composite result.

    For complex pages (mixed data, multiple structures), different extraction
    passes may yield different subsets of fields. This merges them intelligently:
    - If two records have the same key field (e.g., name / title), they're merged
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
                    if not existing_val or (existing_val in (None, "") and value not in (None, "")):
                        existing[field] = value
                # Recompute score
                from app.utils.quality import score_record_quality

                existing["record_score"] = score_record_quality(existing, schema_fields)
            else:
                new_record = dict(record)
                # Generate a synthetic key if no id_field value
                if not norm_key:
                    combined = "|".join(str(v) for v in new_record.values() if v not in (None, ""))
                    norm_key = combined or str(len(merged))
                if norm_key not in merged:
                    merged[norm_key] = new_record

    result = list(merged.values())
    result.sort(key=lambda r: r.get("record_score", 0.0), reverse=True)
    return result


def _multi_pass_extraction(
    html: str,
    schema_fields: list[SchemaField],
    selectors_map: dict[str, Any],
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
        html,
        selectors_map,
        schema_fields,
        base_url=base_url,
        user_intent=user_intent,
    )
    if not isinstance(pass1, list):
        pass1 = []

    # If pass1 is good enough, return it
    if pass1 and len(pass1) >= 3:
        avg_score = _average_record_score(pass1)
        if avg_score > 0.5:
            return pass1

    passes = [pass1]

    # Pass 2: Try alternative containers (different selectors that might match)
    container = selectors_map.get("item_container", "")
    if container:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Try parent / ancestor levels
        alt_containers = []
        for el in soup.select(container)[:3]:
            parent = el.parent if hasattr(el, "parent") and el.parent and el.parent.name != "[document]" else None
            if parent and parent.name not in ("html", "body"):
                # Build a selector for parent
                parent_sel = parent.name
                if parent.get("class"):
                    classes = parent.get("class")
                    if isinstance(classes, list):
                        parent_sel += "." + ".".join(classes[:2])
                if parent_sel != container:
                    alt_containers.append(parent_sel)

        for alt_sel in alt_containers[:2]:
            alt_map = dict(selectors_map)
            alt_map["item_container"] = alt_sel
            try:
                alt_result = apply_selectors(
                    html,
                    alt_map,
                    schema_fields,
                    base_url=base_url,
                    user_intent=user_intent,
                )
                if isinstance(alt_result, list) and alt_result:
                    passes.append(alt_result)
            except (AttributeError, TypeError, ValueError, RuntimeError, KeyError, IndexError) as e:
                logger.debug("[Orchestrator] Alt container pass failed for %s: %s", alt_sel, e)

    # Pass 3: Raw extraction without container (extract from full page)
    if not pass1 or (passes and len(passes) == 1):
        try:
            raw = extract_raw_from_selectors(html, selectors_map, base_url=base_url)
            if raw:
                from app.data_utils import align_extracted_keys_to_schema
                from app.utils.quality import score_record_quality

                aligned = align_extracted_keys_to_schema(
                    raw,
                    schema_fields,
                    user_intent=user_intent,
                )
                for rec in aligned:
                    rec["record_score"] = score_record_quality(rec, schema_fields)
                passes.append([r for r in aligned if r.get("record_score", 0) > 0])
        except (AttributeError, TypeError, ValueError, RuntimeError, KeyError, IndexError) as e:
            logger.debug("[Orchestrator] Raw extraction pass failed: %s", e)

    # Merge all passes
    return _merge_composite_records(passes, schema_fields)


def _record_field_provenance(
    provenance_builder: ProvenanceBuilder | None,
    schema_fields: list[SchemaField],
    records: list[dict],
    method: str,
    selectors: dict | None = None,
) -> None:
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


async def orchestrate_extraction(
    url: str,
    html: str,
    schema_fields: list[SchemaField],
    min_record_score: float,
    provenance_builder: ProvenanceBuilder | None = None,
    world_state=None,
    user_intent: str = "",
    provided_selectors: dict | None = None,
    warnings: list[str] | None = None,
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
    force_container_discovery = bool(provided_selectors and provided_selectors.get("force_container_discovery"))
    
    # C4: Track page invalidation
    page_closed = False
    def _on_page_close():
        nonlocal page_closed
        page_closed = True

    gate_threshold = max(min_record_score * settings.SCORE_GATE_THRESHOLD_FACTOR, settings.SCORE_GATE_ABSOLUTE_MIN)

    # Use module-level helper - defined after this function

    # ── Gather network diagnostics ──
    import json

    from app.session_url_detector import detect_session_params

    session_detect = detect_session_params(url)
    is_session = bool(session_detect.get("is_session_bound"))

    from app.browser_network_capture import get_captures

    captured_payloads = get_captures(url)
    captured_count = len(captured_payloads) if captured_payloads else 0

    parsed_json_count = 0
    bodies = []
    if captured_payloads:
        for p in captured_payloads:
            body = p.get("body") if isinstance(p, dict) else p
            if body is not None:
                bodies.append(body)
                try:
                    if isinstance(body, str):
                        json.loads(body)
                    parsed_json_count += 1
                except (TypeError, ValueError):
                    if isinstance(body, dict):
                        parsed_json_count += 1

    # Count record arrays found in network payloads
    record_arrays_found = 0
    for body in bodies:
        try:
            payload = json.loads(body) if isinstance(body, str) else body
            from app.network_payload_extractor import find_record_arrays

            candidates = find_record_arrays(payload)
            record_arrays_found += len(candidates)
        except (TypeError, ValueError, AttributeError):
            logger.debug("Failed to parse network payload for record arrays", exc_info=True)

    # Extract network results
    from app.network_payload_extractor import (
        arbitrate_sources,
        extract_from_network_payloads,
    )

    network_result = extract_from_network_payloads(bodies, schema_fields)

    best_candidate_path = network_result.source if network_result else None
    network_score = network_result.score if network_result else 0.0

    network_diagnostics = [
        f"session-bound detection result: {is_session}",
        f"captured payload count: {captured_count}",
        f"parsed JSON payload count: {parsed_json_count}",
        f"record arrays found: {record_arrays_found}",
        f"best candidate path: {best_candidate_path}",
        f"network extraction score: {network_score}",
    ]

    if network_result:
        logger.info(
            "[Orchestrator] Network payload extraction found candidate with score %.1f and coverage %.2f",
            network_result.score,
            network_result.field_coverage,
        )

    def _arbitrate_and_return(dom_res: ExtractionResult, warnings: list[str] | None = None) -> ExtractionResult:  # noqa: ARG001, RUF100
        if not network_result:
            network_diagnostics.append("arbitration winner: dom (Reason: No network extraction result available)")
            dom_res.network_diagnostics = list(network_diagnostics)
            return dom_res

        # Calculate DOM score
        dom_records = dom_res.records
        scores = [r.get("record_score", 0.0) for r in dom_records]
        dom_score = sum(scores) / len(scores) if scores else 0.0

        # Arbitrate sources
        winning_records, winning_source, field_map = arbitrate_sources(
            dom_records,
            dom_score,
            network_result,
            schema_fields,
        )

        dom_cov = sum(
            1 for r in dom_records[:20] for f in schema_fields if r.get(f.name) is not None and str(r.get(f.name, "")).strip()
        ) / max(len(dom_records[:20]) * len(schema_fields), 1)
        net_cov = network_result.field_coverage
        net_score = network_result.score

        if winning_source in ("dom", dom_res.method):
            reason = (
                f"DOM coverage / score ({dom_cov:.2f} / {dom_score:.1f}) is equal / better "
                f"than Network ({net_cov:.2f} / {net_score:.1f})"
            )
            network_diagnostics.append(f"arbitration winner: dom (Reason: {reason})")
            dom_res.network_diagnostics = list(network_diagnostics)
            return dom_res

        # If network won:
        reason = ""
        if net_cov >= dom_cov + 0.2:
            reason = f"Network field coverage ({net_cov:.2f}) significantly exceeds DOM coverage ({dom_cov:.2f})"
        elif net_score > dom_score and net_cov >= dom_cov:
            reason = f"Network score ({net_score:.1f}) exceeds DOM score ({dom_score:.1f}) with equal / better coverage"
        else:
            reason = "Network payload won arbitration"

        network_diagnostics.append(f"arbitration winner: network_payload (Reason: {reason})")

        logger.info(
            "[Orchestrator] Network Payload won arbitration against DOM (%s vs %s)",
            winning_source,
            dom_res.method,
        )

        # Record field-level provenance for the network extraction
        if provenance_builder:
            provenance_builder.set_extraction_method(winning_source)
            for idx, record in enumerate(winning_records):
                for field in schema_fields:
                    val = record.get(field.name)
                    mapping = field_map.get(field.name)
                    provenance_builder.add_field_provenance(
                        record_idx=idx,
                        field_name=field.name,
                        value=val,
                        method=winning_source,
                        selector=mapping.mapped_from if mapping else None,
                        confidence=mapping.confidence if mapping else 0.5,
                    )

        # Return winning network extraction result
        net_selectors = {
            "source_path": network_result.source,
            "fields": {k: v.mapped_from for k, v in field_map.items()},
        }
        # Only claim ``selector_success`` if at least one field actually
        # has a non-empty selector to apply. An empty ``mapped_from`` for
        # every field would otherwise let the downstream orchestrator try
        # to apply a useless CSS selector that always fails, masking the
        # real reason network extraction lost to a fallback path.
        selector_success = any((v.mapped_from or "").strip() for v in field_map.values())
        res = ExtractionResult(
            winning_records,
            winning_source,
            selector_success=selector_success,
            selectors=net_selectors,
        )
        res.network_diagnostics = list(network_diagnostics)
        return res

    # ── Layer 0: Network / JSON Extraction (highest priority) ─────────
    # Before trying any DOM-based selectors, check if structured data is
    # available in script tags, hydration state, JSON-LD, or network payloads.
    # This is the most reliable source when available.
    logger.info("[Orchestrator] Trying network / JSON extraction for %s", url)
    evidence = collect_page_evidence(html, url=url)
    if evidence:
        logger.info(
            "[Orchestrator] Page evidence: %d visible blocks, %d tables, %d containers, %d patterns, hydration=%s",
            len(evidence.text_blocks or []),
            len(evidence.tables or []),
            len(evidence.candidate_containers or []),
            len(evidence.patterns or []),
            bool(evidence.hydration_data),
        )
        if not evidence.hydration_data:
            logger.info("[Orchestrator] No hydration data in page evidence — network layer will be skipped")
    else:
        logger.info("[Orchestrator] No page evidence collected — network layer will be skipped")
    network_results = extract_from_network(
        evidence.hydration_data if evidence else {},
        schema_fields,
        url=url,
        network_payloads=evidence.network_json if evidence else None,
    )
    if network_results:
        avg_score = _average_record_score(network_results)
        if avg_score >= gate_threshold:
            logger.info(
                "[Orchestrator] Network / JSON extraction SUCCESS (%d records, avg score: %.2f)",
                len(network_results),
                avg_score,
            )
            _record_field_provenance(provenance_builder, schema_fields, network_results, ExtractionMethod.DISCOVERY)
            return _arbitrate_and_return(ExtractionResult(network_results, "network_json", selector_success=True))
        logger.info(
            "[Orchestrator] Network / JSON extraction LOW QUALITY (avg score: %.2f), falling through",
            avg_score,
        )
        if provenance_builder:
            provenance_builder.add_fallback_step("network_json_low_quality")
    else:
        logger.info("[Orchestrator] Network / JSON extraction returned no results, falling through")
        if provenance_builder:
            provenance_builder.add_fallback_step("network_json_empty")

    # Phase 79 / 80: Strategy Self-Selection
    # ── Layer 1: Provided Selectors (from URL Analysis) ───────────────
    # If the user analyzed the URL via the URL Analyzer, we have pre-discovered
    # CSS selectors. Try these first — they skip memory and LLM discovery.
    if (
        not force_container_discovery
        and provided_selectors
        and provided_selectors.get("item_container")
        and provided_selectors.get("fields")
    ):
        logger.info("[Orchestrator] Trying provided selectors from URL analysis for %s", url)
        provided_results = _multi_pass_extraction(
            html,
            schema_fields,
            provided_selectors,
            base_url=url,
            user_intent=user_intent,
        )
        if provided_results:
            avg_score = _average_record_score(provided_results)
            if avg_score >= gate_threshold:
                logger.info("[Orchestrator] Provided selectors SUCCESS (avg score: %.2f)", avg_score)
                memory.record_success(url, provided_selectors)
                _record_field_provenance(
                    provenance_builder,
                    schema_fields,
                    provided_results,
                    ExtractionMethod.DISCOVERY,
                    provided_selectors,
                )
                return _arbitrate_and_return(
                    ExtractionResult(provided_results, "discovery", selector_success=True, selectors=provided_selectors),
                )
            logger.info("[Orchestrator] Provided selectors LOW QUALITY (avg score: %.2f), falling through", avg_score)
            if provenance_builder:
                provenance_builder.add_fallback_step("provided_selectors_low_quality")
        else:
            logger.info("[Orchestrator] Provided selectors returned no results, falling through")
            if provenance_builder:
                provenance_builder.add_fallback_step("provided_selectors_empty")

    # ── Layer 2: Selector Memory ───────────────────────────────────────
    # If force_llm_discovery, bypass_selector_memory, or
    # force_container_discovery is set, skip memory.
    skip_memory = bool(
        provided_selectors
        and (
            provided_selectors.get("force_skip_memory")
            or provided_selectors.get("bypass_selector_memory")
            or provided_selectors.get("force_llm_discovery")
            or force_container_discovery
        ),
    )
    remembered_selectors = None if skip_memory else memory.get_selectors(url)
    if force_container_discovery:
        logger.info("[Orchestrator] Recovery requested force_container_discovery — skipping selectors, memory, and LLM discovery")
        if provenance_builder:
            provenance_builder.add_fallback_step("force_container_discovery")
    elif provided_selectors and provided_selectors.get("force_llm_discovery"):
        remembered_selectors = None
        logger.info("[Orchestrator] Recovery requested force_llm_discovery — skipping memory and profiles")
        if provenance_builder:
            provenance_builder.add_fallback_step("force_llm_discovery")
    elif provided_selectors and provided_selectors.get("bypass_selector_memory"):
        remembered_selectors = None
        logger.info("[Orchestrator] Recovery requested bypass_selector_memory — skipping memory")
        if provenance_builder:
            provenance_builder.add_fallback_step("bypass_selector_memory")
    if remembered_selectors:
        logger.info("[Orchestrator] Trying remembered selectors for %s", url)
        raw_results = apply_selectors(html, remembered_selectors, schema_fields, base_url=url, user_intent=user_intent)
        if raw_results:
            # Safely ensure raw_results is a list
            if not isinstance(raw_results, list):
                raw_results = []

            # Apply post-extraction semantic validation to memory results
            from app.utils.quality import post_extract_validate_records

            raw_results = post_extract_validate_records(raw_results, schema_fields, warnings=warnings)

            avg_score = _average_record_score(raw_results)

            # Downgrade memory extraction on session-bound URLs
            from app.session_url_detector import detect_session_params

            session_detect = detect_session_params(url)
            is_session = bool(session_detect.get("is_session_bound"))
            fields_sel = remembered_selectors.get("fields", {})
            selectors_empty = not fields_sel or all(not sel for sel in fields_sel.values())

            if is_session and selectors_empty and avg_score < 0.8:
                logger.warning(
                    "[Orchestrator] Downgrading memory extraction on session-bound URL: empty selectors and score %.2f < 0.8",
                    avg_score,
                )
                memory.record_failure(url)
                if provenance_builder:
                    provenance_builder.add_fallback_step("memory_session_downgraded")
                if (
                    warnings is not None
                    and "Memory extraction returned low-confidence records on session-bound URL" not in warnings
                ):
                    warnings.append("Memory extraction returned low-confidence records on session-bound URL")
            elif avg_score >= gate_threshold:
                logger.info("[Orchestrator] Memory SUCCESS (avg score: %.2f)", avg_score)
                memory.record_success(url, remembered_selectors)
                _record_field_provenance(
                    provenance_builder,
                    schema_fields,
                    raw_results,
                    ExtractionMethod.MEMORY,
                    remembered_selectors,
                )
                return _arbitrate_and_return(
                    ExtractionResult(raw_results, "memory", selector_success=True, selectors=remembered_selectors),
                    warnings=warnings,
                )
            else:
                logger.info("[Orchestrator] Memory FAILURE (avg score: %.2f)", avg_score)
                memory.record_failure(url)
                if provenance_builder:
                    provenance_builder.add_fallback_step("memory_failed")

                # Emit SelectorFailureEvent to support event-driven decouple
                # loops (Phase 82)
                try:
                    from app.event_dispatcher import get_dispatcher
                    from app.semantic_events import SemanticEvent, SemanticEventType

                    get_dispatcher().dispatch(
                        SemanticEvent(
                            event_type=SemanticEventType.SELECTOR_FAILURE,
                            source="extraction_orchestrator",
                            payload={"url": url, "avg_score": avg_score},
                        ),
                    )
                except (ImportError, RuntimeError, ValueError) as e:
                    logger.warning("[Orchestrator] Failed to dispatch selector failure event: %s", e)

    # ── Layer 3: LLM Discovery ─────────────────────────────────────────
    discovered_selectors = None
    if not force_container_discovery:
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

        # Check for field-swapping by analyzing extracted values against
        # expected types
        extracted_values = {}
        if raw_results:
            for field in schema_fields:
                vals = [r.get(field.name) for r in raw_results if r.get(field.name)]
                extracted_values[field.name] = vals[:3]  # first 3 values
        swapped = _detect_field_swaps(field_quality, schema_fields, extracted_values)
        if swapped:
            logger.warning("[Orchestrator] Detected field swap in discovery: %s. Attempting alignment.", swapped)
            discovered_selectors = _align_selectors(discovered_selectors, swapped)
            if provenance_builder:
                provenance_builder.add_error(f"Field swap detected and aligned: {swapped}")

        # Multi-pass extraction for complex pages
        raw_results = _multi_pass_extraction(
            html,
            schema_fields,
            discovered_selectors,
            base_url=url,
            user_intent=user_intent,
        )

        if raw_results:
            avg_score = _average_record_score(raw_results)
            if avg_score >= gate_threshold:
                logger.info("[Orchestrator] Discovery SUCCESS (avg score: %.2f)", avg_score)
                memory.record_success(url, discovered_selectors)
                _record_field_provenance(
                    provenance_builder,
                    schema_fields,
                    raw_results,
                    ExtractionMethod.DISCOVERY,
                    discovered_selectors,
                )
                return _arbitrate_and_return(
                    ExtractionResult(raw_results, "discovery", selector_success=True, selectors=discovered_selectors),
                )
            logger.info("[Orchestrator] Discovery LOW QUALITY (avg score: %.2f)", avg_score)
            if provenance_builder:
                provenance_builder.add_fallback_step("discovery_low_quality")

    # ── Layer 4: Container Discovery (general evidence-based) ────────
    logger.info("[Orchestrator] Trying general container discovery for %s", url)
    container_result = await multi_pass_container_extraction(
        html,
        schema_fields,
        url=url,
        user_intent=user_intent,
    )
    if container_result.all_passed and container_result.final_records:
        logger.info(
            "[Orchestrator] Container discovery SUCCESS (%d records from %s)",
            container_result.total_records,
            container_result.best_selector,
        )
        _record_field_provenance(provenance_builder, schema_fields, container_result.final_records, ExtractionMethod.DISCOVERY)
        return _arbitrate_and_return(
            ExtractionResult(
                container_result.final_records,
                "container_discovery",
                selector_success=True,
                selectors={"item_container": container_result.best_selector},
            ),
        )
    if container_result.final_records:
        logger.info(
            "[Orchestrator] Container discovery PARTIAL (%d low-quality records)",
            container_result.total_records,
        )
        # Keep partial results as potential fallback
        _record_field_provenance(provenance_builder, schema_fields, container_result.final_records, ExtractionMethod.DISCOVERY)
        if provenance_builder:
            provenance_builder.add_fallback_step("container_discovery_partial")
    else:
        failure = classify_container_failure(container_result)
        logger.info("[Orchestrator] Container discovery failed: %s", failure["failure_class"])
        if provenance_builder:
            provenance_builder.add_error(f"container_discovery: {failure['failure_class']}")

    # ── Layer 5: Rendered Visible-Text Extraction ────────────────────────
    # Try grouping visible text blocks into visual cards and extracting
    # from the rendered layout. This works when CSS selectors miss content
    # but the text is present in the rendered DOM.
    logger.info("[Orchestrator] Trying rendered visible-text extraction for %s", url)
    visible_results = extract_from_visible_blocks(html, schema_fields, url=url)
    if visible_results:
        avg_score = _average_record_score(visible_results)
        if avg_score >= gate_threshold:
            regex_candidate = extract_with_regex(html, schema_fields, base_url=url)
            if _should_prefer_structural_candidate(visible_results, regex_candidate, min_candidate_avg=gate_threshold):
                logger.info(
                    "[Orchestrator] Regex extraction superseded visible-text candidate (%d vs %d records)",
                    len(regex_candidate),
                    len(visible_results),
                )
                _record_field_provenance(provenance_builder, schema_fields, regex_candidate, ExtractionMethod.REGEX)
                if provenance_builder:
                    provenance_builder.add_fallback_step("visible_text_superseded_by_regex")
                return _arbitrate_and_return(ExtractionResult(regex_candidate, "regex", selector_success=False))
            logger.info(
                "[Orchestrator] Visible-text extraction SUCCESS (%d records, avg score: %.2f)",
                len(visible_results),
                avg_score,
            )
            _record_field_provenance(provenance_builder, schema_fields, visible_results, ExtractionMethod.REGEX)
            return _arbitrate_and_return(ExtractionResult(visible_results, "visible_text", selector_success=False))
        logger.info(
            "[Orchestrator] Visible-text extraction LOW QUALITY (avg score: %.2f)",
            avg_score,
        )
        if provenance_builder:
            provenance_builder.add_fallback_step("visible_text_low_quality")
    else:
        logger.info("[Orchestrator] Visible-text extraction returned no results")
        if provenance_builder:
            provenance_builder.add_fallback_step("visible_text_empty")

    # ── Layer 6: Regex Fallback ──────────────────────────────────────────
    logger.info("[Orchestrator] Falling back to regex extraction for %s", url)
    regex_results = extract_with_regex(html, schema_fields, base_url=url)
    _record_field_provenance(provenance_builder, schema_fields, regex_results, ExtractionMethod.REGEX)

    # If container discovery found partial results, prefer them over regex
    # (container discovery has better structural understanding)
    if container_result.final_records:
        if provenance_builder:
            provenance_builder.add_fallback_step("container_discovery_partial_result")
        return _arbitrate_and_return(ExtractionResult(container_result.final_records, "container_discovery"))

    if provenance_builder:
        provenance_builder.add_fallback_step("regex_fallback")
    return _arbitrate_and_return(ExtractionResult(regex_results, "regex"))


def _detect_field_swaps(
    quality_map: dict[str, float],
    fields: list[SchemaField],
    extracted_values: dict[str, list] | None = None,
) -> dict[str, str]:
    """Identify likely field swaps based on type incompatibility and extracted values.

    Analyzes extracted values against expected FieldType to detect swaps:
    - A CURRENCY field that extracted a long text string (possible swap with STRING)
    - An INTEGER field that extracted non-numeric text (possible swap with STRING)
    - A PHONE field that extracted a URL (possible swap with URL field)

    Returns a map of field_name -> correct_field_name if a swap is likely.
    When extracted_values are available, uses value-level type checking.
    Without values, falls back to quality-based heuristic detection.
    """
    if not extracted_values:
        # No values to check — use quality-based heuristic
        # If a field has very low quality and another has unusually high quality
        # for its type, a swap may have occurred
        likely_swaps: dict[str, str] = {}
        for field in fields:
            quality = quality_map.get(field.name, 1.0)
            if quality < 0.3 and field.field_type in (
                FieldType.CURRENCY,
                FieldType.PHONE,
                FieldType.EMAIL,
                FieldType.URL,
            ):
                # This field has low quality but should be easy to match — look for another
                # field with unusually high quality that might have taken its
                # selector
                for other in fields:
                    if other.name == field.name:
                        continue
                    other_quality = quality_map.get(other.name, 0.0)
                    if other_quality > 0.8 and other.field_type == FieldType.STRING:
                        likely_swaps[field.name] = other.name
                        break
        return likely_swaps

    # Value-aware swap detection
    swaps: dict[str, str] = {}

    for field in fields:
        values = extracted_values.get(field.name, [])
        if not values:
            continue

        # Check each field's values against its expected type
        type_match = _check_type_compatibility(field.field_type, values)
        if type_match >= 0.8:
            continue  # Values look correct for this type

        # Find a field whose values match our expected type better
        for other in fields:
            if other.name == field.name:
                continue
            other_vals = extracted_values.get(other.name, [])
            if not other_vals:
                continue
            # Check if our values look like the other field's type
            our_to_other_match = _check_type_compatibility(other.field_type, values)
            their_to_our_match = _check_type_compatibility(field.field_type, other_vals)
            if our_to_other_match > 0.6 and their_to_our_match > 0.6:
                swaps[field.name] = other.name
                break

    return swaps


def _check_type_compatibility(field_type: FieldType, values: list[Any]) -> float:
    """Check if values are compatible with a given FieldType.

    Returns a score from 0.0 (incompatible) to 1.0 (best observed match).
    """
    import re

    if not values:
        return 0.5  # No data to check

    str_vals = [str(v).strip() for v in values if v]
    if not str_vals:
        return 0.5

    if field_type == FieldType.INTEGER:
        numeric = sum(1 for v in str_vals if re.fullmatch(r"-?\d+", v))
        return numeric / len(str_vals)

    if field_type in (FieldType.FLOAT, FieldType.PERCENTAGE):
        numeric = sum(1 for v in str_vals if re.fullmatch(r"-?\d+(?:\.\d+)?%?", v.replace(",", "")))
        return numeric / len(str_vals)

    if field_type == FieldType.CURRENCY:
        currency_match = sum(1 for v in str_vals if re.search(r"[$£€¥₹]\s*\d+", v) or re.search(r"\d+\s*[$£€¥₹]", v))
        return currency_match / len(str_vals)

    if field_type == FieldType.EMAIL:
        email_match = sum(1 for v in str_vals if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", v))
        return email_match / len(str_vals)

    if field_type == FieldType.PHONE:
        phone_match = sum(1 for v in str_vals if re.search(r"[\+\d][\d\s()\-]{6,}\d", v))
        return phone_match / len(str_vals)

    if field_type == FieldType.URL:
        url_match = sum(1 for v in str_vals if v.startswith("http") or "." in v[:20])
        return url_match / len(str_vals)

    if field_type == FieldType.BOOLEAN:
        bool_match = sum(1 for v in str_vals if v.lower() in ("true", "false", "yes", "no", "0", "1"))
        return bool_match / len(str_vals)

    if field_type == FieldType.DATE:
        date_match = sum(1 for v in str_vals if re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}", v))
        return date_match / len(str_vals)

    # STRING, LIST_STRING, CODE, RATING, LOCATION, NUMBER — generic types,
    # always match
    return 0.8


def _align_selectors(selectors: dict[str, Any], swaps: dict[str, Any]) -> dict[str, Any]:
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

    return {**selectors, "fields": new_sels}
