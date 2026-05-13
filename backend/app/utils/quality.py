import logging
import re
from statistics import mean
from app.models import SchemaField, FieldType

def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))

def safe_score(value) -> float:
    try:
        return float(value)
    except Exception as e:
        logging.exception(e)
        return 0.0

def normalized_dedup_text(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip().casefold()

def compute_source_breakdown(rows: list[dict]) -> dict:
    breakdown = {
        "official": 0,
        "directory": 0,
        "social": 0,
        "search_result": 0,
        "unknown": 0,
    }
    for row in rows:
        st = str((row or {}).get("source_type") or "unknown")
        breakdown[st if st in breakdown else "unknown"] += 1
    return breakdown

def _value_quality(field: SchemaField, value) -> float:
    """Measure the semantic quality of a specific field value."""
    if value is None:
        return 0.0

    if isinstance(value, list):
        if not value:
            return 0.0
        scores = [_value_quality(field, v) for v in value]
        return sum(scores) / len(scores)

    text = str(value).strip()
    if not text:
        return 0.0

    # Minimum length for meaningful values (except codes/ratings)
    if field.field_type not in (FieldType.CODE, FieldType.RATING, FieldType.NUMBER):
        if len(text) < 2:
            return 0.2

    score = 0.5 # Baseline for present value

    # Type-specific quality boosts
    if field.field_type == FieldType.EMAIL:
        if "@" in text and "." in text:
            score += 0.4
    elif field.field_type == FieldType.PHONE:
        digits = re.sub(r"\D", "", text)
        if len(digits) >= 7:
            score += 0.4
    elif field.field_type == FieldType.URL:
        if text.startswith(("http", "www")):
            score += 0.4
    elif field.field_type == FieldType.CURRENCY:
        if any(c.isdigit() for c in text):
            score += 0.3
    elif field.field_type == FieldType.RATING:
        if any(c.isdigit() for c in text) or any(w in text.lower() for w in ["one", "two", "three", "four", "five"]):
            score += 0.4

    return min(score, 1.0)


def score_record_quality(record: dict, schema_fields: list[SchemaField]) -> float:
    """Calculate an overall quality score for an extracted record."""
    if not record or not schema_fields:
        return 0.0

    field_scores = []
    required_missing = False

    for field in schema_fields:
        val = record.get(field.name)
        quality = _value_quality(field, val)

        if field.required and quality < 0.3:
            required_missing = True

        # Weighting: required fields impact score more
        weight = 1.5 if field.required else 1.0
        field_scores.append(quality * weight)

    if not field_scores:
        return 0.0

    avg_quality = sum(field_scores) / sum(1.5 if f.required else 1.0 for f in schema_fields)

    # Penalty for missing required fields
    if required_missing:
        avg_quality *= 0.5

    return round(clamp01(avg_quality), 3)

def build_quality_report(
    raw_results: list[dict],
    post_filter_count: int,
    post_radius_count: int,
    radius_report: dict,
    final_results: list[dict],
    min_record_score: float,
    type_integrity_report: dict,
    source_breakdown: dict,
    ai_source_prediction: dict | None = None,
    ai_structuring_report: dict | None = None,
    warnings: list[str] | None = None,
) -> dict:
    scores = [safe_score(r.get("record_score", 0.0)) for r in raw_results if isinstance(r, dict)]
    kept_scores = [safe_score(r.get("record_score", 0.0)) for r in final_results if isinstance(r, dict)]
    avg_score = round(mean(scores), 3) if scores else 0.0
    avg_final_score = round(mean(kept_scores), 3) if kept_scores else 0.0

    source_trust_scores = [safe_score(r.get("source_trust_score", 0.4)) for r in final_results if isinstance(r, dict)]
    avg_source_trust = round(mean(source_trust_scores), 3) if source_trust_scores else 0.4

    coverage_ratio = round((len(final_results) / len(raw_results)), 3) if raw_results else (1.0 if final_results else 0.0)
    mismatch_count = int((type_integrity_report or {}).get("total_type_mismatches") or 0)
    mismatch_ratio = mismatch_count / max(1, len(final_results))

    # Weighted blend of quality score, retention, source trust, and type integrity.
    overall_score = round(
        clamp01(
            (avg_final_score * 0.55)
            + (coverage_ratio * 0.2)
            + (avg_source_trust * 0.15)
            + ((1.0 - clamp01(mismatch_ratio)) * 0.1)
        ),
        3,
    )

    if not final_results:
        overall_score = 0.0

    source_ai = dict(ai_source_prediction or {})
    processed = int(source_ai.get("records_processed") or 0)
    structured = int(source_ai.get("records_ai_structured") or 0)
    source_ai["ai_row_rate"] = round((structured / processed), 3) if processed else 0.0

    return {
        "raw_records": len(raw_results),
        "post_filter_records": post_filter_count,
        "post_radius_records": post_radius_count,
        "final_records": len(final_results),
        "overall_score": overall_score,
        "quality_threshold": min_record_score,
        "avg_record_score": avg_score,
        "avg_final_record_score": avg_final_score,
        "coverage_ratio": coverage_ratio,
        "avg_source_trust_score": avg_source_trust,
        "records_below_threshold": sum(1 for s in scores if s < min_record_score),
        "type_integrity": type_integrity_report,
        "source_breakdown": source_breakdown,
        "ai_source_prediction": source_ai,
        "ai_structuring": ai_structuring_report or {},
        "warnings": warnings or [],
        "radius": radius_report,
    }
