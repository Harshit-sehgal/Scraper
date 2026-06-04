"""Result contracts — canonical models for extraction results, quality, and failure states."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FailureState(BaseModel):
    """Classification of a failure during extraction."""

    failure_class: str = Field(..., description="e.g. 'anti_bot_block', 'timeout', 'empty_page', 'selector_decay'")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this failure classification")
    detail: str = Field("", description="Human-readable explanation")
    recovery_attempted: bool = False
    recovery_success: bool = False


class ResultRecord(BaseModel):
    """A single extracted record with provenance metadata.

    The record dict contains schema-aligned fields plus reserved metadata keys.
    """

    data: dict[str, Any] = Field(..., description="Schema-aligned field values")
    source_url: str = Field("", description="URL this record was extracted from")
    extraction_method: str = Field("", description="e.g. 'selector', 'container', 'visible_text', 'network'")
    provenance: dict[str, Any] = Field(default_factory=dict, description="Extraction provenance metadata")
    record_score: float = Field(0.0, ge=0.0, le=1.0, description="Quality score for this record")
    scraped_at: str = Field("", description="ISO timestamp of extraction")


class QualityReport(BaseModel):
    """Quality assessment for a completed job."""

    total_records: int = 0
    filtered_count: int = 0
    completeness_score: float = Field(0.0, ge=0.0, le=1.0)
    type_integrity_score: float = Field(0.0, ge=0.0, le=1.0)
    score_distribution: dict[str, int] = Field(default_factory=dict)
    source_breakdown: dict[str, int] = Field(default_factory=dict)
    filtering_summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}
