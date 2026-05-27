"""Network payload extraction — find structured records in captured JSON responses.

Finds record arrays inside arbitrary JSON payloads, scores them against
the requested schema, maps fields using synonym/key matching, and returns
structured extraction results with provenance metadata.

No domain-specific logic — works for flights, hotels, groceries, ecommerce, etc.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field as dc_field
from typing import Any

from app.models import SchemaField, FieldType

logger = logging.getLogger(__name__)

# ── Field synonym map — generic, no domain-specific entries ─────────────
# Maps common JSON key names to canonical field names.
_FIELD_SYNONYMS: dict[str, list[str]] = {
    "name": ["name", "title", "label", "heading", "product_name", "item_name"],
    "price": ["price", "fare", "cost", "amount", "total", "rate", "fee", "value", "sum", "charge"],
    "airline": ["airline", "carrier", "operator", "provider", "vendor", "company", "brand"],
    "date": ["date", "day", "departure_date", "return_date", "arrival_date", "travel_date"],
    "time": ["time", "departure_time", "arrival_time", "dep_time", "arr_time", "schedule"],
    "currency": ["currency", "currency_code", "price_currency"],
    "location": ["location", "city", "country", "region", "place", "area", "destination", "origin"],
    "code": ["code", "id", "ref", "identifier", "flight_number", "sku", "airport_code"],
    "rating": ["rating", "score", "stars", "review", "grade"],
    "description": ["description", "desc", "summary", "details", "info"],
    "url": ["url", "link", "href", "website"],
    "image": ["image", "img", "photo", "picture", "thumbnail"],
}


@dataclass
class RecordArrayCandidate:
    """A candidate array of records found inside a JSON payload."""
    path: str  # e.g., "results" or "data.items"
    records: list[dict]
    source: str  # "network_payload" or "hydration_data"
    score: float = 0.0
    field_map: dict[str, FieldMapping] = dc_field(default_factory=dict)


@dataclass
class FieldMapping:
    """How a requested field maps to a JSON key."""
    requested_field: str
    mapped_from: str
    source: str = "network_payload"
    confidence: float = 0.0


@dataclass
class NetworkExtractionResult:
    """Result of extracting records from network payloads."""
    records: list[dict]
    source: str
    score: float
    field_map: dict[str, FieldMapping]
    record_count: int
    field_coverage: float


def find_record_arrays(payload: Any, path: str = "$", max_depth: int = 10) -> list[RecordArrayCandidate]:
    """Recursively find arrays of objects inside a JSON payload.
    
    Depth-limited to max_depth to prevent infinite recursion on
    circular or deeply nested structures.
    """
    candidates: list[RecordArrayCandidate] = []

    def _recurse(obj: Any, current_path: str, depth: int = 0) -> None:
        if depth >= max_depth:
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                child_path = f"{current_path}.{key}" if current_path else key
                if isinstance(value, list):
                    _check_array(value, child_path, "network_payload")
                _recurse(value, child_path, depth + 1)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _recurse(item, f"{current_path}[{i}]", depth + 1)

    def _check_array(arr: list, arr_path: str, source: str) -> None:
        if not arr:
            return
        records = [item for item in arr if isinstance(item, dict)]
        if len(records) < 2:
            return
        candidates.append(RecordArrayCandidate(
            path=arr_path,
            records=records,
            source=source,
        ))

    _recurse(payload, path)
    candidates.sort(key=lambda c: len(c.records), reverse=True)
    return candidates


def _value_matches_type(value: Any, field_type: FieldType) -> bool:
    """Check if a JSON value is compatible with the expected field type."""
    if value is None:
        return False
    s = str(value).strip()
    if not s:
        return False
    if field_type == FieldType.CURRENCY:
        return bool(re.search(r"[\d.,]+", s))
    if field_type == FieldType.NUMBER or field_type == FieldType.INTEGER or field_type == FieldType.FLOAT:
        return bool(re.match(r"^-?\d+(\.\d+)?$", s))
    if field_type == FieldType.EMAIL:
        return bool(re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", s))
    if field_type == FieldType.URL:
        return s.startswith(("http://", "https://"))
    if field_type == FieldType.DATE:
        return bool(re.search(r"\d{2,4}[-/]\d{2,4}[-/]\d{2,4}", s))
    if field_type == FieldType.PHONE:
        return bool(re.search(r"[\d\s\-()+]{7,}", s))
    if field_type == FieldType.BOOLEAN:
        return isinstance(value, bool) or s.lower() in ("true", "false", "yes", "no")
    return True


def _key_matches_field(key: str, field: SchemaField) -> float:
    """Score how well a JSON key matches a schema field, using synonyms."""
    key_lower = key.lower().replace("_", " ").replace("-", " ")
    field_lower = field.name.lower().replace("_", " ")

    if key_lower == field_lower:
        return 1.0
    if key_lower in field_lower or field_lower in key_lower:
        return 0.8

    for canon, synonyms in _FIELD_SYNONYMS.items():
        if field_lower == canon or field_lower in synonyms:
            if key_lower in synonyms:
                return 0.7
            for syn in synonyms:
                if syn in key_lower or key_lower in syn:
                    return 0.6

    if field.description:
        desc_words = set(field.description.lower().split())
        key_words = set(re.findall(r"[a-z]+", key_lower))
        overlap = desc_words & key_words
        if overlap:
            return min(0.5, len(overlap) * 0.15)

    return 0.0


def score_record_array(candidate: RecordArrayCandidate, schema: list[SchemaField]) -> float:
    """Score a candidate record array against the requested schema."""
    if not candidate.records or not schema:
        return 0.0

    records = candidate.records[:100]
    n = len(records)
    score = 0.0

    # Signal 1: Array size (up to 20)
    score += min(n, 20) * 1.0 * 0.2

    # Signal 2: Key structure consistency
    first_keys = set(records[0].keys())
    common_keys = first_keys.copy()
    for r in records[1:]:
        common_keys &= set(r.keys())
    common_ratio = len(common_keys) / max(len(first_keys), 1)
    score += common_ratio * 20.0

    # Signal 3: Schema field coverage via key matching
    mapped_count = 0
    for field in schema:
        best = 0.0
        for key in first_keys:
            match = _key_matches_field(key, field)
            if match > best:
                best = match
        if best > 0.5:
            mapped_count += 1
            mapped_ratio = mapped_count / len(schema)
            score += mapped_ratio * 30.0

    # Signal 4: Value type compatibility
    type_hits = 0
    type_checks = 0
    for r in records[:10]:
        for field in schema:
            for key, value in r.items():
                if _key_matches_field(key, field) > 0.5 and _value_matches_type(value, field.field_type):
                    type_hits += 1
                type_checks += 1
    if type_checks > 0:
        score += (type_hits / type_checks) * 20.0

    # Signal 5: Non-empty values
    total_values = sum(1 for r in records[:20] for v in r.values() if v is not None and str(v).strip())
    possible = len(records[:20]) * max(len(first_keys), 1)
    if possible > 0:
        score += (total_values / possible) * 10.0

    return min(score, 100.0)


def map_json_records_to_schema(
    records: list[dict],
    schema: list[SchemaField],
    source: str = "network_payload",
) -> tuple[list[dict], dict[str, FieldMapping]]:
    """Map JSON records to the requested schema, building field provenance.

    Returns (mapped_records, field_map).
    """
    field_map: dict[str, FieldMapping] = {}
    mapped_records: list[dict] = []

    # Build the best key→field mapping from the first few records
    first_keys: set[str] = set()
    for r in records[:5]:
        first_keys.update(r.keys())

    key_to_field: dict[str, tuple[SchemaField, float]] = {}
    for key in first_keys:
        for field in schema:
            confidence = _key_matches_field(key, field)
            if confidence > 0.4:
                if key not in key_to_field or confidence > key_to_field[key][1]:
                    key_to_field[key] = (field, confidence)

    # Map each record
    for record in records[:200]:
        mapped: dict = {}
        for key, (field, confidence) in key_to_field.items():
            if key in record and record[key] is not None:
                mapped[field.name] = record[key]
                if field.name not in field_map:
                    field_map[field.name] = FieldMapping(
                        requested_field=field.name,
                        mapped_from=f"$..{key}",
                        source=source,
                        confidence=round(confidence, 2),
                    )
        if mapped:
            mapped_records.append(mapped)

    return mapped_records, field_map


def extract_from_network_payloads(
    payloads: list[str | dict],
    schema: list[SchemaField],
) -> NetworkExtractionResult | None:
    """Find and extract records from captured network JSON payloads.

    Returns the best extraction result, or None if nothing useful was found.
    """
    if not payloads or not schema:
        return None

    best_candidate: RecordArrayCandidate | None = None
    best_score = 0.0

    for raw in payloads:
        try:
            if isinstance(raw, str):
                payload = json.loads(raw)
            else:
                payload = raw
        except Exception:
            continue

        candidates = find_record_arrays(payload)
        for candidate in candidates:
            score = score_record_array(candidate, schema)
            if score > best_score:
                best_score = score
                best_candidate = candidate

    if best_candidate is None or best_score < 15.0:
        return None

    mapped_records, field_map = map_json_records_to_schema(
        best_candidate.records, schema, source=best_candidate.source,
    )
    coverage = len(field_map) / max(len(schema), 1)

    return NetworkExtractionResult(
        records=mapped_records,
        source=best_candidate.source,
        score=round(best_score, 1),
        field_map=field_map,
        record_count=len(mapped_records),
        field_coverage=round(coverage, 2),
    )


def arbitrate_sources(
    dom_records: list[dict],
    dom_score: float,
    network_result: NetworkExtractionResult | None,
    schema: list[SchemaField],
) -> tuple[list[dict], str, dict[str, FieldMapping]]:
    """Choose the best extraction source: DOM or network payload.

    Returns (best_records, winning_source, field_map).
    """
    if network_result is None:
        return dom_records, "dom", {}

    dom_cov = sum(
        1 for r in dom_records[:20] for f in schema
        if r.get(f.name) is not None and str(r.get(f.name, "")).strip()
    ) / max(len(dom_records[:20]) * len(schema), 1)

    net_cov = network_result.field_coverage
    net_score = network_result.score

    # Network wins if significantly better coverage or higher record count
    if net_cov >= dom_cov + 0.2 or (net_score > dom_score and net_cov >= dom_cov):
        return network_result.records, network_result.source, network_result.field_map

    return dom_records, "dom", {}
