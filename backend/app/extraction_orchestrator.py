"""
Extraction Orchestrator — Manages the multi-layered extraction fallback cascade.

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
from app.config import settings
from app.models import FieldType, SchemaField
from app.selector_memory import get_selector_memory

from app.selector_engine import extract_with_regex
from app.extraction_provenance import ProvenanceBuilder, ExtractionMethod
from app.network_extractor import extract_from_network
from app.page_evidence_collector import collect_page_evidence

logger = logging.getLogger(__name__)


class ExtractionResult:
    def __init__(
        self, 
        records: list[dict], 
        method: str, 
        selector_success: bool = False,
        selectors: dict | None = None,
        network_diagnostics: list[str] | None = None,
    ):
        self.records = records
        self.method = method
        self.selector_success = selector_success
        self.selectors = selectors or {}
        self.network_diagnostics = network_diagnostics or []


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
            except Exception as e:
                logger.debug("[Orchestrator] Alt container pass failed for %s: %s", alt_sel, e)
    
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
        except Exception as e:
            logger.debug("[Orchestrator] Raw extraction pass failed: %s", e)
    
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
    force_container_discovery = bool(
        provided_selectors and provided_selectors.get("force_container_discovery")
    )

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

    # ── Gather network diagnostics ──
    import json
    from app.session_url_detector import detect_session_params
    session_detect = detect_session_params(url)
    is_session = bool(session_detect.get("is_session_bound") or "/search/id/" in url)

    from app.browser_network_capture import get_captures
    captured_payloads = get_captures(url)
    captured_count = len(captured_payloads) if captured_payloads else 0

    parsed_json_count = 0
    bodies = []
    if captured_payloads:
        for p in captured_payloads:
            if isinstance(p, dict):
                body = p.get("body")
            else:
                body = p
            if body is not None:
                bodies.append(body)
                try:
                    if isinstance(body, str):
                        json.loads(body)
                    parsed_json_count += 1
                except Exception:
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
        except Exception as e:
            logger.debug("Failed to analyze payload body for record arrays: %s", e)

    # Extract network results
    from app.network_payload_extractor import extract_from_network_payloads, arbitrate_sources
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
            network_result.score, network_result.field_coverage,
        )

    def _arbitrate_and_return(dom_res: ExtractionResult, warnings: list[str] | None = None) -> ExtractionResult:
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
            1 for r in dom_records[:20] for f in schema_fields
            if r.get(f.name) is not None and str(r.get(f.name, "")).strip()
        ) / max(len(dom_records[:20]) * len(schema_fields), 1)
        net_cov = network_result.field_coverage
        net_score = network_result.score

        if winning_source == "dom" or winning_source == dom_res.method:
            reason = "DOM coverage/score (%.2f / %.1f) is equal/better than Network (%.2f / %.1f)" % (dom_cov, dom_score, net_cov, net_score)
            network_diagnostics.append(f"arbitration winner: dom (Reason: {reason})")
            dom_res.network_diagnostics = list(network_diagnostics)
            return dom_res

        # If network won:
        reason = ""
        if net_cov >= dom_cov + 0.2:
            reason = "Network field coverage (%.2f) significantly exceeds DOM coverage (%.2f)" % (net_cov, dom_cov)
        elif net_score > dom_score and net_cov >= dom_cov:
            reason = "Network score (%.1f) exceeds DOM score (%.1f) with equal/better coverage" % (net_score, dom_score)
        else:
            reason = "Network payload won arbitration"
        
        network_diagnostics.append(f"arbitration winner: network_payload (Reason: {reason})")

        logger.info(
            "[Orchestrator] Network Payload won arbitration against DOM (%s vs %s)",
            winning_source, dom_res.method,
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
        res = ExtractionResult(
            winning_records,
            winning_source,
            selector_success=True,
            selectors=net_selectors,
        )
        res.network_diagnostics = list(network_diagnostics)
        return res
    
    # ── Layer 0: Network / JSON Extraction (highest priority) ─────────
    # Before trying any DOM-based selectors, check if structured data is
    # available in script tags, hydration state, JSON-LD, or network payloads.
    # This is the most reliable source when available.
    logger.info("[Orchestrator] Trying network/JSON extraction for %s", url)
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
        scores = [r.get("record_score", 0.0) for r in network_results]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        if avg_score >= gate_threshold:
            logger.info(
                "[Orchestrator] Network/JSON extraction SUCCESS (%d records, avg score: %.2f)",
                len(network_results), avg_score,
            )
            _record_field_provenance(network_results, ExtractionMethod.DISCOVERY)
            return _arbitrate_and_return(ExtractionResult(network_results, "network_json", selector_success=True))
        else:
            logger.info(
                "[Orchestrator] Network/JSON extraction LOW QUALITY (avg score: %.2f), falling through",
                avg_score,
            )
            if provenance_builder:
                provenance_builder.add_fallback_step("network_json_low_quality")
    else:
        logger.info("[Orchestrator] Network/JSON extraction returned no results, falling through")
        if provenance_builder:
            provenance_builder.add_fallback_step("network_json_empty")

    # Phase 79/80: Strategy Self-Selection
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
                return _arbitrate_and_return(ExtractionResult(provided_results, "discovery", selector_success=True, selectors=provided_selectors))
            else:
                logger.info("[Orchestrator] Provided selectors LOW QUALITY (avg score: %.2f), falling through", avg_score)
                if provenance_builder:
                    provenance_builder.add_fallback_step("provided_selectors_low_quality")
        else:
            logger.info("[Orchestrator] Provided selectors returned no results, falling through")
            if provenance_builder:
                provenance_builder.add_fallback_step("provided_selectors_empty")

    # ── Layer 2: Direct LLM Extraction ─────────────────────────────────────────
    from app.llm_extractor import extract_with_llm
    
    logger.info("[Orchestrator] Initiating Direct LLM extraction for %s", url)
    llm_results = await extract_with_llm(html, schema_fields, url)
    
    if llm_results:
        scores = [r.get("record_score", 0.0) for r in llm_results]
        avg_score = sum(scores) / max(len(scores), 1)
        
        if avg_score == 0.0:
            from app.utils.quality import post_extract_validate_records, score_record_quality
            llm_results = post_extract_validate_records(llm_results, schema_fields, warnings=warnings)
            for r in llm_results:
                r["record_score"] = score_record_quality(r, schema_fields)
            scores = [r.get("record_score", 0.0) for r in llm_results]
            avg_score = sum(scores) / max(len(scores), 1)
            
        if avg_score >= gate_threshold:
            logger.info(
                "[Orchestrator] Direct LLM extraction SUCCESS (%d records, avg score: %.2f)",
                len(llm_results), avg_score,
            )
            _record_field_provenance(llm_results, "llm_direct")
            return _arbitrate_and_return(ExtractionResult(llm_results, "llm_direct", selector_success=True))
        else:
            logger.info(
                "[Orchestrator] Direct LLM extraction LOW QUALITY (avg score: %.2f), falling through",
                avg_score,
            )
            if provenance_builder:
                provenance_builder.add_fallback_step("llm_direct_low_quality")
    else:
        logger.info("[Orchestrator] Direct LLM extraction returned no results, falling through")
        if provenance_builder:
            provenance_builder.add_fallback_step("llm_direct_empty")

    # ── Layer 3: Regex Fallback ──────────────────────────────────────────
    logger.info("[Orchestrator] Falling back to regex extraction for %s", url)
    regex_results = extract_with_regex(html, schema_fields, base_url=url)
    _record_field_provenance(regex_results, ExtractionMethod.REGEX)
    
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
            if quality < 0.3 and field.field_type in (FieldType.CURRENCY, FieldType.PHONE, FieldType.EMAIL, FieldType.URL):
                # This field has low quality but should be easy to match — look for another
                # field with unusually high quality that might have taken its selector
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


def _check_type_compatibility(field_type: FieldType, values: list) -> float:
    """Check if values are compatible with a given FieldType.
    Returns a score from 0.0 (incompatible) to 1.0 (perfect match).
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
    
    if field_type == FieldType.FLOAT or field_type == FieldType.PERCENTAGE:
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
    
    # STRING, LIST_STRING, CODE, RATING, LOCATION, NUMBER — generic types, always match
    return 0.8

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
