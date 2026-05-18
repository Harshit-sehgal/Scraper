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
    for mf in ("source_type", "source_url", "source_trust_score", "record_score", "_key"):
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
        id_fields = [f.name for f in schema_fields][:2] # fallback to first two fields

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

def _limit_source_records(records: list[dict], schema_fields: list[SchemaField], max_records: Optional[int] = None) -> list[dict]:
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
