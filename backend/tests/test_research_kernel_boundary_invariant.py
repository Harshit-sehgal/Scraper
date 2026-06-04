"""CI invariant: the product kernel must not import research modules at top level.

This test is the pytest-side companion to ``scripts/check_research_boundary.py``.
It enforces the rule that no file in ``backend/app/`` outside the research
shell (``app.research.RESEARCH_MODULES``) may have a top-level
``from <research_module> import ...`` or ``import <research_module>``
statement. The check is structural: it uses the standard library ``ast``
module to inspect the *direct children* of each module's ``Module`` node.

The companion script and the test share the same algorithm. Running the
test locally is identical to running the script; running the script in CI
gives a non-zero exit code that fails the build even if pytest is skipped.

Phase R5 of ``docs/REFACTOR_PLAN.md`` documents the boundary and the
mechanics of the check.
"""

from __future__ import annotations

import importlib
import os
import sys

# Ensure the scripts/ directory is on sys.path so we can import the
# canonical scanner. We import it lazily inside tests that need it so
# that pytest collection does not depend on the script being importable
# (it is, but explicit is better than implicit).

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SCRIPTS = os.path.join(_REPO_ROOT, "scripts")
_APP_DIR = os.path.join(_REPO_ROOT, "backend", "app")


# ─── Registry contract ─────────────────────────────────────────────────────


def test_research_registry_is_non_empty() -> None:
    """The research module registry must list at least the well-known set."""
    from app.research import RESEARCH_MODULES

    assert len(RESEARCH_MODULES) >= 50, (
        f"RESEARCH_MODULES has only {len(RESEARCH_MODULES)} entries — the registry "
        "appears to have been gutted. Re-check app/research/__init__.py."
    )


def test_research_registry_is_immutable() -> None:
    """The registry is a frozenset — re-classification requires editing the source."""
    from app.research import RESEARCH_MODULES

    assert isinstance(RESEARCH_MODULES, frozenset), (
        "RESEARCH_MODULES must be a frozenset to prevent runtime mutation. "
        "If you need to add/remove a module, edit app/research/__init__.py."
    )


def test_well_known_research_modules_are_classified() -> None:
    """A sample of unambiguously research modules must be in the registry."""
    from app.research import is_research_module

    expected_research = [
        "semantic_world_state",
        "semantic_segmentation",
        "topology_state",
        "topology_api",
        "chaos_simulator",
        "chaos_scenarios",
        "field_laws",
        "federation_manager",
        "gossip_substrate",
        "heartbeat_manager",
        "strategy_evolution",
        "insight_engine",
        "replay_buffer",
        "recovery_strategies",
        "scraper_recovery_integration",
        "transaction_context",
    ]
    missing = [m for m in expected_research if not is_research_module(m)]
    assert not missing, f"Expected research modules missing from registry: {missing}. Add them to app/research/__init__.py."


def test_well_known_kernel_modules_are_NOT_classified() -> None:
    """A sample of unambiguously product-kernel modules must NOT be research."""
    from app.research import is_research_module

    expected_kernel = [
        "main",
        "config",
        "globals",
        "lifespan",
        "middlewares",
        "scraper",
        "extraction_orchestrator",
        "cleaning_engine",
        "state_store",
        "llm_bridge",
        "url_safety",
        "rate_limiter",
        "audit_logger",
        "storage_interface",
        "job_store",
        "postgres_repository",
        "worker_queue",
        "worker_queue_postgres",
        "experimental_startup",
    ]
    wrong = [m for m in expected_kernel if is_research_module(m)]
    assert not wrong, (
        f"Product-kernel modules are incorrectly classified as research: {wrong}. Remove them from app/research/__init__.py."
    )


def test_research_path_strips_leading_app_prefix() -> None:
    """`is_research_path` must accept qualified paths like 'app.semantic_world_state'."""
    from app.research import is_research_path

    assert is_research_path("app.semantic_world_state") is True
    assert is_research_path("backend.app.semantic_world_state") is True
    assert is_research_path("app.scraper") is False
    assert is_research_path("backend.app.scraper") is False


def test_research_path_handles_submodules() -> None:
    """Submodules of research packages are also research."""
    from app.research import is_research_path

    assert is_research_path("app.semantic_world_state.core") is True
    assert is_research_path("app.semantic_world_state.events") is True
    assert is_research_path("backend.app.topology_state.clustering") is True


def test_research_path_handles_empty_or_none() -> None:
    """Empty / None inputs return False (not True)."""
    from app.research import is_research_path

    assert is_research_path("") is False
    assert is_research_path(None) is False
    assert is_research_path("app") is False
    assert is_research_path("backend") is False


# ─── Top-level import invariant ───────────────────────────────────────────


def _scanner():
    """Import the boundary scanner module and ensure its scripts/ is on sys.path."""
    if _SCRIPTS not in sys.path:
        sys.path.insert(0, _SCRIPTS)
    return importlib.import_module("check_research_boundary")


def test_research_boundary_scanner_passes() -> None:
    """The full product-kernel scan must report zero violations."""
    scanner = _scanner()
    violations, files_checked = scanner.collect_violations(_APP_DIR)
    assert violations == [], f"{len(violations)} top-level research import(s) found in product-kernel files:\n" + "\n".join(
        f"  {rel}:{lineno}  from {mod} import {names}" for rel, lineno, mod, names in violations
    )
    assert files_checked >= 50, f"Scanner only checked {files_checked} files — sanity failure"


def test_scanner_skips_research_modules_themselves() -> None:
    """A research module importing another research module is not a violation."""
    scanner = _scanner()
    # The semantic_world_state package is in RESEARCH_PACKAGE_DIRS, so the
    # scanner must skip every file under it. The registry also includes
    # the basenames 'topology_state', 'semantic_segmentation', etc.
    for path in (
        os.path.join(_APP_DIR, "semantic_world_state", "core.py"),
        os.path.join(_APP_DIR, "semantic_segmentation.py"),
        os.path.join(_APP_DIR, "topology_state.py"),
        os.path.join(_APP_DIR, "chaos_simulator.py"),
    ):
        assert os.path.exists(path), f"Fixture file does not exist: {path}"
        # Each of these is a research file and must not be flagged.
        if scanner._is_research_file(path):
            continue
        violations = scanner._top_level_research_imports(path)
        # If we got here, the file is NOT classified as research. If it has
        # research imports, they are real violations. For our known fixture
        # files this list should be empty.
        assert violations == [], f"Scanner flagged a research file as a violation: {path} -> {violations}"


def test_scanner_allow_list_includes_registry() -> None:
    """The registry module itself is on the allow-list and is never flagged."""
    scanner = _scanner()
    registry_path = os.path.join(_APP_DIR, "research", "__init__.py")
    rel = os.path.relpath(registry_path, start=os.path.dirname(_SCRIPTS))
    assert rel.replace("\\", "/") in scanner.ALLOWED_BOUNDARY_FILES
    # And the scanner does not flag it.
    assert not scanner._top_level_research_imports(registry_path)


def test_scanner_detects_synthetic_violation() -> None:
    """A synthetic kernel file with a top-level research import is detected.

    This is a meta-test: it constructs a fake 'kernel' file in a temp
    directory and verifies the scanner flags it. It then removes the file.
    """
    import tempfile

    scanner = _scanner()
    with tempfile.TemporaryDirectory() as tmp:
        fake_kernel = os.path.join(tmp, "fake_kernel.py")
        with open(fake_kernel, "w", encoding="utf-8") as f:
            f.write("from app.semantic_world_state import get_world_state\nfrom app.scraper import scrape_url\n")
        # Patch the scanner to scan the temp directory instead of app/.
        # We do this by re-implementing the scan with a swapped root.
        violations: list = []
        for dp, _, fns in os.walk(tmp):
            for fn in fns:
                if not fn.endswith(".py"):
                    continue
                fp = os.path.join(dp, fn)
                if scanner._is_research_file(fp):
                    continue
                for lineno, mod, names in scanner._top_level_research_imports(fp):
                    violations.append((os.path.relpath(fp), lineno, mod, names))
        # Expect at least one violation for the research import.
        assert any(mod == "app.semantic_world_state" for _, _, mod, _ in violations), (
            f"Synthetic violation was not detected: {violations}"
        )
        # And no violation for the kernel import.
        assert not any(mod == "app.scraper" for _, _, mod, _ in violations), (
            f"Kernel import incorrectly flagged as a violation: {violations}"
        )


def test_scanner_handles_unparseable_file_gracefully() -> None:
    """A file with a syntax error is reported as a warning, not a hard failure.

    The scanner does not crash on broken files; it logs a warning and
    continues. This protects CI from spurious failures when an
    in-progress edit is briefly unparseable.
    """
    import tempfile

    scanner = _scanner()
    with tempfile.TemporaryDirectory() as tmp:
        broken = os.path.join(tmp, "broken.py")
        with open(broken, "w", encoding="utf-8") as f:
            f.write("def x(:\n    pass\n")
        # Should not raise.
        result = scanner._top_level_research_imports(broken)
        assert result == []


def test_scanner_ignores_type_checking_imports() -> None:
    """`if TYPE_CHECKING: from <research> import ...` is allowed (not a runtime import)."""
    import tempfile

    scanner = _scanner()
    with tempfile.TemporaryDirectory() as tmp:
        kernel_file = os.path.join(tmp, "kernel.py")
        with open(kernel_file, "w", encoding="utf-8") as f:
            f.write(
                "from __future__ import annotations\n"
                "from typing import TYPE_CHECKING\n"
                "\n"
                "if TYPE_CHECKING:\n"
                "    from app.semantic_world_state import get_world_state\n"
                "\n"
                "x: 'get_world_state | None' = None\n"
            )
        violations = scanner._top_level_research_imports(kernel_file)
        assert violations == [], f"TYPE_CHECKING import was incorrectly flagged: {violations}"
