"""
Zero-Result Failure Classifier — Explains WHY extraction produced 0 records.

When an extraction pipeline returns zero records, this module classifies the
root cause across nine failure categories, providing a user-facing explanation
and operator hints for automated recovery decisions.

Categories:
  - session_bound_url: Session-specific URL with detectable search form
  - search_replay_required: Session-bound URL without a replayable form
  - auth_required: Login wall or authentication gate detected
  - empty_response: Blank page or page with no usable content
  - anti_bot_block: Anti-bot challenge or block detected
  - js_render_required: JS shell — large HTML but no rendered containers
  - selector_failure: Containers were detected but no candidates extracted
  - schema_mismatch: Expected schema fields do not match page content
  - genuinely_empty: The page genuinely has no extractable data
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from app.config import settings


@dataclass
class ZeroResultClassification:
    """Result of classifying a zero-record extraction outcome."""

    zero_result: bool
    failure_class: str
    confidence: float
    user_message: str
    operator_hint: str
    recommended_action: str

    def to_dict(self) -> dict:
        return asdict(self)


_MESSAGES: dict[str, dict[str, str]] = {
    "session_bound_url": {
        "user_message": "This URL contains session-specific parameters and will expire.",
        "operator_hint": "Extract the canonical URL and use it for subsequent visits.",
        "recommended_action": "use_canonical_url",
    },
    "search_replay_required": {
        "user_message": "This search result page is tied to a session that has expired.",
        "operator_hint": "Replay the search query against the live site to obtain fresh results.",
        "recommended_action": "replay_search",
    },
    "auth_required": {
        "user_message": "The page requires login credentials to view content.",
        "operator_hint": "Provide authentication or use a pre-authenticated session.",
        "recommended_action": "authenticate",
    },
    "empty_response": {
        "user_message": "The page returned no usable data content.",
        "operator_hint": "Verify the URL is correct and the server is serving content.",
        "recommended_action": "verify_url",
    },
    "anti_bot_block": {
        "user_message": "Bot protection or a security challenge blocked the request.",
        "operator_hint": "Rotate proxy identity and increase request delay for this domain.",
        "recommended_action": "rotate_identity",
    },
    "js_render_required": {
        "user_message": "The page content requires JavaScript execution to render.",
        "operator_hint": "Ensure browser rendering is enabled with adequate settle time.",
        "recommended_action": "enable_js_rendering",
    },
    "selector_failure": {
        "user_message": "Page structure did not match any known extraction selectors.",
        "operator_hint": "Run selector discovery to find updated page structure.",
        "recommended_action": "rediscover_selectors",
    },
    "schema_mismatch": {
        "user_message": "Expected data fields were not found on this page.",
        "operator_hint": "Verify the schema definition aligns with the actual page content.",
        "recommended_action": "verify_schema_alignment",
    },
    "genuinely_empty": {
        "user_message": "No records found — the page may genuinely have no extractable data.",
        "operator_hint": "Verify that the source page contains the expected data.",
        "recommended_action": "verify_source_content",
    },
}


def classify_zero_result(
    acquisition_lineage: dict | None = None,
    session_detection: dict | None = None,
    empty_check: dict | None = None,
    anti_bot_score: float = 0.0,
    final_url: str = "",
    html: str | None = None,
    visible_text: str | None = None,
    detected_forms: list | None = None,
    detected_containers: int = 0,
    raw_candidate_count: int = 0,
    schema_fields: list | None = None,
) -> ZeroResultClassification:
    """Classify the root cause of a zero-record extraction result.

    Inspects acquisition telemetry, session detection, empty-response
    indicators, and structural signals to determine the most likely
    failure category and prescribe a recovery action.

    Args:
        acquisition_lineage: Acquisition pipeline lineage metadata.
        session_detection: Output of session_url_detector.detect_session_params.
        empty_check: Output of empty_response_detector.detect_empty_response.
        anti_bot_score: Scored anti-bot risk from telemetry (0.0-1.0).
        final_url: The final URL after all redirects.
        html: Raw HTML of the fetched page.
        visible_text: Visible text extracted from the page.
        detected_forms: List of detected HTML forms on the page.
        detected_containers: Number of repeating structural containers found.
        raw_candidate_count: Number of raw extraction candidates identified.
        schema_fields: Expected schema field names for the extraction.

    Returns:
        ZeroResultClassification with failure class, confidence, and recovery hints.
    """
    session_detection = session_detection or {}
    empty_check = empty_check or {}
    detected_forms = detected_forms or []
    schema_fields = schema_fields or []
    visible_text = visible_text or ""
    html = html or ""

    html_length = len(html)

    # Stage 1: Empty response from the detector
    if empty_check.get("is_empty") and empty_check.get("confidence", 0.0) >= settings.EMPTY_RESPONSE_CONFIDENCE_THRESHOLD:
        return _build("empty_response", empty_check.get("confidence", 0.5))

    # Stage 2: Anti-bot block
    if anti_bot_score >= settings.ANTIBOT_HARD_BLOCK_THRESHOLD:
        return _build("anti_bot_block", 0.85)

    # Stage 3: Session-bound URL (with or without forms)
    if session_detection.get("is_session_bound"):
        has_forms = len(detected_forms) > 0
        if has_forms:
            return _build("session_bound_url", 0.80)
        else:
            return _build("search_replay_required", 0.75)

    # Stage 4: Blank page (very short HTML)
    if html_length < settings.ZERO_RESULT_EMPTY_HTML_LEN:
        return _build("empty_response", 0.95)

    # Stage 5: Authentication gate
    if _has_auth_patterns(visible_text):
        return _build("auth_required", 0.90)

    # Stage 6: JS shell (large HTML but no containers rendered)
    if html_length > settings.ZERO_RESULT_JS_SHELL_HTML_LEN and detected_containers == 0 and raw_candidate_count > 0:
        return _build("js_render_required", 0.80)

    # Stage 7: Selector failure (containers found but no candidates extracted)
    if detected_containers > 0 and raw_candidate_count == 0:
        return _build("selector_failure", 0.85)

    # Stage 8: Schema mismatch (expected fields not present on the page)
    if schema_fields and not _any_field_matches_page(schema_fields, html, visible_text):
        return _build("schema_mismatch", 0.75)

    # Stage 9: Default — genuinely empty
    return _build("genuinely_empty", 0.60)


def _build(failure_class: str, confidence: float) -> ZeroResultClassification:
    msg = _MESSAGES.get(failure_class, _MESSAGES["genuinely_empty"])
    return ZeroResultClassification(
        zero_result=True,
        failure_class=failure_class,
        confidence=round(confidence, 2),
        user_message=msg["user_message"],
        operator_hint=msg["operator_hint"],
        recommended_action=msg["recommended_action"],
    )


def _has_auth_patterns(text: str) -> bool:
    """Check text for authentication-related patterns using word-boundary matching."""
    import re
    text_lower = text.lower()
    for pattern in settings.ZERO_RESULT_AUTH_PATTERNS:
        # Use word boundaries to avoid false positives (e.g. "design in" matching "sign in")
        if re.search(r'\b' + re.escape(pattern) + r'\b', text_lower):
            return True
    return False


def _any_field_matches_page(
    schema_fields: list,
    html: str,
    visible_text: str,
) -> bool:
    content_lower = f"{visible_text} {html}".lower()
    for field in schema_fields:
        if field.lower() in content_lower:
            return True
    return False
