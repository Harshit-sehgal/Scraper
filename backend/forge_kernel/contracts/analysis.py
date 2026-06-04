"""
Analysis contracts — canonical models for URL analysis and extraction attempts.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExtractionAttempt(BaseModel):
    """Record of a single extraction attempt with strategy and telemetry."""

    url: str
    strategy: str = Field(..., description="e.g. 'profile', 'selector', 'container', 'visible_text', 'network'")
    success: bool = False
    records_count: int = 0
    duration_ms: float = 0.0
    failure: dict[str, Any] | None = None
    telemetry: dict[str, Any] = Field(default_factory=dict)


class AnalyzeUrlResponse(BaseModel):
    """Response from URL analysis — page structure and suggested fields."""

    url: str
    page_structure: str = Field("unknown", description="'list', 'detail', 'single', 'unknown'")
    structure_confidence: float = Field(0.0, ge=0.0, le=1.0)
    estimated_record_count: int = 0
    item_container: str | None = None
    suggested_fields: list[dict[str, str]] = Field(default_factory=list)
    anti_bot_score: float = Field(0.0, ge=0.0, le=1.0)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
