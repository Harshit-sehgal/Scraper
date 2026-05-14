
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


# Universal fallback schema for any query
