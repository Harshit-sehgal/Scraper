"""
Universal Container Discovery — Finds and scores result containers on any page.

This module discovers candidate result containers from the DOM and scores
them using only generic signals (text density, pattern matches, repeated
structure, label-value pairs, links, buttons). No domain-specific selectors
or website-specific logic.

Key capabilities:
  1. Score any candidate container using universal signals
  2. Rank containers by likely record quality
  3. Multi-pass fallback: try next container when the best one fails
  4. Classify failures when no container produces useful results
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from bs4 import BeautifulSoup, Tag
from app.models import FieldType
from app.html_utils import _valid_email, _valid_phone

from app.page_evidence_collector import (
    CandidateContainer,
    PageEvidence,
    collect_page_evidence,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — generic signals only
# ---------------------------------------------------------------------------

# Text density thresholds
DENSITY_TOO_LOW = 1.0       # Less than this = basically empty
DENSITY_SPARSE = 3.0        # Between 1 and 3 = sparse
DENSITY_GOOD_LOW = 5.0      # Minimum for a "good" container
DENSITY_GOOD_HIGH = 120.0   # Maximum before it's prose (article text)

# Minimum text length for a meaningful container
MIN_CONTAINER_TEXT_LEN = 30

# Score weights
WEIGHT_TEXT_DENSITY = 0.10
WEIGHT_TEXT_LENGTH = 0.08
WEIGHT_PATTERNS = 0.25
WEIGHT_LABEL_VALUE = 0.10
WEIGHT_REPEATED_STRUCTURE = 0.15
WEIGHT_SIBLING_SIMILARITY = 0.08
WEIGHT_ACTION_ELEMENTS = 0.08
WEIGHT_INTERNAL_SEGMENTS = 0.10
WEIGHT_CHILD_COUNT = 0.06


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ContainerRanking:
    """Ranked list of candidate containers with scores."""
    containers: list[CandidateContainer]
    best_selector: str = ""
    best_score: float = 0.0
    total_candidates: int = 0

    def to_dict(self) -> dict:
        return {
            "best_selector": self.best_selector,
            "best_score": self.best_score,
            "total_candidates": self.total_candidates,
            "containers": [c.to_dict() for c in self.containers[:5]],
        }


@dataclass
class ContainerExtractionResult:
    """Result of extracting from a specific container."""
    selector: str
    records: list[dict]
    record_count: int
    avg_quality: float
    success: bool
    failure_reason: str = ""


@dataclass
class MultiPassResult:
    """Result of multi-pass container extraction."""
    all_passed: bool
    final_records: list[dict]
    total_records: int
    passes_attempted: int
    passes_succeeded: int
    best_selector: str = ""
    failure_reason: str = ""


# ---------------------------------------------------------------------------
# Core discovery
# ---------------------------------------------------------------------------

def discover_containers(
    html: str,
    url: str = "",
    min_score: float = 0.15,
) -> ContainerRanking:
    """Discover and rank result containers on a page.

    Uses the PageEvidenceCollector to gather candidate containers, then
    re-scores them using refined container-quality heuristics.

    Args:
        html: The page HTML.
        url: The page URL.
        min_score: Minimum score for a container to be considered viable.

    Returns:
        ContainerRanking with all containers sorted by score.
    """
    if not html or len(html.strip()) < 100:
        return ContainerRanking(containers=[])

    # Collect evidence (container discovery is embedded in evidence collection)
    evidence = collect_page_evidence(html, url=url)

    # Re-score containers with refined heuristics
    scored = []
    for c in evidence.candidate_containers:
        score = _refine_container_score(c, evidence)
        if score >= min_score:
            scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)

    containers = [c for _, c in scored]
    best_selector = containers[0].selector if containers else ""
    best_score = scored[0][0] if scored else 0.0

    return ContainerRanking(
        containers=containers,
        best_selector=best_selector,
        best_score=best_score,
        total_candidates=len(containers),
    )


def _refine_container_score(
    container: CandidateContainer,
    evidence: PageEvidence,
) -> float:
    """Refine a container's score using page-level context and refined heuristics.

    This is more sophisticated than the initial scoring in page_evidence_collector.
    """
    score = 0.0

    # ── 1. Text density ─────────────────────────────────────────
    if DENSITY_GOOD_LOW <= container.text_density <= DENSITY_GOOD_HIGH:
        score += WEIGHT_TEXT_DENSITY
    elif DENSITY_SPARSE <= container.text_density < DENSITY_GOOD_LOW:
        score += WEIGHT_TEXT_DENSITY * 0.5  # Sparse but has content
    elif container.text_density > 0:
        score += WEIGHT_TEXT_DENSITY * 0.2

    # ── 2. Text length ──────────────────────────────────────────
    combined_len = len(container.combined_text)
    if combined_len > 200:
        score += WEIGHT_TEXT_LENGTH
    elif combined_len > 100:
        score += WEIGHT_TEXT_LENGTH * 0.6
    elif combined_len > MIN_CONTAINER_TEXT_LEN:
        score += WEIGHT_TEXT_LENGTH * 0.3

    # ── 3. Pattern diversity (most important signal) ────────────
    pattern_count = sum([
        container.has_price,
        container.has_date,
        container.has_time,
        container.has_currency,
        container.has_location,
        container.has_organization,
        container.has_contact,
    ])
    # More patterns = more likely a data container
    score += min(pattern_count * (WEIGHT_PATTERNS / 3), WEIGHT_PATTERNS)

    # Bonus for having both descriptive text and data values
    has_values = pattern_count >= 2
    has_description = combined_len > 80
    if has_values and has_description:
        score += WEIGHT_PATTERNS * 0.3

    # ── 4. Label-value pairs ────────────────────────────────────
    if container.has_label_value_pairs:
        score += WEIGHT_LABEL_VALUE

    # ── 5. Repeated structure ───────────────────────────────────
    score += container.repeated_structure_score * WEIGHT_REPEATED_STRUCTURE

    # ── 6. Sibling similarity ───────────────────────────────────
    score += container.sibling_similarity * WEIGHT_SIBLING_SIMILARITY

    # ── 7. Action elements ──────────────────────────────────────
    actions = sum([container.has_link, container.has_button, container.has_image])
    score += min(actions * (WEIGHT_ACTION_ELEMENTS / 2), WEIGHT_ACTION_ELEMENTS)

    # ── 8. Internal segments (compound records) ─────────────────
    score += min(
        container.internal_segment_count * (WEIGHT_INTERNAL_SEGMENTS / 2),
        WEIGHT_INTERNAL_SEGMENTS,
    )

    # ── 9. Child count ──────────────────────────────────────────
    if 3 <= container.child_count <= 20:
        score += WEIGHT_CHILD_COUNT
    elif 1 <= container.child_count <= 2:
        score += WEIGHT_CHILD_COUNT * 0.4

    # ── Penalties ───────────────────────────────────────────────

    # Too deep in the DOM = likely a narrow inner element
    if container.depth > 20:
        score *= 0.7
    elif container.depth > 15:
        score *= 0.85

    # Too shallow = likely not a container at all
    if container.depth < 3:
        score *= 0.5

    # Pure price/button container with almost no text = narrow box
    if (container.has_price or container.has_button) and not container.has_organization:
        if combined_len < 100:
            score *= 0.4
        elif combined_len < 200:
            score *= 0.7

    # Container with only a link/button and no descriptive text
    if container.has_link and not container.has_price and not container.has_date and not container.has_organization:
        if combined_len < 60:
            score *= 0.3

    return round(min(score, 1.0), 4)


# ---------------------------------------------------------------------------
# Multi-pass extraction
# ---------------------------------------------------------------------------

async def multi_pass_container_extraction(
    html: str,
    schema_fields: list,
    url: str = "",
    user_intent: str = "",
    min_quality: float = 0.3,
    max_passes: int = 5,
) -> MultiPassResult:
    """Try multiple container candidates in ranked order until good records are found.

    Args:
        html: The page HTML.
        schema_fields: Schema fields to extract.
        url: Page URL.
        user_intent: Optional user intent.
        min_quality: Minimum average record quality to accept a pass.
        max_passes: Maximum number of containers to try.

    Returns:
        MultiPassResult with the best records found.
    """
    ranking = discover_containers(html, url=url)
    if not ranking.containers:
        return MultiPassResult(
            all_passed=False,
            final_records=[],
            total_records=0,
            passes_attempted=0,
            passes_succeeded=0,
            failure_reason="no_containers_detected",
        )

    all_records: list[dict] = []
    passes_attempted = 0
    passes_succeeded = 0
    best_selector = ""

    for container in ranking.containers[:max_passes]:
        passes_attempted += 1
        result = await _extract_from_container(container, html, schema_fields, url=url)

        if result.success and result.records:
            passes_succeeded += 1
            avg_q = result.avg_quality
            logger.info(
                "[ContainerDiscovery] Pass %d (%s): %d records, avg quality %.2f",
                passes_attempted, container.selector, result.record_count, avg_q,
            )

            all_records.extend(result.records)

            # If quality is good and we have enough records, stop here
            if avg_q >= min_quality and result.record_count >= 3:
                best_selector = container.selector
                logger.info(
                    "[ContainerDiscovery] Accepting pass %d (%s): quality=%.2f count=%d",
                    passes_attempted, container.selector, avg_q, result.record_count,
                )
                return MultiPassResult(
                    all_passed=True,
                    final_records=all_records,
                    total_records=len(all_records),
                    passes_attempted=passes_attempted,
                    passes_succeeded=passes_succeeded,
                    best_selector=best_selector,
                )
        else:
            logger.debug(
                "[ContainerDiscovery] Pass %d (%s) failed: %s",
                passes_attempted, container.selector, result.failure_reason,
            )

    # If we got here, no pass was good enough — return what we have
    failure_reason = "all_passes_low_quality"
    if not all_records:
        failure_reason = "all_passes_empty"

    return MultiPassResult(
        all_passed=False,
        final_records=all_records,
        total_records=len(all_records),
        passes_attempted=passes_attempted,
        passes_succeeded=passes_succeeded,
        best_selector=best_selector,
        failure_reason=failure_reason,
    )


async def _extract_from_container(
    container: CandidateContainer,
    html: str,
    schema_fields: list,
    url: str = "",
) -> ContainerExtractionResult:
    """Attempt to extract structured records from a single container.

    Uses the container's selector to find matching elements and then
    extracts field values using pattern matching and heuristics.

    This is a lightweight extraction that works without CSS selectors
    by analyzing the text content of container elements.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        container_elements = soup.select(container.selector)

        if not container_elements:
            return ContainerExtractionResult(
                selector=container.selector,
                records=[],
                record_count=0,
                avg_quality=0.0,
                success=False,
                failure_reason="selector_not_found",
            )

        records = []
        for element in container_elements[:25]:
            record = _extract_record_from_element(element, schema_fields)
            if record and any(v for v in record.values() if v):
                records.append(record)

        if not records:
            return ContainerExtractionResult(
                selector=container.selector,
                records=[],
                record_count=0,
                avg_quality=0.0,
                success=False,
                failure_reason="no_records_extracted",
            )

        # Compute average quality
        from app.utils.quality import score_record_quality
        qualities = [score_record_quality(r, schema_fields) for r in records]
        avg_quality = sum(qualities) / len(qualities) if qualities else 0.0

        return ContainerExtractionResult(
            selector=container.selector,
            records=records,
            record_count=len(records),
            avg_quality=round(avg_quality, 4),
            success=True,
        )

    except Exception as e:
        logger.warning("[ContainerDiscovery] Extraction error for %s: %s", container.selector, e)
        return ContainerExtractionResult(
            selector=container.selector,
            records=[],
            record_count=0,
            avg_quality=0.0,
            success=False,
            failure_reason=str(e),
        )


def _extract_record_from_element(
    element: Tag,
    schema_fields: list,
) -> dict:
    """Extract field values from a single container element using pattern matching.

    This is a universal text-based extractor. It looks at the text content
    of the element and assigns values to schema fields based on pattern type.

    Uses stateful span tracking to ensure each text span is consumed by only
    one field. Fields named "origin"/"departure"/"from" get the first matching
    value; fields named "destination"/"arrival"/"return"/"to_" get the last.
    String/organization fields are processed last so typed fields get first pick.
    """
    record: dict = {}
    full_text = element.get_text(separator=" ", strip=True)

    # Get all text-node-level snippets
    text_snippets = []
    for t in element.find_all(string=True):
        t = t.strip()
        if t and len(t) > 1:
            text_snippets.append(t)

    # Collect all pattern matches with positions first (pass 1)
    matches_by_type = _collect_all_pattern_matches(full_text)

    # Assign values to fields using used_spans tracking (pass 2)
    used_spans: list[tuple[int, int]] = []
    used_snippet_indices: set[int] = set()

    def _is_span_used(start: int, end: int) -> bool:
        for us, ue in used_spans:
            if start < ue and end > us:
                return True
        return False

    # Process fields in order: typed fields first, string/org last
    _TYPED_PRIORITY: dict = {
        FieldType.EMAIL: 0,
        FieldType.PHONE: 0,
        FieldType.URL: 0,
        FieldType.CURRENCY: 1,
        FieldType.DATE: 1,
    }

    # Sort schema fields: typed first, then location/code, then string/org last
    sorted_fields = sorted(
        enumerate(schema_fields),
        key=lambda item: (
            _TYPED_PRIORITY.get(item[1].field_type if hasattr(item[1], 'field_type') else None, 3),
            # Within same priority, fields with "use_last" semantics go second
            0 if not any(w in (item[1].name or "").lower() for w in ("return", "arrival", "arrive", "dest", "to_")) else 1,
        )
    )

    for idx, field in sorted_fields:
        field_type = field.field_type if hasattr(field, 'field_type') else FieldType.STRING
        field_name = field.name.lower() if hasattr(field, 'name') else ""
        field_desc = field.description.lower() if hasattr(field, 'description') else ""

        value = _extract_field_value_stateful(
            field_type, field_name, field_desc,
            full_text, text_snippets,
            matches_by_type, used_spans, used_snippet_indices,
        )
        if value:
            record[field.name] = value

    # Preserve original element text for compound record assembly downstream
    record["_element_text"] = full_text[:2000]

    return record


def _collect_all_pattern_matches(
    full_text: str,
) -> dict:
    """Pass 1: Collect ALL pattern matches from the text, organized by type.

    Returns a dict:
    {
        "email": [(match, start, end), ...],
        "phone": [(match, start, end), ...],
        "currency": [(match, start, end), ...],
        "date": [(match, start, end), ...],
        "time": [(match, start, end), ...],
        "code": [(match, start, end), ...],
        "organization": [(match, start, end), ...],
    }
    """
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
        validated = _valid_email(m.group(0))
        if validated:
            matches["email"].append((validated, m.start(), m.end()))

    # ── Phone ─────────────────────────────────────────────────
    phone_pattern = re.compile(r'\+?\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}')
    for m in phone_pattern.finditer(full_text):
        validated = _valid_phone(m.group(0))
        if validated:
            matches["phone"].append((validated, m.start(), m.end()))

    # ── URL ───────────────────────────────────────────────────
    url_pattern = re.compile(r'https?://[^\s<>"\'\]\)]+')
    for m in url_pattern.finditer(full_text):
        matches["url"].append((m.group(0), m.start(), m.end()))

    # ── Currency / Price ──────────────────────────────────────
    currency_pattern = re.compile(r'[\$\€\£\¥\₹]\s*\d+[\d,.]*')
    for m in currency_pattern.finditer(full_text):
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
    time_pattern = re.compile(r'\d{1,2}:\d{2}\s*(?:am|pm)?', re.I)
    for m in time_pattern.finditer(full_text):
        matches["time"].append((m.group(0), m.start(), m.end()))

    # ── Location codes (3-letter uppercase codes) ────────────────
    skip_codes = {"THE", "AND", "FOR", "ALL", "ANY", "NEW", "OLD", "OUT", "TOP", "BIG", "GET", "HOW", "ARE", "NOT", "CAN", "WAS", "OFF", "YOU", "HAS", "ITS", "BUT", "NOW", "MAY", "JAN", "FEB", "MAR", "APR", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"}
    for m in re.finditer(r'\b[A-Z]{3}\b', full_text):
        if m.group(0) not in skip_codes:
            matches["code"].append((m.group(0), m.start(), m.end()))

    # ── Organization / Brand (capitalized multi-word names) ──────
    # Scan full_text (not snippets) so positions are in full_text coordinate system
    org_pattern = re.compile(r'\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){1,4})\b')
    for m in org_pattern.finditer(full_text):
        val = m.group(1).strip()
        # Skip common non-org patterns
        if val.lower() not in ("departure", "return", "outbound", "inbound", "arrival", "duration", "total amount", "booking details"):
            matches["organization"].append((val, m.start(), m.end()))

    # Deduplicate each list (same value, keep first occurrence)
    for key in matches:
        seen = set()
        unique = []
        for val, start, end in matches[key]:
            if val not in seen:
                seen.add(val)
                unique.append((val, start, end))
        matches[key] = unique

    return matches


def _extract_field_value_stateful(
    field_type,
    field_name: str,
    field_desc: str,
    full_text: str,
    snippets: list[str],
    matches_by_type: dict,
    used_spans: list[tuple[int, int]],
    used_snippet_indices: set[int],
) -> str | None:
    """Extract a field value using stateful span tracking.

    Consumes matches from matches_by_type so subsequent fields get
    different matches. Uses use_last heuristic for paired fields.
    """
    def _consume_match(matches: list) -> str | None:
        """Pop the next available match, respecting use_last."""
        use_last = any(w in field_name for w in ("return", "arrival", "arrive", "end", "to_", "dest"))
        # Also: "destination" → use last, "origin" → use first
        if field_name in ("destination", "arrival", "arrival_city", "arrival_airport"):
            use_last = True
        if field_name in ("origin", "source", "departure", "departure_city", "departure_airport"):
            use_last = False

        if use_last:
            # Try from end to find an unused span
            for i in range(len(matches) - 1, -1, -1):
                val, start, end = matches[i]
                if not _is_span_used(start, end):
                    matches.pop(i)
                    used_spans.append((start, end))
                    return val
        else:
            # Try from start to find an unused span
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
        """Pop the next unused snippet."""
        for i, snippet in enumerate(snippets):
            if i not in used_snippet_indices:
                # Skip noise snippets
                lower = snippet.lower()
                if any(nav in lower for nav in ["click", "sign", "login", "subscribe", "privacy", "terms", "copyright"]):
                    used_snippet_indices.add(i)
                    continue
                if len(snippet) >= 3:
                    used_snippet_indices.add(i)
                    return snippet.strip()
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
        # Fallback: named price pattern
        alt_pattern = re.compile(r'(?:price|total|fare|cost)\s*:?\s*[\$\€\£\¥\₹]?\s*(\d+[\d,.]*)', re.I)
        m = alt_pattern.search(full_text)
        if m and not _is_span_used(m.start(), m.end()):
            used_spans.append((m.start(), m.end()))
            return m.group(1)
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
        return _consume_match(matches_by_type["code"])

    # ── Organization / Brand / Name ────────────────────────────────────
    org_field_names = {"organization", "company", "carrier", "airline", "brand", "vendor", "provider", "name", "title"}
    if field_name in org_field_names or any(fn in field_name for fn in ["company", "carrier", "airline", "vendor", "brand", "organization"]):
        result = _consume_match(matches_by_type["organization"])
        if result:
            return result
        # Check if any remaining snippet looks like an org name
        return _consume_snippet()

    # ── Unhandled ──────────────────────────────────────────────────────
    logger.debug(
        "[ContainerDiscovery] No extraction logic for field '%s' with type %s",
        field_name, field_type,
    )

    # ── String (default) ───────────────────────────────────────────────
    if field_type == FieldType.STRING:
        # Try to find text matching field name or description
        label_words = set(field_name.split("_") + field_desc.split()[:3])
        label_words = {w for w in label_words if len(w) > 2}

        for i, snippet in enumerate(snippets):
            if i in used_snippet_indices:
                continue
            s_lower = snippet.lower()
            if any(w in s_lower for w in label_words):
                if len(snippet) >= 3 and len(snippet) <= 200:
                    used_snippet_indices.add(i)
                    return snippet.strip()

        # Fallback: best remaining snippet
        best = _consume_snippet()
        if best:
            return best
        return None

    return None


# ---------------------------------------------------------------------------
# Failure classification for container extraction
# ---------------------------------------------------------------------------

def classify_container_failure(
    result: MultiPassResult,
    evidence: PageEvidence | None = None,
) -> dict:
    """Classify why container-based extraction failed.

    Returns a dict with:
    - failure_class: str
    - confidence: float
    - user_message: str
    - recommended_action: str
    """
    if result.failure_reason == "no_containers_detected":
        return {
            "failure_class": "js_render_required",
            "confidence": 0.75,
            "user_message": "No repeated result containers detected. The page may require JavaScript rendering.",
            "recommended_action": "enable_js_rendering",
        }

    if result.failure_reason == "all_passes_empty":
        return {
            "failure_class": "selector_failure",
            "confidence": 0.80,
            "user_message": "Containers were found but no records could be extracted from them.",
            "recommended_action": "try_visible_text_fallback",
        }

    if result.failure_reason == "all_passes_low_quality":
        return {
            "failure_class": "partial_extraction",
            "confidence": 0.60,
            "user_message": "Some data was extracted but quality was below threshold.",
            "recommended_action": "try_alternative_strategy",
        }

    # Check evidence-based signals
    if evidence:
        patterns = evidence.patterns
        has_data_signals = len(patterns.get("price", [])) > 0 or len(patterns.get("email", [])) > 0
        has_containers = len(evidence.candidate_containers) > 0

        if has_data_signals and not has_containers:
            return {
                "failure_class": "js_render_required",
                "confidence": 0.70,
                "user_message": "Data patterns detected but no containers found. Content may be JS-rendered.",
                "recommended_action": "enable_js_rendering",
            }

    return {
        "failure_class": "genuinely_empty",
        "confidence": 0.50,
        "user_message": "No data could be extracted from this page.",
        "recommended_action": "verify_source_content",
    }
