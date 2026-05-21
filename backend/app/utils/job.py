import datetime
from app.utils.quality import normalized_dedup_text

def normalize_job_results(results: list[dict], schema_fields: list):
    """Force consistent schema order in each record and keep extra keys after standard fields."""
    normalized = []
    for record in results:
        ordered = {f.name: record.get(f.name) for f in schema_fields}
        # keep extras in deterministic sorted order to avoid randomness
        for key in sorted(record.keys()):
            if key not in ordered:
                ordered[key] = record[key]
        normalized.append(ordered)
    return normalized

def deduplicate_results(records: list[dict], schema_fields: list, deduplicate_field: str = "") -> list[dict]:
    if not records:
        return records

    seen = set()
    unique = []
    for r in records:
        if deduplicate_field:
            # User specified a specific field to dedup on
            dedup_value = normalized_dedup_text(r.get(deduplicate_field, ""))
        else:
            # Use ALL schema fields as a composite dedup key
            dedup_value = "|".join(
                normalized_dedup_text(r.get(f.name)) for f in schema_fields
            )

        if dedup_value and dedup_value not in seen:
            seen.add(dedup_value)
            unique.append(r)
        elif not dedup_value:
            unique.append(r)

    return unique

def mark_job_canceled(job, reason: str = "Canceled by user"):
    from app.models import JobStatus
    job.status = JobStatus.CANCELED
    job.error = reason
    job.completed_at = datetime.datetime.now().isoformat()
