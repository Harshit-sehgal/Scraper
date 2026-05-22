"""
Cleaning Engine — AI-powered data cleaning, structuring, and schema alignment.

Extracted from scraper.py to reduce the god-object size of that module.
Responsible for:
  - AI cleaning & schema alignment of extracted records
  - Batch chunking for LLM processing
  - Fallback to deterministic processing
"""

from __future__ import annotations

import logging
import inspect
from typing import Any, List, Optional, Tuple
from app.config import settings
from app.data_utils import _prepare_records_for_ai, normalize_scraped_record
from app.llm_bridge import llm_json as _llm_json, llm_json_fast as _llm_json_fast
from app.models import SchemaField
from app.utils.quality import score_record_quality

logger = logging.getLogger(__name__)


def _extract_list_from_json(data: Any) -> Optional[List[dict]]:
    """Helper to extract a list of records from various JSON response shapes."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["records", "items", "data", "results"]:
            if key in data and isinstance(data[key], list):
                return data[key]
    return None


async def ai_clean_and_align_records(
    records: list[dict],
    schema_fields: list[SchemaField],
    min_record_score: float | None = None,
) -> Tuple[list[dict], dict]:
    """Use AI to clean, structure and align records to the schema."""
    if min_record_score is None:
        min_record_score = settings.DEFAULT_MIN_RECORD_SCORE

    if not records:
        return [], {"applied": False, "reason": "no_records", "ai_chunks": 0, "fallback_chunks": 0}

    # Limit to top quality records for AI processing to save tokens
    target_records = sorted(records, key=lambda x: x.get("record_score", 0.0), reverse=True)[:settings.AI_CLEAN_TARGET_RECORDS]

    chunk_size = settings.AI_STRUCTURING_CHUNK_SIZE
    chunks = [target_records[i:i + chunk_size] for i in range(0, len(target_records), chunk_size)]

    final_records = []
    unprocessed_records = []
    consecutive_failures = 0
    chunks_processed = 0
    fallback_chunks = 0
    any_standard_call = False

    for chunk in chunks:
        chunks_processed += 1
        if consecutive_failures >= settings.AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES:
            fallback_chunks += 1
            unprocessed_records.extend(chunk)
            continue

        schema_hint = ", ".join([f"{f.name} ({f.field_type.value})" for f in schema_fields])
        prompt = f"""Clean and structure these {len(chunk)} data records.
Target Schema: {schema_hint}

Input Data:
{_prepare_records_for_ai(chunk, schema_fields)}

Rules:
1. Return ONLY a JSON list of objects matching the schema exactly.
2. DO NOT change, invent, or reorder any extracted values.
3. Only fix obvious typos (e.g., double spaces → single space).
4. DO NOT combine or split records — each input record is one output record.
5. Use null for empty fields, preserve existing values as-is."""

        try:
            messages = [
                {"role": "system", "content": "You are an expert data cleaning agent. Return only JSON."},
                {"role": "user", "content": prompt}
            ]

            raw_response = None
            try:
                res_fast = _llm_json_fast(messages)
                if inspect.isawaitable(res_fast):
                    raw_response = await res_fast
                else:
                    raw_response = res_fast
            except Exception as e:
                logger.warning(
                    "Fast-path semantic inference failed for chunk %d/%d: %s",
                    chunks_processed, len(chunks), e
                )
                try:
                    from app.semantic_world_state import get_world_state
                    ws = get_world_state()
                    ws.record_degradation(
                        subsystem="llm_fastpath",
                        severity="warning",
                        cause=f"Fast-path LLM inference failed for chunk {chunks_processed}: {e}",
                    )
                except Exception as telemetry_err:
                    logger.debug("Telemetry failed: %s", telemetry_err)

            cleaned_list = _extract_list_from_json(raw_response)

            if cleaned_list is None:
                any_standard_call = True
                res_std = _llm_json(messages)
                if inspect.isawaitable(res_std):
                    raw_std = await res_std
                else:
                    raw_std = res_std
                cleaned_std = _extract_list_from_json(raw_std)

                if cleaned_std is None:
                    fallback_chunks += 1
                    consecutive_failures += 1
                    unprocessed_records.extend(chunk)
                    continue
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
            logger.exception(e)
            consecutive_failures += 1
            fallback_chunks += 1
            unprocessed_records.extend(chunk)

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
