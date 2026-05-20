
"""
Layer 3: Semantic Mapper
=========================
Universal semantic mapping that matches values to user intent by WHAT THEY ARE,
not by WHERE THEY CAME FROM or what DOMAIN the page is from.

Core principle: "£238" matches "price" because it's a currency,
regardless of whether it was found on a flight site or a product page.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from app.intent_parser import SEMANTIC_NEED_KEYWORDS, IntentSchema
from app.page_profiler import StructureProfile, ValuePatterns
from app.semantic_ir import SemanticType

@dataclass
class FieldMapping:
    """Mapping of a single extracted value to a semantic need."""
    field_name: str
    semantic_need: str
    original_value: str
    mapped_value: str
    confidence: float
    matched_by: str  # "pattern", "header", "llm", "position"
    evidence: str = ""
    signals: List[str] = field(default_factory=list)


@dataclass
class RecordMapping:
    """Full mapping of an extracted record to user intent."""
    original_data: Dict[str, str]
    mapped_fields: Dict[str, str]
    confidence_scores: Dict[str, float]
    unmatched_values: List[str] = field(default_factory=list)


# Consolidated Semantic Patterns (raw patterns)
_SEMANTIC_PATTERNS_RAW = {
    SemanticType.PRICE: [
        r"[\$\u20a8\u20ac\u00a3\u00a5\u20b9]\s*\d+[\d,]*\.?\d*",
        r"\d+[\d,]*\.?\d*\s*(usd|eur|gbp|inr|rs|yen|pound)",
    ],
    SemanticType.DATE: [
        r"\d{1,2}[/-]\d{1,2}[/-](\d{2}|\d{4})",
        r"\d{4}[-]\d{2}[-]\d{2}",
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}(st|nd|rd|th)?(,\s*\d{4})?",
    ],
    SemanticType.EMAIL: [
        r"[\w.+-]+@[\w-]+\.[\w.-]+",
    ],
    SemanticType.PHONE: [
        r"\+?\d[\d\s\-\(\)]{7,}",
    ],
    SemanticType.RATING: [
        r"\d+\.?\d*\s*/\s*5",
        r"rated\s*\d+\.?\d*",
        r"\d+\.?\d*\s*stars?",
    ],
    SemanticType.URL: [
        r"https?://[^\s]+",
        r"www\.[^\s]+",
    ],
    SemanticType.IDENTIFIER: [
        r"\b[A-Z\-_]+\d+[A-Z\d\-_]*\b",
        r"\b\d+[A-Z\-_]+[A-Z\d\-_]*\b",
    ],
    SemanticType.DURATION: [
        r"\d+h\s*\d*m|\d+h$",
    ],
    SemanticType.CODE: [
        r"^[A-Z]{2,5}$",
    ],
}

# Pre-compile all regex patterns at module load (O(1) per call instead of O(n) recompilation)
SEMANTIC_PATTERNS: Dict[SemanticType, List[Tuple[re.Pattern, int]]] = {}
for stype, patterns in _SEMANTIC_PATTERNS_RAW.items():
    flags = 0 if stype == SemanticType.CODE else re.IGNORECASE
    SEMANTIC_PATTERNS[stype] = [(re.compile(p, flags), flags) for p in patterns]

# Pre-compile common regex patterns used in detect_semantic_type
_DIGIT_PATTERN = re.compile(r"\d+")
_NUMERIC_PATTERN = re.compile(r"^\d+\.?\d*$")
_QUANTIFIER_PATTERN = re.compile(r"\d+\s*(stop|direct|non.?stop)", re.IGNORECASE)


@lru_cache(maxsize=4096)
def detect_semantic_type(value: str, field_name: str = "") -> Tuple[SemanticType, float]:
    """Detect semantic type of a value using regex patterns and field name hints.
    
    Results are cached with LRU (max 4096 entries) to avoid re-processing
    common values. This significantly improves performance for repetitive data.
    """
    if not value:
        return SemanticType.TEXT, 0.0

    # 1. Field-name hinting (higher priority for disambiguation)
    name_lower = (field_name or "").lower()
    
    # 2. Pattern-based matching (universal physics) - using pre-compiled patterns
    for stype, compiled_patterns in SEMANTIC_PATTERNS.items():
        for pattern, _ in compiled_patterns:
            if pattern.search(str(value)):
                # Boost confidence if field name also matches
                confidence = 0.95
                return stype, confidence

    # 3. Numeric context
    if _DIGIT_PATTERN.search(str(value)):
        if any(k in name_lower for k in ["price", "cost", "fare", "amount", "salary"]):
            return SemanticType.PRICE, 0.80
        if any(k in name_lower for k in ["date", "time", "start", "end", "schedule"]):
            return SemanticType.DATE, 0.80
        
        # Numeric with quantifier
        if _QUANTIFIER_PATTERN.search(str(value)):
            return SemanticType.NUMBER, 0.70
        
        # Generic number
        if _NUMERIC_PATTERN.match(str(value).strip()):
            return SemanticType.NUMBER, 0.60

    # 4. Organization/Entity context
    v_str = str(value).strip()
    v_lower = v_str.lower()
    _UI_NOISE = {
        'view', 'more', 'skip', 'contact', 'home', 'menu', 'search', 
        'filter', 'sort', 'send', 'get', 'touch', 'back', 'next',
        'previous', 'click', 'here', 'read', 'learn', 'all', 'rights',
        'reserved', 'copyright', 'powered', 'by', 'content', 'submit',
        'cancel', 'save', 'delete', 'edit', 'update', 'share'
    }
    
    if v_lower in _UI_NOISE:
        return SemanticType.TEXT, 0.30

    if v_str and v_str[0].isupper():
        # Heuristic: multi-word title case or single word with enough length
        words = v_str.split()
        if len(words) > 1:
            # Check if it's "Title Case" (all words start with upper)
            if all(w[0].isupper() for w in words if len(w) > 2):
                return SemanticType.ORGANIZATION, 0.65
            else:
                return SemanticType.TEXT, 0.50
        else:
            if len(v_str) > 3:
                return SemanticType.ORGANIZATION, 0.55
            else:
                return SemanticType.TEXT, 0.50
        
    # Product-like (brand naming: starts lowercase, has internal uppercase, e.g. iPhone)
    if v_str and len(v_str) >= 3 and v_str[0].islower() and any(c.isupper() for c in v_str[1:]):
        return SemanticType.ORGANIZATION, 0.60

    return SemanticType.TEXT, 0.50


def is_child_fragment(value: str, seen_values: set) -> bool:
    """Check if a value is a child fragment of an already-seen larger value.
    
    Prevents over-segmentation by suppressing tokens that are physically contained 
    within larger, already processed tokens, especially for composite entities 
    like currencies and dates.
    """
    if not value or not seen_values:
        return False

    value_lower = value.lower().strip()
    value_is_digit = value_lower.isdigit()

    for seen in seen_values:
        if not seen:
            continue
        seen_str = str(seen)
        seen_lower = seen_str.lower().strip()
        
        # Must be a strict substring
        if len(seen_lower) <= len(value_lower) or value_lower not in seen_lower:
            continue
            
        # Strategy 1: Sub-numeric suppression (e.g., "238" inside "£238")
        if value_is_digit:
            # Suppress if it's a boundary fragment (prefix/suffix)
            is_boundary = seen_lower.startswith(value_lower) or seen_lower.endswith(value_lower)
            
            # OR if it's bounded by common separators (middle fragment, e.g. "-05-" in date)
            if not is_boundary:
                # Check for separators around the value in the parent string
                idx = seen_lower.find(value_lower)
                if idx > 0 and idx + len(value_lower) < len(seen_lower):
                    before = seen_lower[idx-1]
                    after = seen_lower[idx + len(value_lower)]
                    if before in " /-." and after in " /-.":
                        is_boundary = True

            if is_boundary:
                # If the parent is a currency, date, or rated value, suppress pure digits
                if any(sym in seen_str for sym in "$\u20a8\u20ac\u00a3\u00a5\u20b9/-"):
                    return True
                # If parent has numbers followed by text (e.g., "45000 miles")
                if re.search(r"\d+\s*[a-zA-Z]+", seen_str):
                    return True
        
        # Strategy 2: Prefix/Suffix suppression for fragments
        if seen_lower.startswith(value_lower) or seen_lower.endswith(value_lower):
            # Only suppress if it's very short and part of a multi-word or compound value
            if len(value_lower) < 5:
                # If the separator is space or punctuation, it's a fragment
                if value_is_digit or any(c in " /-,." for c in seen_lower.replace(value_lower, "", 1)):
                    if not (value_lower.isalpha() and len(value_lower) == 1):
                        return True

    return False


def match_values_to_intent(
    extracted_records: List[Dict[str, str]],
    intent: IntentSchema,
    page_profile: StructureProfile,
    value_patterns: ValuePatterns,
    headers: Optional[List[str]] = None
) -> List[RecordMapping]:
    """
    Match extracted values to user intent by WHAT THEY ARE, not where they came from.

    Input: extracted_records = [{"col1": "£238", "col2": "22-05-2026", "col3": "Lufthansa"}]
           intent = IntentSchema with semantic_needs = {"price": [...], "date": [...]}
    Output: RecordMapping with mapped fields and confidence scores
    """
    headers = headers or page_profile.headers or []

    mapped_records = []

    for record in extracted_records:
        mapping = _map_single_record(
            record,
            intent,
            headers,
            value_patterns
        )
        mapped_records.append(mapping)

    return mapped_records


def _map_single_record(
    record: Dict[str, str],
    intent: IntentSchema,
    headers: List[str],
    value_patterns: ValuePatterns
) -> RecordMapping:
    """Map a single record's values to user intent."""
    mapped_fields = {}
    confidence_scores = {}
    unmatched_values = []
    field_mappings = []

    # Get all unique values from the record (skip metadata keys)
    metadata_keys = {"record_score", "_field_confidences", "source_url", "source_type", "source_trust_score"}
    seen = set()
    all_values = []
    for k, v in record.items():
        if k in metadata_keys:
            continue
        v_str = str(v) if v is not None else ""
        if v_str and v_str not in seen:
            seen.add(v_str)
            all_values.append(v_str)

    # For each semantic need the user has, try to find a matching value
    used_values: set[str] = set()
    for semantic_need in intent.semantic_needs.keys():
        best_mapping = _find_best_value_for_need(
            all_values,
            semantic_need,
            headers,
            value_patterns,
            used_values
        )

        if best_mapping:
            mapped_fields[best_mapping.field_name] = best_mapping.mapped_value
            confidence_scores[best_mapping.field_name] = best_mapping.confidence
            field_mappings.append(best_mapping)
            # After mapping a value to one need, mark it as used
            # so it won't satisfy ALL needs (prevents blob duplication)
            used_values.add(best_mapping.original_value)
        else:
            # Could not find a value for this need
            unmatched_values.append(semantic_need)

    # Also track any values we couldn't map to a need
    mapped_values = set(m.mapped_value for m in field_mappings)
    for value in all_values:
        if value and value not in mapped_values:
            if not _is_noise_value(value):
                unmatched_values.append(value)

    return RecordMapping(
        original_data=record,
        mapped_fields=mapped_fields,
        confidence_scores=confidence_scores,
        unmatched_values=unmatched_values[:10]  # Limit
    )


def _find_best_value_for_need(
    values: List[str],
    semantic_need: str,
    headers: List[str],
    value_patterns: ValuePatterns,
    used_values: Optional[set] = None
) -> Optional[FieldMapping]:
    """
    Find the best value that matches a semantic need.

    Strategy:
    1. Pattern match: does value match expected pattern for this need?
    2. Header match: does associated header suggest this need?
    3. Position match: is value in expected position?
    4. Fallback: return first non-empty value
    """
    if not values:
        return None

    used_values = used_values or set()

    candidates = []

    # Strategy 1: Pattern matching
    try:
        patterns = SEMANTIC_PATTERNS.get(SemanticType(semantic_need), [])
    except ValueError:
        patterns = []
    if patterns:
        for value in values:
            if not value or _is_noise_value(value):
                continue
            # Skip values already used for another need
            if value in used_values:
                continue

            for compiled in patterns:
                pattern = compiled[0]
                if pattern.search(str(value)):
                    # pattern is a compiled regex object, convert to string for display
                    pattern_str = pattern.pattern
                    snippet = pattern_str[:30] if len(pattern_str) > 30 else pattern_str
                    candidates.append(FieldMapping(
                        field_name=semantic_need,
                        semantic_need=semantic_need,
                        original_value=value,
                        mapped_value=value.strip(),
                        confidence=0.95,
                        matched_by="pattern",
                        evidence=f"Matched pattern {snippet}...",
                        signals=[f"pattern_match:{snippet[:40]}", "high_confidence"]
                    ))
                    break

    if candidates:
        # Return highest confidence
        return max(candidates, key=lambda x: x.confidence)

    # Strategy 2: Header-based matching
    if headers:
        need_keywords = SEMANTIC_NEED_KEYWORDS.get(semantic_need, [])
        for i, header in enumerate(headers):
            header_lower = header.lower()
            for keyword in need_keywords:
                if keyword in header_lower:
                    # Try to get corresponding value from record
                    if i < len(values) and values[i]:
                        return FieldMapping(
                            field_name=semantic_need,
                            semantic_need=semantic_need,
                            original_value=values[i],
                            mapped_value=values[i].strip(),
                            confidence=0.8,
                            matched_by="header",
                            evidence=f"Header '{header}' matches '{keyword}'",
                            signals=[f"header_match:{header}", "keyword_matched"]
                        )

    # Strategy 3: Value pattern detection from page
    value_type = _detect_value_type(values, value_patterns)
    if value_type == semantic_need:
        for value in values:
            if value and not _is_noise_value(value):
                return FieldMapping(
                    field_name=semantic_need,
                    semantic_need=semantic_need,
                    original_value=value,
                    mapped_value=value.strip(),
                    confidence=0.7,
                    matched_by="page_pattern",
                    evidence=f"Page has {semantic_need} values",
                    signals=[f"page_detected:{semantic_need}", "positional_inference"]
                )

    # Strategy 4: Fallback - return first non-empty value
    for value in values:
        if value and not _is_noise_value(value) and len(value.strip()) > 1:
            return FieldMapping(
                field_name=semantic_need,
                semantic_need=semantic_need,
                original_value=value,
                mapped_value=value.strip(),
                confidence=0.3,
                matched_by="fallback",
                evidence="No better match found",
                signals=["low_confidence_fallback", "no_signal_matched"]
            )

    return None


def _detect_value_type(values: List[str], value_patterns: ValuePatterns) -> Optional[str]:
    """Detect what type most values in the list are."""
    if not values:
        return None

    # Check against detected page patterns
    sample = values[0]

    # Currency check
    if value_patterns.currencies:
        for compiled in SEMANTIC_PATTERNS.get(SemanticType.PRICE, []):
            if compiled[0].search(sample):
                return "price"

    # Date check
    if value_patterns.dates:
        for compiled in SEMANTIC_PATTERNS.get(SemanticType.DATE, []):
            if compiled[0].search(sample):
                return "date"

    # Rating check
    if value_patterns.ratings:
        for compiled in SEMANTIC_PATTERNS.get(SemanticType.RATING, []):
            if compiled[0].search(sample):
                return "rating"

    return None


def _is_noise_value(value: str) -> bool:
    """Check if a value is likely noise (navigation, UI elements, etc.)."""
    if value is None:
        return True

    value_str = str(value).strip()
    if not value_str:
        return True

    value_lower = value_str.lower()

    # Common noise patterns (domain-agnostic)
    noise_patterns = [
        "about us", "contact us", "privacy policy", "terms", "conditions",
        "home", "menu", "search", "filter", "sort", "show all", "view all",
        "login", "sign up", "register", "signup", "signin",
        "facebook", "twitter", "instagram", "linkedin", "youtube",
        "copyright", "all rights", "powered by",
        "click here", "read more", "learn more", "view more",
        "call now", "book now", "buy now", "add to cart",
        "next", "previous", "back", "continue",
    ]

    # Single word noise
    if len(value_lower.split()) == 1 and value_lower in noise_patterns:
        return True

    # Full match with noise phrase
    if value_lower in noise_patterns:
        return True

    # Too short to be meaningful data
    if len(value_lower) < 2:
        return True

    # Too long (likely not a data value)
    if len(value_lower) > 300:
        return True

    return False
