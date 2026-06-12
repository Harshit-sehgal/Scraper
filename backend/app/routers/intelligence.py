"""URL Intelligence Router — endpoint for URL classification and recommendations.

Provides the `/api/intelligence/analyze-url` endpoint which accepts a URL
and returns a structured classification result with risk assessment and
recommended extraction mode.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.url_analyzer import analyze_url as _analyze_url
from app.url_safety import validate_public_http_url

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


# ---------------------------------------------------------------------------
# URL Intelligence endpoints
# ---------------------------------------------------------------------------


@router.get("/analyze-url", status_code=200)
async def analyze_url_endpoint(url: str):
    """Analyze a URL and return its classification, risk, and recommendation.

    This endpoint is pure — no HTTP requests are made to the URL.  It
    inspects the URL string only and returns a structured analysis result.

    **Query parameters:**
        - *url*: The URL to analyze (required, must be `http` or `https`)

    **Returns:**
        A ``UrlAnalysisResult`` JSON object with fields ``url``, ``classification``,
        ``risk``, ``recommended_mode``, ``confidence``, ``reason``,
        ``next_steps``, and ``signals``.
    """
    result = _analyze_url(url)
    if not url or not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid or non-HTTP URL.")
    try:
        validate_public_http_url(url)
    except ValueError as e:
        return result.to_guided_dict(safe_to_fetch=False, safety_error=str(e))
    return result.to_guided_dict(safe_to_fetch=True)
