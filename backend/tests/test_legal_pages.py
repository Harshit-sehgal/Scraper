"""Legal pages (E2.5): ToS / Privacy / AUP served by the app."""

from __future__ import annotations

from typing import Any

import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def legal_client() -> Any:
    app = create_app()
    return TestClient(app)


def _get(client: Any, page: str) -> Any:
    return client.get(f"/legal/{page}")


@pytest.mark.parametrize("page", ["terms", "privacy", "aup"])
def test_legal_pages_are_public_html(legal_client: Any, page: str) -> None:
    resp = _get(legal_client, page)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "<!doctype html>" in resp.text


@pytest.mark.parametrize("page", ["terms", "privacy", "aup"])
def test_legal_pages_render_required_sections(legal_client: Any, page: str) -> None:
    resp = _get(legal_client, page)
    assert resp.status_code == 200
    assert resp.text.count("<h2>") >= 8


def test_terms_covers_core_topics(legal_client: Any) -> None:
    resp = _get(legal_client, "terms")
    text = resp.text.lower()
    for needle in ("acceptable use", "termination", "liability", "privacy"):
        assert needle in text, f"terms page missing {needle!r}"


def test_privacy_covers_core_topics(legal_client: Any) -> None:
    resp = _get(legal_client, "privacy")
    text = resp.text.lower()
    for needle in ("retention", "gdpr", "sharing", "security"):
        assert needle in text, f"privacy page missing {needle!r}"


def test_aup_served_version_matches_enforced_version(legal_client: Any) -> None:
    """The served AUP must render the exact enforced CURRENT_AUP_VERSION."""
    from app.saas import CURRENT_AUP_VERSION

    resp = _get(legal_client, "aup")
    assert resp.status_code == 200
    assert CURRENT_AUP_VERSION in resp.text
    assert "Version " + CURRENT_AUP_VERSION in resp.text


def test_aup_prohibits_bypass_behavior(legal_client: Any) -> None:
    """Product-safety rule 10: the AUP must forbid CAPTCHA/paywall/login bypass."""
    resp = _get(legal_client, "aup")
    text = resp.text.lower()
    for needle in ("captcha", "paywall", "login", "anti-bot"):
        assert needle in text, f"AUP missing prohibition of {needle!r}"


def test_aup_enforced_acceptance_flow_exists() -> None:
    """The accept endpoint used by the product pins the same version."""
    from app.saas import CURRENT_AUP_VERSION
    from app.saas.routes.aup import AupAcceptRequest

    assert AupAcceptRequest.model_fields["aup_version"].default == CURRENT_AUP_VERSION


def test_unknown_legal_page_is_404(legal_client: Any) -> None:
    resp = legal_client.get("/legal/not-a-page")
    assert resp.status_code == 404
