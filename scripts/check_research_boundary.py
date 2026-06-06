"""Research Shell Boundary CI Check.

Fails CI if any product-kernel file imports a research/experimental module
at module-load time. This is the runtime companion to the import-time gate
in ``app/research/__init__.py`` (the registry) and
``app/experimental_startup.py`` (the lazy-load gate).

The check is intentionally simple and uses only the standard library
``ast`` module so it does not depend on the test framework, the application
being importable, or any optional dependencies. It walks every ``.py`` file
under ``backend/app/``, parses it, and inspects the *direct children* of
the Module node (i.e. the top-level statements). A top-level
``from X import Y`` or ``import X`` where ``X`` is in ``RESEARCH_MODULES``
is a violation.

Files in the research shell itself are skipped because research modules
are free to import other research modules.

Imports inside ``if TYPE_CHECKING:`` blocks are excluded automatically
because they are wrapped in an ``ast.If`` node, not a direct child of
``Module.body``.

Exit codes:
    0  All kernel files are free of top-level research imports.
    1  One or more violations were found.
    2  Invocation error (e.g. app root does not exist).
"""

from __future__ import annotations

import ast
import os
import sys
from typing import Iterable

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.research import RESEARCH_MODULES  # noqa: E402

# Files / packages that are part of the kernel boundary but may
# legitimately reference the research registry itself. None of these do
# today, but the allow-list makes the gate's intent explicit and reviewable.
ALLOWED_BOUNDARY_FILES: frozenset[str] = frozenset(
    {
        "backend/app/research/__init__.py",
    },
)

# Research packages whose submodules share a directory and may import each
# other freely even though no individual submodule basename is in the
# registry.
RESEARCH_PACKAGE_DIRS: frozenset[str] = frozenset(
    {
        "backend/app/semantic_world_state",
    },
)


def _is_research_target(name: str) -> bool:
    """True if ``name`` (a module basename or dotted path) targets a research module."""
    if not name:
        return False
    parts = name.split(".")
    while parts and parts[0] in {"backend", "app", "src"}:
        parts.pop(0)
    if not parts:
        return False
    return parts[0] in RESEARCH_MODULES


def _is_research_file(path: str) -> bool:
    """True if the file itself belongs to the research shell.

    A file is "research" if its basename (without ``.py``) is in
    ``RESEARCH_MODULES``, or if it lives inside a registered research
    package directory.

    The ``path`` may be absolute or relative. All package-prefix checks are
    performed against the normalised relative path so that both inputs
    work correctly. The repo root (``_REPO_ROOT``) is used as the
    anchor so the check is cwd-independent.
    """
    rel = os.path.relpath(path, start=_REPO_ROOT).replace("\\", "/")
    for pkg in RESEARCH_PACKAGE_DIRS:
        if rel.startswith(pkg + "/") or rel == pkg:
            return True
    base = os.path.basename(rel)
    if base == "__init__.py":
        base = os.path.basename(os.path.dirname(rel))
    if base.endswith(".py"):
        base = base[:-3]
    return base in RESEARCH_MODULES


def _top_level_research_imports(path: str) -> list[tuple[int, str, list[str]]]:
    """Return list of ``(lineno, module, names)`` for top-level research imports.

    "Top-level" means direct children of the ``Module`` AST node. Imports
    inside ``if TYPE_CHECKING:`` blocks or function bodies are intentionally
    ignored: the former do not run at runtime, the latter are not top-level.
    """
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as exc:
        print(f"WARNING: could not read {path}: {exc}", file=sys.stderr)
        return []
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError as exc:
        print(f"WARNING: syntax error in {path}: {exc}", file=sys.stderr)
        return []

    violations: list[tuple[int, str, list[str]]] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if _is_research_target(mod):
                violations.append((node.lineno, mod, [a.name for a in node.names]))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_research_target(alias.name):
                    violations.append((node.lineno, alias.name, ["*"]))
    return violations


def iter_python_files(root: str) -> Iterable[str]:
    """Yield absolute paths of every ``.py`` file under ``root``."""
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn.endswith(".py"):
                yield os.path.join(dp, fn)


def collect_violations(app_root: str) -> tuple[list[tuple[str, int, str, list[str]]], int]:
    """Scan ``app_root`` and return ``(violations, files_checked)``.

    Each violation is a tuple of ``(relative_path, lineno, module, names)``.
    """
    if not os.path.isdir(app_root):
        raise FileNotFoundError(f"app root not found: {app_root}")

    violations: list[tuple[str, int, str, list[str]]] = []
    files_checked = 0
    for fp in sorted(iter_python_files(app_root)):
        rel = os.path.relpath(fp, start=os.path.dirname(_HERE))
        if rel.replace("\\", "/") in ALLOWED_BOUNDARY_FILES:
            continue
        if _is_research_file(fp):
            continue
        for lineno, mod, names in _top_level_research_imports(fp):
            violations.append((rel, lineno, mod, names))
        files_checked += 1
    return violations, files_checked


def main() -> int:
    app_root = os.path.normpath(os.path.join(_HERE, "..", "backend", "app"))
    if not os.path.isdir(app_root):
        print(f"ERROR: app root not found: {app_root}", file=sys.stderr)
        return 2

    violations, files_checked = collect_violations(app_root)
    if violations:
        print(
            f"VALIDATION FAILED: {len(violations)} top-level research import(s) "
            f"across the product kernel ({files_checked} files scanned):",
        )
        for rel, lineno, mod, names in violations:
            print(f"  [VIOLATION] {rel}:{lineno}  top-level import of research module '{mod}' ({names})")
        print(
            "\nSee docs/REFACTOR_PLAN.md (Phase R5) and app/research/__init__.py "
            "for the boundary definition. Kernel files must load research modules "
            "lazily (inside function bodies) so they remain absent from the import "
            "graph when ENABLE_EXPERIMENTAL_ROUTES is False.",
            file=sys.stderr,
        )
        return 1

    print(
        f"VALIDATION PASSED: {files_checked} product-kernel files are free of top-level research imports.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
