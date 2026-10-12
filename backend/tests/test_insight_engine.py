"""Unit Tests for Insight Engine.

Tests generate_data_insight, suggest_schema_from_intent,
and suggest_schema_from_intent_sync with mocked LLM calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.insight_engine import (
    generate_data_insight,
    suggest_schema_from_intent,
    suggest_schema_from_intent_sync,
)


class TestGenerateDataInsight:
    """Tests for generate_data_insight()."""

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        result = await generate_data_insight([])
        assert result == "No data available for analysis."

    @pytest.mark.asyncio
    async def test_calls_llm_text(self) -> None:
        mock_response = "Key insight: prices vary by region."
        mock_llm = AsyncMock(return_value=mock_response)
        with patch.dict(generate_data_insight.__globals__, {"_llm_text": mock_llm}):
            result = await generate_data_insight([{"name": "A", "price": "100"}])
            assert result == mock_response

    @pytest.mark.asyncio
    async def test_none_response_falls_back(self) -> None:
        mock_llm = AsyncMock(return_value=None)
        with patch.dict(generate_data_insight.__globals__, {"_llm_text": mock_llm}):
            result = await generate_data_insight([{"name": "A"}])
            assert "encountered an upstream model error" in result


class TestSuggestSchemaFromIntent:
    """Tests for suggest_schema_from_intent()."""

    @pytest.mark.asyncio
    async def test_returns_schema_dict(self) -> None:
        mock_schema = {
            "name": "Job",
            "fields": [{"name": "title", "type": "string", "required": True, "description": "Product title"}],
        }
        mock_llm = AsyncMock(return_value=mock_schema)
        with patch.dict(suggest_schema_from_intent.__globals__, {"_llm_json": mock_llm}):
            result = await suggest_schema_from_intent("scrape product details")
            assert result == mock_schema
            assert "fields" in result

    @pytest.mark.asyncio
    async def test_passes_max_fields(self) -> None:
        mock_llm = AsyncMock(return_value={"fields": []})
        with patch.dict(suggest_schema_from_intent.__globals__, {"_llm_json": mock_llm}):
            result = await suggest_schema_from_intent("scrape products", max_fields=5)
            assert result == {"fields": []}


class TestSuggestSchemaFromIntentSync:
    """Tests for the sync wrapper suggest_schema_from_intent_sync()."""

    def test_returns_schema_dict(self) -> None:
        mock_schema = {"name": "Sync Job", "fields": [{"name": "x", "type": "string", "required": False, "description": ""}]}
        mock_async = AsyncMock(return_value=mock_schema)
        with patch.dict(suggest_schema_from_intent_sync.__globals__, {"suggest_schema_from_intent": mock_async}):
            result = suggest_schema_from_intent_sync("test intent")
            assert result == mock_schema
