"""Tests for the generated route authorization matrix."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import FastAPI

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "route_auth_matrix.py"


def _load_module():
    from app.config import settings

    settings.ENABLE_EXPERIMENTAL_ROUTES = True

    # Pop app modules so they re-import with experimental routes enabled
    modules_to_pop = ["app.main", "app.routers.experimental", "app.experimental_startup"]
    for m in modules_to_pop:
        sys.modules.pop(m, None)

    spec = importlib.util.spec_from_file_location("route_auth_matrix", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row_by_method_path(rows, method: str, path: str):
    for row in rows:
        if row.method == method and row.path == path:
            return row
    msg = f"route not found: {method} {path}"
    raise AssertionError(msg)


def test_route_auth_matrix_classifies_core_route_tiers(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATAFORGE_DOTENV_PATH", "/dev/null")
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "jobs_state.json"))
    monkeypatch.setenv("DATAFORGE_SEMANTIC_STATE_PATH", str(tmp_path / "semantic_state.json"))

    matrix = _load_module().build_matrix()

    assert _row_by_method_path(matrix, "GET", "/api/jobs").access == "authenticated-user"
    assert _row_by_method_path(matrix, "POST", "/api/jobs").access == "authenticated-user"
    # DELETE on /api/jobs/{job_id} is operator-allowed (operators
    # remove job schedules they manage; only true admin deletions like
    # /api/templates stay admin-only).
    assert _row_by_method_path(matrix, "DELETE", "/api/jobs/{job_id}").access == "operator-or-admin"
    assert _row_by_method_path(matrix, "POST", "/api/url/analyze").access == "authenticated-user"
    assert _row_by_method_path(matrix, "GET", "/metrics").access == "metrics-token-if-configured"


def test_route_auth_matrix_flags_system_merge_legacy_admin_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATAFORGE_DOTENV_PATH", "/dev/null")
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "jobs_state.json"))
    monkeypatch.setenv("DATAFORGE_SEMANTIC_STATE_PATH", str(tmp_path / "semantic_state.json"))

    matrix = _load_module().build_matrix()
    row = _row_by_method_path(matrix, "POST", "/api/system/merge/knowledge")

    assert row.access == "admin"
    assert "X-Admin-Key" in row.notes


def test_route_auth_matrix_markdown_contains_all_rows(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATAFORGE_DOTENV_PATH", "/dev/null")
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "jobs_state.json"))
    monkeypatch.setenv("DATAFORGE_SEMANTIC_STATE_PATH", str(tmp_path / "semantic_state.json"))

    module = _load_module()
    markdown = module.render_markdown(module.build_matrix())

    assert "| `GET` | `/api/jobs` | authenticated-user |" in markdown
    assert "| `DELETE` | `/api/jobs/{job_id}` | operator-or-admin |" in markdown


def test_route_auth_matrix_uses_fresh_app_factory(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATAFORGE_DOTENV_PATH", "/dev/null")
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "jobs_state.json"))
    monkeypatch.setenv("DATAFORGE_SEMANTIC_STATE_PATH", str(tmp_path / "semantic_state.json"))

    module = _load_module()

    import app.main as main_mod

    monkeypatch.setattr(main_mod, "app", FastAPI())

    matrix = module.build_matrix()

    assert _row_by_method_path(matrix, "GET", "/api/jobs").access == "authenticated-user"


def test_route_auth_matrix_has_no_unreviewed_user_level_mutations(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATAFORGE_DOTENV_PATH", "/dev/null")
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "jobs_state.json"))
    monkeypatch.setenv("DATAFORGE_SEMANTIC_STATE_PATH", str(tmp_path / "semantic_state.json"))

    matrix = _load_module().build_matrix()

    # Endpoints that are intentionally open or user-level mutation routes.
    # User-level entries are still authenticated and tenant-scoped; this list
    # prevents the matrix from silently gaining a new user mutation.
    REVIEWED_MUTATIONS = {
        ("POST", "/api/system/csp-violations"),  # browser CSP report, no key
        ("POST", "/api/session"),  # self-service auth — any authenticated user can create a session
        ("DELETE", "/api/session"),  # self-service auth — any authenticated user can clear their session
        ("POST", "/api/saas/signup"),  # self-service account creation
        ("POST", "/api/saas/aup/accept"),  # P1-COMPLIANCE-001: AUP acceptance (idempotent, any authenticated user)
        ("DELETE", "/api/user/data"),  # self-service data deletion — any authenticated user can delete their own data
        ("POST", "/api/compliance/gdpr/forget"),  # GDPR right-to-erasure alias — any authenticated user can request erasure
        ("POST", "/api/billing/webhook"),  # billing webhook called by PayPal (no API key)
        ("POST", "/api/billing/dodo/webhook"),  # billing webhook called by Dodo (Standard-Webhooks signature)
        (
            "POST",
            "/api/billing/dodo/checkout",
        ),  # self-service checkout — any authenticated USER creates their own Dodo checkout session
        ("POST", "/api/saas/email-verification/send"),  # any authenticated user can request verification
        ("POST", "/api/saas/email-verification/verify"),  # any authenticated user can verify their email
        ("POST", "/api/saas/invitations/{invitation_id}/respond"),  # any authenticated user can respond to invitations
        ("POST", "/api/saas/password-reset/request"),  # unauthenticated — prevents email enumeration
        ("POST", "/api/saas/password-reset/reset"),  # unauthenticated — uses token, not session
        ("POST", "/api/discover"),  # AUP-gated customer discovery wedge
        ("POST", "/api/schema/suggest"),  # AUP-gated customer schema wedge
        ("POST", "/api/url/analyze"),  # AUP-gated customer page analysis wedge
        ("POST", "/api/jobs"),  # AUP-gated tenant job creation
        ("POST", "/api/scheduled"),  # AUP-gated tenant schedule creation
        ("PUT", "/api/scheduled/{job_id}"),  # tenant-scoped schedule update
        ("DELETE", "/api/scheduled/{job_id}"),  # tenant-scoped schedule deletion
    }

    unsafe = [
        row
        for row in matrix
        if (
            row.path.startswith("/api/")
            and row.method != "GET"
            and row.access == "authenticated-user"
            and (row.method, row.path) not in REVIEWED_MUTATIONS
        )
    ]

    assert unsafe == []
