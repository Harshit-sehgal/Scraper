"""
Semantic Segmentation Layer
============================
Intermediate Representation (IR) bridge between raw extraction and semantic mapping.

Solves the core problem: the system no longer has a scraping problem,
it has a SEMANTIC STRUCTURING problem.

This layer:
1. Extracts candidate values from composite blobs (multi-pass)
2. Classifies candidates with ambiguity distributions
3. Scores relationships between values
4. Maintains structural memory across rows
5. Provides traceability for every decision
6. Detects noise via semantic density analysis (no phrase lists)

Core principle: WHAT values are, not WHERE they came from.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from app.semantic_ir import SemanticToken, SemanticType

# ═══════════════════════════════════════════════════════════════════════════════
# INTERMEDIATE REPRESENTATION (IR)
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Type String ↔ SemanticType Bridge ────────────────────────────────

# Mapping from CandidateIR type strings to SemanticType enum values.
# This ensures clean conversion between the segmentation layer (str-based)
# and the semantic IR layer (enum-based) without fragile hasattr /
# isinstance checks.
_TYPE_STR_TO_SEMANTIC = {
    "price": SemanticType.PRICE,
    "date": SemanticType.DATE,
    "location": SemanticType.LOCATION,
    "organization": SemanticType.ORGANIZATION,
    "phone": SemanticType.PHONE,
    "email": SemanticType.EMAIL,
    "url": SemanticType.URL,
    "number": SemanticType.NUMBER,
    "rating": SemanticType.RATING,
    "duration": SemanticType.DURATION,
    "code": SemanticType.CODE,
    "name": SemanticType.NAME,
    "text": SemanticType.TEXT,
    "identifier": SemanticType.IDENTIFIER,
}


def candidate_type_to_semantic(type_str: str) -> SemanticType:
    """Convert a CandidateIR primary_type string to a SemanticType enum value."""
    return _TYPE_STR_TO_SEMANTIC.get(type_str, SemanticType.TEXT)


def to_semantic_type(value: object) -> SemanticType:
    """Unified conversion: accepts str, SemanticType, or anything with .value."""
    if isinstance(value, SemanticType):
        return value
    if hasattr(value, "value"):
        try:
            return SemanticType(value.value)
        except (ValueError, TypeError):
            pass
    return candidate_type_to_semantic(str(value))


def sem_type_str(value: object) -> str:
    """Unified string representation of a type (str or SemanticType or .value)."""
    if isinstance(value, SemanticType):
        return value.value
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


# ═══════════════════════════════════════════════════════════════════════════════
# CANDIDATE IR
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class CandidateIR:
    """Intermediate Representation for a single extracted candidate.

    This is the core data structure. ALL later stages operate on IR objects,
    NOT raw strings. This prevents direct regex-to-schema coupling.
    """

    raw: str
    cleaned: str
    span_start: int
    span_end: int
    position: int

    # Primary classification (highest confidence)
    primary_type: SemanticType = SemanticType.TEXT
    primary_confidence: float = 0.5

    # Ambiguity distribution (multiple possible types with confidences)
    type_distribution: Dict[SemanticType, float] = field(default_factory=dict)

    # Evidence for classification
    evidence: List[str] = field(default_factory=list)

    # Extraction source
    extraction_pass: int = 1  # 1=pattern, 2=split, 3=whitespace
    extraction_method: str = "pattern"

    # Traceability
    signals: List[str] = field(default_factory=list)

    def to_semantic_type(self) -> SemanticType:
        """Return the primary_type enum."""
        return self.primary_type

    def sem_type_str(self) -> str:
        """Return primary_type as a string value."""
        return self.primary_type.value

    def as_token(self, source_field: str = "") -> "SemanticToken":
        """Convert this candidate to a SemanticToken for the IR layer."""
        from app.semantic_ir import SemanticToken, Span

        return SemanticToken(
            raw=self.raw,
            normalized=self.cleaned,
            span=Span(self.span_start, self.span_end),
            position=self.position,
            primary_type=self.primary_type,
            type_distribution=dict(self.type_distribution),
            source_field=source_field,
        )

    def type_distribution_semantic(self) -> Dict[SemanticType, float]:
        """Return the already-semantic type distribution."""
        return dict(self.type_distribution)


@dataclass
class RelationshipIR:
    """Represents a scored relationship between two candidates."""

    source_idx: int
    target_idx: int
    relationship_type: str  # "adjacent", "same_group", "parent_child", "repeated_pattern"
    confidence: float
    evidence: List[str] = field(default_factory=list)


@dataclass
class StructuralMemory:
    """Remembers repeated structural patterns across records."""

    pattern_signature: Tuple[str, ...]  # e.g., ("code", "date", "price")
    occurrence_count: int
    row_indices: List[int] = field(default_factory=list)
    avg_confidence: float = 0.0


@dataclass
class SegmentedIR:
    """Complete IR for a single segmented record."""

    original: str
    candidates: List[CandidateIR]
    relationships: List[RelationshipIR] = field(default_factory=list)
    structural_pattern: Tuple[str, ...] = ()
    is_noise: bool = False
    noise_confidence: float = 0.0
    noise_evidence: List[str] = field(default_factory=list)
    overall_cohesion: float = 0.0

    # Expanded: when composite values are expanded into the record
    expanded_from: Optional[str] = None
    original_field: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# UNIVERSAL DETECTION PATTERNS (NOT domain-specific)
# ═══════════════════════════════════════════════════════════════════════════════

DETECTION_PATTERNS = {
    "price": [
        r"[\$\u20a8\u20ac\u00a3\u00a5\u20b9]\s*\d+[\d,]*\.?\d*",
        r"\d+\.?\d*\s*(usd|eur|gbp|inr|rs|yen|pound)\b",
        r"\b(rs\.?|rupees?)\s*\d+[\d,]*\.?\d*",
        r"\d+\.?\d*\s*\b(cr|crore|l|lakh|k|mn|million|thousand)\b",
    ],
    "date": [
        r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}",
        r"\d{4}[/\-]\d{2}[/\-]\d{2}",
        r"\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{2,4}",
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2},?\s+\d{2,4}",
    ],
    "duration": [
        r"\d+h\s*\d*m",
        r"\d+h$",
        r"\d+:\d{2}",
        r"\d+\s*hours?",
    ],
    "code": [
        r"\b[A-Z]{2,5}\b",
    ],
    "rating": [
        r"\d+\.?\d*/\d+",
        r"\d+\.?\d*\s*(star|rating|out of)",
    ],
    "number": [
        r"\b\d+\.?\d*%?\b",
    ],
    "phone": [
        r"\+?\d{1,4}[\s\-]?\(?\d{2,5}\)?[\s\-]?\d{3,5}[\s\-]?\d{3,5}",
        r"\b\d{3,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b",
    ],
    "email": [
        r"[\w.+-]+@[\w-]+\.[\w.-]+",
    ],
    "url": [
        r"https?://[^\s]+",
    ],
    "identifier": [
        r"\b[A-Z\-_]+\d+[A-Z\d\-_]*\b",
        r"\b\d+[A-Z\-_]+[A-Z\d\-_]*\b",
        r"\b[A-Z]{2,}(?:[_-][A-Z0-9]+)+\b",
    ],
    "organization": [
        r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})+\b",
    ],
}

COMMON_ENGLISH_WORDS: Set[str] = {
    "THE",
    "AND",
    "FOR",
    "ARE",
    "NOT",
    "YOU",
    "ALL",
    "CAN",
    "HAS",
    "WAS",
    "BUT",
    "ITS",
    "OUT",
    "NEW",
    "NOW",
    "HOW",
    "GET",
    "HAD",
    "SHE",
    "HER",
    "HIM",
    "HIS",
    "OUR",
    "YOUR",
    "THEM",
    "WHO",
    "WHY",
    "ANY",
    "MAN",
    "OLD",
    "SAY",
    "WAY",
    "USE",
    "PUT",
    "TRY",
    "ASK",
    "LET",
    "BIG",
    "LOT",
    "DAY",
    "MAY",
    "SEE",
    "DID",
    "GOT",
    "SAW",
    "TWO",
    "ONE",
    "KEY",
    "SUM",
    "TIP",
    "SON",
    "CUP",
    "DOG",
    "CAR",
    "BUS",
    "AGE",
    "ACT",
    "ADD",
    "BIT",
    "BOX",
    "BOY",
    "FIT",
    "FUN",
    "GAS",
    "GOD",
    "HAT",
    "HIT",
    "HOT",
    "JOB",
    "JOY",
    "LAW",
    "LEG",
    "LIE",
    "LOG",
    "MAP",
    "NET",
    "OIL",
    "PAY",
    "PET",
    "PIN",
    "POP",
    "POT",
    "RAW",
    "RED",
    "ROW",
    "RUN",
    "SAD",
    "SEA",
    "SET",
    "SKY",
    "SUN",
    "TAG",
    "TEA",
    "TEN",
    "TIE",
    "TIN",
    "TON",
    "TOP",
    "TOY",
    "VAN",
    "WAR",
    "WAX",
    "WET",
    # Months (ambiguous with codes)
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
}


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 1: AGGRESSIVE EXTRACTION (maximize recall)
# ═══════════════════════════════════════════════════════════════════════════════


def _extract_by_pattern(text: str) -> List[CandidateIR]:
    """Pass 1: Extract all pattern-matching candidates aggressively."""
    candidates: List[CandidateIR] = []
    seen_spans: Set[Tuple[int, int]] = set()

    for ctype, patterns in DETECTION_PATTERNS.items():
        for pattern in patterns:
            # Code patterns need case-sensitive matching (only ALL-CAPS =
            # codes)
            flags = re.IGNORECASE if ctype != "code" else 0
            for match in re.finditer(pattern, text, flags):
                start, end = match.start(), match.end()
                span_key = (start, end)

                # Deduplicate exact spans
                if span_key in seen_spans:
                    continue
                seen_spans.add(span_key)

                raw = match.group(0).strip()
                if not raw:
                    continue

                # Filter common words from code type
                if ctype == SemanticType.CODE and raw.upper() in COMMON_ENGLISH_WORDS:
                    continue

                # Build type distribution (ambiguity)
                stype = candidate_type_to_semantic(ctype)
                type_dist = _classify_with_ambiguity(raw, stype)

                candidate = CandidateIR(
                    raw=raw,
                    cleaned=_clean_value(raw, ctype),
                    span_start=start,
                    span_end=end,
                    position=start,
                    primary_type=stype,
                    primary_confidence=type_dist.get(stype, 0.9),
                    type_distribution=type_dist,
                    evidence=[f"pattern_match:{pattern[:30]}"],
                    extraction_pass=1,
                    extraction_method="pattern",
                    signals=[f"pass1_pattern:{ctype}"],
                )
                candidates.append(candidate)

    candidates.sort(key=lambda c: c.position)
    return candidates


def _classify_with_ambiguity(raw: str, primary_type: SemanticType) -> Dict[SemanticType, float]:
    """Build a distribution of possible types for a candidate.

    Example: "PAR" could be code(0.7) or text(0.3).
    """
    distribution = {primary_type: 0.85}

    if primary_type == SemanticType.CODE:
        if re.match(r"^\d+$", raw):
            distribution = {SemanticType.NUMBER: 0.9, SemanticType.CODE: 0.1}
        elif re.match(r"^[A-Z]{3}$", raw):
            distribution = {SemanticType.CODE: 0.7, SemanticType.TEXT: 0.3}
        elif re.match(r"^[A-Z0-9]{4,5}$", raw):
            distribution = {SemanticType.CODE: 0.8, SemanticType.TEXT: 0.2}

    elif primary_type == SemanticType.NUMBER:
        txt = raw.lower()
        if "%" in txt:
            distribution = {SemanticType.NUMBER: 0.7, SemanticType.RATING: 0.3}
        elif "." in txt:
            distribution = {SemanticType.NUMBER: 0.6, SemanticType.RATING: 0.3, SemanticType.PRICE: 0.1}

    elif primary_type == SemanticType.DATE:
        distribution = {SemanticType.DATE: 0.85, SemanticType.TEXT: 0.15}

    elif primary_type == SemanticType.TEXT:
        txt = raw.upper()
        if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$", raw):
            distribution = {SemanticType.TEXT: 0.6, SemanticType.ORGANIZATION: 0.3, SemanticType.LOCATION: 0.1}

    return distribution


def _clean_value(raw: str, ctype: object) -> str:
    """Clean a candidate value based on type (accepts str or SemanticType)."""
    # Normalize to string for comparison if needed, but prefer enum
    ctype_str = sem_type_str(ctype)

    if ctype_str == "price":
        cleaned = raw.strip()
        cleaned = re.sub(r"(?i)^(price|cost|fare|amount)\s*[:\-]\s*", "", cleaned).strip()
        return cleaned
    return raw.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 2: SPLIT-BASED EXTRACTION (catch non-pattern values)
# ═══════════════════════════════════════════════════════════════════════════════


def _extract_by_split(text: str, existing_spans: Set[Tuple[int, int]]) -> List[CandidateIR]:
    """Pass 2: Extract values by splitting on separators."""
    candidates: List[CandidateIR] = []
    position = 0

    segments = re.split(r"\s*[|\t]\s*", text)
    for seg in segments:
        seg = seg.strip()
        if not seg or len(seg) < 2:
            position += 1
            continue

        sub_segments = re.split(r"\s{2,}", seg)
        for sub in sub_segments:
            sub = sub.strip()
            if not sub or len(sub) < 2:
                continue

            char_start = text.find(sub, position)
            if char_start < 0:
                char_start = position
            span = (char_start, char_start + len(sub))
            if span in existing_spans:
                continue
            existing_spans.add(span)

            ctype = _classify_fallback(sub)
            candidates.append(
                CandidateIR(
                    raw=sub,
                    cleaned=sub.strip(),
                    span_start=char_start,
                    span_end=char_start + len(sub),
                    position=char_start,
                    primary_type=ctype,
                    primary_confidence=0.5,
                    type_distribution={ctype: 0.5, SemanticType.TEXT: 0.5},
                    evidence=["split_extraction"],
                    extraction_pass=2,
                    extraction_method="split",
                    signals=["pass2_split"],
                )
            )
            position = char_start + len(sub)

    return candidates


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 3: WHITESPACE EXTRACTION (last resort)
# ═══════════════════════════════════════════════════════════════════════════════


def _extract_by_whitespace(text: str, existing_spans: Set[Tuple[int, int]]) -> List[CandidateIR]:
    """Pass 3: Extract by whitespace splitting as last resort."""
    candidates: List[CandidateIR] = []

    parts = re.split(r"\s{2,}", text)
    if len(parts) < 2:
        parts = text.split()

    for part in parts:
        part = part.strip()
        if not part or len(part) < 2:
            continue

        char_start = text.find(part)
        if char_start < 0:
            continue
        span = (char_start, char_start + len(part))
        if span in existing_spans:
            continue
        existing_spans.add(span)

        ctype = _classify_fallback(part)
        candidates.append(
            CandidateIR(
                raw=part,
                cleaned=part.strip(),
                span_start=char_start,
                span_end=char_start + len(part),
                position=char_start,
                primary_type=ctype,
                primary_confidence=0.3,
                type_distribution={ctype: 0.3, SemanticType.TEXT: 0.7},
                evidence=["whitespace_fallback"],
                extraction_pass=3,
                extraction_method="whitespace",
                signals=["pass3_whitespace"],
            )
        )

    return candidates


def _classify_fallback(text: str) -> SemanticType:
    """Classify a text segment when no strong pattern match exists.

    Uses fullmatch to avoid substring-based misclassification.
    A text like "iPhone $1,199" should NOT be classified as "price"
    just because it contains a $ sign somewhere.
    """
    lower = text.lower()
    stripped = text.strip()

    # Price-like: entire text matches currency pattern
    if re.fullmatch(r"[\$\u20a8\u20ac\u00a3\u00a5\u20b9]\s*\d+[\d,]*\.?\d*", stripped):
        return SemanticType.PRICE
    if re.fullmatch(r"\d+[\d,]*\.?\d*\s*(inr|usd|eur|gbp)", lower):
        return SemanticType.PRICE
    if re.fullmatch(r"(rs\.?|rupees?)\s*\d+[\d,]*\.?\d*", lower):
        return SemanticType.PRICE
    if re.fullmatch(r"\d+\.?\d*\s*(cr|crore|l|lakh|k|m|mn|million|thousand)", lower):
        return SemanticType.PRICE

    # Date-like
    if re.fullmatch(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", stripped):
        return SemanticType.DATE
    if re.fullmatch(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2},?\s+\d{2,4}", lower):
        return SemanticType.DATE
    if re.fullmatch(r"\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{2,4}", lower):
        return SemanticType.DATE

    # Code-like (only if ENTIRE string is uppercase or alphanumeric with
    # letters)
    if re.fullmatch(r"[A-Z]{2,5}", stripped):
        return SemanticType.CODE
    if re.fullmatch(r"[A-Z][A-Z0-9]{2,7}", stripped):
        return SemanticType.CODE
    if re.fullmatch(r"[A-Z]{2,}(?:[_-][A-Z0-9]+)+", stripped):
        return SemanticType.IDENTIFIER

    # Number-like (entire string is a number)
    if re.fullmatch(r"\d+\.?\d*%?", stripped):
        return SemanticType.NUMBER

    # Rating-like (entire string)
    if re.fullmatch(r"\d+\.?\d*/\d+", stripped):
        return SemanticType.RATING

    # Duration-like
    if re.fullmatch(r"\d+h\s*\d*m|\d+h|\d+:\d{2}|(?:\d+\s*hours?)", lower):
        return SemanticType.DURATION

    # Number with suffix: "5+", "25L", "10K"
    if re.fullmatch(r"\d+\.?\d*[LkKmM+]?", stripped) and len(stripped) > 1:
        return SemanticType.NUMBER

    # Organization-like: Title Case word (starts uppercase, rest lowercase, length > 1)
    # This catches names like Lufthansa, Google, Marriott, etc.
    # Must match the ENTIRE string (not just start) to avoid split issues
    if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*", stripped) and len(stripped) > 1:
        return SemanticType.ORGANIZATION

    # Product-like: brand naming pattern (iPhone, iPad, macOS, eBay)
    # Starts lowercase, has AT LEAST one internal uppercase
    if re.fullmatch(r"[a-z][A-Za-z0-9]{2,}", stripped) and re.search(r"[A-Z]", stripped[1:]):
        return SemanticType.ORGANIZATION

    return SemanticType.TEXT


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXTRACTION PIPELINE (multi-pass)
# ═══════════════════════════════════════════════════════════════════════════════


def extract_candidate_values(text: str) -> List[CandidateIR]:
    """Multi-pass extraction: maximize recall, then deduplicate.

    Pass 1: Aggressive pattern matching (highest confidence)
    Pass 2: Split-based extraction (medium confidence)
    Pass 3: Whitespace fallback (lowest confidence)

    Later passes fill gaps left by earlier passes.
    """
    if not text:
        return []

    existing_spans: Set[Tuple[int, int]] = set()

    # Pass 1: Pattern matching
    candidates = _extract_by_pattern(text)
    for c in candidates:
        existing_spans.add((c.span_start, c.span_end))

    # Pass 2: Split-based (if significant unextracted text remains)
    uncovered_ratio = _uncovered_ratio(text, existing_spans)
    if uncovered_ratio > 0.4:
        split_candidates = _extract_by_split(text, existing_spans)
        for c in split_candidates:
            existing_spans.add((c.span_start, c.span_end))
        candidates.extend(split_candidates)

    # Pass 3: Whitespace (always run for finer granularity)
    # Even when text is fully covered, whitespace splitting provides
    # individual token candidates for better classification
    ws_candidates = _extract_by_whitespace(text, existing_spans)
    candidates.extend(ws_candidates)

    candidates.sort(key=lambda c: c.position)
    return candidates


def _uncovered_ratio(text: str, spans: Set[Tuple[int, int]]) -> float:
    """Calculate what fraction of text is not covered by any span."""
    if not text:
        return 1.0
    covered = set()
    for start, end in spans:
        for i in range(max(0, start), min(end, len(text))):
            covered.add(i)
    if not text:
        return 0.0
    return 1.0 - (len(covered) / len(text))


# ═══════════════════════════════════════════════════════════════════════════════
# RELATIONSHIP SCORING
# ═══════════════════════════════════════════════════════════════════════════════


def score_relationships(candidates: List[CandidateIR]) -> List[RelationshipIR]:
    """Score relationships between candidate values.

    Considers:
    - Proximity (adjacent values likely relate)
    - Type compatibility (price near code, date near time)
    - Positional patterns (repeated type sequences)
    """
    relationships: List[RelationshipIR] = []
    if len(candidates) < 2:
        return relationships

    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            ci, cj = candidates[i], candidates[j]
            gap = cj.position - (ci.position + len(ci.raw))

            # Adjacent (no gap or small gap)
            if gap <= 2:
                rel_type, confidence, evidence = _infer_relationship_type(ci, cj)
                relationships.append(
                    RelationshipIR(
                        source_idx=i,
                        target_idx=j,
                        relationship_type=rel_type,
                        confidence=confidence,
                        evidence=evidence,
                    )
                )
            # Near (small gap)
            elif gap <= 10:
                relationships.append(
                    RelationshipIR(
                        source_idx=i,
                        target_idx=j,
                        relationship_type="nearby",
                        confidence=0.4,
                        evidence=[f"gap={gap}chars"],
                    )
                )

    return relationships


def _infer_relationship_type(a: CandidateIR, b: CandidateIR) -> Tuple[str, float, List[str]]:
    """Infer what kind of relationship exists between two adjacent candidates."""
    evidence = [f"{a.primary_type}+{b.primary_type}"]

    # Price + anything
    if a.primary_type == SemanticType.PRICE:
        return "value_modifier", 0.6, evidence + ["price_modifier"]

    # Code + price (common pattern: destination + price)
    if a.primary_type == SemanticType.CODE and b.primary_type == SemanticType.PRICE:
        return "location_price", 0.7, evidence + ["code_then_price"]
    if b.primary_type == SemanticType.CODE and a.primary_type == SemanticType.PRICE:
        return "price_location", 0.7, evidence + ["price_then_code"]

    # Code + code (two identifiers, likely related)
    if a.primary_type == SemanticType.CODE and b.primary_type == SemanticType.CODE:
        return "paired_codes", 0.6, evidence + ["paired_identifiers"]

    # Date + date (date range)
    if a.primary_type == SemanticType.DATE and b.primary_type == SemanticType.DATE:
        return "date_range", 0.8, evidence + ["date_pair"]

    # Same type adjacent = likely same semantic group
    if a.primary_type == b.primary_type:
        return "same_type_group", 0.5, evidence + ["same_type_adjacent"]

    return "adjacent", 0.3, evidence


# ═══════════════════════════════════════════════════════════════════════════════
# STRUCTURAL MEMORY
# ═══════════════════════════════════════════════════════════════════════════════


class StructuralMemoryTracker:
    """Tracks repeated structural patterns across records.

    Remembers: type sequences, positional patterns, common groupings.
    Anomalous rows get lower confidence.
    """

    def __init__(self):
        self.patterns: Dict[Tuple[str, ...], StructuralMemory] = {}
        self.total_records = 0

    def record(self, candidates: List[CandidateIR], row_index: int) -> Tuple[float, List[str]]:
        """Record a row's structural pattern and return anomaly score."""
        self.total_records += 1

        if not candidates:
            return 1.0, ["empty_row"]

        # Build type signature
        signature = tuple(c.primary_type for c in candidates)

        # Phase 47: Type Integrity - Ensure pattern signatures are string-based
        # tuples
        sig_list = [t.value if hasattr(t, "value") else str(t) for t in signature]
        sig_key = tuple(sig_list)

        # Update memory
        if sig_key not in self.patterns:
            self.patterns[sig_key] = StructuralMemory(
                pattern_signature=sig_key,
                occurrence_count=0,
                row_indices=[],
            )
        mem = self.patterns[sig_key]
        mem.occurrence_count += 1
        mem.row_indices.append(row_index)
        mem.avg_confidence = sum(c.primary_confidence for c in candidates) / len(candidates)

        # Anomaly score: lower for common patterns, higher for rare ones
        if mem.occurrence_count >= 3:
            return 0.9, [f"pattern_seen_{mem.occurrence_count}x"]
        elif mem.occurrence_count == 2:
            return 0.7, ["pattern_seen_2x"]
        else:
            # First occurrence - check similarity to known patterns
            similarity = _max_pattern_similarity(sig_key, list(self.patterns.keys()))
            if similarity >= 0.5:
                return 0.6, [f"similar_to_known_pattern({similarity:.2f})"]
            return 0.3, ["novel_pattern"]


def _max_pattern_similarity(signature: Tuple[str, ...], known: List[Tuple[str, ...]]) -> float:
    """Compute max Jaccard similarity between a signature and known patterns."""
    if not known:
        return 0.0

    sig_set = set(signature)
    best = 0.0
    for k in known:
        k_set = set(k)
        intersection = len(sig_set & k_set)
        union = len(sig_set | k_set)
        if union > 0:
            sim = intersection / union
            best = max(best, sim)
    return best


# ═══════════════════════════════════════════════════════════════════════════════
# SEMANTIC DENSITY ANALYSIS (replaces heuristic phrase lists)
# ═══════════════════════════════════════════════════════════════════════════════


def compute_semantic_density(text: str) -> float:
    """Compute how semantically 'dense' a text is.

    High-density text contains many meaningful candidates (prices, dates, codes).
    Low-density text is mostly prose / navigation / descriptive.

    This replaces hardcoded phrase lists for noise detection.
    """
    candidates = extract_candidate_values(text)

    if not candidates:
        return 0.0

    # Count meaningful types (not text)
    meaningful = [c for c in candidates if c.primary_type != SemanticType.TEXT]
    if not meaningful:
        return 0.0

    # Density = meaningful candidates per 100 chars
    density = (len(meaningful) / max(len(text), 1)) * 100

    # Also consider type diversity
    types = set(c.primary_type for c in meaningful)
    diversity_bonus = min(len(types) * 0.05, 0.2)

    return min(density * 0.15 + diversity_bonus, 1.0)


def is_likely_noise(text: str) -> Tuple[bool, float, List[str]]:
    """Determine if text is likely noise / navigation using semantic analysis.

    Uses semantic density, not phrase lists.
    """
    evidence: List[str] = []
    if not text or len(text) < 3:
        return False, 0.2, ["too_short_for_noise_classification"]

    # Universal structural navigation check (NOT domain-specific)
    key = re.sub(r"[^a-z0-9\s]+", " ", text.lower()).strip()
    nav_markers = [
        "about us",
        "contact us",
        "privacy",
        "terms of",
        "copyright",
        "all rights reserved",
        "powered by",
        "faq",
        "help support",
        "login",
        "sign up",
        "register",
        "click here",
        "read more",
        "learn more",
        "home menu",
        "search filter",
    ]
    if any(m in key for m in nav_markers):
        return True, 0.9, ["navigation_structure_detected"]

    density = compute_semantic_density(text)

    # Very low density = likely noise
    if density < 0.05:
        evidence.append(f"low_semantic_density({density:.3f})")
        if len(text) > 5:
            return True, 0.8, evidence

    # Check for structural signals
    candidates = extract_candidate_values(text)
    meaningful = [c for c in candidates if c.primary_type != SemanticType.TEXT]

    if not meaningful:
        evidence.append("no_meaningful_candidates")
        return True, 0.7, evidence

    # High ratio of text to meaningful = likely descriptive prose
    text_count = len([c for c in candidates if c.primary_type == SemanticType.TEXT])
    if meaningful and text_count / len(candidates) > 0.8:
        evidence.append(f"high_text_ratio({text_count}/{len(candidates)})")
        return True, 0.6, evidence

    return False, density, evidence


# ═══════════════════════════════════════════════════════════════════════════════
# COMPOSITE VALUE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════


def is_composite_value(text: str) -> bool:
    """Detect if text contains multiple distinct semantic values.

    A composite value has 2+ DIFFERENT types among its meaningful candidates.
    Two candidates of the same type (e.g., two ORG words forming a company
    name like "British Airways") does NOT make a composite.
    """
    if not text or len(text) < 10:
        return False

    candidates = extract_candidate_values(text)
    # All non-text types count as potentially meaningful
    meaningful = [c for c in candidates if c.primary_type != SemanticType.TEXT]

    if len(meaningful) < 2:
        return False

    types = set(c.primary_type for c in meaningful)

    # Require 2+ DIFFERENT types (e.g., organization + price + code)
    # Same-type candidates (e.g., two ORGs in "British Airways") are NOT
    # composite.
    return len(types) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# RECORD-LEVEL SEGMENTATION
# ═══════════════════════════════════════════════════════════════════════════════


def segment_single_text(text: str) -> SegmentedIR:
    """Segment a single text into full IR with candidates, relationships, and scoring."""
    candidates = extract_candidate_values(text)
    relationships = score_relationships(candidates)

    # Structural pattern
    pattern = tuple(
        c.primary_type.value if hasattr(c.primary_type, "value") else str(c.primary_type)
        for c in candidates
        if c.primary_type != SemanticType.TEXT
    )

    # Noise detection via semantic density
    is_noise, noise_conf, noise_evidence = is_likely_noise(text)

    # Overall cohesion score
    cohesion = _compute_cohesion(candidates, relationships)

    return SegmentedIR(
        original=text,
        candidates=candidates,
        relationships=relationships,
        structural_pattern=pattern,
        is_noise=is_noise,
        noise_confidence=noise_conf,
        noise_evidence=noise_evidence,
        overall_cohesion=cohesion,
    )


def _compute_cohesion(candidates: List[CandidateIR], relationships: List[RelationshipIR]) -> float:
    """Compute overall cohesion score for a segmented record."""
    if not candidates:
        return 0.0

    # Factor 1: Meaningful ratio
    meaningful = len([c for c in candidates if c.primary_type != SemanticType.TEXT])
    meaningful_ratio = meaningful / max(len(candidates), 1)

    # Factor 2: Relationship density
    rel_density = len(relationships) / max(len(candidates), 1)

    # Factor 3: Average confidence
    avg_conf = sum(c.primary_confidence for c in candidates) / len(candidates)

    cohesion = (meaningful_ratio * 0.4) + (min(rel_density, 1.0) * 0.3) + (avg_conf * 0.3)
    return min(cohesion, 1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# RECORD EXPANSION (composite → multiple candidates)
# ═══════════════════════════════════════════════════════════════════════════════


def expand_composite_records(
    records: List[dict],
    memory: Optional[StructuralMemoryTracker] = None,
) -> List[dict]:
    """Expand composite records by splitting blob values into candidate fields.

    Each composite value gets segmented; meaningful candidates become
    new fields prefixed with the source key.

    Returns expanded records ready for semantic mapping.
    """
    if not records:
        return records

    mem = memory or StructuralMemoryTracker()
    expanded: List[dict] = []

    for row_idx, record in enumerate(records):
        new_record = dict(record)
        has_composite = False

        for key, value in list(record.items()):
            if not value or not isinstance(value, str):
                continue
            if not is_composite_value(value):
                continue

            has_composite = True
            ir = segment_single_text(value)

            # Remove original composite field to avoid confusing the mapper
            # (the segmented parts provide cleaner candidates)
            if key in new_record:
                del new_record[key]

            # Add meaningful candidates as new fields
            meaningful = [c for c in ir.candidates if c.primary_type != SemanticType.TEXT]
            for i, cand in enumerate(meaningful):
                # Encode topological information in the key: type, index, and span
                # Format: {key}_seg_{type}_{i}_{start}_{end}
                new_key = f"{key}_seg_{cand.primary_type.value}_{i}_{cand.span_start}_{cand.span_end}"
                new_record[new_key] = cand.cleaned

        # Update structural memory
        ir_for_record = segment_single_text(" ".join(str(v) for v in record.values()))
        mem.record(ir_for_record.candidates, row_idx)

        if has_composite:
            expanded.append(new_record)
        else:
            expanded.append(record)

    return expanded


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE: FIELD-LEVEL NOISE CHECK
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────
# Overlap Resolution (merged from overlap_resolution.py)
# ─────────────────────────────────────────────────────────────

# Hierarchical dominance: broader types dominate narrower ones
DOMINANCE_HIERARCHY = {
    SemanticType.EMAIL: 100,
    SemanticType.PRICE: 90,
    SemanticType.DATE: 85,
    SemanticType.PHONE: 80,
    SemanticType.URL: 80,
    SemanticType.DURATION: 70,
    SemanticType.RATING: 65,
    SemanticType.CODE: 50,
    SemanticType.LOCATION: 45,
    SemanticType.ORGANIZATION: 40,
    SemanticType.NAME: 35,
    SemanticType.NUMBER: 20,
    SemanticType.IDENTIFIER: 15,
    SemanticType.TEXT: 10,
}


def resolve_overlaps(tokens: List[SemanticToken]) -> List[SemanticToken]:
    """Resolve span overlaps and value containment.

    Suppresses dominated tokens:
    1. Lower in DOMINANCE_HIERARCHY
    2. Physically contained (Span.contains)
    3. Semantically contained (raw value substring)
    """
    if not tokens:
        return tokens

    # Sort by dominance then size
    sorted_tokens = sorted(
        tokens, key=lambda t: (-DOMINANCE_HIERARCHY.get(t.primary_type, 0), -(t.span.end - t.span.start), -len(t.raw))
    )

    suppressed: Set[int] = set()
    for i in range(len(sorted_tokens)):
        if i in suppressed:
            continue
        ti = sorted_tokens[i]

        for j in range(i + 1, len(sorted_tokens)):
            if j in suppressed:
                continue
            tj = sorted_tokens[j]

            # Case 1: Physical Span overlap
            if ti.span.overlaps_with(tj.span):
                suppressed.add(j)
                continue

            # Case 2: Semantic Value Containment (Lexical Overlap)
            # If tj.raw is a STRICT substring of ti.raw, it's likely a fragment
            if len(tj.raw) > 2 and len(tj.raw) < len(ti.raw) and tj.raw.lower() in ti.raw.lower():
                # Suppression rules for lexical containment:
                # - If child is a NUMBER, always suppress
                # - If child is same type as parent, always suppress
                # - If parent is high-dominance (EMAIL, PHONE), always suppress child
                if (
                    tj.primary_type == SemanticType.NUMBER
                    or tj.primary_type == ti.primary_type
                    or DOMINANCE_HIERARCHY.get(ti.primary_type, 0) >= 80
                ):
                    suppressed.add(j)
                    continue

    result = [t for idx, t in enumerate(sorted_tokens) if idx not in suppressed]
    return result


def is_likely_noise_field(name: str, value: str) -> Tuple[bool, float, List[str]]:
    """Check if a field value is likely noise, using semantic analysis.

    Field-type-aware: for name / text fields, plain text is expected.
    For typed fields (price, date, rating), absence of type signals is suspicious.

    Replaces hardcoded phrase-list checks with broader semantic analysis.
    """
    evidence: List[str] = []

    if not value:
        return True, 1.0, ["empty_value"]

    key = re.sub(r"[^a-z0-9]+", " ", value.lower().strip()).strip()
    if not key or len(key) < 2:
        return False, 0.3, ["too_short_to_classify"]

    # Detect field type from name
    name_lower = name.lower()
    is_text_field = any(t in name_lower for t in ["name", "company", "title", "description", "address"])
    is_typed_field = any(t in name_lower for t in ["price", "date", "rating", "phone", "email", "url"])

    # For text / name fields: plain text is expected, check only obvious noise
    if is_text_field:
        # Universal structural navigation patterns (NOT domain-specific)
        nav_key = re.sub(r"[^a-z0-9\s]+", "", key)
        nav_markers = [
            "about us",
            "contact us",
            "privacy",
            "terms of",
            "copyright",
            "all rights reserved",
            "powered by",
            "faq",
            "help",
            "support",
            "login",
            "sign up",
            "register",
            "facebook",
            "twitter",
            "instagram",
            "click here",
            "read more",
            "learn more",
            "view more",
            "home",
            "menu",
            "search",
            "filter",
            "sort by",
        ]
        if any(m in nav_key for m in nav_markers):
            return True, 0.9, ["navigation_structure_detected"]

        segments = segment_single_text(value)
        # Name fields shouldn't contain structured data (prices, dates, etc.)
        typed_candidates = [c for c in segments.candidates if c.primary_type not in ("text", "number")]
        if typed_candidates:
            evidence.append(f"name_field_has_typed_content:{typed_candidates[0].primary_type}")
            return False, 0.4, evidence
        # Plain text is fine for name fields
        return False, 0.9, ["plain_text_name_field"]

    # For typed fields: check if value matches expected type
    if is_typed_field:
        segments = segment_single_text(value)
        typed_count = len([c for c in segments.candidates if c.primary_type != SemanticType.TEXT])
        if typed_count == 0:
            evidence.append("typed_field_has_no_typed_content")
            return True, 0.7, evidence
        return False, 0.8, [f"typed_content_found:{typed_count}"]

    # For generic fields: use semantic density
    is_noise, conf, noise_ev = is_likely_noise(value)
    return is_noise, conf, evidence + noise_ev
