"""Characterization tests for async lock safety (Phase 1, B1 P0).

These tests assert that no ``threading.Lock`` is held across an ``await``
in critical API paths. The B1 P0 bug is in the ``restore_job`` route:

    with manager.lock:
        ...
        await run_in_threadpool(...)   # BUG: sync lock held across await

A simple static analysis of the source file proves the fix: the ``await``
must be outside the ``with manager.lock:`` block. We assert that by
parsing the route function body.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JOBS_WRITE = ROOT / "backend" / "app" / "routers" / "jobs_write.py"


class _LockAwaitVisitor(ast.NodeVisitor):
    """AST visitor that finds ``with manager.lock:`` blocks containing ``await``."""

    def __init__(self) -> None:
        self.violations: list[tuple[int, str]] = []

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            if self._is_manager_lock(item.context_expr):
                for child in ast.walk(node):
                    if isinstance(child, ast.Await):
                        func_name = "<unknown>"
                        for parent in ast.walk(node):
                            if isinstance(parent, ast.AsyncFunctionDef):
                                func_name = parent.name
                                break
                        self.violations.append((node.lineno, func_name))
                        break
        self.generic_visit(node)

    @staticmethod
    def _is_manager_lock(expr: ast.expr) -> bool:
        if isinstance(expr, ast.Attribute):
            return expr.attr == "lock"
        if isinstance(expr, ast.Call):
            return _LockAwaitVisitor._is_manager_lock(expr.func)
        if isinstance(expr, ast.Name):
            return expr.id == "lock"
        return False


def test_no_sync_lock_held_across_await() -> None:
    """Every ``with manager.lock:`` block in jobs_write.py must be free of ``await``.

    The B1 fix moves the ``await`` outside the lock; this test proves no
    similar regression exists anywhere else in the file.
    """
    source = JOBS_WRITE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    visitor = _LockAwaitVisitor()
    visitor.visit(tree)
    assert not visitor.violations, f"Found {len(visitor.violations)} lock-across-await violations:\n" + "\n".join(
        f"  line {lineno}: {func}" for lineno, func in visitor.violations
    )


def test_restore_job_await_outside_lock() -> None:
    """The ``restore_job`` function must have separate lock blocks for the
    pre-await check and the post-await update."""
    source = JOBS_WRITE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "restore_job":
            await_nodes = [n for n in ast.walk(node) if isinstance(n, ast.Await)]
            lock_with_nodes = [
                n
                for n in ast.walk(node)
                if isinstance(n, ast.With) and any(_LockAwaitVisitor._is_manager_lock(item.context_expr) for item in n.items)
            ]
            assert await_nodes, "restore_job has no await"
            assert len(lock_with_nodes) >= 2, "need at least 2 lock blocks"
            first_lock_end = lock_with_nodes[0].end_lineno or lock_with_nodes[0].lineno + 1
            first_await_line = min(n.lineno for n in await_nodes)
            assert first_lock_end < first_await_line, (
                f"first lock block ends at line {first_lock_end}, but await at line {first_await_line} is inside it"
            )
            return
    pytest.fail("Could not find restore_job function")
