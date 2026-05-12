"""
Layer 1: Intent Parser
======================
Universal intent parsing that understands what the user wants,
regardless of domain (flight, hotel, product, job, etc.)

Core principle: Match by semantic need (price, date, rating), not by domain.
"""

from dataclasses import dataclass, field
from app.models import FieldType


@dataclass
class IntentSchema:
    """Represents what the user wants, not what domain they're in."""
    raw_query: str
    entity_hint: str = ""  # weak metadata only, NOT core logic
    semantic_needs: dict = field(default_factory=dict)  # {need: [synonyms]}
    required_needs: list = field(default_factory=list)  # explicitly requested
    optional_needs: list = field(default_factory=list)  # inferred from context


# Universal semantic need mappings (not domain-specific)
SEMANTIC_NEED_KEYWORDS = {
    "name": ["name", "title", "title", "entity", "business", "company", "item", "product", "hotel", "flight", "job", "property"],
    "price": ["price", "fare", "cost", "amount", "rate", "fee", "rent", "sale", "budget", "cheap", "expensive", "under", "above"],
    "date": ["date", "departure", "arrival", "when", "check-in", "check-out", "schedule", "timing", "time"],
    "duration": ["duration", "hours", "time", "takes", "travel time", "flight time"],
    "rating": ["rating", "stars", "review", "score", "feedback", "rank", "out of"],
    "location": ["location", "address", "place", "area", "city", "near", "around", "from", "to", "destination", "origin"],
    "phone": ["phone", "contact", "call", "mobile", "tel"],
    "email": ["email", "mail", "contact"],
    "description": ["description", "about", "details", "info", "specs", "features", "amenities"],
    "link": ["link", "url", "website", "book", "visit", "apply"],
    "availability": ["available", "stock", "in stock", "slots", "open", "vacancy"],
    "size": ["size", "sqft", "sq ft", "bedroom", "bathroom", "area", "capacity"],
    "seller": ["seller", "vendor", "provider", "company", "brand", "airline", "hotel chain"],
    "status": ["status", "stops", "direct", "stop", "class", "type", "category"],
}

# Map semantic needs to field types
SEMANTIC_NEED_TO_FIELD_TYPE = {
    "name": FieldType.STRING,
    "price": FieldType.CURRENCY,
    "date": FieldType.DATE,
    "duration": FieldType.STRING,
    "rating": FieldType.FLOAT,
    "location": FieldType.LOCATION,
    "phone": FieldType.PHONE,
    "email": FieldType.EMAIL,
    "description": FieldType.STRING,
    "link": FieldType.URL,
    "availability": FieldType.STRING,
    "size": FieldType.STRING,
    "seller": FieldType.STRING,
    "status": FieldType.STRING,
}


def parse_user_intent(query: str) -> IntentSchema:
    """
    Parse user query to understand what they want, regardless of domain.

    Input: "Find cheap flights from Delhi to Mumbai with prices and duration"
    Output: IntentSchema with semantic_needs, not domain-specific fields

    Key principle: entity_hint (flight, hotel) is ONLY metadata,
    the real logic is in semantic_needs (price, date, location).
    """
    query_lower = query.lower()

    # Extract entity hint (weak metadata only)
    entity_hint = _detect_entity_hint(query_lower)

    # Extract semantic needs from query
    semantic_needs = _extract_semantic_needs(query_lower)

    # Determine required vs optional needs
    required_needs = _determine_required_needs(semantic_needs, query_lower)
    optional_needs = _determine_optional_needs(semantic_needs, required_needs)

    return IntentSchema(
        raw_query=query,
        entity_hint=entity_hint,
        semantic_needs=semantic_needs,
        required_needs=required_needs,
        optional_needs=optional_needs
    )


def _detect_entity_hint(query_lower: str) -> str:
    """Detect weak entity hint for metadata only, NOT core logic."""
    entity_patterns = {
        "flight": ["flight", "flights", "airline", "airport", "airfare"],
        "hotel": ["hotel", "hotels", "resort", "stay", "accommodation", "inn", "lodge"],
        "product": ["product", "products", "item", "items", "buy", "purchase", "shopping"],
        "job": ["job", "jobs", "vacancy", "vacancies", "career", "hiring", "employment"],
        "restaurant": ["restaurant", "restaurants", "food", "dining", "eat"],
        "real_estate": ["property", "properties", "house", "apartment", "flat", "villa", "real estate"],
        "car": ["car", "cars", "vehicle", "vehicles", "auto", "automobile"],
        "event": ["event", "events", "ticket", "tickets", "show", "concert"],
    }

    for entity, patterns in entity_patterns.items():
        if any(p in query_lower for p in patterns):
            return entity

    return "general"


def _extract_semantic_needs(query_lower: str) -> dict:
    """Extract what information the user wants, not what domain.

    Always includes a core set of universal semantic needs (price, date,
    location, name) because these are almost always relevant regardless
    of what the user explicitly says. Additional needs are inferred
    from query keywords.
    """
    needs = {}

    # Always include universal needs (always relevant for ANY extraction)
    universal_needs = ["price", "date", "location", "name"]
    for need in universal_needs:
        needs[need] = SEMANTIC_NEED_KEYWORDS.get(need, [need])[:3]

    # Add any additional needs inferred from query keywords
    for need, keywords in SEMANTIC_NEED_KEYWORDS.items():
        if need in needs:
            continue  # already included as universal
        matched_keywords = [kw for kw in keywords if kw in query_lower]
        if matched_keywords:
            needs[need] = matched_keywords

    return needs


def _determine_required_needs(semantic_needs: dict, query_lower: str) -> list:
    """Determine which needs are explicitly required by user."""
    required = []

    # Explicit requirement markers
    explicit_markers = ["with", "including", "showing", "including", "need", "want", "must have"]

    for need in semantic_needs:
        # Check if explicitly mentioned with requirement marker
        for keyword in semantic_needs.get(need, []):
            for marker in explicit_markers:
                if f"{marker} {keyword}" in query_lower or f"{keyword} {marker}" in query_lower:
                    if need not in required:
                        required.append(need)
                    break

    # If nothing explicitly marked, assume first 2-3 needs are required
    if not required and len(semantic_needs) > 0:
        required = list(semantic_needs.keys())[:3]

    return required


def _determine_optional_needs(semantic_needs: dict, required_needs: list) -> list:
    """Determine which needs are optional (inferred but not explicitly requested)."""
    optional = []

    for need in semantic_needs:
        if need not in required_needs:
            optional.append(need)

    return optional


def infer_schema_from_intent(intent: IntentSchema, max_fields: int = 10) -> list:
    """
    Generate schema fields based on what user wants, NOT based on domain.

    Input: IntentSchema from parse_user_intent()
    Output: List of SchemaField objects

    Example:
    - User asks for "flights with prices and dates"
    - Output: [name, price, date, duration, location] (generic fields)
    - NOT: [airline, flight_number, departure_time, ...] (domain-specific)
    """
    from app.models import SchemaField

    schema_fields = []
    field_count = 0

    # Priority order for field generation
    priority_needs = ["name", "price", "date", "duration", "rating", "location", "phone", "email", "description", "link"]

    for need in priority_needs:
        if need not in intent.semantic_needs:
            continue

        if field_count >= max_fields:
            break

        field_type = SEMANTIC_NEED_TO_FIELD_TYPE.get(need, FieldType.STRING)
        is_required = need in intent.required_needs

        field = SchemaField(
            name=need,
            field_type=field_type,
            description=_get_field_description(need),
            required=is_required
        )

        schema_fields.append(field)
        field_count += 1

    # Add optional needs if we haven't reached max
    for need in intent.optional_needs:
        if field_count >= max_fields:
            break
        if need not in [f.name for f in schema_fields]:
            field_type = SEMANTIC_NEED_TO_FIELD_TYPE.get(need, FieldType.STRING)
            field = SchemaField(
                name=need,
                field_type=field_type,
                description=_get_field_description(need),
                required=False
            )
            schema_fields.append(field)
            field_count += 1

    return schema_fields


def _get_field_description(need: str) -> str:
    """Get generic field description based on semantic need."""
    descriptions = {
        "name": "Primary entity name or title",
        "price": "Price, cost, fare, or amount",
        "date": "Date, date range, or schedule",
        "duration": "Duration, time taken, or travel time",
        "rating": "Rating, score, or review count",
        "location": "Location, address, or place",
        "phone": "Contact phone number",
        "email": "Contact email address",
        "description": "Description, details, or additional info",
        "link": "URL link to detail page",
        "availability": "Availability status or stock",
        "size": "Size, area, or capacity",
        "seller": "Seller, vendor, or provider name",
        "status": "Status, type, or category",
    }
    return descriptions.get(need, f"{need} information")


def parse_intent_with_llm(query: str) -> IntentSchema:
    """
    Use LLM for more sophisticated intent parsing when rules are insufficient.
    Falls back to rule-based parsing if LLM fails.
    """
    from app.scraper import _llm_json

    prompt = f"""Parse this user query into a structured intent.

Query: {query}

Return ONLY JSON with this shape:
{{
  "entity_hint": "weak entity type or empty string",
  "semantic_needs": {{"need_name": ["keyword1", "keyword2"]}},
  "required_needs": ["need1", "need2"],
  "optional_needs": ["need3", "need4"]
}}

Rules:
- entity_hint is ONLY metadata, NOT the core logic
- semantic_needs contains what information user wants (price, date, rating, etc.)
- Do NOT use domain-specific field names (airline, hotel_name, etc.)
- Use generic semantic needs (name, price, date, location, rating, etc.)
- required_needs = what user explicitly asked for
- optional_needs = inferred from context but not explicitly stated
"""

    try:
        messages = [
            {"role": "system", "content": "You parse user intents for web scraping."},
            {"role": "user", "content": prompt}
        ]
        result = _llm_json(messages, temperature=0.2)

        if isinstance(result, dict):
            return IntentSchema(
                raw_query=query,
                entity_hint=result.get("entity_hint", ""),
                semantic_needs=result.get("semantic_needs", {}),
                required_needs=result.get("required_needs", []),
                optional_needs=result.get("optional_needs", [])
            )
    except Exception:
        pass

    # Fallback to rule-based parsing
    return parse_user_intent(query)


# Universal fallback schema for any query
def get_universal_schema() -> list:
    """Return universal schema that works for most cases."""
    from app.models import SchemaField

    return [
        SchemaField(name="name", field_type=FieldType.STRING, description="Entity name or title", required=True),
        SchemaField(name="price", field_type=FieldType.CURRENCY, description="Price or cost", required=False),
        SchemaField(name="date", field_type=FieldType.DATE, description="Date or schedule", required=False),
        SchemaField(name="location", field_type=FieldType.LOCATION, description="Location or address", required=False),
        SchemaField(name="rating", field_type=FieldType.FLOAT, description="Rating or score", required=False),
        SchemaField(name="phone", field_type=FieldType.PHONE, description="Contact phone", required=False),
        SchemaField(name="email", field_type=FieldType.EMAIL, description="Contact email", required=False),
        SchemaField(name="description", field_type=FieldType.STRING, description="Description or details", required=False),
        SchemaField(name="link", field_type=FieldType.URL, description="Detail page URL", required=False),
    ]