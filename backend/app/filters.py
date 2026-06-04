"""
Post-Processing Engine: Type coercion, Geospatial distance calculation, and Data Filtering.
Uses geopy (free OpenStreetMap Nominatim geocoder) for distance calculations.
"""

import asyncio
import logging
import re
from typing import Any

from geopy.distance import geodesic
from geopy.geocoders import Nominatim

from app.config import settings
from app.models import FieldType, FilterOperator, FilterRule, SchemaField

# ──────────────────────────────────────────────
# Geocoding & Distance (Nominatim; no paid API key required)
# ──────────────────────────────────────────────

_geocoder = Nominatim(user_agent=settings.GEOCODER_USER_AGENT, timeout=settings.GEOCODER_TIMEOUT)
_geocode_cache: dict[str, tuple[float, float] | None] = {}
_LOCATION_NAME_HINTS = ("location", "address", "city", "area", "region", "zip", "pincode")


async def geocode_address(address: str) -> tuple[float, float] | None:
    """Convert an address string to (latitude, longitude) using free OpenStreetMap."""
    from app.geocode_cache import get_geocode_cache

    cache = get_geocode_cache()
    cached = cache.get(address)
    if cached is not None:
        if cached[2] == "EXCLUDED_NEGATIVE_CACHE":
            return None
        return (cached[0], cached[1])

    max_retries = 3
    backoff = 1.0  # Base delay in seconds
    for attempt in range(max_retries):
        try:
            location = await asyncio.to_thread(_geocoder.geocode, address)
            if location:
                coords = (location.latitude, location.longitude)
                cache.set(address, location.latitude, location.longitude, location.address)
                return coords
            break  # If geocoding succeeded but returned no location, break early
        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(
                    "Geocoding attempt %d failed for '%s' (retrying in %.1fs): %s",
                    attempt + 1,
                    address,
                    backoff,
                    str(e),
                )
                await asyncio.sleep(backoff)
                backoff *= 2.0  # Exponential backoff
            else:
                logging.exception("Geocode error for %s after %d attempts: %s", address, max_retries, e)

    cache.set_negative(address)
    return None


def calculate_distance(point1: tuple[float, float], point2: tuple[float, float], unit: str = "km") -> float:
    """
    Calculate straight-line (geodesic) distance between two lat / lng points.
    Returns distance in km or miles.
    """
    dist_km = geodesic(point1, point2).kilometers
    if unit == "miles":
        return dist_km * 0.621371  # type: ignore[no-any-return]
    return dist_km  # type: ignore[no-any-return]


# ──────────────────────────────────────────────
# Type Coercion Engine
# ──────────────────────────────────────────────


def coerce_value(value: Any, field_type: FieldType):
    """
    Coerce a raw value to its declared type.
    e.g., "18 years old" → 18 (integer), "true" → True (boolean)
    """
    if value is None:
        return None

    try:
        if field_type == FieldType.INTEGER:
            if isinstance(value, (int, float)):
                return int(value)
            # Extract first number from string like "Age: 25 years"
            match = re.search(r"-?\d+", str(value))
            return int(match.group()) if match else None

        elif field_type == FieldType.FLOAT:
            if isinstance(value, (int, float)):
                return float(value)
            match = re.search(r"-?\d+\.?\d*", str(value))
            return float(match.group()) if match else None

        elif field_type == FieldType.BOOLEAN:
            if isinstance(value, bool):
                return value
            s = str(value).lower().strip()
            if s in ("true", "yes", "1", "y"):
                return True
            elif s in ("false", "no", "0", "n"):
                return False
            return None

        elif field_type == FieldType.EMAIL:
            match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", str(value))
            return match.group() if match else str(value)

        elif field_type == FieldType.PHONE:
            # Keep digits, +, -, (, ), spaces
            cleaned = re.sub(r"[^\d+\-() ]", "", str(value))
            return cleaned if cleaned else str(value)

        elif field_type == FieldType.LIST_STRING:
            if isinstance(value, list):
                return [str(v) for v in value]
            return [str(value)]

        elif field_type == FieldType.CURRENCY:
            # Extract number from currency strings like "$1,200.50" or "₹5000"
            cleaned = re.sub(r"[^\d.\-]", "", str(value))
            match = re.search(r"-?\d+\.?\d*", cleaned)
            return float(match.group()) if match else None

        elif field_type == FieldType.PERCENTAGE:
            # Extract number from "85%" or "85 percent"
            match = re.search(r"-?\d+\.?\d*", str(value))
            return float(match.group()) if match else None

        else:
            return str(value) if value is not None else None

    except Exception as e:
        logging.exception(e)
        return str(value) if value is not None else None


def coerce_record(record: dict, schema_fields: list[SchemaField]) -> dict:
    """Apply type coercion to all fields in a record."""
    field_types = {f.name: f.field_type for f in schema_fields}
    coerced = {}
    for key, value in record.items():
        if key in field_types:
            coerced[key] = coerce_value(value, field_types[key])
        else:
            coerced[key] = value
    return coerced


def normalize_record(record: dict, schema_fields: list[SchemaField]) -> dict:
    """Ensure a record contains all schema fields (same order), plus any extra keys."""
    normalized = {}
    for field in schema_fields:
        normalized[field.name] = record.get(field.name)

    for key, value in record.items():
        if key not in normalized:
            normalized[key] = value

    return normalized


def _looks_like_email(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", (value or "").strip()))


def _looks_like_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    return 10 <= len(digits) <= 15


def _looks_like_url(value: str) -> bool:
    text = (value or "").strip().lower()
    if text.startswith(("http://", "https://", "www.")):
        return True
    if "@" in text:
        return False
    return bool(re.search(r"\b[\w.-]+\.[a-z]{2,}(?:/\S*)?\b", text))


def _is_entity_name_field(field_name: str) -> bool:
    low = (field_name or "").lower()
    return any(token in low for token in ["company", "name", "studio", "firm", "agency"])


def enforce_schema_integrity(record: dict, schema_fields: list[SchemaField]) -> tuple[dict, list[str]]:
    """Apply strict per-field semantic cleanup and record mismatch flags."""
    cleaned = dict(record)
    mismatches: list[str] = []

    email_fields = [f.name for f in schema_fields if f.field_type == FieldType.EMAIL]
    phone_fields = [f.name for f in schema_fields if f.field_type == FieldType.PHONE]

    for field in schema_fields:
        key = field.name
        value = cleaned.get(key)
        if value is None:
            continue

        if isinstance(value, list):
            value_text = ", ".join(str(v) for v in value if v is not None)
        else:
            value_text = str(value).strip()

        if not value_text:
            continue

        if field.field_type == FieldType.EMAIL and not _looks_like_email(value_text):
            mismatches.append(f"{key}:expected_email")
            cleaned[key] = None
            continue

        if field.field_type == FieldType.PHONE and not _looks_like_phone(value_text):
            mismatches.append(f"{key}:expected_phone")
            cleaned[key] = None
            continue

        if field.field_type == FieldType.URL and not _looks_like_url(value_text):
            mismatches.append(f"{key}:expected_url")
            cleaned[key] = None
            continue

        if _is_entity_name_field(key):
            if _looks_like_email(value_text):
                target = next((ef for ef in email_fields if not cleaned.get(ef)), None)
                if target:
                    cleaned[target] = value_text
                    mismatches.append(f"{key}:moved_to_{target}")
                else:
                    mismatches.append(f"{key}:email_in_name")
                cleaned[key] = None
                continue

            if _looks_like_phone(value_text):
                target = next((pf for pf in phone_fields if not cleaned.get(pf)), None)
                if target:
                    cleaned[target] = value_text
                    mismatches.append(f"{key}:moved_to_{target}")
                else:
                    mismatches.append(f"{key}:phone_in_name")
                cleaned[key] = None
                continue

            if _looks_like_url(value_text):
                mismatches.append(f"{key}:url_in_name")
                cleaned[key] = None

    if mismatches:
        cleaned["type_mismatch_flags"] = sorted(set(mismatches))

    return cleaned, mismatches


# ──────────────────────────────────────────────
# Filter Engine
# ──────────────────────────────────────────────


async def apply_filter(record: dict, rule: FilterRule, schema_fields: list[SchemaField]) -> bool:
    """
    Check if a single record passes a filter rule.
    Returns True if the record should be KEPT.
    """
    value = record.get(rule.field_name)

    # Special case: Distance filter
    if rule.operator == FilterOperator.DISTANCE_WITHIN:
        return await _apply_distance_filter(value, rule)

    # Is Empty / Is Not Empty (works on None)
    if rule.operator == FilterOperator.IS_EMPTY:
        return value is None or str(value).strip() == ""
    if rule.operator == FilterOperator.IS_NOT_EMPTY:
        return value is not None and str(value).strip() != ""

    if value is None:
        return False

    try:
        compare_value = rule.value

        # Numeric comparisons
        if rule.operator in (
            FilterOperator.GREATER_THAN,
            FilterOperator.LESS_THAN,
            FilterOperator.GREATER_EQUAL,
            FilterOperator.LESS_EQUAL,
        ):
            num_val = float(value) if not isinstance(value, (int, float)) else value
            num_compare = float(compare_value)

            if rule.operator == FilterOperator.GREATER_THAN:
                return num_val > num_compare
            elif rule.operator == FilterOperator.LESS_THAN:
                return num_val < num_compare
            elif rule.operator == FilterOperator.GREATER_EQUAL:
                return num_val >= num_compare
            elif rule.operator == FilterOperator.LESS_EQUAL:
                return num_val <= num_compare

        # Regex matching
        if rule.operator == FilterOperator.MATCHES_REGEX:
            return bool(re.search(compare_value, str(value), re.IGNORECASE))

        # String comparisons
        str_val = str(value).lower()
        str_compare = compare_value.lower()

        if rule.operator == FilterOperator.EQUALS:
            return str_val == str_compare
        elif rule.operator == FilterOperator.NOT_EQUALS:
            return str_val != str_compare
        elif rule.operator == FilterOperator.CONTAINS:
            return str_compare in str_val
        elif rule.operator == FilterOperator.NOT_CONTAINS:
            return str_compare not in str_val
        elif rule.operator == FilterOperator.STARTS_WITH:
            return str_val.startswith(str_compare)
        elif rule.operator == FilterOperator.ENDS_WITH:
            return str_val.endswith(str_compare)
        elif rule.operator == FilterOperator.IN_LIST:
            allowed = [v.strip().lower() for v in compare_value.split(",")]
            return str_val in allowed

    except (ValueError, TypeError) as e:
        logging.warning("Could not apply filter on %s: %s", rule.field_name, e)
        return False

    return True


async def _apply_distance_filter(location_value, rule: FilterRule) -> bool:
    """
    Special distance filter: geocodes both the record's location and the
    origin address, then checks if the distance is within the threshold.
    """
    if not location_value or not rule.origin_address:
        return False

    target_coords = await geocode_address(str(location_value))
    origin_coords = await geocode_address(rule.origin_address)

    if not target_coords or not origin_coords:
        logging.warning("Could not geocode: %s or %s", location_value, rule.origin_address)
        return False

    unit = rule.distance_unit or "km"
    distance = calculate_distance(origin_coords, target_coords, unit)
    threshold = float(rule.value)

    return distance <= threshold


def _infer_location_field_names(
    schema_fields: list[SchemaField],
    preferred_field: str = "",
) -> list[str]:
    candidates: list[str] = []

    if preferred_field:
        candidates.append(preferred_field)

    for field in schema_fields:
        if field.field_type == FieldType.LOCATION:
            candidates.append(field.name)

    for field in schema_fields:
        name_l = field.name.lower()
        if any(h in name_l for h in _LOCATION_NAME_HINTS):
            candidates.append(field.name)

    # Preserve order and remove duplicates
    seen = set()
    deduped = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def _pick_record_location(record: dict, candidate_fields: list[str]) -> str | None:
    for field in candidate_fields:
        value = record.get(field)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


async def apply_location_radius(
    records: list[dict],
    schema_fields: list[SchemaField],
    origin_address: str,
    max_distance_km: float | None,
    preferred_location_field: str = "",
) -> tuple[list[dict], dict]:
    """
    Filter records to those within the given km radius from origin_address.
    Adds distance_km field to kept records when distance can be computed.
    """
    report = {
        "applied": False,
        "origin": origin_address,
        "max_distance_km": max_distance_km,
        "kept": len(records),
        "dropped": 0,
        "reason": "",
    }

    if not records:
        report["reason"] = "empty_records"
        return records, report

    if not origin_address or max_distance_km is None:
        report["reason"] = "radius_not_configured"
        return records, report

    if max_distance_km < 0:
        report["reason"] = "invalid_radius"
        return records, report

    origin_coords = await geocode_address(origin_address)
    if not origin_coords:
        report["reason"] = "origin_geocode_failed"
        return records, report

    candidate_fields = _infer_location_field_names(schema_fields, preferred_location_field)
    if not candidate_fields:
        report["reason"] = "no_location_field"
        return records, report

    kept: list[dict] = []
    dropped_missing_location = 0
    dropped_geocode_fail = 0

    for record in records:
        location_value = _pick_record_location(record, candidate_fields)
        if not location_value:
            dropped_missing_location += 1
            continue

        target_coords = await geocode_address(location_value)
        if not target_coords:
            dropped_geocode_fail += 1
            continue

        distance_km = calculate_distance(origin_coords, target_coords, unit="km")
        if distance_km <= max_distance_km:
            with_distance = dict(record)
            with_distance["distance_km"] = round(distance_km, 2)
            kept.append(with_distance)

    report["applied"] = True
    report["kept"] = len(kept)
    report["dropped"] = len(records) - len(kept)
    report["dropped_missing_location"] = dropped_missing_location
    report["dropped_geocode_failed"] = dropped_geocode_fail
    report["location_fields_checked"] = candidate_fields

    return kept, report


async def process_results(
    raw_results: list[dict],
    schema_fields: list[SchemaField],
    filters: list[FilterRule],
) -> tuple[list[dict], int, int, dict]:
    """
    Full post-processing pipeline:
    1. Coerce types
    2. Apply all filters
    3. Return (filtered_results, total_count, filtered_count)
    """
    total = len(raw_results)

    # Step 1: Type coercion
    coerced = [coerce_record(r, schema_fields) for r in raw_results]

    # Step 2: Apply filters
    if filters:
        filtered = []
        for record in coerced:
            results = []
            for rule in filters:
                results.append(await apply_filter(record, rule, schema_fields))
            if all(results):
                filtered.append(record)
    else:
        filtered = coerced

    # Step 3: Normalize records to schema order and include missing keys
    normalized = [normalize_record(r, schema_fields) for r in filtered]

    mismatch_total = 0
    records_with_mismatch = 0
    strict_cleaned = []
    for record in normalized:
        cleaned, mismatches = enforce_schema_integrity(record, schema_fields)
        if mismatches:
            records_with_mismatch += 1
            mismatch_total += len(mismatches)
        strict_cleaned.append(cleaned)

    integrity_report = {
        "records_with_type_mismatch": records_with_mismatch,
        "total_type_mismatches": mismatch_total,
    }

    return strict_cleaned, total, len(strict_cleaned), integrity_report
