"""
Scraping engine with LLM-guided selector mapping, schema-aware cleanup,
record quality scoring, and optional Groq support.

Now using universal intent-driven extraction layers:
- intent_parser: Parse user intent to semantic schemas
- discovery: Auto-discover URLs based on topic
- html_utils: DOM cleaning and contact extraction
- selector_engine: Intelligent selector mapping and execution
- llm_bridge: Multi-provider LLM orchestration
- data_utils: Normalization, deduplication and limiting
"""

import logging
import os
from typing import List, Optional, Tuple, Any


from app.async_utils import run_sync_in_thread
from app.html_utils import (
    _is_empty_value, fetch_page_content, clean_html_for_selectors,
    _boost_contacts_with_page_html
)
from app.llm_bridge import (
    llm_json as _llm_json, 
    llm_json_fast as _llm_json_fast, 
    llm_text as _llm_text
)
from app.models import SchemaField
from app.semantic_pipeline import run_pipeline
from app.selector_engine import (
    _analyze_page_data_type, build_selector_prompt, extract_css_selectors,
    apply_selectors, extract_with_regex
)
from app.data_utils import (
    _dedupe_records, _limit_source_records as _base_limit_source_records,
    _prepare_records_for_ai, normalize_scraped_record
)
from app.utils.quality import score_record_quality


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except (ValueError, TypeError):
        logging.warning(f"Invalid integer for env var {name}: {raw!r}. Using default: {default}")
        value = default
    return max(minimum, min(maximum, value))


MAX_RECORDS_PER_SOURCE = _env_int("DATAFORGE_MAX_RECORDS_PER_SOURCE", 25, 5, 250)
MAX_CONSECUTIVE_MODEL_FAILURES = _env_int(
    "DATAFORGE_AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES", 5, 1, 20
)
AI_STRUCTURING_CHUNK_SIZE = 15
AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES = MAX_CONSECUTIVE_MODEL_FAILURES

def _limit_source_records(records: list[dict], schema_fields: list[SchemaField]) -> list[dict]:
    """Wrapper to allow monkeypatching MAX_RECORDS_PER_SOURCE in tests."""
    return _base_limit_source_records(records, schema_fields, max_records=MAX_RECORDS_PER_SOURCE)

async def scrape_url(
    url: str,
    schema_fields: list[SchemaField],
    min_record_score: float = 0.35,
    user_intent: str = "",
) -> list[dict]:
    """Orchestrate the full extraction flow for a single URL."""
    logging.info("Fetching: %s", url)
    try:
        html = await fetch_page_content(url)
    except Exception as e:
        logging.error("Failed to fetch %s: %s", url, e)
        return []

    # 1. Analyze page structure and patterns
    page_analysis = _analyze_page_data_type(html, schema_fields)
    
    # 2. Map schema to CSS selectors via LLM
    html_snippet = clean_html_for_selectors(html)
    prompt = build_selector_prompt(html_snippet, schema_fields, page_analysis)
    
    try:
        selectors = await extract_css_selectors(prompt)
    except Exception as e:
        logging.exception(e)
        selectors = {}

    # 3. Apply selectors or fallback to regex
    results = []
    if selectors and selectors.get("item_container"):
        results = apply_selectors(html, selectors, schema_fields, base_url=url)
    
    if not results:
        logging.info("Selectors failed or no results for %s, falling back to regex", url)
        results = extract_with_regex(html, schema_fields, base_url=url)

    # 4. Global page-level contact boosting (if records are thin)
    contact_counts = sum(1 for r in results if not _is_empty_value(r.get("email")) or not _is_empty_value(r.get("phone")))
    if len(results) > 2 and contact_counts / len(results) < 0.2:
        results = _boost_contacts_with_page_html(results, html, schema_fields)

    # 5. Local filtering and limiting
    results = [r for r in results if r.get("record_score", 0.0) >= (min_record_score * 0.8)]
    results = _dedupe_records(results, schema_fields)
    results = _limit_source_records(results, schema_fields)

    # 6. Final semantic pipeline orchestration (World State integration)
    results = run_pipeline(results, [f.name for f in schema_fields])

    return results


def _extract_list_from_json(data: Any) -> Optional[List[dict]]:
    """Helper to extract a list of records from various JSON response shapes."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Look for common keys: 'records', 'items', 'data', 'results'
        for key in ["records", "items", "data", "results"]:
            if key in data and isinstance(data[key], list):
                return data[key]
    return None


async def ai_clean_and_align_records(
    records: list[dict],
    schema_fields: list[SchemaField],
    min_record_score: float = 0.35,
) -> Tuple[list[dict], dict]:
    """Use AI to clean, structure and align records to the schema."""
    if not records:
        return [], {"applied": False, "reason": "no_records", "ai_chunks": 0, "fallback_chunks": 0}

    # Limit to top quality records for AI processing to save tokens
    target_records = sorted(records, key=lambda x: x.get("record_score", 0.0), reverse=True)[:30]
    
    chunk_size = AI_STRUCTURING_CHUNK_SIZE
    chunks = [target_records[i:i + chunk_size] for i in range(0, len(target_records), chunk_size)]
    
    final_records = []
    unprocessed_records = []  # original records that couldn't be AI-processed — preserved, not dropped
    consecutive_failures = 0
    chunks_processed = 0
    fallback_chunks = 0
    any_standard_call = False

    for chunk in chunks:
        chunks_processed += 1
        if consecutive_failures >= AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES:
            fallback_chunks += 1
            unprocessed_records.extend(chunk)
            continue

        schema_hint = ", ".join([f"{f.name} ({f.field_type.value})" for f in schema_fields])
        prompt = f"""Clean and structure these {len(chunk)} data records.
Target Schema: {schema_hint}

Input Data:
{_prepare_records_for_ai(chunk, schema_fields)}

Rules:
1. Return ONLY a JSON list of objects matching the schema.
2. Fix typos, normalize capitalization.
3. Infer missing fields from available text where obvious.
4. Use null for truly missing data.
"""

        try:
            messages = [
                {"role": "system", "content": "You are an expert data cleaning agent. Return only JSON."},
                {"role": "user", "content": prompt}
            ]

            raw_response = None
            try:
                # Try fast-path first
                raw_response = await run_sync_in_thread(lambda: _llm_json_fast(messages))
            except Exception as e:
                logging.warning(
                    "Fast-path semantic inference failed for chunk %d/%d: %s",
                    chunks_processed, len(chunks), e
                )
                # Record degradation telemetry
                try:
                    from app.semantic_world_state import get_world_state
                    ws = get_world_state()
                    ws.record_degradation(
                        subsystem="llm_fastpath",
                        severity="warning",
                        cause=f"Fast-path LLM inference failed for chunk {chunks_processed}: {e}",
                    )
                except Exception as telemetry_err:
                    logging.getLogger(__name__).debug("Telemetry failed: %s", telemetry_err)

            cleaned_list = _extract_list_from_json(raw_response)

            if cleaned_list is None:
                # Standard fallback triggered.
                any_standard_call = True

                raw_std = await run_sync_in_thread(lambda: _llm_json(messages))
                cleaned_std = _extract_list_from_json(raw_std)

                if cleaned_std is None:
                    # BOTH failed to return a list: treat as fallback chunk
                    fallback_chunks += 1
                    consecutive_failures += 1
                    unprocessed_records.extend(chunk)
                    continue  # skip the "add cleaned_list to final_records" block
                else:
                    consecutive_failures = 0
                    cleaned_list = cleaned_std
            else:
                consecutive_failures = 0

            if cleaned_list is not None:
                for item in cleaned_list:
                    norm = normalize_scraped_record(item, schema_fields)
                    norm["record_score"] = score_record_quality(norm, schema_fields)
                    if norm["record_score"] >= min_record_score:
                        final_records.append(norm)

        except Exception as e:
            logging.exception(e)
            consecutive_failures += 1
            fallback_chunks += 1
            unprocessed_records.extend(chunk)

    # Process ALL unprocessed records through the deterministic pipeline
    if unprocessed_records:
        for item in unprocessed_records:
            norm = normalize_scraped_record(item, schema_fields)
            norm["record_score"] = score_record_quality(norm, schema_fields)
            if norm["record_score"] >= min_record_score:
                final_records.append(norm)

    return final_records or records, {
        "applied": len(final_records) > 0,
        "records_processed": len(target_records),
        "records_returned": len(final_records),
        "ai_chunks": chunks_processed,
        "fallback_chunks": fallback_chunks,
        "model_fallback_mode": any_standard_call
    }


async def generate_data_insight(results: list[dict]) -> str:
    """Generate high-level summary and patterns from the extracted dataset."""
    if not results:
        return "No data available for analysis."

    sample = results[:20]
    prompt = f"Analyze these {len(results)} scraped records and provide 3 key insights or patterns found:\n\n{sample}"

    def _sync_call():
        messages = [
            {"role": "system", "content": "You are a data analyst. Provide concise, valuable insights."},
            {"role": "user", "content": prompt},
        ]
        response = _llm_text(messages, temperature=0.5, timeout=20)
        return response or "Analysis generation encountered an upstream model error."

    return await run_sync_in_thread(_sync_call)


async def suggest_schema_from_intent(intent: str, max_fields: int = 8) -> dict:
    """Convert a natural language intent into a structured SchemaField list."""
    def _sync_call() -> dict:
        return suggest_schema_from_intent_sync(intent, max_fields=max_fields)
    return await run_sync_in_thread(_sync_call)


def suggest_schema_from_intent_sync(intent: str, max_fields: int = 8) -> dict:
    """Sync version of suggest_schema_from_intent."""
    prompt = f"""Convert this scraping intent into a JSON plan.

Intent:
{intent}

Return ONLY JSON with this shape:
{{
  "name": "Job Name",
  "fields": [
    {{"name": "field_name", "type": "string|number|url|email|phone|date", "required": true|false, "description": "..."}}
  ]
}}

Maximum number of fields: {max_fields}
"""
    messages = [
        {"role": "system", "content": "You are a schema architect. Return only JSON."},
        {"role": "user", "content": prompt},
    ]
    return _llm_json(messages)
