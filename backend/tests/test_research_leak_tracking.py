"""
Tests for the research-shell boundary gate.

The full quarantine of research modules from the product-kernel import
graph is the work of Phase R2-R5 (see docs/REFACTOR_PLAN.md). Phase R1
(this slice) establishes the import-time and HTTP-level gates but does
not yet prevent every legacy kernel file from importing research
modules at top level.

This file documents BOTH:
1. What Phase R1 has achieved (the gates work).
2. The known-pending set of research modules that are still pulled in
   by legacy product-kernel files. Tracking these here means a
   regression that introduces a NEW leak is caught by adding a single
   line to LEAKY_MODULES, and any future phase that fixes a leak
   removes the corresponding line.

Test ordering note
------------------
This test file requires a fresh Python import graph to observe the
transitive research imports. When run after other test files that
import app modules, stale sys.modules entries can mask leaks. The
_clean_import_app_main helper pops the full import chain (app.main
→ lifespan → services → job_runner → scraper_recovery_integration →
acquisition_state, etc.) before re-importing. This is intentional:
the test is not testing "does pytest have stale caches?" — it is
testing "does a fresh import of the production app pull in research
modules?".
"""

from __future__ import annotations

import os
import sys

import pytest

# ─── Helper: a clean import of app.main ─────────────────────────────────────

# Modules that form the import chain from app.main to the known
# research leaks. Every module in this list is popped before
# re-importing app.main so the full transitive graph re-runs.
# This is the single source of truth for which modules to evict.
_IMPORT_CHAIN_MODULES: tuple[str, ...] = (
    "app.main",
    "app.lifespan",
    "app.routers.experimental",
    "app.routers.scraper",
    "app.routers.operator",
    "app.experimental_startup",
    "app.url_redirects",
    "app.services",
    "app.services.job_runner",
    "app.scraper_recovery_integration",
    "app.extraction_orchestrator",
    "app.scraper",
    "app.selector_discovery",
    "app.html_utils",
    "app.core_types",
    "app.observability",
    "app.recovery_handlers",
    "app.checkpoint_manager",
    "app.acquisition_state",
    "app.acquisition_telemetry",
    "app.intent_parser",
    "app.semantic_mapper",
    "app.semantic_persistence",
    "app.semantic_pipeline",
    "app.semantic_world_state",
    "app.strategy_evolution",
    "app.degradation_predictor",
    "app.domain_health_alerts",
    "app.trend_analyzer",
    "app.visualization",
    "app.motif_feedback",
    "app.domain_evolution_model",
    "app.insight_engine",
)


def _clean_import_app_main():
    """Force a fresh import of app.main with the experimental gate off.

    This is tricky because pytest, conftest.py, and earlier test files
    may have already imported app.main with ENABLE_EXPERIMENTAL_ROUTES
    set to "true" by conftest. We need to:
      1. Set the env var to "false" before the import.
      2. Patch the already-constructed settings singleton so the gate
         sees "false" even if it was constructed earlier with "true".
      3. Drop every module in the import chain so the full transitive
         graph re-runs from scratch.
      4. Re-import app.main so its top-level code re-runs.
    """
    os.environ["DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES"] = "false"
    # Patch the settings singleton. pydantic-settings reads env at
    # construction time, so the singleton may already be cached with
    # the conftest value ("true"). We mutate the attribute directly.
    try:
        from app.config import settings

        settings.ENABLE_EXPERIMENTAL_ROUTES = False
    except Exception:
        # If app.config can't be imported yet, the re-import below will
        # construct it from the env var we just set.
        pass
    # Evict every module in the import chain. This is the key to making
    # the test order-independent: we don't just pop app.main, we pop
    # every intermediate module between app.main and the research leaks.
    for name in _IMPORT_CHAIN_MODULES:
        sys.modules.pop(name, None)
    import app.main  # noqa: F401


# ─── Phase R1 achievement tests ─────────────────────────────────────────────


def test_app_main_does_not_load_experimental_router_when_gate_off():
    """When ENABLE_EXPERIMENTAL_ROUTES is False, the experimental router
    module must not be in sys.modules after a clean import of app.main.

    This is the contract that the configure_routes() refactor in
    commit 455441b established.
    """
    _clean_import_app_main()
    assert "app.routers.experimental" not in sys.modules, (
        "app.main eagerly imported app.routers.experimental even though "
        "ENABLE_EXPERIMENTAL_ROUTES=False. The configure_routes() gate "
        "is broken."
    )


# ─── Known-pending leaks (Phase R2-R5 work) ────────────────────────────────
#
# Each entry is a research module that is currently loaded at startup
# via a top-level import in some product-kernel file. As Phases R2-R5
# fix each leak, remove the corresponding entry. A new leak (a new
# research module that the kernel pulls in at startup) should be
# detected by adding a new entry here.
#
# We assert these are PRESENT in sys.modules after a clean app.main
# import. The test fails if the module is NOT loaded, which would
# mean someone fixed the leak and forgot to update this file.

LEAKY_MODULES: tuple[str, ...] = (
    # Imported by backend/app/extraction_orchestrator.py at module level
    # for type hints and topology lookups. Phase R2 will move these
    # behind lazy/gated imports.
    "app.semantic_world_state",
    "app.intent_parser",
    "app.acquisition_state",
    # Imported by backend/app/scraper_recovery_integration.py and
    # indirectly by several other kernel files. Phase R3 will move
    # these behind lazy/gated imports.
    "app.strategy_evolution",
)


@pytest.mark.parametrize("leaky_module", LEAKY_MODULES)
def test_known_pending_research_leak_is_still_present(leaky_module):
    """Document that this research module is still pulled in at startup.

    This test passes as long as the leak still exists. When a future
    phase fixes the leak, this test will start failing and the fix
    should:
      1. Update LEAKY_MODULES to remove the entry.
      2. Add a positive assertion that the module is NOT loaded.
    """
    _clean_import_app_main()
    assert leaky_module in sys.modules, (
        f"{leaky_module} is no longer loaded at startup. The leak has "
        f"been fixed. Update LEAKY_MODULES to remove this entry and add "
        f"a positive assertion test that the module stays absent."
    )
