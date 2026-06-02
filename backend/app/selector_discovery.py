"""
Selector Discovery — Entry point for LLM-guided CSS selector generation.

This module has been refactored into focused sub-modules:
- selector_discovery_analysis: Page analysis and DOM-based selector discovery
- selector_discovery_url: URL analysis, redirect detection, form recovery

All public symbols are re-exported for backward compatibility.
"""

from __future__ import annotations

import logging
import time
from typing import Any, cast

from bs4 import BeautifulSoup

from app.acquisition_mode import AcquisitionConfig, AcquisitionMode, escalate_mode, should_escalate
from app.acquisition_telemetry import get_acquisition_telemetry
from app.config import settings
from app.content_quality import (
    _assess_content_quality,
    _extract_container_text_values,
)
from app.empty_response_detector import EmptyResponseCheck, detect_empty_response
from app.html_utils import clean_html_for_selectors
from app.llm_bridge import llm_json, reset_llm_call_count
from app.motif_feedback import MotifFeedbackEngine
from app.page_profiler import detect_page_structure, detect_value_patterns
from app.search_form_recovery import (
    _build_absolute_url,
    _detect_search_form,
    _map_search_params_to_fields,
    _try_form_search_recovery,
)

# ── Re-exports from sub-modules for backward compatibility ──────────────
from app.selector_discovery_analysis import (
    _analyze_page_data_type,
    _build_css_for_element,
    _compute_ui_noise_score,
    _discover_direct_repeating_elements,
    _discover_selectors_from_dom,
    _fallback_parent_child_discovery,
    _infer_field_selectors_from_container,
    build_selector_prompt,
    discover_selectors,
)
from app.session_url_detector import detect_session_params
from app.strategy_evolution import FetchStrategy

# ── Re-exports from refactored url-analysis sub-modules ───────────────
from app.url_redirects import (
    _detect_redirect,
    build_redirect_info,
)
from app.url_value_classification import (
    _classify_value,
    _infer_field_name,
    _rename_generic_fields,
    _value_patterns_to_field_types,
    build_url_analysis_prompt,
)

__all__ = [
    "analyze_url_for_fields",
    "clean_html_for_selectors",
    "discover_selectors",
    "_analyze_page_data_type",
    "build_selector_prompt",
    "_discover_selectors_from_dom",
    "_compute_ui_noise_score",
    "_discover_direct_repeating_elements",
    "_fallback_parent_child_discovery",
    "_build_css_for_element",
    "_infer_field_selectors_from_container",
    "MotifFeedbackEngine",
    "_detect_redirect",
    "build_redirect_info",
    "_assess_content_quality",
    "_extract_container_text_values",
    "_classify_value",
    "_value_patterns_to_field_types",
    "build_url_analysis_prompt",
    "_detect_search_form",
    "_build_absolute_url",
    "_map_search_params_to_fields",
    "_try_form_search_recovery",
    "_rename_generic_fields",
    "_infer_field_name",
]

logger = logging.getLogger(__name__)


async def analyze_url_for_fields(
    url: str,
    search_params: dict[str, str] | None = None,
    acquisition_mode: str = "standard",
    _escalation_depth: int = 0,
) -> dict:
    """Analyze a URL and auto-detect what data fields can be extracted.

    This is the core of the "preview URL → suggest fields" workflow.

    1. Fetches the URL using anti-bot stealth headers
    2. Detects redirects by comparing original vs final URL
    3. If redirected (session_expired) AND search_params provided, attempts
       recovery by POSTing to the site's search form to generate a fresh session
    4. Assesses content quality (landing page vs data page)
    5. Analyzes page structure (table / cards / list / mixed)
    6. Detects value patterns (currencies, dates, ratings, etc.)
    7. Uses LLM to discover all data fields and their selectors
    8. Returns suggested fields with types, confidence, and example values

    Every step is fully generic — no hardcoded domains, paths, or selectors.

    Args:
        url: The URL to analyze
        search_params: Optional dict of search parameters to POST to the
            site's search form if the URL has expired. Keys are semantic
            (e.g. origin, destination, departure_date, return_date, adults).
            Values are the search values (e.g. "NYC", "LHR", "05 / 15 / 2026").

    Returns:
        dict with:
        - url: str
        - redirect_info: dict (redirect detection result or None)
        - content_quality: dict (content quality assessment or None)
        - search_form: dict (detected search form structure or None)
        - search_recovery: dict (recovery attempt result or None)
        - page_structure: str (table|cards|list|mixed)
        - structure_confidence: float
        - estimated_record_count: int
        - item_container: str (CSS selector)
        - suggested_fields: list of field suggestions
        - anti_bot_score: float
    """
    import httpx

    from app.html_utils import fetch_page_content as _fetch_page_content
    from app.scrape_telemetry import detect_anti_bot

    reset_llm_call_count()
    start_time = time.time()

    # Build acquisition config from the requested mode
    try:
        mode_enum = AcquisitionMode(acquisition_mode)
    except ValueError:
        mode_enum = AcquisitionMode.STANDARD
    config = AcquisitionConfig.from_mode(mode_enum)

    logger.info("[URLAnalyzer] Fetching and analyzing: %s", url)

    # ── Step 1: Determine final URL (lightweight check) ──────────────
    # Use a quick httpx request to determine where the URL ultimately
    # resolves to, without the overhead of a full Playwright session.
    final_url = url
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(10.0),
        ) as client:
            resp = await client.get(url, follow_redirects=False)

            # Manually follow redirects with SSRF validation at each hop
            max_hops = 10
            hops = 0
            while resp.is_redirect and hops < max_hops:
                hops += 1
                location = resp.headers.get("location", "")
                if not location:
                    break
                from urllib.parse import urljoin as _urljoin

                redirect_target = _urljoin(str(resp.url), location)

                # SSRF: Validate each redirect hop target
                from app.url_safety import validate_public_http_url

                try:
                    validate_public_http_url(redirect_target)
                except ValueError as e:
                    logger.warning(
                        "[URLAnalyzer] Redirect target blocked by SSRF validation: %s → %s: %s", url, redirect_target, e
                    )
                    break

                resp = await client.get(redirect_target, follow_redirects=False)

            if str(resp.url) != url:
                final_url = str(resp.url)
                logger.info("[URLAnalyzer] URL resolved: %s → %s (after %d redirect hops)", url, final_url, hops)
    except Exception as exc:
        logger.debug(
            "[URLAnalyzer] Could not determine final URL via httpx for %s: %s",
            url,
            exc,
            exc_info=True,
        )

    # Run redirect detection immediately (before full fetch)
    redirect_info = _detect_redirect(url, final_url)

    # Detect session-bound URL parameters
    session_detection: dict[str, Any]
    if config.detect_session_params:
        session_detection = cast(dict[str, Any], detect_session_params(url))
    else:
        session_detection = {
            "is_session_bound": False,
            "ephemeral_params": [],
            "canonical_url": url,
            "confidence": 0.0,
            "details": [],
        }

    # ── Step 2: Fetch the URL with anti-bot stealth ──────────────────
    try:
        html, js_render_delay, fetch_method, retry_count = await _fetch_page_content(
            url, preferred_method=FetchStrategy.PLAYWRIGHT_FULL
        )
    except Exception as e:
        logger.error("[URLAnalyzer] Failed to fetch %s: %s", url, e)
        from app.acquisition_state import AcquisitionLineage, AcquisitionState

        return {
            "url": url,
            "redirect_info": redirect_info,
            "acquisition_lineage": AcquisitionLineage(
                original_url=url,
                final_url=final_url,
                state=AcquisitionState.DIRECT,
                message=f"Failed to fetch URL: {
                    str(e)}",
            ).model_dump(mode="json"),
            "user_message": f"Failed to fetch the URL: {
                str(e)}",
            "session_detection": session_detection,
            "canonical_url": session_detection.get("canonical_url", url),
            "content_quality": None,
            "empty_check": {
                "is_empty": True,
                "empty_type": "blank",
                "confidence": 1.0,
                "message": "Failed to fetch",
                "suggestions": [],
            },
            "search_form": None,
            "search_recovery": None,
            "error": f"Failed to fetch URL: {
                str(e)}",
            "page_structure": "unknown",
            "structure_confidence": 0.0,
            "estimated_record_count": 0,
            "item_container": None,
            "suggested_fields": [],
            "anti_bot_score": 0.0,
            "acquisition_mode": acquisition_mode,
        }

    if not html or len(html.strip()) < 100:
        from app.acquisition_state import AcquisitionLineage, AcquisitionState

        return {
            "url": url,
            "redirect_info": redirect_info,
            "acquisition_lineage": AcquisitionLineage(
                original_url=url,
                final_url=final_url,
                state=AcquisitionState.DIRECT,
                message="Fetched page appears empty",
            ).model_dump(mode="json"),
            "user_message": "The fetched page appears to be empty.",
            "session_detection": session_detection,
            "canonical_url": session_detection.get("canonical_url", url),
            "content_quality": None,
            "empty_check": {
                "is_empty": True,
                "empty_type": "blank",
                "confidence": 1.0,
                "message": "Fetched page appears empty",
                "suggestions": ["The URL may be incorrect or the server returned an empty page"],
            },
            "search_form": None,
            "search_recovery": None,
            "error": "Fetched page appears empty",
            "page_structure": "unknown",
            "structure_confidence": 0.0,
            "estimated_record_count": 0,
            "item_container": None,
            "suggested_fields": [],
            "anti_bot_score": 0.0,
            "acquisition_mode": acquisition_mode,
        }

    # ── Step 3: Search Form Recovery (for expired session URLs) ──────
    # If the URL redirected (e.g. session token expired) and the user
    # provided search params, attempt to POST to the site's search form
    # to generate a fresh search session.
    search_form: dict[str, Any]
    if config.attempt_search_form:
        search_form = cast(dict[str, Any], _detect_search_form(html))
    else:
        search_form = {"detected": False, "form_fields": [], "search_fields": [], "action": ""}
    search_recovery = None

    if config.attempt_recovery and redirect_info.get("redirected") and search_params and search_form.get("detected"):
        logger.info(
            "[URLAnalyzer] Redirected URL with search params — attempting recovery via %s",
            search_form.get("action", "/search"),
        )
        search_recovery = await _try_form_search_recovery(
            landing_page_html=html,
            landing_page_url=final_url,
            search_params=search_params,
        )

        # If recovery succeeded, analyze the fresh session page
        if search_recovery.get("success") and search_recovery.get("fresh_html"):
            logger.info(
                "[URLAnalyzer] Recovery succeeded → %s, re-analyzing fresh page",
                search_recovery.get("fresh_url", ""),
            )
            # Re-analyze the fresh session results page
            html = search_recovery["fresh_html"]
            fetch_method = "search_form_post"
            # Update final URL for the fresh session
            if search_recovery.get("fresh_url"):
                final_url = search_recovery["fresh_url"]
            # Update redirect_info to reflect successful recovery
            redirect_info = build_redirect_info(
                original_url=url,
                final_url=final_url,
                search_recovery=search_recovery,
                search_form=search_form,
                search_params=search_params,
                fetch_method=fetch_method,
                existing_redirect_info=redirect_info,
            )
    else:
        # If redirected but no search params provided, still detect the form
        # to guide the user on what params are available
        if redirect_info.get("redirected") and search_form.get("detected"):
            logger.info(
                "[URLAnalyzer] Redirected URL with search form detected — "
                "provide search_params to attempt recovery. Fields: %s",
                [f["name"] or f["id"] for f in (search_form.get("search_fields") or []) if isinstance(f, dict)],
            )

    # ── Step 4: Check anti-bot score ─────────────────────────────────
    anti_bot_score = detect_anti_bot(html)

    # ── Step 5: Analyze page structure and value patterns ─────────────
    profile = detect_page_structure(html)
    patterns = detect_value_patterns(html)

    page_analysis = {
        "structure_type": profile.structure_type,
        "structure_confidence": profile.structure_confidence,
        "headers": profile.headers,
    }

    # ── Step 6: Content Quality Gate ─────────────────────────────────
    content_quality = _assess_content_quality(html, profile)

    # ── Step 6b: Empty Response Check ─────────────────────────────────
    # Detect pages that return 200 but have no useful data
    empty_check = (
        detect_empty_response(html)
        if config.detect_empty_responses
        else EmptyResponseCheck(
            is_empty=False, empty_type="", confidence=0.0, message="Empty response detection disabled"
        )
    )

    # ── Step 7: Extract container values and build structured prompt ─
    container_values = _extract_container_text_values(html, profile.container_selector)

    # If we got very few values from the container, fall back to scanning
    # visible page text for individual values
    if len(container_values) < 3:
        soup = BeautifulSoup(html, "html.parser")
        for noise in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]):
            noise.decompose()
        visible_text = soup.get_text(separator=" ", strip=True)
        chunks = []
        for tok in visible_text.split():
            tok = tok.strip()
            if tok and len(tok) > 1 and len(tok) < 80 and tok not in chunks:
                chunks.append(tok)
        container_values = chunks[:40]

    prompt = build_url_analysis_prompt(container_values, page_analysis)

    try:
        result = await llm_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You output valid JSON objects for data schema design. "
                        "No markdown, no commentary. Return ONLY the JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=settings.URL_ANALYZER_TEMPERATURE,
            timeout=settings.LLM_SELECTOR_TIMEOUT,
        )
    except Exception as e:
        logger.exception("[URLAnalyzer] LLM analysis failed for %s: %s", url, e)
        result = None

    # ── Step 8: Build structured response ────────────────────────────
    field_type_map = {
        "string": "string",
        "text": "string",
        "number": "number",
        "float": "float",
        "integer": "integer",
        "int": "integer",
        "boolean": "boolean",
        "bool": "boolean",
        "email": "email",
        "phone": "phone",
        "url": "url",
        "website": "url",
        "date": "date",
        "currency": "currency",
        "price": "currency",
        "rating": "rating",
        "location": "location",
        "address": "location",
        "percentage": "percentage",
        "list": "list_string",
        "code": "code",
        "time": "time",
    }

    suggested_fields = []
    if result and isinstance(result, dict):
        raw_fields = result.get("fields", [])
        if isinstance(raw_fields, dict):
            raw_fields = [
                {"name": k, "example_value": v, "type": "string", "confidence": 0.5}
                for k, v in raw_fields.items()
                if isinstance(v, str)
            ]

        if isinstance(raw_fields, list):
            for f in raw_fields:
                if not isinstance(f, dict):
                    continue
                name = str(f.get("name", "")).strip()
                if not name:
                    continue

                raw_type = str(f.get("type", "string")).lower().strip()
                mapped_type = field_type_map.get(raw_type, "string")

                suggested_fields.append(
                    {
                        "name": name,
                        "type": mapped_type,
                        "selector": "",
                        "example_value": f.get("example_value", ""),
                        "confidence": min(float(f.get("confidence", 0.5)), 1.0),
                        "description": str(f.get("description", "")),
                    }
                )

    # If LLM returned no fields, use pattern analysis as fallback
    if not suggested_fields:
        for hint in _value_patterns_to_field_types(patterns):
            suggested_fields.append(
                {
                    "name": hint["type"],
                    "type": hint["type"],
                    "selector": "",
                    "example_value": hint.get("example", ""),
                    "confidence": hint["confidence"],
                    "description": hint.get("description", ""),
                }
            )

    # Post-processing: rename generic type-name fields to more descriptive
    # names
    suggested_fields = _rename_generic_fields(suggested_fields)

    # Sort by confidence descending
    suggested_fields.sort(key=lambda f: f["confidence"], reverse=True)

    # Use URL-analyzer-specific field limit
    suggested_fields = suggested_fields[: settings.URL_ANALYZER_MAX_FIELDS]

    item_container = profile.container_selector
    estimated_records = 0
    if result and isinstance(result, dict):
        estimated_records = int(result.get("estimated_record_count", 0))

    elapsed = time.time() - start_time

    # Log with redirect / quality / recovery context
    quality_warning = ""
    if redirect_info.get("redirected"):
        quality_warning = f" [REDIRECTED: {
            redirect_info.get(
                'redirect_type', 'unknown')}]"
    if content_quality.get("quality") != "good":
        quality_warning += f" [QUALITY: {
            content_quality.get(
                'quality', 'unknown')}]"
    if search_recovery and search_recovery.get("success"):
        quality_warning += " [RECOVERED via search form]"
    logger.info(
        "[URLAnalyzer] Analyzed %s: %s structure, %d fields suggested, %.1fs%s",
        url if not search_recovery else search_recovery.get("fresh_url", url),
        profile.structure_type,
        len(suggested_fields),
        elapsed,
        quality_warning,
    )

    # Build acquisition lineage from the final state
    from app.acquisition_state import AcquisitionLineage, AcquisitionState

    acquisition_lineage = AcquisitionLineage.from_redirect_info(
        redirect_info=redirect_info,
        original_url=url,
        final_url=final_url,
        fetch_method=fetch_method,
        search_recovery=search_recovery,
        search_form=search_form if search_form else None,
        search_params=search_params,
    )
    # Enrich lineage with session detection results
    acquisition_lineage.session_bound = bool(session_detection.get("is_session_bound", False))
    acquisition_lineage.ephemeral_params = list(session_detection.get("ephemeral_params") or [])

    # Enrich lineage with evidence-based quality signals
    acquisition_lineage.data_evidence_score = (
        round(
            1.0
            if content_quality.get("has_data_containers")
            else 0.0 + (0.5 if not empty_check.is_empty else 0.0) - anti_bot_score * 0.3
        )
        / 1.5
    )
    acquisition_lineage.anti_bot_score = round(anti_bot_score, 3)
    acquisition_lineage.containers_detected = content_quality.get("data_container_count", 0)
    acquisition_lineage.forms_detected = 1 if (search_form or {}).get("detected") else 0
    from app.browser_network_capture import get_browser_state, get_captures

    browser_state_evidence = get_browser_state(url)
    acquisition_lineage.network_payloads_found = len(get_captures(url))
    if not acquisition_lineage.recommended_next_action:
        if empty_check.is_empty and anti_bot_score > 0.5:
            acquisition_lineage.recommended_next_action = "try_browser_mode_or_search_params"
        elif session_detection.get("is_session_bound"):
            acquisition_lineage.recommended_next_action = "provide_search_params"
        elif not content_quality.get("has_data_containers"):
            acquisition_lineage.recommended_next_action = "try_deep_scan_mode"

    # If the page is effectively empty, update the acquisition state
    if empty_check.is_empty and acquisition_lineage.state == AcquisitionState.DIRECT:
        acquisition_lineage.state = AcquisitionState.EMPTY_RESPONSE
        acquisition_lineage.message = empty_check.message

    # Determine the canonical URL: the stable, bookmarkable URL
    # If recovery succeeded, use the recovered URL; otherwise use the
    # session-stripped version of the original URL
    canonical_url = session_detection["canonical_url"]
    if acquisition_lineage.state == AcquisitionState.RECOVERED and acquisition_lineage.recovered_url:
        canonical_url = acquisition_lineage.recovered_url

    # Record acquisition telemetry
    try:
        get_acquisition_telemetry().record(
            url=url,
            state=acquisition_lineage.state,
            original_url=acquisition_lineage.original_url,
            final_url=acquisition_lineage.final_url,
            canonical_url=canonical_url,
            fetch_method=fetch_method,
            session_bound=bool(session_detection.get("is_session_bound", False)),
            ephemeral_params=list(session_detection.get("ephemeral_params") or []),
            recovery_method=acquisition_lineage.recovery_method,
            recovered_url=acquisition_lineage.recovered_url,
            fetch_time_ms=round((time.time() - start_time) * 1000, 1),
        )
    except Exception:
        logger.debug("[URLAnalyzer] Failed to record acquisition telemetry", exc_info=True)

    # ── Escalation Check ─────────────────────────────────────────────
    # If the acquisition failed or was degraded, check whether we should
    # escalate to a more aggressive mode and retry.
    escalated_mode = None
    max_depth = config.max_retries
    if _escalation_depth < max_depth and should_escalate(
        mode_enum, acquisition_lineage.state.value, empty_check.is_empty
    ):
        escalated_mode = escalate_mode(mode_enum)
        if escalated_mode != mode_enum:
            logger.info(
                "[URLAnalyzer] Escalating from %s → %s (depth %d) due to state=%s",
                mode_enum.value,
                escalated_mode.value,
                _escalation_depth + 1,
                acquisition_lineage.state.value,
            )
            return await analyze_url_for_fields(
                url=url,
                search_params=search_params,
                acquisition_mode=escalated_mode.value,
                _escalation_depth=_escalation_depth + 1,
            )

    return {
        "url": url,
        "redirect_info": redirect_info,
        "acquisition_lineage": acquisition_lineage.model_dump(mode="json"),
        "user_message": acquisition_lineage.get_user_message(),
        "session_detection": session_detection,
        "canonical_url": canonical_url,
        "acquisition_mode": acquisition_mode,
        "acquisition_config": {
            "mode": config.mode.value,
            "attempt_recovery": config.attempt_recovery,
            "attempt_search_form": config.attempt_search_form,
            "use_playwright": config.use_playwright,
            "detect_empty_responses": config.detect_empty_responses,
            "detect_session_params": config.detect_session_params,
            "max_retries": config.max_retries,
            "escalated": escalated_mode is not None,
        },
        "content_quality": content_quality,
        "empty_check": {
            "is_empty": empty_check.is_empty,
            "empty_type": empty_check.empty_type,
            "confidence": empty_check.confidence,
            "message": empty_check.message,
            "suggestions": empty_check.suggestions,
        },
        "search_form": search_form if search_form.get("detected") else None,
        "search_recovery": search_recovery,
        "page_structure": profile.structure_type,
        "structure_confidence": profile.structure_confidence,
        "estimated_record_count": estimated_records,
        "item_container": item_container,
        "fetch_method": fetch_method,
        "fetch_time_ms": round((time.time() - start_time) * 1000, 1),
        "anti_bot_score": round(anti_bot_score, 3),
        "browser_state_evidence": browser_state_evidence,
        "suggested_fields": suggested_fields,
    }
