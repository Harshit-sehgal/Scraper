"""Selector Discovery — Entry point for LLM-guided CSS selector generation.

This module has been refactored into focused sub-modules:
- selector_discovery_analysis: Page analysis and DOM-based selector discovery
- selector_discovery_url: URL analysis, redirect detection, form recovery

All public symbols are re-exported for backward compatibility.

The core orchestrator ``analyze_url_for_fields`` (~500 lines with 8 numbered
steps) has been cleaned up: early-return error paths now share a common
``_build_error_response`` helper, and field processing is extracted into
``_build_llm_fields`` with a module-level ``FIELD_TYPE_MAP`` constant.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.content_quality import (
    _assess_content_quality,
    _extract_container_text_values,
)
from app.empty_response_detector import EmptyResponseCheck, detect_empty_response
from app.html_utils import clean_html_for_selectors
from app.llm_bridge import llm_json, reset_llm_call_count
from app.page_profiler import ValuePatterns, detect_page_structure, detect_value_patterns
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

# ── Satisfy pyflakes ────────────────────────────────────────────────────
# Some imports are referenced at runtime by url_analysis_pipeline._import_sd()
# via importlib.import_module("app.selector_discovery").  These assert expressions
# keep the names in the module namespace and suppress F401 warnings.
#
# ``app.acquisition_telemetry`` symbols are NOT imported at module level
# because the research boundary checker requires kernel files to import
# research modules lazily.  They are imported on demand by the pipeline
# stages that need them.
_PIPELINE_IMPORTS = (
    detect_session_params,
    EmptyResponseCheck,
    detect_empty_response,
    detect_page_structure,
    detect_value_patterns,
    llm_json,
    reset_llm_call_count,
    settings,
)


# ── Lazy re-exports for backward compatibility ────────────────────────────
# ``acquisition_telemetry`` is a research module; kernel files must import it
# lazily (inside function bodies).  PEP 562 module __getattr__ allows us to
# keep the re-exports available for monkeypatch targets and runtime lookups
# (``url_analysis_pipeline._import_sd("get_acquisition_telemetry")``) without
# importing at module load time, which would violate the research boundary.


def __getattr__(name: str):
    if name in {"AcquisitionTelemetryCollector", "get_acquisition_telemetry", "reset_acquisition_telemetry_collector"}:
        import importlib

        telemetry = importlib.import_module("app.acquisition_telemetry")
        return getattr(telemetry, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "_analyze_page_data_type",
    "_assess_content_quality",
    "_build_absolute_url",
    "_build_css_for_element",
    "_classify_value",
    "_compute_ui_noise_score",
    "_detect_redirect",
    "_detect_search_form",
    "_discover_direct_repeating_elements",
    "_discover_selectors_from_dom",
    "_extract_container_text_values",
    "_fallback_parent_child_discovery",
    "_infer_field_name",
    "_infer_field_selectors_from_container",
    "_map_search_params_to_fields",
    "_rename_generic_fields",
    "_try_form_search_recovery",
    "_value_patterns_to_field_types",
    "analyze_url_for_fields",
    "build_redirect_info",
    "build_selector_prompt",
    "build_url_analysis_prompt",
    "clean_html_for_selectors",
    "discover_selectors",
]


logger = logging.getLogger(__name__)


# ── Response-building helpers ─────────────────────────────────────


def _build_error_response(
    url: str,
    redirect_info: dict,
    session_detection: dict,
    final_url: str,
    error_message: str,
    user_message: str,
    acquisition_state: str = "direct",
    acquisition_message: str | None = None,
    empty_type: str = "blank",
    suggestions: list[str] | None = None,
    *,
    acquisition_mode: str = "standard",
) -> dict:
    """Build a consistent error response for early-return paths.

    Shared by the fetch-failure and empty-page early returns to avoid
    duplicating the dict-building logic.
    """
    from app.acquisition_state import AcquisitionLineage, AcquisitionState

    state = (
        AcquisitionState(acquisition_state) if hasattr(AcquisitionState, acquisition_state.upper()) else AcquisitionState.DIRECT
    )

    lineage = AcquisitionLineage(
        original_url=url,
        final_url=final_url,
        state=state,
        message=acquisition_message or error_message,
    )

    return {
        "url": url,
        "redirect_info": redirect_info,
        "acquisition_lineage": lineage.model_dump(mode="json"),
        "user_message": user_message,
        "session_detection": session_detection,
        "canonical_url": session_detection.get("canonical_url", url),
        "content_quality": None,
        "empty_check": {
            "is_empty": True,
            "empty_type": empty_type,
            "confidence": 1.0,
            "message": error_message,
            "suggestions": suggestions or [],
        },
        "search_form": None,
        "search_recovery": None,
        "error": error_message,
        "page_structure": "unknown",
        "structure_confidence": 0.0,
        "estimated_record_count": 0,
        "item_container": None,
        "suggested_fields": [],
        "anti_bot_score": 0.0,
        "acquisition_mode": acquisition_mode,
    }


FIELD_TYPE_MAP: dict[str, str] = {
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


def _build_llm_fields(result: dict | None, patterns: ValuePatterns) -> list[dict]:
    """Build suggested_fields list from LLM result or pattern fallback."""
    suggested_fields: list[dict] = []
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
                mapped_type = FIELD_TYPE_MAP.get(raw_type, "string")

                suggested_fields.append(
                    {
                        "name": name,
                        "type": mapped_type,
                        "selector": "",
                        "example_value": f.get("example_value", ""),
                        "confidence": min(float(f.get("confidence", 0.5)), 1.0),
                        "description": str(f.get("description", "")),
                    },
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
                    "description": hint.get("description", "") if hint.get("description") else "",
                },
            )

    return suggested_fields


async def analyze_url_for_fields(
    url: str,
    search_params: dict[str, str] | None = None,
    acquisition_mode: str = "standard",
    _escalation_depth: int = 0,
) -> dict[str, Any]:
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
    from app.services.url_analysis_pipeline import URLAnalysisPipeline

    pipeline = URLAnalysisPipeline()
    return await pipeline.run(
        url=url,
        search_params=search_params,
        acquisition_mode=acquisition_mode,
        _escalation_depth=_escalation_depth,
    )
