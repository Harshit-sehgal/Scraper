from typing import Optional
from app.models import SchemaField


def normalize_scraped_record(record: dict, schema_fields: list[SchemaField]) -> dict:
    """Ensure consistent schema order and basic normalization of values."""
    from app.html_utils import _is_empty_value

    normalized: dict = {}
    for field in schema_fields:
        val = record.get(field.name)
        if _is_empty_value(val):
            normalized[field.name] = None
        else:
            normalized[field.name] = val
    # Preserve metadata fields needed for source breakdown and tracking
    for mf in ("source_type", "source_url", "source_trust_score", "record_score", "_key", "_extraction_method"):
        if mf in record:
            normalized[mf] = record[mf]
    return normalized


def _validate_extracted_data(record: dict, schema_fields: list[SchemaField]) -> bool:
    """Basic validation to ensure at least some meaningful data was found."""
    from app.html_utils import _is_empty_value

    meaningful_count = 0
    for field in schema_fields:
        val = record.get(field.name)
        if not _is_empty_value(val):
            meaningful_count += 1
    return meaningful_count > 0


def _dedupe_records(records: list[dict], schema_fields: list[SchemaField]) -> list[dict]:
    """Remove duplicate records based on normalized field content."""
    if not records:
        return []

    from app.utils.quality import normalized_dedup_text

    seen_keys = set()
    unique = []

    # Identify primary identifying fields (e.g., name, company)
    id_fields = [f.name for f in schema_fields if any(k in f.name.lower() for k in ["name", "company", "title"])]
    if not id_fields:
        # fallback to all fields for domain-specific records
        id_fields = [f.name for f in schema_fields]

    for record in records:
        id_vals = []
        for f in id_fields:
            v = record.get(f)
            id_vals.append(normalized_dedup_text(v))

        key = "|".join(id_vals)
        if key not in seen_keys:
            unique.append(record)
            seen_keys.add(key)

    return unique


def _limit_source_records(
    records: list[dict], schema_fields: list[SchemaField], max_records: Optional[int] = None
) -> list[dict]:
    """Limit the number of records from a single source, prioritizing those with contacts."""
    if max_records is None:
        from app.config import settings

        max_records = settings.MAX_RECORDS_PER_SOURCE

    if len(records) <= max_records:
        return records

    from app.models import FieldType

    email_fields = {f.name for f in schema_fields if f.field_type == FieldType.EMAIL}
    phone_fields = {f.name for f in schema_fields if f.field_type == FieldType.PHONE}

    def _priority(r):
        has_email = 1 if any(r.get(f) for f in email_fields) else 0
        has_phone = 1 if any(r.get(f) for f in phone_fields) else 0
        return (has_email + has_phone, r.get("record_score", 0.0))

    return sorted(records, key=_priority, reverse=True)[:max_records]


def _trim_prompt_value(value, max_chars: int = 180):
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _prepare_records_for_ai(records: list[dict], schema_fields: list[SchemaField]) -> list[dict]:
    """Convert records to a compact JSON format for LLM processing."""
    from app.html_utils import _is_empty_value

    prepared = []
    for r in records:
        item = {}
        for f in schema_fields:
            val = r.get(f.name)
            if not _is_empty_value(val):
                item[f.name] = _trim_prompt_value(val)
        if item:
            prepared.append(item)
    return prepared


def _get_word_tokens(name: str) -> set[str]:
    """Split a field name into word tokens for boundary-safe matching."""
    import re

    return {t.lower() for t in re.split(r"[_\-\s]+", name) if t}


def _profile_field_type_hint(profile_field_cfg: dict | None) -> str | None:
    if not profile_field_cfg:
        return None
    return (profile_field_cfg.get("type") or "").strip().lower() or None


def _schema_type_alignment_bonus(profile_type: str | None, schema_field: SchemaField) -> float:
    if not profile_type:
        return 0.0
    from app.config import settings

    compatible = settings.PROFILE_SELECTOR_TYPE_COMPATIBILITY.get(profile_type, ())
    if schema_field.field_type.value in compatible:
        return settings.PROFILE_ALIGNMENT_SCORE_TYPE_BONUS
    return 0.0


def _alignment_score(
    profile_key: str,
    schema_field: SchemaField,
    profile_field_cfg: dict | None = None,
) -> float:
    """Score how well a profile field key matches a user schema field (higher = better)."""
    from app.config import settings
    from app.intent_parser import (
        build_semantic_synonym_groups,
        role_tokens_are_exclusive,
        semantic_needs_are_exclusive,
        tokens_to_semantic_need,
    )

    pk_lower = profile_key.lower()
    sf_lower = schema_field.name.lower()
    pk_tokens = _get_word_tokens(profile_key)
    sf_tokens = _get_word_tokens(schema_field.name)
    if schema_field.description:
        sf_tokens |= _get_word_tokens(schema_field.description)

    if pk_lower == sf_lower:
        return settings.PROFILE_ALIGNMENT_SCORE_EXACT

    score = 0.0

    if pk_lower.rstrip("s") == sf_lower.rstrip("s") and min(len(pk_lower), len(sf_lower)) >= 3:
        score += settings.PROFILE_ALIGNMENT_SCORE_PLURAL
    if pk_lower + "s" == sf_lower or sf_lower + "s" == pk_lower:
        score += settings.PROFILE_ALIGNMENT_SCORE_PLURAL - 5.0
    if pk_tokens and sf_tokens:
        overlap = pk_tokens & sf_tokens
        if overlap:
            score += settings.PROFILE_ALIGNMENT_SCORE_TOKEN_OVERLAP * len(overlap) / max(len(pk_tokens), len(sf_tokens))

    if len(pk_lower) >= 3 and pk_lower in sf_lower:
        score += settings.PROFILE_ALIGNMENT_SCORE_SUBSTRING
    elif len(sf_lower) >= 3 and sf_lower in pk_lower:
        score += settings.PROFILE_ALIGNMENT_SCORE_REVERSE_SUBSTRING

    for group in build_semantic_synonym_groups():
        if pk_tokens & group and sf_tokens & group:
            score += settings.PROFILE_ALIGNMENT_SCORE_SYNONYM
            break

    pk_need = tokens_to_semantic_need(pk_tokens)
    sf_need = tokens_to_semantic_need(sf_tokens)

    profile_type = _profile_field_type_hint(profile_field_cfg)
    score += _schema_type_alignment_bonus(profile_type, schema_field)

    if semantic_needs_are_exclusive(pk_need, sf_need) or role_tokens_are_exclusive(pk_tokens, sf_tokens):
        score -= settings.PROFILE_ALIGNMENT_NEGATIVE_PENALTY

    return score


def align_extracted_keys_to_schema(
    raw_records: list[dict],
    schema_fields: list[SchemaField],
    selector_field_defs: dict | None = None,
    user_intent: str = "",
) -> list[dict]:
    """Map extracted selector keys to the user's schema using best-match scoring.

    Reads every key present in raw records (full selector field set), then assigns
    each to the schema field with the highest alignment score (one-to-one).
    """
    if not raw_records or not schema_fields:
        return raw_records

    profile_keys = [k for k in raw_records[0].keys() if not k.startswith("_")]
    if "_extraction_method" in raw_records[0]:
        profile_keys.append("_extraction_method")
    if not profile_keys:
        return raw_records

    selector_field_defs = selector_field_defs or {}
    intent_boost_fields: set[str] = set()
    if user_intent:
        from app.intent_parser import keywords_to_tokens, parse_user_intent

        intent = parse_user_intent(user_intent)
        for _need, kws in intent.semantic_needs.items():
            intent_boost_fields |= keywords_to_tokens(kws)

    candidates: list[tuple[float, str, str]] = []
    schema_name_set = {f.name.lower(): f.name for f in schema_fields}
    for pk in profile_keys:
        pk_cfg = selector_field_defs.get(pk) if isinstance(selector_field_defs.get(pk), dict) else None
        pk_tokens = _get_word_tokens(pk)
        pk_lower = pk.lower()
        if pk_lower in schema_name_set:
            candidates.append((float("inf"), pk, schema_name_set[pk_lower]))
            continue
        for sf in schema_fields:
            sc = _alignment_score(pk, sf, pk_cfg)
            sf_tokens = _get_word_tokens(sf.name)
            if sf.description:
                sf_tokens |= _get_word_tokens(sf.description)
            if intent_boost_fields and (pk_tokens & intent_boost_fields) and (sf_tokens & intent_boost_fields):
                from app.config import settings

                sc += settings.PROFILE_ALIGNMENT_SCORE_SYNONYM / 2
            if sc > 0:
                candidates.append((sc, pk, sf.name))

    candidates.sort(key=lambda x: x[0], reverse=True)
    mapping: dict[str, str] = {}
    used_schema: set[str] = set()
    for sc, pk, sf_name in candidates:
        if pk in mapping or sf_name in used_schema:
            continue
        mapping[pk] = sf_name
        used_schema.add(sf_name)

    schema_names = {f.name for f in schema_fields}
    aligned_records = []
    for r in raw_records:
        aligned = {}
        for pk, val in r.items():
            if pk.startswith("_") and pk != "_extraction_method":
                continue
            if pk in mapping:
                aligned[mapping[pk]] = val
            elif pk in schema_names:
                aligned[pk] = val
            elif pk == "_extraction_method":
                aligned[pk] = val
        aligned_records.append(aligned)

    return aligned_records


def align_profile_keys_to_schema(
    raw_records: list[dict],
    schema_fields: list[SchemaField],
    profile_fields: dict | None = None,
) -> list[dict]:
    """Backward-compatible alias for profile-based extraction."""
    return align_extracted_keys_to_schema(raw_records, schema_fields, selector_field_defs=profile_fields)


def process_raw_records(
    raw_records: list[dict],
    schema_fields: list[SchemaField],
    min_record_score: float,
    profile_fields: dict | None = None,
    user_intent: str = "",
) -> list[dict]:
    """Normalize, score, dedup, limit, and run pipeline on raw extracted records."""
    from app.utils.quality import score_record_quality
    from app.semantic_pipeline import run_pipeline
    from app.config import settings

    # Align full selector output to the user schema (best match per field)
    aligned_records = align_extracted_keys_to_schema(
        raw_records,
        schema_fields,
        selector_field_defs=profile_fields,
        user_intent=user_intent,
    )

    results = []
    for r in aligned_records:
        norm = normalize_scraped_record(r, schema_fields)
        norm["record_score"] = score_record_quality(norm, schema_fields)
        results.append(norm)

    results = [
        r for r in results if r.get("record_score", 0.0) >= (min_record_score * settings.RECORD_ACCEPTANCE_FACTOR)
    ]
    results = _dedupe_records(results, schema_fields)
    results = _limit_source_records(results, schema_fields)
    avg_score = sum(r.get("record_score", 0) for r in results) / max(len(results), 1)
    if avg_score < 0.5 and results:
        results = run_pipeline(results, [f.name for f in schema_fields])
    return results
