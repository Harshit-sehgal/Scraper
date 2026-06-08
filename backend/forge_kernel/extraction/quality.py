"""Quality scoring — record quality assessment and quality report generation.

Ported from existing app.utils.quality and app.content_quality modules.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def score_record_quality(record: dict[str, Any], schema_fields: list[dict[str, Any]]) -> float:  # noqa: C901, PLR0912
    """Score a single record's quality based on field completeness and content.

    Returns a score between 0.0 and 1.0.
    """
    if not record:
        return 0.0

    field_scores = []
    for field in schema_fields:
        name = field.get("name", "")
        required = field.get("required", True)
        value = record.get(name, "")

        if not value or (isinstance(value, str) and not value.strip()):
            if required:
                field_scores.append(0.0)
            else:
                field_scores.append(0.1)
            continue

        # Score based on content quality
        score = 0.3  # base score for non-empty
        if isinstance(value, str):
            length = len(value.strip())
            if length > 20:
                score += 0.3
            elif length > 4:
                score += 0.2
            score = min(1.0, score)
        elif isinstance(value, bool):
            score = 0.6
        elif isinstance(value, (int, float)):
            score = 0.8
        elif isinstance(value, list):
            score = 0.5 if len(value) > 0 else 0.0
        else:
            score = 0.5

        field_scores.append(score)

    if not field_scores:
        return 0.0

    return sum(field_scores) / len(field_scores)


def build_quality_report(
    records: list[dict[str, Any]],
    schema_fields: list[dict[str, Any]],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build a quality report from extracted records."""
    if not records:
        return {
            "total_records": 0,
            "filtered_count": 0,
            "completeness_score": 0.0,
            "warnings": warnings or [],
        }

    scores = [score_record_quality(r, schema_fields) for r in records]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    score_dist = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
    for s in scores:
        if s >= 0.8:
            score_dist["excellent"] += 1
        elif s >= 0.6:
            score_dist["good"] += 1
        elif s >= 0.35:
            score_dist["fair"] += 1
        else:
            score_dist["poor"] += 1

    return {
        "total_records": len(records),
        "filtered_count": len(records),
        "completeness_score": round(avg_score, 3),
        "score_distribution": score_dist,
        "warnings": warnings or [],
    }
