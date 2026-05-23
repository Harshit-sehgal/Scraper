"""
Compound Record Assembler — Detects internal segments inside a result container
and assembles them into structured compound records.

A compound record has repeated internal segments (e.g., outbound/return legs in
a flight, room/rate in a hotel, product/offer in an ecommerce listing) plus
shared fields (e.g., total price, fare type, rating).

This is completely generic — no domain-specific fields, no hardcoded segment names.
It works by detecting repeated structural patterns within a container element.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    """A single detected internal segment within a result container."""
    index: int
    label: str  # e.g., "Departure", "Outbound", "Leg 1", or inferred label
    fields: dict[str, str] = field(default_factory=dict)
    raw_text: str = ""
    confidence: float = 0.0


@dataclass
class CompoundRecord:
    """A complete compound record with segments and shared fields."""
    segments: list[Segment] = field(default_factory=list)
    shared_fields: dict[str, str] = field(default_factory=dict)
    original_text: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "segments": [
                {"label": s.label, "fields": s.fields, "raw_text": s.raw_text}
                for s in self.segments
            ],
            "shared_fields": self.shared_fields,
        }

    def flatten(self, schema_fields: list[str] | None = None) -> dict:
        """Flatten into a single dict for schema-aligned output.

        Naming convention: {segment_label}_{field_name}
        e.g., departure_carrier, return_carrier, total_price
        """
        flat = dict(self.shared_fields)
        for seg in self.segments:
            prefix = seg.label.lower().replace(" ", "_")
            for fname, fval in seg.fields.items():
                key = f"{prefix}_{fname}"
                flat[key] = fval
        return flat


# ---------------------------------------------------------------------------
# Segment labels — these are generic labels, not domain-specific
# ---------------------------------------------------------------------------

SEGMENT_LABELS = [
    "segment", "leg", "part", "section",
    "outbound", "inbound",
    "departure", "arrival", "return",
    "from", "to",
    "going", "coming",
    "trip", "stop",
]

# Labels that act as segment separators
SEGMENT_SEPARATORS = [
    "departure", "return", "outbound", "inbound",
    "leg 1", "leg 2", "leg1", "leg2",
    "segment 1", "segment 2",
    "going", "coming",
    "from", "to",
    "trip", "stop",
]


# ---------------------------------------------------------------------------
# Segment detection
# ---------------------------------------------------------------------------

def detect_segments(element_text: str) -> list[dict[str, Any]]:
    """Detect internal segments within a single element's text.

    Looks for repeated structural patterns: sections separated by labels,
    repeated field groups, or visually separated blocks.

    Args:
        element_text: Combined text of the container element.

    Returns:
        List of detected segments with their labels and text content.
    """
    segments: list[dict[str, Any]] = []

    # Strategy 1: Label-separated segments
    # Look for common segment separators in the text
    lines = [l.strip() for l in element_text.split("\n") if l.strip()]
    if not lines:
        lines = [l.strip() for l in re.split(r'\s{2,}', element_text) if l.strip()]

    current_segment: dict[str, Any] | None = None
    segment_idx = 0

    for line in lines:
        line_lower = line.lower().strip(":,. ")

        # Check if this line is a segment separator
        matched_separator = None
        for sep in SEGMENT_SEPARATORS:
            if line_lower == sep or line_lower.startswith(sep + ":") or line_lower.startswith(sep + " "):
                matched_separator = sep.title()
                break

        if matched_separator:
            if current_segment:
                segments.append(current_segment)
            current_segment = {
                "index": segment_idx,
                "label": matched_separator,
                "lines": [],
                "raw_text": "",
            }
            segment_idx += 1
        elif current_segment is not None:
            current_segment["lines"].append(line)
            current_segment["raw_text"] += " " + line

    if current_segment:
        segments.append(current_segment)

    # Strategy 2: If no label-separated segments found, try repeated field groups
    if not segments:
        segments = _detect_repeated_groups(element_text)

    # Clean up
    for s in segments:
        s["raw_text"] = s["raw_text"].strip()

    return segments


def _detect_repeated_groups(text: str) -> list[dict[str, Any]]:
    """Detect repeated field groups without explicit labels.

    Uses only generic patterns:
    - Repeated section-like structures separated by whitespace or punctuation
    - Repeated date/label/value patterns
    - Repeated blocks with similar internal structure
    """
    segments: list[dict[str, Any]] = []

    # Strategy 1: repeated blocks with whitespace separation (generic)
    blocks = re.split(r'\n\s*\n|\s{4,}|(?<=\d)\s{3,}(?=\w)', text)
    if len(blocks) >= 2:
        non_empty = [b.strip() for b in blocks if b.strip() and len(b.strip()) > 10]
        if len(non_empty) >= 2:
            for i, block in enumerate(non_empty[:10]):
                segments.append({
                    "index": i,
                    "label": f"Part {i + 1}",
                    "lines": [block],
                    "raw_text": block,
                })
            return segments

    # Strategy 2: repeated date/value clusters (generic for any listing)
    # Look for repeated patterns of date/time followed by text and values
    date_value_pattern = re.compile(
        r'(?:(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})|'       # date
        r'(?:\d{1,2}:\d{2}\s*(?:am|pm)?))'               # or time
        r'[\s\S]{10,100}?'                                 # intervening text
        r'(?:[\$\€\£\¥\₹]\s*\d+|\d{1,3}(?:,\d{3})*(?:\.\d{2})?)'  # price
    )
    matches = list(date_value_pattern.finditer(text))
    if len(matches) >= 2:
        for i, m in enumerate(matches):
            label = "Item" if i == 0 else f"Item {i + 1}"
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 30)
            context = text[start:end].strip()
            if context:
                segments.append({
                    "index": i,
                    "label": label,
                    "lines": [context],
                    "raw_text": context,
                })
        if len(segments) >= 2:
            return segments

    return segments


# ---------------------------------------------------------------------------
# Field extraction from segments
# ---------------------------------------------------------------------------

def _extract_segment_fields(raw_text: str) -> dict[str, str]:
    """Extract typed fields from a segment's text using pattern matching.

    Returns a dict of field_name -> value for detected patterns.
    """
    fields: dict[str, str] = {}

    # Carrier / airline / organization
    org_match = re.search(
        r'\b([A-Z][a-zA-Z\s]{2,30}(?:Airlines?|Airways?|Express|Air|Lines?|Fly|Jet|Star|Aviation|Travel|Tours?))\b',
        raw_text,
    )
    if org_match:
        fields["carrier"] = org_match.group(1).strip()

    # Time patterns (start and end times)
    times = re.findall(r'\d{1,2}:\d{2}\s*(?:am|pm)?', raw_text, re.I)
    if len(times) >= 2:
        fields["time_start"] = times[0]
        fields["time_end"] = times[1]
    elif len(times) == 1:
        fields["time_start"] = times[0]

    # 3-letter location codes
    codes = re.findall(r'\b[A-Z]{3}\b', raw_text)
    if len(codes) >= 2:
        fields["origin"] = codes[0]
        fields["destination"] = codes[1]
    elif len(codes) == 1:
        fields["location"] = codes[0]

    # Date
    date_match = re.search(r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}', raw_text)
    if date_match:
        fields["date"] = date_match.group(0)

    # Price / currency
    price_match = re.search(r'[\$\€\£\¥\₹]\s*\d+[\d,.]*', raw_text)
    if price_match:
        fields["price"] = price_match.group(0).replace(" ", "")

    # Duration
    dur_match = re.search(r'(\d+h\s*\d*m|\d{1,2}:\d{2})\s*(?:duration|travel|flight|trip)', raw_text, re.I)
    if dur_match:
        fields["duration"] = dur_match.group(1)

    # Flight/route numbers
    fn_match = re.search(r'\b[A-Z]{2}\d{3,4}\b', raw_text)
    if fn_match:
        fields["flight_number"] = fn_match.group(0)

    return fields


def _extract_shared_fields(segments: list[dict[str, Any]], full_text: str) -> dict[str, str]:
    """Extract fields that apply to the entire compound record (not per-segment).

    Shared fields typically include: total price, rating, availability, status.
    """
    shared: dict[str, str] = {}

    # Total price (look for large currency values)
    prices = re.findall(r'[\$\€\£\¥\₹]\s*\d+[\d,.]*', full_text)
    if prices:
        # The largest price is likely the total
        def _parse_price(p: str) -> float:
            nums = re.findall(r'\d+[\d,.]*', p)
            return float(nums[0].replace(",", "")) if nums else 0.0
        prices_with_values = [(p, _parse_price(p)) for p in prices]
        prices_with_values.sort(key=lambda x: x[1], reverse=True)
        shared["price"] = prices_with_values[0][0]

    # Rating
    rating_match = re.search(r'(?:rating|score|stars?)\s*:?\s*(\d+(?:\.\d+)?)\s*(?:\/\s*\d+)?', full_text, re.I)
    if rating_match:
        shared["rating"] = rating_match.group(1)

    # Status / availability
    status_patterns = {
        "status": r'\b(available|sold\s*out|in\s*stock|out\s*of\s*stock|booked|confirmed|cancelled|canceled|pending)\b',
        "fare_type": r'\b(basic\s*economy|economy|premium\s*economy|business\s*class|first\s*class|flexible|saver|standard)\b',
    }
    for field_name, pattern in status_patterns.items():
        match = re.search(pattern, full_text, re.I)
        if match:
            shared[field_name] = match.group(1)

    return shared


# ---------------------------------------------------------------------------
# Main assembly function
# ---------------------------------------------------------------------------

def assemble_compound_records(
    records: list[dict],
    full_texts: dict[str, str] | None = None,
) -> list[dict]:
    """Detect and assemble compound records from a list of flat records.

    Takes records extracted from containers, checks if they contain
    internal segments, and if so, assembles them into structured
    compound records.

    Args:
        records: List of flat records (each representing one container).
        full_texts: Optional mapping of record index -> original element text.
            If not provided, records are checked using their string values.

    Returns:
        List of records — some may be expanded into compound records,
        others left as-is if no segments detected.
    """
    if not records:
        return []

    assembled: list[dict] = []

    for i, record in enumerate(records):
        # Get the full text for this record
        # Priority: 1) _element_text set by extractor, 2) full_texts dict, 3) concatenated values
        text = ""
        if record.get("_element_text"):
            text = record["_element_text"]
        elif full_texts and str(i) in full_texts:
            text = full_texts[str(i)]
        else:
            # Combine all field values as a proxy for the element text
            text = " ".join(str(v) for v in record.values() if isinstance(v, str) and v)

        # Detect segments
        segments = detect_segments(text)

        if len(segments) >= 2:
            # This is a compound record — assemble it
            shared = _extract_shared_fields(segments, text)

            compound = CompoundRecord(
                shared_fields=shared,
                original_text=text[:500],
            )

            for seg in segments:
                seg_fields = _extract_segment_fields(seg.get("raw_text", ""))
                # Also copy any record fields that match segment patterns
                for k, v in record.items():
                    if k in ("carrier", "airline", "origin", "destination", "departure", "arrival"):
                        if k not in seg_fields:
                            seg_fields[k] = str(v)

                segment = Segment(
                    index=seg.get("index", 0),
                    label=seg.get("label", f"Segment_{seg.get('index', 0)}"),
                    fields=seg_fields,
                    raw_text=seg.get("raw_text", ""),
                    confidence=0.7 if seg_fields else 0.3,
                )
                compound.segments.append(segment)

            # Flatten into schema-compatible dict
            flat = compound.flatten()
            # Preserve metadata from original record
            for meta_key in ("source_url", "source_type", "source_trust_score", "record_score", "_extraction_method", "_key"):
                if meta_key in record:
                    flat[meta_key] = record[meta_key]
            assembled.append(flat)
        else:
            # Not compound — keep as-is
            assembled.append(record)

    return assembled


def assemble_single_container(
    element_text: str,
    schema_fields: list | None = None,
) -> CompoundRecord | None:
    """Analyze a single container element's text and attempt to assemble
    a compound record from it.

    Args:
        element_text: The full text of the container element.
        schema_fields: Optional schema fields to guide field extraction.

    Returns:
        CompoundRecord if segments detected, None otherwise.
    """
    if not element_text or len(element_text) < 50:
        return None

    segments = detect_segments(element_text)
    if len(segments) < 2:
        return None

    shared = _extract_shared_fields(segments, element_text)
    compound = CompoundRecord(
        shared_fields=shared,
        original_text=element_text[:500],
        confidence=0.6,
    )

    for seg in segments:
        seg_fields = _extract_segment_fields(seg.get("raw_text", ""))
        segment = Segment(
            index=seg.get("index", 0),
            label=seg.get("label", f"Segment_{seg.get('index', 0)}"),
            fields=seg_fields,
            raw_text=seg.get("raw_text", ""),
            confidence=0.7 if seg_fields else 0.3,
        )
        compound.segments.append(segment)

    return compound
