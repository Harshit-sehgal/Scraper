"""
Record Classifier Engine
=========================
Classifies records by type: entity, filter, navigation, metadata, etc.

Core principle: The engine must distinguish REAL DATA from UI/control structures.
Without domain-specific rules.

Key insight: entity records have HIGH semantic density (prices, dates, codes, names).
Filter/control records have LOW semantic density (ranges, labels, buttons).
"""

from typing import List, Set, Tuple

from app.semantic_ir import (
    DatasetIR,
    RecordType,
    SemanticRecord,
    SemanticToken,
    SemanticType,
)

# Universal indicators of non-entity records
# These are structural patterns, NOT domain-specific keywords
CONTROL_INDICATORS: Set[str] = {
    "sort by", "filter", "show all", "view all", "page",
    "previous", "next", "first", "last", "load more",
    "search", "refine", "clear all",
}

RANGE_PATTERNS = [
    r"\d{3,}\s*[-–]\s*\d{3,}",  # "500-1000", "100-200" (min 3 digits to avoid dates)
    r"[£$€¥₹]\s*\d+[\d,]*\s*[-–]\s*[£$€¥₹]?\s*\d+[\d,]*",  # "£0-£500", "$100-500"
    r"(under|above|over|up to|from)\s",  # "under $500"
]


def classify_record_type(record: SemanticRecord) -> Tuple[RecordType, float]:
    """Classify what type of record this is.

    Uses semantic density analysis and structural patterns,
    NOT domain keywords or heuristics.

    Returns (record_type, confidence).
    """
    tokens = record.tokens
    if not tokens:
        return RecordType.UNKNOWN, 0.0

    combined = " ".join(t.raw for t in tokens)
    combined_lower = combined.lower()

    # 1. Check for navigation first (highest priority)
    if _is_navigation_record(combined_lower):
        return RecordType.NAVIGATION, 0.8

    # 2. Check for filter/price range patterns
    if _is_filter_record(tokens, combined, combined_lower):
        return RecordType.FILTER, 0.8

    # 3. Check for metadata
    if _is_metadata_record(combined_lower):
        return RecordType.METADATA, 0.7

    # 4. Check for UI components
    if _is_ui_component(tokens, combined_lower):
        return RecordType.UI_COMPONENT, 0.7

    # 5. Compute semantic density for entity classification
    density = _compute_record_semantic_density(record)

    if density >= 0.4:
        return RecordType.ENTITY, density
    elif density >= 0.2:
        return RecordType.ENTITY, 0.5  # Low confidence entity
    else:
        return RecordType.UNKNOWN, 0.3


def _is_filter_record(tokens: List[SemanticToken], combined: str, lower: str) -> bool:
    """Detect filter/range records (Price: £0-£500, ratings 4+, etc.).

    Filter records typically contain:
    - Price ranges with - separator
    - Comparison operators (under, above, up to)
    - Single price with range modifiers
    """
    # Check range patterns
    import re
    for pattern in RANGE_PATTERNS:
        if re.search(pattern, combined):
            return True

    # Check control indicators
    if any(ind in lower for ind in CONTROL_INDICATORS):
        return True

    return False


def _is_navigation_record(lower: str) -> bool:
    """Detect navigation records (page 1, next, previous, etc.)."""
    nav_patterns = [
        "page", "previous", "next", "first", "last",
        "showing", "results", "items per page",
    ]
    count = sum(1 for p in nav_patterns if p in lower)
    return count >= 2


def _is_metadata_record(lower: str) -> bool:
    """Detect metadata records (copyright, powered by, etc.)."""
    meta_patterns = [
        "copyright", "all rights reserved", "powered by",
        "terms", "privacy", "cookie",
    ]
    return any(p in lower for p in meta_patterns)


def _is_ui_component(tokens: List[SemanticToken], lower: str) -> bool:
    """Detect UI component records (buttons, forms, controls)."""
    ui_patterns = [
        "sign up", "login", "register", "subscribe",
        "book now", "call now", "get quote",
    ]
    if any(p in lower for p in ui_patterns):
        return True

    # UI components typically have no structured data types
    meaningful_types = {SemanticType.PRICE, SemanticType.DATE, SemanticType.CODE,
                        SemanticType.RATING, SemanticType.DURATION, SemanticType.LOCATION}
    token_types = set(t.primary_type for t in tokens)
    if not token_types & meaningful_types:
        # If only text/number tokens, likely UI
        if all(t.primary_type in (SemanticType.TEXT, SemanticType.NUMBER) for t in tokens):
            return True

    return False


def _compute_record_semantic_density(record: SemanticRecord) -> float:
    """Compute semantic density of a record.

    High density = many meaningful types (price, date, code, rating)
    Low density = mostly text, numbers, or noise

    Used to distinguish entity records from control/UI records.
    """
    tokens = record.tokens
    if not tokens:
        return 0.0

    meaningful_types = {
        SemanticType.PRICE, SemanticType.DATE, SemanticType.CODE,
        SemanticType.RATING, SemanticType.DURATION, SemanticType.LOCATION,
        SemanticType.IDENTIFIER, SemanticType.ORGANIZATION, SemanticType.NAME,
    }

    meaningful = [t for t in tokens if t.primary_type in meaningful_types]
    if not meaningful:
        return 0.0

    # Ratio of meaningful tokens
    ratio = len(meaningful) / len(tokens)

    # Type diversity bonus
    types = set(t.primary_type for t in meaningful)
    diversity = len(types) / 4.0

    density = (ratio * 0.6) + (min(diversity, 1.0) * 0.4)
    return min(density, 1.0)


def classify_dataset_records(dataset: DatasetIR) -> DatasetIR:
    """Classify all records in a dataset."""
    for record in dataset.records:
        rtype, conf = classify_record_type(record)
        record.record_type = rtype
        record.record_type_confidence = conf
    return dataset
