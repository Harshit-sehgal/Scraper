"""Insight Engine — data analysis, insight generation, and schema suggestion.

Extracted from scraper.py to reduce the god-object size.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.llm_bridge import llm_json as _llm_json
from app.llm_bridge import llm_text as _llm_text

logger = logging.getLogger(__name__)


async def generate_data_insight(results: list[dict]) -> str:
    """Generate high-level summary and patterns from the extracted dataset."""
    if not results:
        return "No data available for analysis."

    sample = results[: settings.INSIGHT_SAMPLE_SIZE]
    prompt = f"Analyze these {len(results)} scraped records and provide 3 key insights or patterns found:\n\n{sample}"

    messages = [
        {"role": "system", "content": "You are a data analyst. Provide concise, valuable insights."},
        {"role": "user", "content": prompt},
    ]
    response = await _llm_text(messages, temperature=settings.INSIGHT_TEMPERATURE, timeout=settings.INSIGHT_TIMEOUT)
    return response or "Analysis generation encountered an upstream model error."


async def suggest_schema_from_intent(intent: str, max_fields: int | None = None) -> dict:
    """Convert a natural language intent into a structured SchemaField list."""
    if max_fields is None:
        max_fields = settings.INSIGHT_MAX_FIELDS

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
    return await _llm_json(messages, temperature=settings.LLM_TEMPERATURE, timeout=settings.LLM_TIMEOUT)  # type: ignore[no-any-return]


def suggest_schema_from_intent_sync(intent: str, max_fields: int | None = None) -> dict:
    """Sync version of suggest_schema_from_intent.

    Runs the async coroutine in a dedicated event loop on a background
    thread to avoid conflicts with any already-running event loop.
    """
    import asyncio
    import concurrent.futures

    def _run():
        return asyncio.run(suggest_schema_from_intent(intent, max_fields))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        return future.result()
