"""
Insight Engine — data analysis, insight generation, and schema suggestion.

Extracted from scraper.py to reduce the god-object size.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.async_utils import run_sync_in_thread
from app.llm_bridge import llm_json as _llm_json, llm_text as _llm_text

logger = logging.getLogger(__name__)


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
        response = _llm_text(messages, temperature=0.5, timeout=settings.INSIGHT_TIMEOUT)
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
