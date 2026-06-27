"""Quality gates for acquisition data.

Evaluates acquisition quality signals against thresholds to determine
whether data is trustworthy enough for downstream processing.
"""

from __future__ import annotations

from typing import Any

from app.config import settings


def assess_acquisition_quality(
    *,
    data_evidence_score: float = 0.0,
    anti_bot_score: float = 0.0,
    visible_text_length: int = 0,
) -> str:
    """Assess acquisition quality and return a gate result.

    Parameters are passed as keyword-only arguments (not an
    AcquisitionLineage object) to keep this module free of top-level
    research-module imports.
    """
    data_threshold = getattr(settings, "ACQUISITION_QUALITY_DATA_EVIDENCE_THRESHOLD", 0.3)
    anti_bot_threshold = getattr(settings, "ACQUISITION_QUALITY_ANTI_BOT_THRESHOLD", 0.2)
    text_length_threshold = getattr(settings, "ACQUISITION_QUALITY_VISIBLE_TEXT_THRESHOLD", 50)
    
    if data_evidence_score < data_threshold:
        return "block"
    if anti_bot_score < anti_bot_threshold:
        return "block"
    if visible_text_length < text_length_threshold:
        return "review"
    return "pass"


def should_proceed_with_acquisition(
    *,
    data_evidence_score: float = 0.0,
    anti_bot_score: float = 0.0,
    visible_text_length: int = 0,
) -> bool:
    """Return True if the acquisition quality allows further processing."""
    return assess_acquisition_quality(
        data_evidence_score=data_evidence_score,
        anti_bot_score=anti_bot_score,
        visible_text_length=visible_text_length,
    ) in ("pass", "review")


def quality_summary(
    *,
    data_evidence_score: float = 0.0,
    anti_bot_score: float = 0.0,
    visible_text_length: int = 0,
) -> dict[str, Any]:
    """Return a dict with the score breakdown and overall gate result."""
    result = assess_acquisition_quality(
        data_evidence_score=data_evidence_score,
        anti_bot_score=anti_bot_score,
        visible_text_length=visible_text_length,
    )
    return {
        "data_evidence_score": data_evidence_score,
        "anti_bot_score": anti_bot_score,
        "visible_text_length": visible_text_length,
        "result": result,
    }
