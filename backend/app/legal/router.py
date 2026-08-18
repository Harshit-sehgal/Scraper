"""Public legal pages served by the app (E2.5).

These routes are intentionally unauthenticated: users must be able to
read the AUP before accepting it. The AUP page renders the exact
version enforced by ``app.utils.aup``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.legal.content import build_page

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("/{page}", response_class=HTMLResponse)
def get_legal_page(page: str) -> HTMLResponse:
    """Serve a legal page (ToS, Privacy Policy, or AUP) as HTML."""
    if page not in ("terms", "privacy", "aup"):
        raise HTTPException(status_code=404, detail="unknown legal page")
    html = build_page(page)
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=3600"})
