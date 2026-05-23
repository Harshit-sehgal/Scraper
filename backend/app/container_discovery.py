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
    """
    record: dict = {}
    full_text = element.get_text(separator=" ", strip=True)

    # Get all text-node-level snippets
    text_snippets = []
    for t in element.find_all(string=True):
        t = t.strip()
        if t and len(t) > 1:
            text_snippets.append(t)

    # Extract field values by pattern type
    for field in schema_fields:
        value = _extract_field_value(field, full_text, text_snippets)
        if value:
            record[field.name] = value

    return record


def _extract_field_value(
    field,
    full_text: str,
    snippets: list[str],
) -> str | None:
    """Extract a single field value from text using pattern matching.

    Uses field type to determine which patterns to match.
    """
    field_type = field.field_type if hasattr(field, 'field_type') else FieldType.STRING
    field_name = field.name.lower() if hasattr(field, 'name') else ""
    field_desc = field.description.lower() if hasattr(field, 'description') else ""

    # ── Email ──────────────────────────────────────────────────────────
    if field_type == FieldType.EMAIL:
        for snippet in snippets:
            email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', snippet)
            if email_match:
                validated = _valid_email(email_match.group(0))
                if validated:
                    return validated
        # Fallback: check full text
        email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', full_text)
        if email_match:
            validated = _valid_email(email_match.group(0))
            if validated:
                return validated
        return None

    # ── Phone ──────────────────────────────────────────────────────────
    if field_type == FieldType.PHONE:
        phone_pattern = re.compile(r'\+?\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}')
        match = phone_pattern.search(full_text)
        if match:
            validated = _valid_phone(match.group(0))
            if validated:
                return validated
        return None

    # ── URL ────────────────────────────────────────────────────────────
    if field_type == FieldType.URL:
        url_pattern = re.compile(r'https?://[^\s<>"\'\]\)]+')
        match = url_pattern.search(full_text)
        if match:
            return match.group(0)
        return None

    # ── Currency / Price ───────────────────────────────────────────────
    if field_type == FieldType.CURRENCY:
        currency_pattern = re.compile(r'[\$\€\£\¥\₹]\s*\d+[\d,.]*')
        match = currency_pattern.search(full_text)
        if match:
            return match.group(0).replace(" ", "")
        # Fallback: just a number preceded by "price" or "$"
        alt_pattern = re.compile(r'(?:price|total|fare|cost)\s*:?\s*[\$\€\£\¥\₹]?\s*(\d+[\d,.]*)', re.I)
        match = alt_pattern.search(full_text)
        if match:
            return match.group(1)
        return None

    # ── Date ───────────────────────────────────────────────────────────
    if field_type == FieldType.DATE:
        date_patterns = [
            re.compile(r'\d{4}-\d{2}-\d{2}'),
            re.compile(r'\d{1,2}/\d{1,2}/\d{2,4}'),
            re.compile(r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}', re.I),
        ]
        for pattern in date_patterns:
            match = pattern.search(full_text)
            if match:
                return match.group(0)
        return None

    # ── Time ───────────────────────────────────────────────────────────
    # Only match exact "time" field names, not "timezone", "timeout", "timeline"
    time_field_names = {"time", "departure_time", "arrival_time", "start_time", "end_time", "duration", "travel_time"}
    if field_type in (FieldType.STRING, ) and (field_name in time_field_names or field_name.endswith("_time")):
        time_pattern = re.compile(r'\d{1,2}:\d{2}\s*(?:am|pm)?', re.I)
        match = time_pattern.search(full_text)
        if match:
            return match.group(0)
        return None

    # ── Location / Code (3-letter codes like MIA, JFK) ────────────────
    if field_type == FieldType.LOCATION or "location" in field_name or "code" in field_name:
        code_pattern = re.compile(r'\b[A-Z]{3}\b')
        matches = code_pattern.findall(full_text)
        if matches:
            # Return the first unique code
            return matches[0]
        return None

    # ── Organization / Brand / Carrier (generic) ─────────────────────
    org_field_names = {"organization", "company", "carrier", "airline", "brand", "vendor", "provider", "name", "title"}
    if field_name in org_field_names or any(fn in field_name for fn in ["company", "carrier", "airline", "vendor", "brand", "organization"]):
        # Look for capitalized org/brand patterns in snippets
        for snippet in snippets:
            # Match any capitalized multi-word name (2-5 words) that could be an organization
            org_pattern = re.compile(r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,4})\b')
            match = org_pattern.search(snippet)
            if match:
                return match.group(1).strip()
        return None

    # ── Unhandled field type ────────────────────────────────────────────
    logger.debug(
        "[ContainerDiscovery] No extraction logic for field '%s' with type %s",
        field_name, field_type,
    )

    # ── String / Text (default) ────────────────────────────────────────
    if field_type == FieldType.STRING:
        # Try to find most relevant text snippet
        # Look for a label match first
        label_words = set(field_name.split("_") + field_desc.split()[:3])
        if label_words:
            for snippet in snippets:
                s_lower = snippet.lower()
                if any(w in s_lower for w in label_words if len(w) > 2):
                    if len(snippet) >= 3 and len(snippet) <= 200:
                        return snippet.strip()

        # Fallback: return first non-empty text snippet that seems meaningful
        for snippet in snippets:
            if len(snippet) >= 3 and len(snippet) <= 200:
                # Skip pure navigation/noise
                lower = snippet.lower()
                if any(nav in lower for nav in ["click", "sign", "login", "subscribe", "privacy", "terms"]):
                    continue
                return snippet.strip()

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
