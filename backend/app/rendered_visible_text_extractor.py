"""
Rendered Visible-Text Extractor — Extracts records from visible text blocks
using DOM-order proximity grouping and pattern matching.

This module works as a fallback when CSS selectors fail and the page
content is rendered but not captured by DOM-based selectors. It uses
the PageEvidenceCollector's visible text blocks and groups them into
visual cards using parent-path similarity and DOM adjacency heuristics.

NOTE: This currently groups by DOM order (parent path similarity), not by
actual spatial pixel coordinates. For full spatial grouping, Playwright
bounding box data would be needed — tracked as future enhancement.

Key capabilities:
  1. Group visible text blocks into visual cards using DOM-order proximity
  2. Detect repeated card patterns (similar structure/patterns)
  3. Extract field values from each card using pattern matching
  4. Assign values using proximity and label-value relationships
  5. Detect repeated clusters across cards for schema field identification

No domain-specific selectors or hardcoded field names.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from app.page_evidence_collector import PageEvidence, VisibleTextBlock, collect_page_evidence
from app.models import FieldType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class VisualCard:
    """A group of nearby text blocks that likely form a single result card."""
    index: int
    y_start: float
    y_end: float
    blocks: list[VisibleTextBlock] = dataclass_field(default_factory=list)
    combined_text: str = ""
    pattern_signature: str = ""  # Ordered list of pattern types in this card
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "y_start": self.y_start,
            "y_end": self.y_end,
            "block_count": len(self.blocks),
            "combined_text": self.combined_text[:300],
            "pattern_signature": self.pattern_signature,
            "score": self.score,
        }


@dataclass
class CardGroupingResult:
    """Result of grouping visible text blocks into visual cards."""
    cards: list[VisualCard]
    card_count: int
    has_repeated_structure: bool
    cluster_signature: str  # Repeated pattern across cards


# ---------------------------------------------------------------------------
# Constants — generic grouping parameters
# ---------------------------------------------------------------------------

# Minimum blocks per card to be considered meaningful
MIN_BLOCKS_PER_CARD = 3

# Minimum cards for a "repeated cards" detection
MIN_CARDS_FOR_REPEAT = 2

# Minimum combined text length for a meaningful card
MIN_CARD_TEXT_LEN = 40

# Estimated gap between cards (for cosmetic y_start/y_end only)
CARD_Y_SPACING = 60.0


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def extract_from_visible_blocks(
    html: str,
    schema_fields: list,
    url: str = "",
) -> list[dict]:
    """Extract structured records from rendered visible text blocks.

    Uses the page evidence collector to get visible text blocks, groups
    them into visual cards, detects repeated patterns, and extracts
    field values from each card.

    Args:
        html: The page HTML.
        schema_fields: Schema fields to extract.
        url: The page URL.

    Returns:
        List of extracted records, or empty list if no cards detected.
    """
    if not html or not schema_fields:
        return []

    # Collect page evidence (which includes text blocks)
    evidence = collect_page_evidence(html, url=url)

    if not evidence.text_blocks:
        logger.debug("[VisibleTextExtractor] No text blocks found")
        return []

    # Group blocks into visual cards
    grouping = _group_into_cards(evidence)
    if grouping.card_count < MIN_CARDS_FOR_REPEAT:
        logger.debug(
            "[VisibleTextExtractor] Only %d cards found (need %d)",
            grouping.card_count, MIN_CARDS_FOR_REPEAT,
        )
        return []

    logger.info(
        "[VisibleTextExtractor] Found %d visual cards, repeated=%s",
        grouping.card_count, grouping.has_repeated_structure,
    )

    # Extract records from each card
    records = []
    for card in grouping.cards:
        record = _extract_record_from_card(card, schema_fields)
        if record and any(v for v in record.values() if v):
            records.append(record)

    if not records:
        logger.debug("[VisibleTextExtractor] No records extracted from cards")
        return []

    # Score records
    from app.utils.quality import score_record_quality
    for r in records:
        r["record_score"] = score_record_quality(r, schema_fields)
    records.sort(key=lambda r: r.get("record_score", 0.0), reverse=True)

    return records


# ---------------------------------------------------------------------------
# Visual card grouping
# ---------------------------------------------------------------------------

def _group_into_cards(evidence: PageEvidence) -> CardGroupingResult:
    """Group visible text blocks into visual cards by structural parent containers.

    Uses the block's parent_path to cluster blocks into card-like groups.
    Blocks under the same container sub-tree (depth <= 3) form one card.
    Structural boundaries (shallow-to-deep path transitions, repeated
    container patterns) separate cards.

    NOTE: This groups by DOM structure, not spatial layout. Blocks that are
    visually adjacent but in different DOM branches may end up in different
    groups. True spatial grouping requires Playwright bounding box data.
    """
    blocks = evidence.text_blocks
    if not blocks:
        return CardGroupingResult(cards=[], card_count=0, has_repeated_structure=False, cluster_signature="")

    # ── Strategy: Group by container prefix at depth 3 ────────────────
    # Each block has a parent_path like "html/body/div/div[2]/section/span"
    # We group by a prefix that represents the card-level container.
    # The prefix depth is adaptive: use depth 3 (2 tag levels) for most pages.

    def _container_prefix(path: str, depth: int = 3) -> str:
        """Extract the first `depth` levels of a parent path."""
        parts = path.split("/")
        return "/".join(parts[:min(depth, len(parts))])

    # First pass: group blocks by container prefix depth 3
    groups: dict[str, list[VisibleTextBlock]] = {}
    for block in blocks:
        prefix = _container_prefix(block.parent_path, 3)
        if prefix not in groups:
            groups[prefix] = []
        groups[prefix].append(block)

    # Second pass: split oversized groups (likely merged cards) by
    # detecting repeated pattern boundaries within the same prefix
    cards: list[VisualCard] = []
    for prefix, group in groups.items():
        # A good card has 3-12 blocks. If a group fits, keep it.
        if len(group) <= 12:
            if _is_meaningful_card(group):
                cards.append(_build_card(group, len(cards)))
            continue

        # Large group: split by depth-4 prefix (finer granularity)
        sub_groups: dict[str, list[VisibleTextBlock]] = {}
        for block in group:
            sub_prefix = _container_prefix(block.parent_path, 4)
            if sub_prefix not in sub_groups:
                sub_groups[sub_prefix] = []
            sub_groups[sub_prefix].append(block)

        for sub_prefix, sub_group in sub_groups.items():
            # If still too large, split by depth 5
            if len(sub_group) > 12:
                finer_groups: dict[str, list[VisibleTextBlock]] = {}
                for block in sub_group:
                    fine_prefix = _container_prefix(block.parent_path, 5)
                    if fine_prefix not in finer_groups:
                        finer_groups[fine_prefix] = []
                    finer_groups[fine_prefix].append(block)
                for fine_prefix, fine_group in finer_groups.items():
                    if _is_meaningful_card(fine_group):
                        cards.append(_build_card(fine_group, len(cards)))
            else:
                if _is_meaningful_card(sub_group):
                    cards.append(_build_card(sub_group, len(cards)))

    # Third pass: if we have very few cards (0-1), try depth-2 prefix
    # (broader grouping) to catch cases where cards span deeper DOM
    if len(cards) <= 1:
        broader: dict[str, list[VisibleTextBlock]] = {}
        for block in blocks:
            prefix = _container_prefix(block.parent_path, 2)
            if prefix not in broader:
                broader[prefix] = []
            broader[prefix].append(block)
        for prefix, group in broader.items():
            if len(group) > 12:
                # Still too large — don't force merge everything
                continue
            if _is_meaningful_card(group):
                cards.append(_build_card(group, len(cards)))

    # Deduplicate by combined_text (same blocks in multiple groupings)
    seen_texts: set[str] = set()
    unique_cards: list[VisualCard] = []
    for card in cards:
        if card.combined_text not in seen_texts:
            seen_texts.add(card.combined_text)
            unique_cards.append(card)
    cards = unique_cards

    # Re-index after dedup
    for i, card in enumerate(cards):
        card.index = i
        card.y_start = float(i * CARD_Y_SPACING)
        card.y_end = float(i * CARD_Y_SPACING + CARD_Y_SPACING)

    # Detect repeated structure
    has_repeated = _detect_repeated_patterns(cards)
    cluster_sig = _build_cluster_signature(cards)

    return CardGroupingResult(
        cards=cards,
        card_count=len(cards),
        has_repeated_structure=has_repeated,
        cluster_signature=cluster_sig,
    )


def _is_meaningful_card(blocks: list[VisibleTextBlock]) -> bool:
    """Check if a set of blocks forms a meaningful card."""
    if len(blocks) < MIN_BLOCKS_PER_CARD:
        return False
    combined = " ".join(b.text for b in blocks if b.text)
    return len(combined) >= MIN_CARD_TEXT_LEN


def _build_card(blocks: list[VisibleTextBlock], index: int) -> VisualCard:
    """Build a VisualCard from a list of text blocks."""
    combined = " ".join(b.text for b in blocks if b.text)
    # Build pattern signature
    pattern_types = [b.pattern_type for b in blocks if b.pattern_type]
    sig = "|".join(pattern_types) if pattern_types else "text"

    # Score the card based on content diversity
    score = _score_card(blocks, combined)

    return VisualCard(
        index=index,
        y_start=float(index * CARD_Y_SPACING),
        y_end=float(index * CARD_Y_SPACING + CARD_Y_SPACING),
        blocks=blocks,
        combined_text=combined,
        pattern_signature=sig,
        score=score,
    )


def _score_card(blocks: list[VisibleTextBlock], combined: str) -> float:
    """Score a visual card based on content quality.

    Higher score = more likely to be a meaningful result card.
    """
    score = 0.0

    # Text length
    text_len = len(combined)
    if text_len > 200:
        score += 0.3
    elif text_len > 100:
        score += 0.2
    elif text_len > MIN_CARD_TEXT_LEN:
        score += 0.1

    # Pattern diversity
    pattern_set = set(b.pattern_type for b in blocks if b.pattern_type)
    score += min(len(pattern_set) * 0.12, 0.3)

    # Has price
    has_price = any(b.pattern_type == "price" for b in blocks)
    if has_price:
        score += 0.15

    # Has multiple value types
    has_values = any(b.pattern_type in ("date", "time", "currency", "email", "phone", "location_code") for b in blocks)
    if has_values:
        score += 0.15

    # Has organization / carrier / name type
    has_org = any(b.pattern_type in ("organization", "airline_code") for b in blocks)
    if has_org:
        score += 0.1

    # Block count
    if 3 <= len(blocks) <= 20:
        score += 0.1

    return round(min(score, 1.0), 4)


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

def _detect_repeated_patterns(cards: list[VisualCard]) -> bool:
    """Check if cards have repeated structural patterns."""
    if len(cards) < MIN_CARDS_FOR_REPEAT:
        return False

    # Check pattern signature similarity
    signatures = [c.pattern_signature for c in cards if c.pattern_signature != "text"]
    if len(signatures) >= MIN_CARDS_FOR_REPEAT:
        unique = set(signatures)
        if len(unique) <= max(2, len(signatures) // 2):
            return True

    # Check block count similarity
    block_counts = [len(c.blocks) for c in cards]
    if len(block_counts) >= MIN_CARDS_FOR_REPEAT:
        avg = sum(block_counts) / len(block_counts)
        similar = sum(1 for c in block_counts if abs(c - avg) / max(avg, 1) <= 0.5)
        if similar >= MIN_CARDS_FOR_REPEAT and similar / len(block_counts) >= 0.5:
            return True

    return False


def _build_cluster_signature(cards: list[VisualCard]) -> str:
    """Build a string signature representing the repeated pattern across cards."""
    if not cards:
        return ""

    # Collect all pattern types across all cards
    all_types: list[set[str]] = []
    for card in cards:
        types = set(b.pattern_type for b in card.blocks if b.pattern_type)
        all_types.append(types)

    if not all_types:
        return ""

    # Find common pattern types across cards
    common = all_types[0]
    for types in all_types[1:]:
        common = common & types

    # Build signature
    common_list = sorted(common)
    return "+".join(common_list) if common_list else "unknown"


# ---------------------------------------------------------------------------
# Record extraction from cards
# ---------------------------------------------------------------------------

def _extract_record_from_card(
    card: VisualCard,
    schema_fields: list,
) -> dict:
    """Extract field values from a visual card using pattern matching.

    Uses stateful span tracking to ensure each text span is consumed by only
    one field. Fields with "return"/"arrival"/"dest"/"to_" semantics get the
    LAST matching value; fields with "origin"/"departure"/"from" get the first.
    """
    record: dict = {}
    full_text = card.combined_text

    # Get all text snippets with their pattern types
    text_snippets = [(b.text, b.pattern_type) for b in card.blocks if b.text]

    # Pass 1: Collect all pattern matches with positions
    matches_by_type = _collect_card_pattern_matches(full_text)

    # Pass 2: Assign values with span tracking
    used_spans: list[tuple[int, int]] = []
    used_snippet_indices: set[int] = set()

    def _is_span_used(start: int, end: int) -> bool:
        for us, ue in used_spans:
            if start < ue and end > us:
                return True
        return False

    # Priority sort: typed fields first, string/org last
    _TYPED_PRIORITY = {
        FieldType.EMAIL: 0,
        FieldType.PHONE: 0,
        FieldType.URL: 0,
        FieldType.CURRENCY: 1,
        FieldType.DATE: 1,
    }

    sorted_fields = sorted(
        enumerate(schema_fields),
        key=lambda item: (
            _TYPED_PRIORITY.get(item[1].field_type if hasattr(item[1], 'field_type') else None, 3),
            0 if not any(w in (item[1].name or "").lower() for w in ("return", "arrival", "arrive", "dest", "to_")) else 1,
        )
    )

    for idx, field in sorted_fields:
        field_type = field.field_type if hasattr(field, 'field_type') else FieldType.STRING
        field_name = field.name.lower() if hasattr(field, 'name') else ""
        field_desc = field.description.lower() if hasattr(field, 'description') else ""

        value = _extract_card_field_stateful(
            field_type, field_name, field_desc,
            full_text, text_snippets,
            matches_by_type, used_spans, used_snippet_indices,
        )
        if value and value not in ("", None, [], {}):
            record[field.name] = value

    # Preserve original card text for compound record assembly downstream
    record["_element_text"] = full_text[:2000]

    return record


def _collect_card_pattern_matches(
    full_text: str,
) -> dict:
    """Pass 1: Collect ALL pattern matches from card text, organized by type."""
    matches: dict[str, list[tuple[str, int, int]]] = {
        "email": [],
        "phone": [],
        "url": [],
        "currency": [],
        "date": [],
        "time": [],
        "code": [],
        "organization": [],
    }

    # ── Email ─────────────────────────────────────────────────
    for m in re.finditer(r'[\w.+-]+@[\w-]+\.[\w.-]+', full_text):
        from app.html_utils import _valid_email
        validated = _valid_email(m.group(0))
        if validated:
            matches["email"].append((validated, m.start(), m.end()))

    # ── Phone ─────────────────────────────────────────────────
    phone_pattern = re.compile(r'\+?\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}')
    for m in phone_pattern.finditer(full_text):
        from app.html_utils import _valid_phone
        validated = _valid_phone(m.group(0))
        if validated:
            matches["phone"].append((validated, m.start(), m.end()))

    # ── URL ───────────────────────────────────────────────────
    for m in re.finditer(r'https?://[^\s<>"\'\)\]]+', full_text):
        url = m.group(0)
        if url.startswith("http"):
            matches["url"].append((url, m.start(), m.end()))

    # ── Currency / Price ──────────────────────────────────────
    for m in re.finditer(r'[\$\€\£\¥\₹]\s*\d+[\d,.]*', full_text):
        matches["currency"].append((m.group(0).replace(" ", ""), m.start(), m.end()))

    # ── Date ──────────────────────────────────────────────────
    date_patterns = [
        re.compile(r'\d{4}-\d{2}-\d{2}'),
        re.compile(r'\d{1,2}/\d{1,2}/\d{2,4}'),
        re.compile(r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}', re.I),
    ]
    for dp in date_patterns:
        for m in dp.finditer(full_text):
            matches["date"].append((m.group(0), m.start(), m.end()))

    # ── Time ──────────────────────────────────────────────────
    for m in re.finditer(r'\d{1,2}:\d{2}\s*(?:am|pm)?', full_text, re.I):
        matches["time"].append((m.group(0), m.start(), m.end()))

    # ── Location codes ────────────────────────────────────────
    skip_codes = {"THE", "AND", "FOR", "ALL", "ANY", "NEW", "OLD", "OUT", "TOP", "BIG", "GET", "HOW", "ARE", "NOT", "CAN", "WAS", "OFF", "YOU", "HAS", "ITS", "BUT", "NOW", "MAY", "JAN", "FEB", "MAR", "APR", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"}
    for m in re.finditer(r'\b[A-Z]{3}\b', full_text):
        if m.group(0) not in skip_codes:
            matches["code"].append((m.group(0), m.start(), m.end()))

    # ── Organization / Brand ──────────────────────────────────
    # Scan full_text (not snippets) so positions are in full_text coordinate system
    org_pattern = re.compile(r'\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){1,4})\b')
    for m in org_pattern.finditer(full_text):
        val = m.group(1).strip()
        if val.lower() not in ("departure", "return", "outbound", "inbound", "arrival", "duration", "total amount", "booking details"):
            matches["organization"].append((val, m.start(), m.end()))

    # Deduplicate each list
    for key in matches:
        seen = set()
        unique = []
        for val, start, end in matches[key]:
            if val not in seen:
                seen.add(val)
                unique.append((val, start, end))
        matches[key] = unique

    return matches


def _extract_card_field_stateful(
    field_type,
    field_name: str,
    field_desc: str,
    full_text: str,
    snippets: list[tuple[str, str]],
    matches_by_type: dict,
    used_spans: list[tuple[int, int]],
    used_snippet_indices: set[int],
) -> Any:
    """Extract a field value with stateful span tracking."""
    def _consume_match(matches: list) -> str | None:
        use_last = any(w in field_name for w in ("return", "arrival", "arrive", "end", "to_", "dest"))
        if field_name in ("destination", "arrival", "arrival_city", "arrival_airport"):
            use_last = True
        if field_name in ("origin", "source", "departure", "departure_city", "departure_airport"):
            use_last = False

        if use_last:
            for i in range(len(matches) - 1, -1, -1):
                val, start, end = matches[i]
                if not _is_span_used(start, end):
                    matches.pop(i)
                    used_spans.append((start, end))
                    return val
        else:
            for i in range(len(matches)):
                val, start, end = matches[i]
                if not _is_span_used(start, end):
                    matches.pop(i)
                    used_spans.append((start, end))
                    return val
        return None

    def _is_span_used(start: int, end: int) -> bool:
        for us, ue in used_spans:
            if start < ue and end > us:
                return True
        return False

    def _consume_snippet() -> str | None:
        """Pop the next unused non-noise snippet."""
        for i, (text, ptype) in enumerate(snippets):
            if i in used_snippet_indices:
                continue
            lower = text.lower()
            if any(nav in lower for nav in ["click", "sign", "login", "subscribe", "privacy", "terms", "copyright"]):
                used_snippet_indices.add(i)
                continue
            if len(text) >= 3:
                used_snippet_indices.add(i)
                return text.strip()
        return None

    # ── Email ──────────────────────────────────────────────────────────
    if field_type == FieldType.EMAIL:
        return _consume_match(matches_by_type["email"])

    # ── Phone ──────────────────────────────────────────────────────────
    if field_type == FieldType.PHONE:
        return _consume_match(matches_by_type["phone"])

    # ── URL ────────────────────────────────────────────────────────────
    if field_type == FieldType.URL:
        return _consume_match(matches_by_type["url"])

    # ── Currency / Price ───────────────────────────────────────────────
    if field_type == FieldType.CURRENCY:
        result = _consume_match(matches_by_type["currency"])
        if result:
            return result
        # Fallback: named price
        m = re.search(r'(?:price|total|fare|cost|amount)\s*:?\s*[\$\€\£\¥\₹]?\s*(\d+[\d,.]*)', full_text, re.I)
        if m and not _is_span_used(m.start(), m.end()):
            used_spans.append((m.start(), m.end()))
            val = m.group(1)
            symbol_match = re.search(r'[\$\€\£\¥\₹]', full_text[:m.start() + 10])
            symbol = symbol_match.group(0) if symbol_match else ""
            return f"{symbol}{val}" if symbol else val
        # Last resort: decimal number
        num_m = re.search(r'(\d+\.\d{2})\b', full_text)
        if num_m and not _is_span_used(num_m.start(), num_m.end()):
            used_spans.append((num_m.start(), num_m.end()))
            symbol_match = re.search(r'[\$\€\£\¥\₹]', full_text[:num_m.start() + 10])
            symbol = symbol_match.group(0) if symbol_match else ""
            return f"{symbol}{num_m.group(1)}" if symbol else num_m.group(1)
        return None

    # ── Date ───────────────────────────────────────────────────────────
    if field_type == FieldType.DATE:
        return _consume_match(matches_by_type["date"])

    # ── Time ───────────────────────────────────────────────────────────
    time_field_names = {"time", "departure_time", "arrival_time", "start_time", "end_time", "duration", "travel_time"}
    if field_type in (FieldType.STRING,) and (field_name in time_field_names or field_name.endswith("_time")):
        return _consume_match(matches_by_type["time"])

    # ── Location / Code ────────────────────────────────────────────────
    if field_type == FieldType.LOCATION or "location" in field_name or "code" in field_name:
        result = _consume_match(matches_by_type["code"])
        if result:
            return result
        # Broader: location-like name
        loc_pattern = re.compile(r'(?:at|from|to|in|near)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)', re.I)
        m = loc_pattern.search(full_text)
        if m and not _is_span_used(m.start(), m.end()):
            used_spans.append((m.start(), m.end()))
            return m.group(1)
        return None

    # ── Organization / Brand / Name ────────────────────────────────────
    name_parts = ["name", "title", "company", "organization", "brand", "carrier", "airline", "vendor", "provider"]
    is_name_field = any(p in field_name for p in name_parts) or field_type == FieldType.STRING

    if is_name_field:
        result = _consume_match(matches_by_type["organization"])
        if result:
            return result

        # Look for capitalized words in remaining snippets
        for i, (text, ptype) in enumerate(snippets):
            if i in used_snippet_indices:
                continue
            if ptype:
                continue
            if len(text) < 4 or any(nav in text.lower() for nav in ["click", "sign", "login", "privacy", "terms", "copyright"]):
                continue
            if re.match(r'^[A-Z][a-zA-Z\s\'-]+$', text) and len(text) <= 100:
                used_snippet_indices.add(i)
                return text.strip()

        # Fallback: next unused snippet
        best = _consume_snippet()
        if best:
            return best
        return None

    # ── String (default) ───────────────────────────────────────────────
    if field_type == FieldType.STRING:
        search_words = set(field_name.split("_") + field_desc.split()[:5])
        search_words = {w for w in search_words if len(w) > 2}

        for i, (text, ptype) in enumerate(snippets):
            if i in used_snippet_indices:
                continue
            if not ptype:
                text_lower = text.lower()
                if search_words and any(w in text_lower for w in search_words):
                    if len(text) < 200:
                        used_snippet_indices.add(i)
                        return text.strip()

        best = _consume_snippet()
        if best:
            return best
        return None

    # ── Integer / Float / Number / Percentage ──────────────────────────
    if field_type in (FieldType.INTEGER, FieldType.FLOAT, FieldType.NUMBER, FieldType.PERCENTAGE):
        is_percentage = field_type == FieldType.PERCENTAGE
        pattern = re.compile(r'\d+[\.,]?\d*%?' if is_percentage else r'\d+[\.,]?\d*')
        matches_list = list(pattern.finditer(full_text))
        for m in matches_list:
            if _is_span_used(m.start(), m.end()):
                continue
            v = m.group(0).strip()
            if is_percentage and "%" in v:
                used_spans.append((m.start(), m.end()))
                return v
            if not is_percentage:
                used_spans.append((m.start(), m.end()))
                return v
        if matches_list:
            m = matches_list[0]
            if not _is_span_used(m.start(), m.end()):
                used_spans.append((m.start(), m.end()))
                return m.group(0).strip()
        return None

    return None
