"""Characterization tests for the in-memory store TOCTOU fix (FU-2026-07-06).

The template and notification-channel stores (``_extraction_templates_store``,
``_notification_channels_store``) in ``backend/app/routers/jobs_write.py`` are
mutable module-level dicts mutated from concurrent async requests. The
check-then-act on create / update / delete previously raced:

  * create-template  — two concurrent creates with the same id in the same
    tenant both miss the existence check and the second silently overwrites
    the first (no 409 raised).
  * update-template  — find returns a reference into the shared dict; a
    concurrent update/delete mutates it between the find and the reassign,
    losing a patch or reintroducing a just-deleted record.
  * create-channel   — two concurrent creates both observe the job key
    missing, both assign ``[]``, and the reassignment drops the channel
    the first appended.
  * update/delete-channel — iterate-and-mutate / iterate-and-pop on a list
    that a concurrent op re-indexes mid-iteration (lost patch or 500).

The fix guards every check-then-act / read-modify-write section with the
matching module-level ``threading.Lock``. These tests assert the fix at the
AST level — exactly the pattern used by ``test_async_lock_safety.py`` for
the B1 sync-lock-across-await invariant — because the race is too fast to
reproduce deterministically in a unit test:

  1. Each mutating route holds the matching store lock across BOTH the
     existence/find check AND the write (the whole check-then-act).
  2. No ``await`` appears inside either store-lock block (the lock is a
     sync ``threading.Lock`` held only across pure in-memory mutation, so
     there is no B1-class async-lock hazard).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JOBS_WRITE = ROOT / "backend" / "app" / "routers" / "jobs_write.py"

_TEMPLATE_LOCK = "_extraction_templates_lock"
_CHANNEL_LOCK = "_notification_channels_lock"

# Routes that must do their entire check-then-act under the matching lock.
# Each entry: (function name, lock-name, min number of `with <lock>:` blocks
# expected inside that function body).
_TEMPLATE_ROUTES = [
    ("create_template", _TEMPLATE_LOCK, 1),
    ("update_template", _TEMPLATE_LOCK, 1),
    ("delete_template", _TEMPLATE_LOCK, 1),
]
_CHANNEL_ROUTES = [
    ("create_notification_channel", _CHANNEL_LOCK, 1),
    ("update_notification_channel", _CHANNEL_LOCK, 1),
    ("delete_notification_channel", _CHANNEL_LOCK, 1),
]


def _is_named_lock(expr: ast.expr, lock_name: str) -> bool:
    """True if ``expr`` is a bare ``lock_name`` Name used as a context manager."""
    return isinstance(expr, ast.Name) and expr.id == lock_name


def _lock_block_count(func: ast.AsyncFunctionDef, lock_name: str) -> int:
    return sum(
        1
        for node in ast.walk(func)
        if isinstance(node, ast.With) and any(_is_named_lock(item.context_expr, lock_name) for item in node.items)
    )


def _func(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    pytest.fail(f"Could not find {name}() in jobs_write.py")


@pytest.fixture(scope="module")
def tree() -> ast.Module:
    return ast.parse(JOBS_WRITE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,lock_name,expected", _TEMPLATE_ROUTES)
def test_template_routes_hold_store_lock(tree: ast.Module, name: str, lock_name: str, expected: int) -> None:
    """Each template mutating route must wrap its check-then-act in the
    store lock so concurrent creates/updates/deletes cannot interleave."""
    func = _func(tree, name)
    assert _lock_block_count(func, lock_name) >= expected, (
        f"{name}() must hold {lock_name} across its check-then-act (expected >= {expected} `with` block)"
    )


@pytest.mark.parametrize("name,lock_name,expected", _CHANNEL_ROUTES)
def test_channel_routes_hold_store_lock(tree: ast.Module, name: str, lock_name: str, expected: int) -> None:
    """Each notification-channel mutating route must wrap its list mutation
    in the channel store lock."""
    func = _func(tree, name)
    assert _lock_block_count(func, lock_name) >= expected, (
        f"{name}() must hold {lock_name} across its list mutation (expected >= {expected} `with` block)"
    )


class _LockAwaitVisitor(ast.NodeVisitor):
    """Finds ``with <store_lock>:`` blocks that contain an ``await``.

    The store locks are sync ``threading.Lock``: holding one across an
    ``await`` is the B1-class async-lock hazard (blocks the event loop
    while another coroutine owns the lock waiting for IO, or deadlocks on
    re-entry). The fix holds these locks only across pure in-memory dict /
    list mutation, which has no ``await``.
    """

    def __init__(self, lock_names: set[str]) -> None:
        self.lock_names = lock_names
        self.violations: list[tuple[int, str]] = []

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            ctx = item.context_expr
            if isinstance(ctx, ast.Name) and ctx.id in self.lock_names:
                for child in ast.walk(node):
                    if isinstance(child, ast.Await):
                        enclosing = "<unknown>"
                        for parent in ast.walk(node):
                            if isinstance(parent, ast.AsyncFunctionDef):
                                enclosing = parent.name
                                break
                        self.violations.append((node.lineno, enclosing))
                        break
        self.generic_visit(node)


def test_store_locks_not_held_across_await(tree: ast.Module) -> None:
    """No ``with _extraction_templates_lock:`` / ``with _notification_channels_lock:``
    block may contain an ``await`` — sync locks must never cross an await."""
    visitor = _LockAwaitVisitor({_TEMPLATE_LOCK, _CHANNEL_LOCK})
    visitor.visit(tree)
    assert not visitor.violations, f"Found {len(visitor.violations)} store-lock-across-await violations:\n" + "\n".join(
        f"  line {ln}: {fn}" for ln, fn in visitor.violations
    )


def test_store_locks_exist() -> None:
    """The two module-level store locks must be defined — guards against
    a rename / deletion regressing the fix silently."""
    source = JOBS_WRITE.read_text(encoding="utf-8")
    assert f"{_TEMPLATE_LOCK} = threading.Lock()" in source, f"{_TEMPLATE_LOCK} must be declared as a module-level threading.Lock"
    assert f"{_CHANNEL_LOCK} = threading.Lock()" in source, f"{_CHANNEL_LOCK} must be declared as a module-level threading.Lock"
