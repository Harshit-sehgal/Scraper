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

# Maximum y-gap between blocks in the same card (in pixels)
MAX_VERTICAL_GAP = 60.0

# Maximum x-distance for blocks to be in the same column
MAX_HORIZONTAL_GAP = 200.0

# Minimum blocks per card to be considered meaningful
MIN_BLOCKS_PER_CARD = 3

# Minimum cards for a "repeated cards" detection
MIN_CARDS_FOR_REPEAT = 2

# Minimum combined text length for a meaningful card
MIN_CARD_TEXT_LEN = 40

# Maximum y-gap between cards
MAX_CARD_GAP = 200.0


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
    """Group visible text blocks into visual cards based on y-proximity.

    Uses a simple greedy algorithm on DOM-order:
    1. Group blocks whose parent paths share a common prefix (same container)
    2. Adjacent blocks in DOM order with close parent paths are grouped
    3. Separate groups when parent paths diverge significantly
    4. Merge adjacent cards that are likely part of the same card (split by DOM structure)
    5. Score each group based on content density

    NOTE: This groups by DOM proximity, not spatial layout. Blocks that are
    visually adjacent but in different DOM branches may end up in different
    groups. True spatial grouping requires Playwright bounding box data.
    """
    blocks = evidence.text_blocks
    if not blocks:
        return CardGroupingResult(cards=[], card_count=0, has_repeated_structure=False, cluster_signature="")

    # Group blocks by parent path similarity (same container = likely same card)
    cards: list[VisualCard] = []
    current_card_blocks: list[VisibleTextBlock] = []
    current_parent_prefix = ""
    current_y = 0.0

    for i, block in enumerate(blocks):
        block_parent = block.parent_path
        block_y = current_y  # Simulate y position based on order

        # Check: is this block in the same parent container as current card?
        same_parent = (
            current_parent_prefix
            and (block_parent.startswith(current_parent_prefix) or current_parent_prefix.startswith(block_parent))
        )

        # Also check: is the gap from the last block small?
        gap = abs(block_y - current_y) if current_y > 0 else 0
        is_nearby = gap < 3  # Adjacent in order

        if (same_parent or is_nearby) and current_card_blocks:
            current_card_blocks.append(block)
        else:
            # Finish current card
            if current_card_blocks and _is_meaningful_card(current_card_blocks):
                card = _build_card(current_card_blocks, len(cards))
                cards.append(card)
            # Start new card
            current_card_blocks = [block]
            current_parent_prefix = block_parent.rsplit("/", 1)[0] if "/" in block_parent else block_parent

        current_y = block_y + 1.0  # Increment simulated y

    # Don't forget the last card
    if current_card_blocks and _is_meaningful_card(current_card_blocks):
        card = _build_card(current_card_blocks, len(cards))
        cards.append(card)

    # Merge cards that are too close together
    cards = _merge_nearby_cards(cards)

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
        y_start=float(index * MAX_VERTICAL_GAP),
        y_end=float(index * MAX_VERTICAL_GAP + MAX_VERTICAL_GAP),
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


def _merge_nearby_cards(cards: list[VisualCard]) -> list[VisualCard]:
    """Merge cards that are very close together (likely same card split)."""
    if len(cards) <= 1:
        return cards

    merged: list[VisualCard] = []
    current = cards[0]

    for next_card in cards[1:]:
        gap = next_card.y_start - current.y_end
        if gap < MAX_VERTICAL_GAP * 0.5:
            # Merge
            all_blocks = current.blocks + next_card.blocks
            combined = current.combined_text + " " + next_card.combined_text
            merged_card = VisualCard(
                index=current.index,
                y_start=current.y_start,
                y_end=next_card.y_end,
                blocks=all_blocks,
                combined_text=combined,
                pattern_signature=current.pattern_signature + "|" + next_card.pattern_signature,
                score=max(current.score, next_card.score),
            )
            current = merged_card
        else:
            merged.append(current)
            current = next_card

    merged.append(current)
    # Re-index
    for i, card in enumerate(merged):
        card.index = i
        card.y_start = float(i * MAX_VERTICAL_GAP)
        card.y_end = float(i * MAX_VERTICAL_GAP + MAX_VERTICAL_GAP)

    return merged


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

    For each schema field, looks for matching patterns in the card's
    text blocks, using proximity to labels when possible.
    """
    record: dict = {}
    full_text = card.combined_text

    # Get all text snippets with their pattern types
    text_snippets = [(b.text, b.pattern_type) for b in card.blocks if b.text]

    for field in schema_fields:
        value = _extract_card_field(field, full_text, text_snippets)
        if value and value not in ("", None, [], {}):
            record[field.name] = value

    return record


def _extract_card_field(
    field,
    full_text: str,
    snippets: list[tuple[str, str]],
) -> Any:
    """Extract a single field value from card text.

    Uses field type and field name to determine which patterns to look for.
    """
    field_type = field.field_type if hasattr(field, 'field_type') else FieldType.STRING
    field_name = field.name.lower() if hasattr(field, 'name') else ""
    field_desc = field.description.lower() if hasattr(field, 'description') else ""

    # ── Email ──────────────────────────────────────────────────────────
    if field_type == FieldType.EMAIL:
        for text, _ in snippets:
            match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
            if match:
                from app.html_utils import _valid_email
                validated = _valid_email(match.group(0))
                if validated:
                    return validated
        match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', full_text)
        if match:
            from app.html_utils import _valid_email
            validated = _valid_email(match.group(0))
            if validated:
                return validated
        return None

    # ── Phone ──────────────────────────────────────────────────────────
    if field_type == FieldType.PHONE:
        for text, _ in snippets:
            match = re.search(r'\+?\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}', text)
            if match:
                from app.html_utils import _valid_phone
                validated = _valid_phone(match.group(0))
                if validated:
                    return validated
        return None

    # ── URL ────────────────────────────────────────────────────────────
    if field_type == FieldType.URL:
        for text, _ in snippets:
            match = re.search(r'https?://[^\s<>"\'\)\]]+', text)
            if match:
                url = match.group(0)
                if url.startswith("http"):
                    return url
        match = re.search(r'https?://[^\s<>"\'\)\]]+', full_text)
        if match:
            return match.group(0)
        return None

    # ── Currency / Price ───────────────────────────────────────────────
    if field_type == FieldType.CURRENCY:
        # Look for price patterns: $500.01, EUR 50, etc.
        currency_match = re.search(r'[\$\€\£\¥\₹]\s*\d+[\d,.]*', full_text)
        if currency_match:
            return currency_match.group(0).replace(" ", "")

        # Named price
        named_match = re.search(r'(?:price|total|fare|cost|amount)\s*:?\s*[\$\€\£\¥\₹]?\s*(\d+[\d,.]*)', full_text, re.I)
        if named_match:
            val = named_match.group(1)
            symbol_match = re.search(r'[\$\€\£\¥\₹]', full_text)
            symbol = symbol_match.group(0) if symbol_match else ""
            return f"{symbol}{val}" if symbol else val

        # Last resort: any number that looks like a price (has decimals)
        num_match = re.search(r'(\d+\.\d{2})\b', full_text)
        if num_match:
            symbol_match = re.search(r'[\$\€\£\¥\₹]', full_text)
            symbol = symbol_match.group(0) if symbol_match else ""
            return f"{symbol}{num_match.group(1)}" if symbol else num_match.group(1)

        return None

    # ── Date ───────────────────────────────────────────────────────────
    if field_type == FieldType.DATE:
        date_patterns = [
            re.compile(r'\d{4}-\d{2}-\d{2}'),
            re.compile(r'\d{1,2}/\d{1,2}/\d{2,4}'),
            re.compile(r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}', re.I),
        ]
        for pattern in date_patterns:
            for text, _ in snippets:
                match = pattern.search(text)
                if match:
                    return match.group(0)
            match = pattern.search(full_text)
            if match:
                return match.group(0)
        return None

    # ── Location / Code ────────────────────────────────────────────────
    if field_type == FieldType.LOCATION or "location" in field_name or "code" in field_name:
        code_match = re.findall(r'\b[A-Z]{3}\b', full_text)
        if code_match:
            # Filter out common words that are 3 uppercase letters
            skip_words = {"THE", "AND", "FOR", "ALL", "ANY", "NEW", "OLD", "OUT", "TOP", "BIG", "GET", "HOW", "ARE", "NOT", "CAN", "WAS", "OFF"}
            codes = [c for c in code_match if c not in skip_words]
            if codes:
                return codes[0]
        # Broader: any location-like name
        loc_pattern = re.compile(r'(?:at|from|to|in|near)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)', re.I)
        match = loc_pattern.search(full_text)
        if match:
            return match.group(1)
        return None

    # ── Organization / Brand / Name (generic) ──────────────────────────
    if field_type == FieldType.STRING or "name" in field_name or "title" in field_name:
        name_parts = ["name", "title", "company", "organization", "brand", "carrier", "airline", "vendor", "provider"]
        is_name_field = any(p in field_name for p in name_parts) or field_type == FieldType.STRING

        if is_name_field:
            # Look for capitalized words (potential org/brand names)
            for text, ptype in snippets:
                if ptype:  # Has a known pattern type, skip for name fields
                    continue
                # Skip very short or navigation-like text
                if len(text) < 4 or any(nav in text.lower() for nav in ["click", "sign", "login", "privacy", "terms", "copyright"]):
                    continue
                # Check if it looks like a name (capitalized words)
                if re.match(r'^[A-Z][a-zA-Z\s\'-]+$', text):
                    if len(text) <= 100:
                        return text.strip()

            # Look for text near labels
            for text, ptype in snippets:
                if ptype == "organization" or re.search(r'(?:inc\.?|llc|ltd\.?|corp\.?|co\.?|airlines?|airways?)', text, re.I):
                    return text.strip()

            # Fallback: longest non-pattern text snippet
            non_pattern = [(t, p) for t, p in snippets if not p and len(t) >= 4]
            if non_pattern:
                non_pattern.sort(key=lambda x: len(x[0]), reverse=True)
                return non_pattern[0][0].strip()

            return None

    # ── String (default catch-all) ─────────────────────────────────────
    if field_type == FieldType.STRING:
        # Try to find text matching the field name or description
        search_words = set(field_name.split("_") + field_desc.split()[:5])
        search_words = {w for w in search_words if len(w) > 2}

        for text, ptype in snippets:
            if not ptype:  # Only plain text
                text_lower = text.lower()
                if search_words and any(w in text_lower for w in search_words):
                    if len(text) < 200:
                        return text.strip()

        return None

    # ── Integer / Float / Number ───────────────────────────────────────
    if field_type in (FieldType.INTEGER, FieldType.FLOAT, FieldType.NUMBER, FieldType.PERCENTAGE):
        is_percentage = field_type == FieldType.PERCENTAGE
        pattern = re.compile(r'\d+[\.,]?\d*%?' if is_percentage else r'\d+[\.,]?\d*')
        matches = pattern.findall(full_text)
        if matches:
            for m in matches:
                v = m.strip()
                if is_percentage and "%" in v:
                    return v
                if not is_percentage:
                    return v
            if matches:
                return matches[0]
        return None

    return None
