"""Regression test for the read-path refactor.

After the storage split, the hot read paths (``GET /api/jobs/{id}``,
``GET /api/jobs``) MUST go through ``repo.get_job`` and
``repo.list_job_summaries`` — never through ``repo.load_jobs()``,
which performs a full ``SELECT *`` and deserializes every row.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROUTER_FILES = [
    Path("backend/app/routers/jobs.py"),
    Path("backend/app/routers/exports.py"),
]


def _load_module(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def _function_calls(node: ast.AST) -> set[str]:
    """Return the set of attribute-method call names reachable in a function."""
    names: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, n: ast.Call) -> None:
            if isinstance(n.func, ast.Attribute):
                names.add(n.func.attr)
            elif isinstance(n.func, ast.Name):
                names.add(n.func.id)
            self.generic_visit(n)

    Visitor().visit(node)
    return names


def _walk_async_functions(tree: ast.Module) -> list[ast.AsyncFunctionDef]:
    out: list[ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            out.append(node)  # noqa: PERF401
    return out


class TestRoutersNoFullLoad:
    def test_jobs_router_has_no_load_jobs_call(self) -> None:
        path = Path("backend/app/routers/jobs.py")
        if not path.exists():
            return  # pragma: no cover
        tree = _load_module(path)
        offenders: list[tuple[str, str]] = []
        for fn in _walk_async_functions(tree):
            calls = _function_calls(fn)
            if "load_jobs" in calls:
                offenders.append((fn.name, "load_jobs"))
        assert not offenders, f"Router hot paths must not call repo.load_jobs() (full table load). Found: {offenders}"

    def test_exports_router_has_no_load_jobs_call(self) -> None:
        path = Path("backend/app/routers/exports.py")
        if not path.exists():
            return  # pragma: no cover
        tree = _load_module(path)
        offenders: list[tuple[str, str]] = []
        for fn in _walk_async_functions(tree):
            calls = _function_calls(fn)
            if "load_jobs" in calls:
                offenders.append((fn.name, "load_jobs"))
        assert not offenders, f"Router hot paths must not call repo.load_jobs() (full table load). Found: {offenders}"


class TestRouterFilesExist:
    def test_both_router_files_present(self) -> None:
        for path in ROUTER_FILES:
            assert path.exists(), f"Missing router file: {path}"
