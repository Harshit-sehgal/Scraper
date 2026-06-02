"""Tests for the generated route authorization matrix."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "route_auth_matrix.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("route_auth_matrix", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row_by_method_path(rows, method: str, path: str):
    for row in rows:
        if row.method == method and row.path == path:
            return row
    raise AssertionError(f"route not found: {method} {path}")


def test_route_auth_matrix_classifies_core_route_tiers(monkeypatch, tmp_path):
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


def test_route_auth_matrix_flags_system_merge_legacy_admin_key(monkeypatch, tmp_path):
    monkeypatch.setenv("DATAFORGE_DOTENV_PATH", "/dev/null")
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "jobs_state.json"))
    monkeypatch.setenv("DATAFORGE_SEMANTIC_STATE_PATH", str(tmp_path / "semantic_state.json"))

    matrix = _load_module().build_matrix()
    row = _row_by_method_path(matrix, "POST", "/api/system/merge/knowledge")

    assert row.access == "admin"
    assert "X-Admin-Key" in row.notes


def test_route_auth_matrix_markdown_contains_all_rows(monkeypatch, tmp_path):
    monkeypatch.setenv("DATAFORGE_DOTENV_PATH", "/dev/null")
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "jobs_state.json"))
    monkeypatch.setenv("DATAFORGE_SEMANTIC_STATE_PATH", str(tmp_path / "semantic_state.json"))

    module = _load_module()
    markdown = module.render_markdown(module.build_matrix())

    assert "| `GET` | `/api/jobs` | authenticated-user |" in markdown
    assert "| `DELETE` | `/api/jobs/{job_id}` | admin |" in markdown


def test_route_auth_matrix_has_no_user_level_mutations(monkeypatch, tmp_path):
    monkeypatch.setenv("DATAFORGE_DOTENV_PATH", "/dev/null")
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "jobs_state.json"))
    monkeypatch.setenv("DATAFORGE_SEMANTIC_STATE_PATH", str(tmp_path / "semantic_state.json"))

    matrix = _load_module().build_matrix()
    unsafe = [
        row for row in matrix if row.path.startswith("/api/") and row.method not in {"GET"} and row.access == "authenticated-user"
    ]

    assert unsafe == []
