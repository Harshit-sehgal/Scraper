import re
from statistics import mean
from typing import Any

from app.config import settings
from app.models import FieldType, SchemaField


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalized_dedup_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip().casefold()


def compute_source_breakdown(results: list[dict]) -> dict[str, Any]:
    """Compute count and percentage of records per source domain."""
    from urllib.parse import urlparse

    counts: dict[str, int] = {}
    for r in results:
        url = r.get("_source_url") or r.get("source_url") or ""
        domain = urlparse(url).netloc or "unknown"
        counts[domain] = counts.get(domain, 0) + 1

    total = len(results)
    return {
        domain: {"count": count, "percentage": round(count / total, 3) if total > 0 else 0.0} for domain, count in counts.items()
    }


def safe_score(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


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

    # Probabilistic scoring: start with a baseline and add "evidence"
    score = settings.QUALITY_BASE_SCORE  # Base for non-empty text

    # Text length density (too short is suspicious for non-codes)
    if field.field_type not in (FieldType.CODE, FieldType.RATING, FieldType.NUMBER):
        if len(text) > settings.QUALITY_TEXT_LEN_THRESHOLD_1:
            score += 0.2
        if len(text) > settings.QUALITY_TEXT_LEN_THRESHOLD_2:
            score += 0.1

    # Negative Evidence: identify "swapped" or "noise" text in identifying
    # fields
    field_name_lower = field.name.lower()

    # Strict airport / IATA code validation
    if ("airport_code" in field_name_lower or "iata" in field_name_lower) and not re.match(r"^[A-Z]{3}$", text):
        return 0.0

    is_identity_field = any(k in field_name_lower for k in ["name", "title", "company"])
    is_status_field = any(k in field_name_lower for k in ["availability", "stock", "status", "condition"])

    noise_status_phrases = [
        "in stock",
        "out of stock",
        "click here",
        "read more",
        "view details",
        "add to cart",
        "instock",
    ]

    if is_identity_field:
        if any(p in text.lower() for p in noise_status_phrases):
            score -= settings.QUALITY_NOISE_PENALTY  # Heavy penalty
        if len(text) < 3:
            score -= settings.QUALITY_SHORT_IDENTITY_PENALTY

    if is_status_field:
        # Status fields should be short. If it's a long sentence, it's likely a
        # swapped title.
        if len(text) > 25:
            score -= settings.QUALITY_STATUS_LONG_PENALTY
        if not any(p in text.lower() for p in noise_status_phrases) and field.field_type == FieldType.STRING and len(text) > 10:
            score -= settings.QUALITY_STATUS_MISMATCH_PENALTY

    # Type-specific quality "votes"
    if field.field_type == FieldType.EMAIL:
        if re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text):
            score += 0.5
    elif field.field_type == FieldType.PHONE:
        digits = re.sub(r"\D", "", text)
        if 7 <= len(digits) <= 15:
            score += 0.5
    elif field.field_type == FieldType.URL:
        if text.startswith(("http://", "https://", "www.")):
            score += 0.5
    elif field.field_type == FieldType.CURRENCY:
        if any(c.isdigit() for c in text):
            score += 0.3
        if any(c in text for c in "$£€¥₹"):
            score += 0.2
    elif field.field_type == FieldType.RATING:
        if any(c.isdigit() for c in text) or any(w in text.lower() for w in ["one", "two", "three", "four", "five", "star"]):
            score += 0.5
    elif field.field_type == FieldType.NUMBER:
        if re.match(r"^-?\d+(\.\d+)?$", text):
            score += 0.5
    elif field.field_type == FieldType.DATE and any(c.isdigit() for c in text) and len(text) >= 6:
        score += 0.4

    return min(score, 1.0)


def score_record_quality(record: dict[str, Any], schema_fields: list[SchemaField]) -> float:
    """Ensemble-based quality scoring for an extracted record.

    Uses multiple "votes" to determine probabilistic confidence:
    1. Field Presence: Percentage of schema fields populated.
    2. Semantic Value: Sum of per-field quality scores.
    3. Structural Cohesion: Penalty for outliers / anomalies.
    """
    if not record or not schema_fields:
        return 0.0

    present_fields = 0
    total_quality = 0.0
    required_count = 0
    required_missing_count = 0

    for field in schema_fields:
        val = record.get(field.name)
        quality = _value_quality(field, val)

        if quality > settings.QUALITY_PRESENT_FIELD_THRESHOLD:
            present_fields += 1

        if field.required:
            required_count += 1
            if quality < settings.QUALITY_REQUIRED_MISSING_THRESHOLD:
                required_missing_count += 1

        weight = settings.QUALITY_REQUIRED_WEIGHT if field.required else 1.0
        total_quality += quality * weight

    # 1. Presence Vote (0.0 to 1.0)
    presence_vote = present_fields / len(schema_fields)

    # 2. Quality Vote (0.0 to 1.0)
    max_possible_quality = sum(settings.QUALITY_REQUIRED_WEIGHT if f.required else 1.0 for f in schema_fields)
    quality_vote = total_quality / max_possible_quality

    # 3. Structural Cohesion Vote
    # If we have very few fields present but they are high quality, it's still suspicious.
    # Conversely, many low quality fields are also bad.
    cohesion_vote = 1.0
    if presence_vote < settings.QUALITY_PRESENCE_COHESION_THRESHOLD:
        cohesion_vote *= 0.7
    if required_missing_count > 0:
        missing_ratio = required_missing_count / max(required_count, 1)
        cohesion_vote *= 1.0 - (missing_ratio * 0.5)

    # Ensemble blending
    # We use a weighted geometric mean-ish approach to ensure one bad vote
    # impacts heavily
    raw_confidence = (presence_vote * settings.QUALITY_PRESENCE_VOTE_WEIGHT) + (
        quality_vote * settings.QUALITY_QUALITY_VOTE_WEIGHT
    )
    final_confidence = raw_confidence * cohesion_vote

    return round(clamp01(final_confidence), 3)


def build_quality_report(
    raw_results: list[dict],
    post_filter_count: int,
    post_radius_count: int,
    radius_report: dict[str, Any],
    final_results: list[dict],
    min_record_score: float,
    type_integrity_report: dict[str, Any],
    source_breakdown: dict[str, Any],
    ai_source_prediction: dict | None = None,
    ai_structuring_report: dict | None = None,
    warnings: list[str] | None = None,
    acquisition_lineages: list[dict] | None = None,
) -> dict[str, Any]:
    scores = [safe_score(r.get("record_score", 0.0)) for r in raw_results if isinstance(r, dict)]
    kept_scores = [safe_score(r.get("record_score", 0.0)) for r in final_results if isinstance(r, dict)]
    avg_score = round(mean(scores), 3) if scores else 0.0
    avg_final_score = round(mean(kept_scores), 3) if kept_scores else 0.0

    source_trust_scores = [safe_score(r.get("source_trust_score", 0.4)) for r in final_results if isinstance(r, dict)]
    avg_source_trust = round(mean(source_trust_scores), 3) if source_trust_scores else 0.4

    coverage_ratio = round((len(final_results) / len(raw_results)), 3) if raw_results else (1.0 if final_results else 0.0)
    mismatch_count = int((type_integrity_report or {}).get("total_type_mismatches") or 0)
    mismatch_ratio = mismatch_count / max(1, len(final_results))

    # Weighted blend of quality score, retention, source trust, and type
    # integrity.
    overall_score = round(
        clamp01(
            (avg_final_score * settings.SCORE_QUALITY_WEIGHT)
            + (coverage_ratio * settings.SCORE_COVERAGE_WEIGHT)
            + (avg_source_trust * settings.SCORE_SOURCE_TRUST_WEIGHT)
            + ((1.0 - clamp01(mismatch_ratio)) * settings.SCORE_TYPE_INTEGRITY_WEIGHT),
        ),
        3,
    )

    if not final_results:
        overall_score = 0.0

    source_ai = dict(ai_source_prediction or {})
    processed = int(source_ai.get("records_processed") or 0)
    structured = int(source_ai.get("records_ai_structured") or 0)
    source_ai["ai_row_rate"] = round((structured / processed), 3) if processed else 0.0

    # Build acquisition summary from per-URL lineages
    acquisition_summary: dict[str, Any] = {
        "per_url": acquisition_lineages or [],
        "direct": sum(1 for lin in (acquisition_lineages or []) if lin.get("state") == "direct"),
        "recovered": sum(1 for lin in (acquisition_lineages or []) if lin.get("state") == "recovered"),
        "session_expired": sum(
            1 for lin in (acquisition_lineages or []) if "session" in lin.get("state", "") or "recovery" in lin.get("state", "")
        ),
        "anti_bot_blocked": sum(1 for lin in (acquisition_lineages or []) if lin.get("state") == "anti_bot_blocked"),
        "empty_response": sum(
            1 for lin in (acquisition_lineages or []) if lin.get("state") in ("empty_response", "no_search_form")
        ),
    }
    # Summarize recommended next actions
    next_actions: dict[str, int] = {}
    for lin in acquisition_lineages or []:
        action = lin.get("recommended_next_action", "") or ""
        if action:
            next_actions[action] = next_actions.get(action, 0) + 1
    acquisition_summary["recommended_next_actions"] = next_actions

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
        "acquisition": acquisition_summary,
    }


def post_extract_validate_records(
    results: list[dict],
    schema_fields: list[SchemaField],
    warnings: list[str] | None = None,
) -> list[dict]:
    """Validate extracted records against semantic field rules.

    If a required field fails validation, the record is rejected.
    If an optional field fails validation, it is set to None (lowering score).
    """
    import logging

    val_logger = logging.getLogger("app.utils.quality")
    valid_records = []
    airport_failed = False
    for r in results:
        validated = dict(r)
        discard = False
        for field in schema_fields:
            val = validated.get(field.name)
            if val is not None and str(val).strip() != "":
                field_name_lower = field.name.lower()
                # Strict airport code or IATA code validation
                if "airport_code" in field_name_lower or "iata" in field_name_lower:
                    text = str(val).strip()
                    # Must be exactly 3 uppercase letters (e.g. JFK, MIA)
                    if not re.match(r"^[A-Z]{3}$", text):
                        airport_failed = True
                        val_logger.warning(
                            "[Validation] Field '%s' has invalid airport / IATA code value '%s' (must match ^[A-Z]{3}$)",
                            field.name,
                            text,
                        )
                        if field.required:
                            discard = True
                            break
                        validated[field.name] = None
        if not discard:
            valid_records.append(validated)

    if airport_failed and warnings is not None and "Airport-code fields failed semantic validation" not in warnings:
        warnings.append("Airport-code fields failed semantic validation")

    return valid_records
