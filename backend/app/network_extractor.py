"""Network / XHR Extractor — Extracts structured records from network JSON payloads,
hydration data, and script state objects.

Priority order (highest first):
  1. JSON-LD structured data (ld+json scripts)
  2. Next.js __NEXT_DATA__ page props
  3. Window __INITIAL_STATE__ / __PRELOADED_STATE__
  4. Apollo / Relay client-side cache
  5. Inline structured JSON in <script> tags
  6. Application / JSON responses captured during rendering

This module uses domain-agnostic heuristics rather than site-specific field
names or selectors. It maps structured JSON keys to schema fields using
semantic alignment.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_from_network(
    hydration_data: dict[str, Any],
    schema_fields: list,
    url: str = "",  # noqa: ARG001, RUF100
    network_payloads: list[dict] | None = None,
) -> list[dict]:
    """Try to extract structured records from page hydration / network data.

    Args:
        hydration_data: The hydration_data dict collected by page_evidence_collector.
        schema_fields: Schema fields to map extracted values to.
        url: The page URL (for context).
        network_payloads: Optional list of captured network JSON payloads from
                          browser network interception (fetch / XHR / GraphQL responses).

    Returns:
        List of extracted records aligned to schema fields, or empty list.

    """
    if not schema_fields:
        return []

    records: list[dict] = []

    # Priority 0: Network payloads (actual API responses captured via Playwright)
    # These are the most reliable source when available.
    if network_payloads:
        extracted = _extract_records_from_payloads(network_payloads, schema_fields)
        if extracted:
            logger.info(
                "[NetworkExtractor] Extracted %d records from %d browser network payloads",
                len(extracted),
                len(network_payloads),
            )
            records.extend(extracted)

    if not hydration_data:
        return records

    # Priority 1: JSON-LD structured data
    jsonld = hydration_data.get("jsonld", [])
    if jsonld:
        extracted = _extract_from_jsonld(jsonld, schema_fields)
        if extracted:
            logger.info(
                "[NetworkExtractor] Extracted %d records from JSON-LD",
                len(extracted),
            )
            records.extend(extracted)

    # Priority 2: Next.js page props (often contain the main data)
    nextjs_props = hydration_data.get("nextjs_page_props", {})
    if nextjs_props:
        extracted = _extract_from_nested_json(nextjs_props, schema_fields)
        if extracted:
            logger.info(
                "[NetworkExtractor] Extracted %d records from Next.js page props",
                len(extracted),
            )
            records.extend(extracted)

    # Priority 3: Next.js initial state
    nextjs_state = hydration_data.get("nextjs_initial_state", {})
    if nextjs_state:
        extracted = _extract_from_nested_json(nextjs_state, schema_fields)
        if extracted:
            logger.info(
                "[NetworkExtractor] Extracted %d records from Next.js initial state",
                len(extracted),
            )
            records.extend(extracted)

    # Priority 4: Window INITIAL_STATE / PRELOADED_STATE
    for var_name in ["__INITIAL_STATE__", "__PRELOADED_STATE__", "window.__INITIAL_STATE__"]:
        state_data = hydration_data.get(var_name, {})
        if state_data:
            extracted = _extract_from_nested_json(state_data, schema_fields)
            if extracted:
                logger.info(
                    "[NetworkExtractor] Extracted %d records from %s",
                    len(extracted),
                    var_name,
                )
                records.extend(extracted)

    # Priority 5: Apollo state (GraphQL cache)
    apollo = hydration_data.get("apollo_state", {})
    if apollo:
        extracted = _extract_from_apollo_state(apollo, schema_fields)
        if extracted:
            logger.info(
                "[NetworkExtractor] Extracted %d records from Apollo state",
                len(extracted),
            )
            records.extend(extracted)

    if records:
        # Deduplicate records by content similarity
        records = _deduplicate_records(records)
        # Score records
        from app.utils.quality import score_record_quality

        for r in records:
            r["record_score"] = score_record_quality(r, schema_fields)
        records.sort(key=lambda r: r.get("record_score", 0.0), reverse=True)

    return records


# ---------------------------------------------------------------------------
# JSON-LD extraction
# ---------------------------------------------------------------------------


def _extract_from_jsonld(
    jsonld_data: list[dict],
    schema_fields: list,
) -> list[dict]:
    """Extract records from JSON-LD structured data."""
    records: list[dict] = []

    for item in jsonld_data:
        if not isinstance(item, dict):
            continue

        # Handle @graph (collections of items)
        graph = item.get("@graph", [])
        if isinstance(graph, list) and graph:
            for graph_item in graph:
                if isinstance(graph_item, dict):
                    record = _map_jsonld_item(graph_item, schema_fields)
                    if record:
                        records.append(record)
            continue

        # Handle @type-based single items
        if item.get("@type"):
            record = _map_jsonld_item(item, schema_fields)
            if record:
                records.append(record)
            continue

        # Handle @set or itemListElement (lists of items)
        for list_key in ["itemListElement", "items", "results", "data", "elements", "entries"]:
            items = item.get(list_key, [])
            if isinstance(items, list) and items:
                for sub_item in items:
                    if isinstance(sub_item, dict):
                        record = _map_jsonld_item(sub_item, schema_fields)
                        if record:
                            records.append(record)
                if records:
                    return records

        # Handle hasPart (structured content sections)
        has_parts = item.get("hasPart", [])
        if isinstance(has_parts, list):
            for part in has_parts:
                if isinstance(part, dict):
                    record = _map_jsonld_item(part, schema_fields)
                    if record:
                        records.append(record)
            if records:
                return records

        # Direct key-value mapping
        record = _map_json_keys_to_schema(item, schema_fields)
        if record:
            records.append(record)

    return records


def _map_jsonld_item(item: dict, schema_fields: list) -> dict | None:
    """Map a single JSON-LD item to schema fields.

    Extracts common JSON-LD properties and maps them to schema fields
    by semantic role (type -> field mapping).
    """
    if not item or not isinstance(item, dict):
        return None

    record: dict = {}
    item_type = (item.get("@type") or "").lower()

    # Type-based extraction
    type_handlers = {
        "product": _extract_product_fields,
        "offer": _extract_offer_fields,
        "aggregateoffer": _extract_offer_fields,
        "flight": _extract_flight_fields,
        "flightreservation": _extract_flight_fields,
        "hotel": _extract_hotel_fields,
        "lodgingbusiness": _extract_hotel_fields,
        "restaurant": _extract_restaurant_fields,
        "foodestablishment": _extract_restaurant_fields,
        "jobposting": _extract_job_fields,
        "event": _extract_event_fields,
        "localbusiness": _extract_business_fields,
        "organization": _extract_business_fields,
        "person": _extract_person_fields,
        "article": _extract_article_fields,
        "newsarticle": _extract_article_fields,
        "book": _extract_book_fields,
        "movie": _extract_movie_fields,
        "softwareapplication": _extract_app_fields,
    }

    handler = type_handlers.get(item_type)
    if handler:
        record = handler(item)

    # Always try key-value alignment as well (in case type handler missed
    # something)
    key_mapped = _map_json_keys_to_schema(item, schema_fields)
    for k, v in key_mapped.items():
        if k not in record or not record.get(k):
            record[k] = v

    # Filter: only return if at least one meaningful value
    if any(v for v in record.values() if v not in (None, "", [])):
        return record

    return None


# ---------------------------------------------------------------------------
# Type-specific JSON-LD handlers
# ---------------------------------------------------------------------------


def _extract_product_fields(item: dict) -> dict:
    return {
        "name": item.get("name", "") or "",
        "description": item.get("description", "") or "",
        "brand": item.get("brand", {}).get("name", "") if isinstance(item.get("brand"), dict) else "",
        "sku": item.get("sku", "") or "",
        "image": item.get("image", "") or "",
        "category": item.get("category", "") or "",
    }


def _extract_offer_fields(item: dict) -> dict:
    price = (
        item.get("price", "") or item.get("priceSpecification", {}).get("price", "")
        if isinstance(item.get("priceSpecification"), dict)
        else ""
    )
    currency = item.get("priceCurrency", "") or ""
    price_str = f"{currency}{price}" if price and currency else str(price)
    return {
        "price": price_str,
        "price_currency": currency,
        "availability": item.get("availability", "") or "",
        "condition": item.get("itemCondition", "") or "",
        "name": item.get("name", "") or "",
        "description": item.get("description", "") or "",
    }


def _extract_flight_fields(item: dict) -> dict:
    carrier = ""
    if isinstance(item.get("airline"), dict):
        carrier = item["airline"].get("name", "")
    elif isinstance(item.get("airline"), str):
        carrier = item["airline"]

    departure_airport = ""
    arrival_airport = ""
    departure_time = ""
    arrival_time = ""
    departure_date = ""

    dep_info = item.get("departureAirport") or item.get("departureTerminal") or {}
    arr_info = item.get("arrivalAirport") or item.get("arrivalTerminal") or {}

    if isinstance(dep_info, dict):
        departure_airport = dep_info.get("name", "") or dep_info.get("iataCode", "") or ""
    if isinstance(arr_info, dict):
        arrival_airport = arr_info.get("name", "") or arr_info.get("iataCode", "") or ""

    dep_time = item.get("departureTime", "") or ""
    arr_time = item.get("arrivalTime", "") or ""
    if dep_time:
        parts = dep_time.split("T")
        if len(parts) == 2:
            departure_date = parts[0]
            departure_time = parts[1][:5]
    if arr_time:
        parts = arr_time.split("T")
        if len(parts) == 2:
            arrival_time = parts[1][:5]

    return {
        "carrier": carrier,
        "flight_number": item.get("flightNumber", "") or "",
        "origin": departure_airport,
        "destination": arrival_airport,
        "departure_date": departure_date,
        "departure_time": departure_time,
        "arrival_time": arrival_time,
        "price": item.get("totalPrice", "") or "",
    }


def _extract_hotel_fields(item: dict) -> dict:
    return {
        "name": item.get("name", "") or "",
        "description": item.get("description", "") or "",
        "address": _extract_address(item),
        "rating": (
            item.get("aggregateRating", {}).get("ratingValue", "") if isinstance(item.get("aggregateRating"), dict) else ""
        ),
        "price_range": item.get("priceRange", "") or "",
        "telephone": item.get("telephone", "") or "",
        "image": item.get("image", "") or "",
        "url": item.get("url", "") or "",
    }


def _extract_restaurant_fields(item: dict) -> dict:
    return {
        "name": item.get("name", "") or "",
        "description": item.get("description", "") or "",
        "address": _extract_address(item),
        "rating": (
            item.get("aggregateRating", {}).get("ratingValue", "") if isinstance(item.get("aggregateRating"), dict) else ""
        ),
        "price_range": item.get("priceRange", "") or "",
        "telephone": item.get("telephone", "") or "",
        "cuisine": ", ".join(item.get("servesCuisine", [])) if isinstance(item.get("servesCuisine"), list) else "",
        "url": item.get("url", "") or "",
    }


def _extract_job_fields(item: dict) -> dict:
    return {
        "title": item.get("title", "") or item.get("name", "") or "",
        "description": item.get("description", "") or "",
        "company": (
            item.get("hiringOrganization", {}).get("name", "") if isinstance(item.get("hiringOrganization"), dict) else ""
        ),
        "location": _extract_address(item.get("jobLocation", {}) if isinstance(item.get("jobLocation"), dict) else item),
        "salary": (
            item.get("baseSalary", {}).get("value", {}).get("value", "") if isinstance(item.get("baseSalary"), dict) else ""
        ),
        "employment_type": item.get("employmentType", "") or "",
        "url": item.get("url", "") or "",
    }


def _extract_event_fields(item: dict) -> dict:
    return {
        "name": item.get("name", "") or "",
        "description": item.get("description", "") or "",
        "date": item.get("startDate", "") or "",
        "end_date": item.get("endDate", "") or "",
        "location": _extract_address(item.get("location", {}) if isinstance(item.get("location"), dict) else item),
        "price": _extract_price_from_offers(item),
        "url": item.get("url", "") or "",
        "image": item.get("image", "") or "",
    }


def _extract_business_fields(item: dict) -> dict:
    return {
        "name": item.get("name", "") or "",
        "description": item.get("description", "") or "",
        "address": _extract_address(item),
        "telephone": item.get("telephone", "") or "",
        "email": item.get("email", "") or "",
        "url": item.get("url", "") or item.get("sameAs", "") or "",
        "rating": (
            item.get("aggregateRating", {}).get("ratingValue", "") if isinstance(item.get("aggregateRating"), dict) else ""
        ),
    }


def _extract_person_fields(item: dict) -> dict:
    return {
        "name": item.get("name", "") or "",
        "email": item.get("email", "") or "",
        "telephone": item.get("telephone", "") or "",
        "url": item.get("url", "") or item.get("sameAs", "") or "",
        "description": item.get("description", "") or item.get("jobTitle", "") or "",
    }


def _extract_article_fields(item: dict) -> dict:
    return {
        "headline": item.get("headline", "") or item.get("name", "") or "",
        "description": item.get("description", "") or item.get("abstract", "") or "",
        "author": item.get("author", {}).get("name", "") if isinstance(item.get("author"), dict) else "",
        "date_published": item.get("datePublished", "") or "",
        "publisher": item.get("publisher", {}).get("name", "") if isinstance(item.get("publisher"), dict) else "",
        "image": item.get("image", "") or "",
        "url": item.get("url", "") or item.get("mainEntityOfPage", "") or "",
    }


def _extract_book_fields(item: dict) -> dict:
    return {
        "name": item.get("name", "") or "",
        "author": item.get("author", {}).get("name", "") if isinstance(item.get("author"), dict) else "",
        "isbn": item.get("isbn", "") or "",
        "description": item.get("description", "") or "",
        "rating": (
            item.get("aggregateRating", {}).get("ratingValue", "") if isinstance(item.get("aggregateRating"), dict) else ""
        ),
        "price": _extract_price_from_offers(item),
        "url": item.get("url", "") or "",
    }


def _extract_movie_fields(item: dict) -> dict:
    return {
        "name": item.get("name", "") or "",
        "description": item.get("description", "") or item.get("abstract", "") or "",
        "director": item.get("director", {}).get("name", "") if isinstance(item.get("director"), dict) else "",
        "rating": (
            item.get("aggregateRating", {}).get("ratingValue", "") if isinstance(item.get("aggregateRating"), dict) else ""
        ),
        "date_published": item.get("datePublished", "") or "",
        "image": item.get("image", "") or "",
    }


def _extract_app_fields(item: dict) -> dict:
    return {
        "name": item.get("name", "") or "",
        "description": item.get("description", "") or item.get("abstract", "") or "",
        "rating": (
            item.get("aggregateRating", {}).get("ratingValue", "") if isinstance(item.get("aggregateRating"), dict) else ""
        ),
        "price": item.get("offers", {}).get("price", "") if isinstance(item.get("offers"), dict) else "",
        "url": item.get("url", "") or item.get("sameAs", "") or "",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_address(item: dict) -> str:
    """Extract a formatted address from a JSON-LD item."""
    addr = item.get("address", {})
    if isinstance(addr, dict):
        parts = [
            addr.get("streetAddress", ""),
            addr.get("addressLocality", ""),
            addr.get("addressRegion", ""),
            addr.get("postalCode", ""),
            addr.get("addressCountry", ""),
        ]
        return ", ".join(p for p in parts if p) or addr.get("name", "") or ""
    if isinstance(addr, str):
        return addr
    return ""


def _extract_price_from_offers(item: dict) -> str:
    """Extract a price from the offers field of any JSON-LD item."""
    offers = item.get("offers", {})
    if isinstance(offers, list):
        for offer in offers:
            if isinstance(offer, dict):
                price = offer.get("price", "")
                currency = offer.get("priceCurrency", "")
                if price:
                    return f"{currency}{price}" if currency else str(price)
    if isinstance(offers, dict):
        price = offers.get("price", "")
        currency = offers.get("priceCurrency", "")
        if price:
            return f"{currency}{price}" if currency else str(price)
    return ""


# ---------------------------------------------------------------------------
# Generic nested JSON extraction
# ---------------------------------------------------------------------------


def _extract_from_nested_json(
    data: dict,
    schema_fields: list,
    max_depth: int = 6,
) -> list[dict]:
    """Recursively search a nested JSON object for arrays of structured records.

    Walks the JSON tree looking for arrays of dicts that contain values
    matching schema field names or types.
    """
    if not data or not isinstance(data, dict):
        return []

    candidates: list[list[dict]] = []

    def _walk(obj: Any, depth: int = 0) -> None:
        if depth > max_depth:
            return

        if isinstance(obj, dict):
            # Check if this dict has any key that looks like a record
            for value in obj.values():
                if isinstance(value, list) and value:
                    # Check if this list contains structured records
                    records = []
                    for item in value:
                        if isinstance(item, dict) and _is_record_like(item, schema_fields):
                            records.append(item)
                    if records:
                        candidates.append(records)
                elif isinstance(value, dict):
                    _walk(value, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item, depth + 1)

    _walk(data)

    if not candidates:
        return []

    # Convert best candidate list to schema-aligned records
    # Use the largest candidate list that has the most field matches
    candidates.sort(
        key=lambda recs: (len(recs), _count_field_matches(recs, schema_fields)),
        reverse=True,
    )

    records = []
    for item in candidates[0]:
        record = _map_json_keys_to_schema(item, schema_fields)
        if record and any(v for v in record.values() if v not in (None, "", [])):
            records.append(record)

    return records


def _is_record_like(item: dict, schema_fields: list) -> bool:
    """Check if a dict looks like a data record (contains typed values)."""
    if not item or not isinstance(item, dict):
        return False

    # Must have at least 2 meaningful fields or 1 field matching a schema field
    meaningful = 0
    for key, value in item.items():
        if isinstance(value, (str, int, float)) and value not in (None, "", []):
            meaningful += 1
        if key.lower() in {f.name.lower() for f in schema_fields}:
            return True  # Direct schema field match is strong evidence

    return meaningful >= 2


def _count_field_matches(records: list[dict], schema_fields: list) -> int:
    """Count how many schema field names appear as keys in the records."""
    keys: set[str] = set()
    for r in records:
        keys.update(r.keys())
    schema_names = {f.name.lower() for f in schema_fields}
    return len(keys & schema_names)


# ---------------------------------------------------------------------------
# Key-value alignment (generic, any JSON structure)
# ---------------------------------------------------------------------------


def _map_json_keys_to_schema(
    item: dict,
    schema_fields: list,
) -> dict:
    """Map JSON keys to schema fields using key-level alignment.

    For each schema field, looks through the JSON item for matching keys
    using exact match, alias match, and prefix / suffix match.
    """
    if not item or not isinstance(item, dict):
        return {}

    record: dict = {}

    # Build a flat key-value map from the item (handles nesting)
    flat_values = _flatten_json_keys(item)

    for field in schema_fields:
        field_name = field.name
        field_lower = field_name.lower()
        field_type = field.field_type if hasattr(field, "field_type") else None

        value = _find_value_for_field(field_name, field_lower, field_type, flat_values)
        if value is not None and value not in ("", [], {}):
            record[field_name] = value

    return record


def _flatten_json_keys(
    obj: Any,
    prefix: str = "",
    max_depth: int = 3,
    depth: int = 0,
) -> dict[str, Any]:
    """Flatten a nested JSON object into {key: value} pairs.

    Converts nested keys like {"product": {"name": "X"}} to
    {"product_name": "X", "name": "X"} for easier matching.
    """
    result: dict[str, Any] = {}

    if depth > max_depth:
        return result

    if isinstance(obj, dict):
        for key, value in obj.items():
            flat_key = f"{prefix}_{key}".lower().lstrip("_") if prefix else key.lower()
            flat_key = flat_key.replace("-", "_").replace(" ", "_")

            if isinstance(value, (str, int, float, bool)) and not isinstance(value, bool):
                result[flat_key] = value
                result[key.lower()] = value  # Also store under plain key
            elif isinstance(value, dict) and depth < max_depth:
                nested = _flatten_json_keys(value, key, max_depth, depth + 1)
                result.update(nested)
            elif isinstance(value, list) and value and depth < max_depth:
                # For lists of strings, join them
                if all(isinstance(v, str) for v in value):
                    result[flat_key] = ", ".join(value)
                    result[key.lower()] = ", ".join(value)

        # Also store the raw value under each key
        for key, value in obj.items():
            if isinstance(value, str) and value:
                result[key.lower()] = value

    return result


_ALIAS_MAP: dict[str, list[str]] = {
    "name": [
        "name",
        "title",
        "label",
        "heading",
        "item_name",
        "product_name",
        "company_name",
        "business_name",
        "full_name",
    ],
    "description": ["description", "desc", "summary", "details", "about", "abstract", "text", "body"],
    "email": ["email", "e_mail", "mail", "contact_email", "email_address"],
    "phone": ["phone", "telephone", "tel", "phone_number", "contact_phone", "mobile", "cell"],
    "url": ["url", "link", "website", "site", "web", "href", "same_as", "permalink"],
    "image": ["image", "img", "photo", "picture", "thumbnail", "logo", "icon"],
    "price": ["price", "cost", "amount", "total", "rate", "fee", "charge", "value"],
    "currency": ["currency", "price_currency", "currency_code", "symbol"],
    "rating": ["rating", "score", "stars", "review_score", "aggregate_rating", "rating_value"],
    "address": ["address", "location", "place", "venue", "full_address"],
    "city": ["city", "locality", "town", "municipality"],
    "state": ["state", "region", "province", "territory"],
    "country": ["country", "nation"],
    "zip": ["zip", "postal_code", "zip_code", "postcode"],
    "date": [
        "date",
        "start_date",
        "end_date",
        "date_published",
        "publication_date",
        "created_at",
        "updated_at",
        "available_from",
    ],
    "time": ["time", "start_time", "end_time", "duration"],
    "category": ["category", "type", "kind", "genre", "classification", "section"],
    "status": ["status", "state", "availability", "condition"],
    "company": ["company", "organization", "employer", "brand", "publisher", "hiring_organization", "manufacturer"],
    "author": ["author", "creator", "director", "artist", "producer", "seller"],
    "origin": ["origin", "from", "source"],
    "destination": ["destination", "to", "target"],
    "carrier": ["carrier", "operator", "provider", "vendor"],
    "rating_count": ["rating_count", "review_count", "votes", "count"],
}


def _find_value_for_field(
    field_name: str,  # noqa: ARG001, RUF100
    field_lower: str,
    field_type: Any,  # noqa: ARG001, RUF100
    flat_values: dict[str, Any],
) -> Any:
    """Find the best value for a schema field from flat JSON key-value pairs."""
    # Step 1: Direct key match
    if field_lower in flat_values:
        return flat_values[field_lower]

    # Step 2: Alias-based match
    aliases = _ALIAS_MAP.get(field_lower, [])
    # Also check if any alias group contains our field name
    for canonical, alias_list in _ALIAS_MAP.items():
        if field_lower in alias_list or field_lower == canonical:
            aliases = alias_list
            break

    for alias in aliases:
        if alias in flat_values:
            return flat_values[alias]

    # Step 3: Prefix / suffix match (e.g., field name "company_name" contains "name")
    # Priority: longer prefix matches first
    candidates = []
    for key, value in flat_values.items():
        if not isinstance(value, str) or not value:
            continue

        # Exact word boundary match
        key_words = set(re.split(r"[_\-\s]+", key))
        field_words = set(re.split(r"[_\-\s]+", field_lower))

        overlap = key_words & field_words
        if overlap:
            # Score by: more overlap = better match
            score = len(overlap) / max(len(field_words), 1)
            candidates.append((score, value))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        if candidates[0][0] >= 0.5:  # At least 50% word overlap
            return candidates[0][1]

    return None


# ---------------------------------------------------------------------------
# Apollo / Relay state extraction
# ---------------------------------------------------------------------------


def _extract_from_apollo_state(
    apollo_data: dict,
    schema_fields: list,
) -> list[dict]:
    """Extract records from Apollo / Relay client-side cache state.

    Apollo state typically has ROOT_QUERY entries and __typename references.
    """
    if not apollo_data or not isinstance(apollo_data, dict):
        return []

    records: list[dict] = []
    seen_refs: set[str] = set()

    # Collect all entities (nodes that are not ROOT_QUERY)
    entities: list[dict] = []
    for key, value in apollo_data.items():
        if key.startswith("ROOT_"):
            continue
        if isinstance(value, dict) and "__typename" in value:
            # Check if this is a list item (has index-like key)
            entities.append(value)

    # Also extract from ROOT_QUERY values
    for key, value in apollo_data.items():
        if key.startswith("ROOT_QUERY") and isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    # Check for __ref references
                    ref = item.get("__ref", "")
                    if ref and ref not in seen_refs:
                        seen_refs.add(ref)
                        ref_data = apollo_data.get(ref, {})
                        if isinstance(ref_data, dict) and ref_data not in entities:
                            entities.append(ref_data)
                    elif item not in entities:
                        entities.append(item)

    for entity in entities:
        record = _map_json_keys_to_schema(entity, schema_fields)
        if record and any(v for v in record.values() if v not in (None, "", [])):
            records.append(record)

    return records


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _extract_records_from_payloads(
    payloads: list[dict],
    schema_fields: list,
) -> list[dict]:
    """Try to extract structured records from captured network payloads.

    Uses the generic extraction logic to map JSON keys to schema fields.
    Each payload is treated as a potential source of records.

    Args:
        payloads: List of captured network payloads (from browser_network_capture).
        schema_fields: Schema fields to map to.

    Returns:
        List of extracted records, or empty list.

    """
    if not payloads or not schema_fields:
        return []

    records: list[dict] = []

    for payload in payloads:
        body = payload.get("body")
        if not isinstance(body, (dict, list)):
            continue

        # Try deep search for record arrays (nested JSON traversal)
        if isinstance(body, dict):
            extracted = _extract_from_nested_json(body, schema_fields)
            if extracted:
                records.extend(extracted)
                continue

            # Try direct key mapping
            record = _map_json_keys_to_schema(body, schema_fields)
            if record and any(v for v in record.values() if v not in (None, "", [])):
                records.append(record)

        elif isinstance(body, list):
            for item in body:
                if isinstance(item, dict) and _is_record_like(item, schema_fields):
                    record = _map_json_keys_to_schema(item, schema_fields)
                    if record and any(v for v in record.values() if v not in (None, "", [])):
                        records.append(record)

    # Deduplicate
    return _deduplicate_records(records)


def _deduplicate_records(records: list[dict]) -> list[dict]:
    """Remove duplicate records based on field value similarity."""
    seen = set()
    unique = []

    for r in records:
        # Create a signature from non-empty string values
        sig_parts = []
        for k, v in sorted(r.items()):
            if isinstance(v, str) and v and len(v) > 2:
                sig_parts.append(f"{k}:{v.lower().strip()[:50]}")
        if not sig_parts:
            continue
        sig = "|".join(sig_parts)
        if sig not in seen:
            seen.add(sig)
            unique.append(r)

    return unique
