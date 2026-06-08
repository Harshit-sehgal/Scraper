"""Tests for the generated route authorization matrix."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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
    assert _row_by_method_path(matrix, "POST", "/api/jobs").access == "operator-or-admin"
    assert _row_by_method_path(matrix, "DELETE", "/api/jobs/{job_id}").access == "admin"
    assert _row_by_method_path(matrix, "POST", "/api/url/analyze").access == "operator-or-admin"
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
    assert "| `DELETE` | `/api/jobs/{job_id}` | admin |" in markdown


def test_route_auth_matrix_has_no_user_level_mutations(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATAFORGE_DOTENV_PATH", "/dev/null")
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "jobs_state.json"))
    monkeypatch.setenv("DATAFORGE_SEMANTIC_STATE_PATH", str(tmp_path / "semantic_state.json"))

    matrix = _load_module().build_matrix()

    # Endpoints that are intentionally unauthenticated mutation routes. Each
    # entry is a (method, path) pair that has a documented reason for being
    # open (e.g. browser-generated reports). The reason is enforced by the
    # body-size middleware (5 MB cap) and the global /api/* rate limiter.
    UNAUTHENTICATED_MUTATIONS = {  # noqa: N806
        ("POST", "/api/system/csp-violations"),  # browser CSP report, no key
    }

    unsafe = [
        row
        for row in matrix
        if (
            row.path.startswith("/api/")
            and row.method != "GET"
            and row.access == "authenticated-user"
            and (row.method, row.path) not in UNAUTHENTICATED_MUTATIONS
        )
    ]

    assert unsafe == []
