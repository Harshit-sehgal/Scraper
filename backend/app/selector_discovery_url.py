"""
Selector Discovery URL — re-exports from focused sub-modules for
backward compatibility.

This module has been refactored into:
- url_redirects.py: Redirect detection and acquisition lineage
- content_quality.py: Page content quality assessment
- url_value_classification.py: Value classification and field naming
- search_form_recovery.py: Search form detection and POST recovery
"""

from __future__ import annotations

# ── Content Quality ───────────────────────────────────────────────────
from app.content_quality import (
    _assess_content_quality,
    _extract_container_text_values,
)

# ── Search Form Recovery ──────────────────────────────────────────────
from app.search_form_recovery import (
    _build_absolute_url,
    _detect_search_form,
    _map_search_params_to_fields,
    _try_form_search_recovery,
)

# Re-export all public symbols for backward compatibility
# ── URL Redirects ─────────────────────────────────────────────────────
from app.url_redirects import (
    _detect_redirect,
    build_redirect_info,
)

# ── Value Classification ──────────────────────────────────────────────
from app.url_value_classification import (
    _classify_value,
    _infer_field_name,
    _rename_generic_fields,
    _value_patterns_to_field_types,
    build_url_analysis_prompt,
)

__all__ = [
    "_assess_content_quality",
    "_build_absolute_url",
    "_classify_value",
    "_detect_redirect",
    "_detect_search_form",
    "_extract_container_text_values",
    "_infer_field_name",
    "_map_search_params_to_fields",
    "_rename_generic_fields",
    "_try_form_search_recovery",
    "_value_patterns_to_field_types",
    "build_redirect_info",
    "build_url_analysis_prompt",
]
