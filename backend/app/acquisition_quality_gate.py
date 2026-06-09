"""Quality gates for acquisition data.

Evaluates acquisition quality signals against thresholds to determine
whether data is trustworthy enough for downstream processing.
"""

from __future__ import annotations


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
    if data_evidence_score < 0.3:
        return "block"
    if anti_bot_score < 0.2:
        return "block"
    if visible_text_length < 50:
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
) -> dict:
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
