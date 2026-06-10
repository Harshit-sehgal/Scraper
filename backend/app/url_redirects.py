"""URL redirect detection and classification.

Extracted from selector_discovery_url.py for modularity.

Ownership boundary: handles URL-level redirect detection and acquisition
lineage construction. Content analysis lives in content_quality.py.
"""

from __future__ import annotations

from typing import Any

# ─── Imports boundary ──────────────────────────────────────────────────────
#
# `acquisition_state` is a research-shell module (see
# backend/app/research/__init__.py). We import it lazily inside
# `build_redirect_info` so that the product kernel can run with
# ENABLE_EXPERIMENTAL_ROUTES=False without pulling in the research
# shell at startup.

# ─── Redirect Detection ────────────────────────────────────────────────


def _detect_redirect(original_url: str, final_url: str) -> dict[str, Any]:
    """Detect and classify URL redirects by comparing original vs final URL.

    Compares the originally requested URL against the final URL after
    browser navigation to detect redirects and classify them.
    Works with ANY domain — no hardcoded values.

    Classification logic:
    - Same URL (or trailing-slash difference only) → no redirect
    - Different domain / scheme → cross-domain (not flagged as redirect)
    - Final URL is homepage (/) and original had a deep path → homepage redirect
    - Path shortened significantly (deep → shallow) → session / expired token redirect
    - Path changed → generic path_changed redirect

    Args:
        original_url: The URL that was requested
        final_url: The URL after browser navigation (after all redirects)

    Returns:
        dict with:
        - redirected: bool
        - redirect_type: str (none|homepage_redirect|session_expired|path_changed)
        - message: str
        - original_url: str
        - final_url: str

    """
    from urllib.parse import urlparse

    # Normalize trailing slash
    orig_norm = original_url.rstrip("/")
    final_norm = final_url.rstrip("/")

    # Same URL → no redirect
    if orig_norm == final_norm:
        return {
            "redirected": False,
            "redirect_type": "none",
            "message": "No redirect detected — URLs match after normalization",
            "original_url": original_url,
            "final_url": final_url,
        }

    parsed_orig = urlparse(original_url)
    parsed_final = urlparse(final_url)

    # Different domain / scheme — cross-domain navigation, not a site redirect
    if parsed_orig.netloc != parsed_final.netloc:
        return {
            "redirected": False,
            "redirect_type": "none",
            "message": f"Different domain: {parsed_orig.netloc} → {parsed_final.netloc}",
            "original_url": original_url,
            "final_url": final_url,
        }

    orig_path = parsed_orig.path.rstrip("/")
    final_path = parsed_final.path.rstrip("/")

    orig_segments = [s for s in orig_path.split("/") if s]
    final_segments = [s for s in final_path.split("/") if s]

    # Redirect to homepage (final is "/" or empty)
    if not final_path or final_path == "/":
        # Deep path (3+ segments) redirected to homepage → likely expired
        # session / token
        if len(orig_segments) >= 3:
            return {
                "redirected": True,
                "redirect_type": "session_expired",
                "message": (
                    f"URL redirected to homepage — the search session, token, "
                    f"or page identifier has likely expired. Original path had "
                    f"{len(orig_segments)} segments (/{'/'.join(orig_segments)}), "
                    f"final is the root homepage."
                ),
                "original_url": original_url,
                "final_url": final_url,
            }
        return {
            "redirected": True,
            "redirect_type": "homepage_redirect",
            "message": "URL redirected to the site homepage",
            "original_url": original_url,
            "final_url": final_url,
        }

    # Path changed
    if orig_path != final_path:
        # Deep path → shallow path: likely expired session / token
        if len(orig_segments) >= 3 and len(final_segments) <= 2:
            return {
                "redirected": True,
                "redirect_type": "session_expired",
                "message": (
                    f"URL redirected from a deep path (/{'/'.join(orig_segments)}) "
                    f"to a shallower path (/{'/'.join(final_segments)}) — "
                    f"the session, token, or identifier likely expired."
                ),
                "original_url": original_url,
                "final_url": final_url,
            }
        return {
            "redirected": True,
            "redirect_type": "path_changed",
            "message": f"URL path changed: {orig_path} → {final_path}",
            "original_url": original_url,
            "final_url": final_url,
        }

    return {
        "redirected": False,
        "redirect_type": "none",
        "message": "No redirect detected",
        "original_url": original_url,
        "final_url": final_url,
    }


def build_redirect_info(
    original_url: str,
    final_url: str,
    search_recovery: dict | None = None,
    search_form: dict | None = None,
    search_params: dict[str, str] | None = None,
    fetch_method: str = "",
    existing_redirect_info: dict | None = None,
) -> dict[str, Any]:
    """Build redirect_info dict from an AcquisitionLineage.

    Uses the typed AcquisitionLineage model to determine the correct
    acquisition state, then converts back to the legacy dict format
    for backward compatibility with the API response.

    Args:
        original_url: The URL as originally provided
        final_url: The URL after redirects and recovery
        search_recovery: Result from _try_form_search_recovery (if attempted)
        search_form: Result from _detect_search_form (if detected)
        search_params: User-provided search parameters
        fetch_method: How the page was fetched
        existing_redirect_info: Pre-computed redirect_info dict (if available).
            If provided, uses this instead of re-running _detect_redirect.

    Returns:
        dict with redirected, redirect_type, message, original_url, final_url

    """
    redirect_info = existing_redirect_info or _detect_redirect(original_url, final_url)

    # Lazy import: AcquisitionLineage is part of the research shell
    # (see backend/app/research/__init__.py). We import it inside the
    # function so that the product kernel does not pull in the research
    # shell at startup when ENABLE_EXPERIMENTAL_ROUTES=False.
    from app.acquisition_state import AcquisitionLineage

    lineage = AcquisitionLineage.from_redirect_info(
        redirect_info=redirect_info,
        original_url=original_url,
        final_url=final_url,
        fetch_method=fetch_method,
        search_recovery=search_recovery,
        search_form=search_form,
        search_params=search_params,
    )

    return lineage.to_dict()
